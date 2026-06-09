"""R3 — absturzsichere Helfer (fail-closed, keine unbehandelten Ausnahmen im Spiegel-Pfad)."""
from __future__ import annotations

import html
import logging
from typing import Any, Optional

_LOG = logging.getLogger(__name__)

_MIN_WAIT_SEC = 5.0
_MAX_WAIT_SEC = 120.0


def clamp_wait_sec(value: Any, *, default: float = 60.0) -> float:
    try:
        sec = float(value)
    except (TypeError, ValueError):
        sec = float(default)
    return max(_MIN_WAIT_SEC, min(_MAX_WAIT_SEC, sec))


def safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        v = float(value)
        if v != v:  # NaN
            return default
        return v
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def empty_mirror_state(*, detail_de: str = "") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mirror_de": "Spiegel der technischen Exekutive — nur Anzeige",
        "updated_at_utc": None,
        "package_ready": False,
        "headline_de": "Anzeige vorübergehend nicht verfügbar",
        "notional_eur": 0.0,
        "buy_count": 0,
        "model_output": {
            "title_de": "R3",
            "source_de": "evidence/pilot_investment_plan_latest.json",
            "investable_eur": 0.0,
            "allocations": [],
        },
        "t212_connected": False,
        "t212_detail_de": "",
        "quote_count": 0,
        "us_session_open": False,
        "prep_rows": [],
        "last_batch": None,
        "orders_ref": "evidence/r3_stock_orders_latest.json",
        "execution_package": {
            "active": False,
            "source_de": "evidence/r3_stock_orders_latest.json",
            "notional_eur": 0.0,
            "buy_count": 0,
            "lines": [],
        },
        "submission_mode": {"live_submit": False, "mode_de": "Dry-Run", "reasons_de": []},
        "pipeline_layers": [],
        "system_metrics": [],
        "broker_summary": {},
        "snapshot_health": {},
        "cost_risk": {},
        "trading_cycle": {},
        "closed_loop": {},
        "kreis_score": {},
        "local_runtime": {"hub_url": "http://127.0.0.1:17890", "local_only": True},
        "trading_functions": {"functions": []},
        "error_de": str(detail_de or "")[:200],
    }


def render_mirror_fallback_page(
    detail: str = "",
    *,
    port: int = 17890,
) -> bytes:
    """Minimale HTML-Seite wenn Render/State fehlschlägt — Hub bleibt erreichbar."""
    msg = html.escape(str(detail or "Interner Fehler — bitte r3 neu starten.")[:300])
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<link rel="icon" type="image/svg+xml" href="/assets/r3-icon.svg"/>
<meta name="theme-color" content="#e95420"/>
<title>R3</title>
<style>
  body{{margin:0;padding:40px 24px;background:#f5f5f7;color:#1d1d1f;
    font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif}}
  h1{{font-size:22px;color:#ff3b30;margin:0 0 12px}}
  p{{font-size:15px;color:#86868b;line-height:1.5}}
  code{{background:#e8e8ed;padding:2px 6px;border-radius:6px}}
</style></head><body>
<h1>R3</h1>
<p>{msg}</p>
<script>window.R3_HUB_PORT = {int(port)};</script>
</body></html>""".encode(
        "utf-8"
    )
