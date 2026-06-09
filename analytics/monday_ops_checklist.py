"""Monday (and pre-US) ops checklist — visible in dashboard activity log."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from analytics.linux_operator_scope import log_operator_action


def checklist_items_de(root: Path) -> List[str]:
    items = [
        "1. Dashboard «Aktualisieren» — Live-Kurse prüfen (Ziel 14/14)",
        "2. warnings grün prüfen: python3 tools/ai_kernel.py warnings",
        "3. ② Rebalance — Order-Welle nur mit GUI bestätigen (kein Autotrading)",
        "4. Nach Orders: learn läuft 22:20 automatisch (oder jetzt: ai_kernel learn)",
        "5. Ziel Sport Plus: ≥3 reife Live-Fills für Slippage-Kalibrierung",
    ]
    try:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        h1 = h1_backtest_status(root)
        st = str(h1.get("status") or "—")
        if not is_h1_backtest_sealed(root):
            items.append(f"6. H1-Backtest: {st} — ai_kernel h1-status")
    except Exception:
        pass
    return items


def write_monday_checklist_to_activity_log(root: Path, *, source: str = "AUTO") -> Dict[str, Any]:
    root = Path(root)
    items = checklist_items_de(root)
    body = "Montag-Checkliste · " + " | ".join(items)
    try:
        from ui.live_trading_dashboard.activity_log import log_dashboard_activity

        entry = log_dashboard_activity(
            root,
            category="Active Alpha",
            action="Montag-Vorbereitung",
            result=body[:240],
            status="INFO",
            source=source,
            details={"checklist_de": items, "user_action_required": True},
            user_action_required=True,
        )
        log_operator_action(root, level="A", action="monday_checklist", result="geschrieben")
        return {"ok": True, "items": items, "entry_id": entry.get("id")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "items": items}


def is_trading_prep_day() -> bool:
    """Mon–Fri — US session prep relevant."""
    return datetime.now().weekday() < 5
