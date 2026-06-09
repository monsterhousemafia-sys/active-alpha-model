"""P8 acceptance audit smoke tests."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from aa_acceptance_audit import (
    check_status_consistency,
    create_audit_backup,
    load_promotion_config,
    promotion_modes_from_config,
    verify_phase_evidence,
    write_secure_promotion_config,
)
from aa_auto_promotion import attempt_auto_promotion, evaluate_auto_promotion_gates, load_promotion_gate_config
from aa_dashboard_result import load_result_context
from aa_model_status import build_model_status, format_model_status_block


def test_p8_phase_evidence_present():
    root = Path(__file__).resolve().parents[1]
    out = root / "model_output_sp500_pit_t212"
    if not out.is_dir():
        return
    results = verify_phase_evidence(root, out)
    for phase_id, status in results.items():
        assert status == "PASS", f"{phase_id} missing evidence"


def test_p8_default_no_auto_promotion(tmp_path: Path):
    root = tmp_path
    cfg = {
        "schema_version": 1,
        "auto_research_enabled": False,
        "auto_promote_paper_enabled": False,
        "auto_promote_signal_enabled": False,
        "auto_execute_real_money_enabled": False,
    }
    (root / "promotion_gate_config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    out = root / "model_output"
    out.mkdir()
    (out / "background_research_status.json").write_text('{"entries":[]}', encoding="utf-8")
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["promotion_allowed"] is False
    result = attempt_auto_promotion(root, out, mode="paper")
    assert result["status"] == "BLOCKED"


def test_p8_real_money_cannot_be_enabled(tmp_path: Path):
    root = tmp_path
    (root / "promotion_gate_config.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "auto_execute_real_money_enabled": True}),
        encoding="utf-8",
    )
    cfg = load_promotion_gate_config(root)
    assert cfg.get("auto_execute_real_money_enabled") is False


def test_p8_audit_backup_non_destructive(tmp_path: Path):
    root = tmp_path
    (root / "promotion_gate_config.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    (root / "control").mkdir(parents=True)
    (root / "control" / "pipeline_pending.json").write_text("{}", encoding="utf-8")
    dest = create_audit_backup(root)
    assert dest.is_dir()
    assert (dest / "promotion_gate_config.yaml").is_file()


def test_p8_exe_status_loader_smoke():
    root = Path(__file__).resolve().parents[1]
    out = root / "model_output_sp500_pit_t212"
    if not out.is_dir():
        return
    ctx = load_result_context(out, metrics={"cagr": 0.1})
    status = ctx.get("model_status") or {}
    text = str(ctx.get("model_status_text") or "")
    assert status.get("auto_execute_real_money_status") == "DISABLED"
    assert "AI-Entwicklung" in text
    assert "Modellstatus" in text


def test_p8_secure_commissioning_config(tmp_path: Path):
    root = tmp_path
    (root / "promotion_gate_config.yaml").write_text(
        yaml.safe_dump({"schema_version": 1, "auto_research_enabled": True, "auto_promote_paper_enabled": True}),
        encoding="utf-8",
    )
    write_secure_promotion_config(root, auto_research=True)
    modes = promotion_modes_from_config(load_promotion_config(root))
    assert modes["AUTO_RESEARCH"] == "ENABLED"
    assert modes["AUTO_PROMOTE_PAPER"] == "DISABLED"
    assert modes["AUTO_EXECUTE_REAL_MONEY"] == "DISABLED"
