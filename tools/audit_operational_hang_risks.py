#!/usr/bin/env python3
"""Scan operational hang risks — writes evidence/operational_hang_audit_latest.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    root = ROOT
    findings: list[dict] = []

    hooks = root / ".cursor" / "hooks.json"
    if hooks.is_file():
        doc = json.loads(hooks.read_text(encoding="utf-8"))
        if not doc.get("hooks"):
            findings.append(
                {
                    "severity": "INFO",
                    "area": "cursor_hooks",
                    "issue": "hooks.json leer — Selbstverbesserung nur via tools/run_pipeline_autopilot.py",
                    "mitigation": "Autopilot-Loop mit --loop ausführen oder Phase manuell claimen",
                }
            )

    pending = root / "control" / "pipeline_pending.json"
    if pending.is_file():
        p = json.loads(pending.read_text(encoding="utf-8"))
        if p.get("has_work") and int(p.get("attempt_count") or 0) == 0:
            findings.append(
                {
                    "severity": "WARN",
                    "area": "pipeline_pending",
                    "issue": f"Pending Phase {p.get('pending_phase')} ohne Claim",
                    "mitigation": "run_pipeline_autopilot --once oder Phase ausführen; stale >168h auto-release",
                }
            )

    from aa_refresh_guard import quote_refresh_in_progress

    findings.append(
        {
            "severity": "OK",
            "area": "quote_refresh",
            "issue": "single-flight lock aktiv",
            "in_progress": quote_refresh_in_progress(),
        }
    )

    out = root / "evidence" / "operational_hang_audit_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"findings": findings}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(findings, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
