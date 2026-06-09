#!/usr/bin/env python3
"""Generate portfolio comparison evidence (R1 weekly report hook)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.human_vs_base_comparison import (
    compare_human_vs_base,
    export_comparison_pdf,
    render_comparison_dashboard_png,
    write_comparison_evidence,
)
from integrations.trading212.t212_readonly_trade_history_sync import sync_live_readonly_trade_history
from integrations.trading212.t212_readonly_connection_service import connection_status_summary


def main() -> int:
    broker = connection_status_summary(ROOT, force_sync=True)
    broker_dict = broker.to_dict() if hasattr(broker, "to_dict") else {}
    broker_dict["credentials_configured"] = bool(broker_dict.get("credentials_configured"))
    sync_live_readonly_trade_history(ROOT)
    report = compare_human_vs_base(ROOT, broker_dict)
    path = write_comparison_evidence(ROOT, report)
    render_comparison_dashboard_png(report, ROOT / "evidence/portfolio_comparison_dashboard.png")
    export_comparison_pdf(report, ROOT / "evidence/portfolio_comparison_report.pdf")
    weekly = ROOT / "evidence/revenue_expansion_metrics_weekly.json"
    doc = {"portfolio_comparison_report": str(path), "status": report.get("status")}
    if weekly.is_file():
        try:
            existing = json.loads(weekly.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        existing.update(doc)
        weekly.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    else:
        weekly.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report.get("status") == "OK", "path": str(path)}, indent=2))
    return 0 if report.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
