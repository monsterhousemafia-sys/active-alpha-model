#!/usr/bin/env python3
"""Verify UI/plan cash matches Trading 212 availableToTrade (not totalValue)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SYNC_PATH = ROOT / "live_pilot/manual_execution/readonly_real_account_state/latest_sync.json"


def main() -> int:
    from integrations.trading212.t212_cash_parser import parse_cash_breakdown, verify_cash_eur_matches_summary

    if not SYNC_PATH.is_file():
        print(json.dumps({"ok": False, "error": "NO_LATEST_SYNC"}, indent=2))
        return 1

    doc = json.loads(SYNC_PATH.read_text(encoding="utf-8"))
    summary = doc.get("summary") or {}
    breakdown = parse_cash_breakdown(account_summary=summary)
    alignment = verify_cash_eur_matches_summary(doc.get("cash_eur"), summary)
    report = {
        "ok": alignment.get("ok") and breakdown.planning_cash_eur is not None,
        "stored_cash_eur": doc.get("cash_eur"),
        "cash_breakdown": breakdown.to_dict(),
        "alignment": alignment,
        "planning_uses_total_value": False,
        "note_de": (
            "Strategie und Orders nutzen nur availableToTrade. "
            "reservedForOrders und inPies werden nicht eingeplant."
        ),
    }
    out = ROOT / "evidence" / "t212_cash_alignment_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
