"""Tests for aa_vision_review_gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from aa_vision_phase_catalog import ensure_phase_catalog
from aa_vision_review_gate import (
    check_phase_authorization,
    is_template_path,
    verify_champion_evidence,
    verify_safety_status_artifacts,
    verify_sidecar_hash,
)


def _safe_root(tmp_path: Path) -> Path:
    (tmp_path / ".cursor").mkdir(parents=True)
    (tmp_path / ".cursor" / "hooks.json").write_text('{"version":1,"hooks":{}}', encoding="utf-8")
    cfg = {
        "auto_research_enabled": False,
        "auto_promote_paper_enabled": False,
        "auto_promote_signal_enabled": False,
        "auto_execute_real_money_enabled": False,
    }
    (tmp_path / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    (tmp_path / "control").mkdir()
    (tmp_path / "control" / "auto_promotion_status.json").write_text(
        json.dumps(
            {
                "champion_variant_id": "R3_w075_q065_noexit",
                "promotion_allowed": False,
                "auto_execute_real_money_enabled": False,
                "automation_modes": {
                    "AUTO_RESEARCH": "DISABLED",
                    "AUTO_PROMOTE_PAPER": "DISABLED",
                    "AUTO_PROMOTE_SIGNAL": "DISABLED",
                    "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
                },
                "gate_evaluation": {"promotion_allowed": False, "gates": {}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control" / "promotion_status.json").write_text(
        json.dumps({"all_gates_pass": False, "auto_execute_real_money": False}),
        encoding="utf-8",
    )
    (tmp_path / "control" / "last_known_good_state.json").write_text(
        json.dumps({"validated_variant_id": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    ensure_phase_catalog(tmp_path)
    return tmp_path


def test_missing_champion_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "last_known_good_state.json").write_text("{}", encoding="utf-8")
    result = verify_champion_evidence(root)
    assert result["ok"] is False
    assert result["error"] == "champion_evidence_missing"


def test_champion_conflict_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "last_known_good_state.json").write_text(
        json.dumps({"validated_variant_id": "OTHER"}), encoding="utf-8"
    )
    result = verify_champion_evidence(root)
    assert result["ok"] is False
    assert result["error"] == "champion_evidence_conflict"


def test_promotion_allowed_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "auto_promotion_status.json").write_text(
        json.dumps({"promotion_allowed": True, "champion_variant_id": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    result = verify_safety_status_artifacts(root)
    assert result["ok"] is False


def test_real_money_flag_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "auto_promotion_status.json").write_text(
        json.dumps({"auto_execute_real_money_enabled": True}), encoding="utf-8"
    )
    result = verify_safety_status_artifacts(root)
    assert result["ok"] is False


def test_approval_alone_does_not_authorize(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "EXTERNAL_REVIEW_APPROVAL_V1.md").write_text(
        "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION\n", encoding="utf-8"
    )
    result = check_phase_authorization(
        root, phase_id="V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION"
    )
    assert result["authorized"] is False


def test_template_never_authorizes(tmp_path: Path):
    assert is_template_path(Path("TEMPLATE_EXTERNAL_REVIEW_APPROVAL_V2.md"))


def test_missing_auto_promotion_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "auto_promotion_status.json").unlink()
    result = verify_safety_status_artifacts(root)
    assert "auto_promotion_status_missing_or_invalid" in result["errors"]


def test_unparseable_auto_promotion_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "auto_promotion_status.json").write_text("not-json", encoding="utf-8")
    result = verify_safety_status_artifacts(root)
    assert "auto_promotion_status_missing_or_invalid" in result["errors"]


def test_missing_required_field_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "auto_promotion_status.json").write_text("{}", encoding="utf-8")
    result = verify_safety_status_artifacts(root)
    assert "auto_promotion_required_field_missing" in result["errors"]


def test_missing_promotion_status_blocks(tmp_path: Path):
    root = _safe_root(tmp_path)
    (root / "control" / "promotion_status.json").unlink()
    result = verify_safety_status_artifacts(root)
    assert "promotion_status_missing_or_invalid" in result["errors"]


def test_sidecar_hash_verification(tmp_path: Path):
    root = _safe_root(tmp_path)
    data = b"test-zip-content"
    zip_path = root / "review.zip"
    zip_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    sidecar = root / "review.zip.sha256"
    sidecar.write_text(f"{digest}  review.zip\n", encoding="utf-8")
    ok, val = verify_sidecar_hash(zip_path, sidecar)
    assert ok
    assert val == digest
