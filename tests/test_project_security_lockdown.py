from __future__ import annotations

import json
from pathlib import Path

import yaml

from tools.project_security_lockdown import run_security_lockdown


def test_security_lockdown_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / ".cursor").mkdir(parents=True)
    (tmp_path / ".cursor/hooks.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "promotion_gate_config.yaml").write_text(
        yaml.dump(
            {
                "promotion_mode": "MANUAL",
                "auto_research_enabled": False,
                "auto_promote_paper_enabled": False,
                "auto_promote_signal_enabled": False,
                "auto_execute_real_money_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/operational_safety_flags.json").write_text(
        json.dumps(
            {
                "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
                "AUTO_PROMOTE_PAPER": "DISABLED",
                "AUTO_PROMOTE_SIGNAL": "DISABLED",
                "AUTO_RESEARCH": "DISABLED",
                "REAL_MONEY_AUTHORIZED": False,
                "CHAMPION_CHANGED": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_live_quote_access_policy.json").write_text(
        json.dumps({"schema_version": 1, "status": "AUTHORITATIVE", "allowed_owners": ["king_ops"]}),
        encoding="utf-8",
    )
    doc = run_security_lockdown(tmp_path, apply_chmod=False)
    assert doc.get("status") == "LOCKED"
