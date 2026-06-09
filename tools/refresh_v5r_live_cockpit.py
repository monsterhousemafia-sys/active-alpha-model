#!/usr/bin/env python3
"""Refresh V5R live review snapshot via full operational refinement chain."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from aa_config_env import load_aa_env
    from aa_operational_refinement import load_refinement_config, run_operational_refinement

    env = load_aa_env(ROOT)
    cfg = load_refinement_config(ROOT)
    cfg["refresh_cockpit_snapshot"] = True
    cfg["refresh_signal"] = True

    report = run_operational_refinement(ROOT, env, cfg=cfg, log_print=False)

    from aa_decision_cockpit_readonly_snapshot import SNAPSHOT_REL

    path = ROOT / SNAPSHOT_REL
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "snapshot missing"}, indent=2))
        return 1

    snap = json.loads(path.read_text(encoding="utf-8"))
    cockpit = snap.get("cockpit_data") or {}
    overview = cockpit.get("executive_overview") or {}
    summary = {
        "snapshot_path": str(path),
        "active_champion": overview.get("active_champion"),
        "candidate": overview.get("candidate"),
        "evidence_stage": overview.get("evidence_stage"),
        "blockers": len(snap.get("blockers") or []),
        "generated_at_utc": snap.get("generated_at_utc"),
        "r3_regime_match": report.r3_regime_match,
        "refinement_ok": report.ok,
    }
    print(json.dumps(summary, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
