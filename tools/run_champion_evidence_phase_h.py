#!/usr/bin/env python3
"""Phase H — Cockpit operator transparency panels (H1–H4)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_champion_cockpit_phase_h import build_operator_transparency_de
from aa_decision_cockpit_gui import build_cockpit_tab_labels
from aa_decision_cockpit_viewmodel import load_decision_cockpit
from aa_safe_io import atomic_write_json, atomic_write_text


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_phase_h(root: Path) -> dict:
    root = Path(root)
    panels = build_operator_transparency_de(root)
    cockpit = load_decision_cockpit(root)
    tabs = build_cockpit_tab_labels(cockpit)

    conflicts: list[str] = []
    if panels["h1_model_comparison"].get("status") != "OK":
        conflicts.append("H1_canonical_comparison_missing")
    if panels["h2_champion_status"].get("status") == "PARTIAL":
        conflicts.append("H2_charter_missing")
    if panels["h4_pointer_drift"].get("drift_detected"):
        conflicts.append("H4_pointer_drift_FAILSAFE")

    summary = {
        "schema_version": 1,
        "phase": "H",
        "generated_at_utc": _utc_now(),
        "status": "COMPLETE_WITH_FAILSAFE" if panels["h4_pointer_drift"].get("drift_detected") else (
            "COMPLETE" if not conflicts else "PARTIAL"
        ),
        "panels": panels,
        "cockpit_tabs": list(tabs.keys()),
        "conflicts": conflicts,
        "pointer_drift_active": panels.get("pointer_drift_active"),
    }
    atomic_write_json(root / "evidence" / "phase_h_operator_transparency_summary.json", summary)

    md_lines = [
        "# Phase H — Operator Transparency",
        "",
        f"Generated: {summary['generated_at_utc']}",
        f"Status: {summary['status']}",
        "",
    ]
    for key, title in (
        ("h1_model_comparison", "H1 Modell-Vergleich"),
        ("h2_champion_status", "H2 Champion-Status"),
        ("h3_rebalance_precheck", "H3 Rebalance-Vorcheck"),
        ("h4_pointer_drift", "H4 Pointer-Drift"),
    ):
        block = panels.get(key) or {}
        md_lines.append(f"## {title} ({block.get('status', '—')})")
        md_lines.append("")
        md_lines.extend(block.get("lines_de") or [])
        md_lines.append("")
    atomic_write_text(root / "docs" / "PHASE_H_OPERATOR_TRANSPARENCY_REPORT.md", "\n".join(md_lines) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase H cockpit transparency")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    summary = run_phase_h(Path(args.root))
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    drift = summary.get("pointer_drift_active")
    print(f"\nPhase H — {summary['status']}" + (" (POINTER DRIFT FAILSAFE)" if drift else ""))
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
