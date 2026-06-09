"""R3 operative Unabhängigkeit von Cursor."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_operational_independence import (
    apply_r3_operational_detach,
    load_operational_policy,
    scan_r3_operational_independence,
)


def test_operational_policy_authoritative() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_operational_policy(root)
    assert policy.get("cursor_runtime_required") is False
    assert policy.get("status") == "AUTHORITATIVE"


def test_scan_returns_gates(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".cursor").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".cursor/hooks.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/alpha_model_agent_home.json").write_text(
        json.dumps({"cursor_retired": True}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_operational_independence.json").write_text(
        (Path(__file__).resolve().parents[1] / "control/r3_operational_independence.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    doc = scan_r3_operational_independence(tmp_path)
    assert doc.get("gates_total", 0) >= 8
    assert "gates" in doc
    assert doc.get("cursor_runtime_required") is False


def test_apply_detach_scan_only_writes_evidence(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".cursor").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".cursor/hooks.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/alpha_model_agent_home.json").write_text(
        json.dumps({"cursor_retired": True}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_operational_independence.json").write_text(
        (Path(__file__).resolve().parents[1] / "control/r3_operational_independence.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    doc = apply_r3_operational_detach(tmp_path, repair=False, seal_bridge=False, persist=True)
    assert (tmp_path / "evidence/r3_operational_independence_latest.json").is_file()
    assert doc.get("repair_applied") is False
