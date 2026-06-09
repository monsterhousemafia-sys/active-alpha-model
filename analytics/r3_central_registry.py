"""R3 Zentrale — alles fließt zusammen (Hub, Apps, Status, KI, H1)."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_central_source_policy.json")
_EVIDENCE_REL = Path("evidence/r3_central_latest.json")
_MANDATE_REL = Path("evidence/king_32b_r3_central_mandate.txt")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_central_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _feed_trading_platform(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_trading_platform import build_r3_trading_platform_status

        doc = build_r3_trading_platform_status(root, persist=False)
        result = doc.get("trading_result") or {}
        return {
            "id": "trading_platform",
            "label_de": "Handelsplattform",
            "signal_date": result.get("signal_date"),
            "positions": result.get("positions"),
            "headline_de": doc.get("message_de"),
            "ok": bool(result.get("ok")),
        }
    except Exception as exc:
        return {
            "id": "trading_platform",
            "label_de": "Handelsplattform",
            "ok": False,
            "error_de": str(exc)[:80],
        }


def _feed_browser_data(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_browser_data import load_ingest_status

        doc = load_ingest_status(root)
        if not doc:
            return {
                "id": "browser_data",
                "label_de": "Internet-Daten",
                "ok": False,
                "headline_de": "Ingest ausstehend — GET /api/r3/ingest",
            }
        return {
            "id": "browser_data",
            "label_de": "Internet-Daten",
            "price_source": doc.get("price_source"),
            "price_latest": doc.get("price_latest"),
            "internet_ok": doc.get("internet_ok"),
            "headline_de": doc.get("message_de"),
            "ok": bool(doc.get("internet_ok")) and bool(doc.get("ok")),
        }
    except Exception as exc:
        return {
            "id": "browser_data",
            "label_de": "Internet-Daten",
            "ok": False,
            "error_de": str(exc)[:80],
        }


def _feed_t212_api(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_t212_api_bond import build_r3_t212_api_bond

        doc = build_r3_t212_api_bond(root, persist=False)
        return {
            "id": "t212_api",
            "label_de": "Trading212 API",
            "bonded": doc.get("bonded"),
            "connected": doc.get("connected"),
            "headline_de": doc.get("confirmation_de"),
            "ok": bool(doc.get("bonded")) and bool(doc.get("connected")),
        }
    except Exception as exc:
        return {
            "id": "t212_api",
            "label_de": "Trading212 API",
            "ok": False,
            "error_de": str(exc)[:80],
        }


def _feed_t212_prognosis(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_t212_prognosis import build_r3_t212_daily_prognosis

        doc = build_r3_t212_daily_prognosis(root, persist=False)
        return {
            "id": "t212_prognosis",
            "label_de": "Tagesprognose T212",
            "signal_date": doc.get("signal_date"),
            "positions": doc.get("positions"),
            "summary_de": doc.get("summary_de"),
            "headline_de": doc.get("headline_de"),
            "ok": bool(doc.get("ok")),
        }
    except Exception as exc:
        return {
            "id": "t212_prognosis",
            "label_de": "Tagesprognose T212",
            "ok": False,
            "error_de": str(exc)[:80],
        }


def _feed_launch(root: Path) -> Dict[str, Any]:
    doc = _load_json(root / "evidence/launch_progress_latest.json")
    return {
        "id": "launch",
        "label_de": "Bereitstellung",
        "phase": doc.get("phase"),
        "headline_de": doc.get("headline_de"),
        "overall_pct": doc.get("overall_pct"),
        "hub_url": doc.get("hub_url") or "http://127.0.0.1:17890/",
        "join_url": doc.get("join_url"),
        "ok": bool(doc.get("overall_pct", 0) >= 0),
    }


def _feed_daily_learning(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_minimal_scope import build_daily_learning_status

        doc = build_daily_learning_status(root)
        return {
            "id": "daily_learning",
            "label_de": "Lernen aus Kursen",
            "headline_de": doc.get("headline_de"),
            "eod_observations": doc.get("eod_observations"),
            "last_eod_date": doc.get("last_eod_date"),
            "ok": bool(doc.get("ok")),
        }
    except Exception as exc:
        return {
            "id": "daily_learning",
            "label_de": "Lernen aus Kursen",
            "ok": False,
            "error_de": str(exc)[:80],
        }


def _feed_h1(root: Path) -> Dict[str, Any]:
    try:
        from analytics.h1_governance_status import sync_h1_governance_status

        doc = sync_h1_governance_status(root, write_readiness=False)
    except Exception:
        doc = _load_json(root / "control/h1_governance_status.json")
    return {
        "id": "h1",
        "label_de": "Validierung H1",
        "status": doc.get("status"),
        "banner_de": doc.get("banner_de"),
        "sealed": doc.get("sealed"),
        "ok": str(doc.get("status") or "") == "COMPLETE",
    }


def _feed_ki(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_local_surface import collect_ki_next_steps

        doc = collect_ki_next_steps(root)
        return {
            "id": "ki",
            "label_de": "Alpha Model KI",
            "next_step_de": doc.get("next_step_de"),
            "active_interface_de": doc.get("active_interface_de"),
            "kernel_active": bool(doc.get("kernel_active")),
            "ok": bool(doc.get("next_step_de") or doc.get("active_interface_de")),
        }
    except Exception as exc:
        return {"id": "ki", "label_de": "KI", "ok": False, "error_de": str(exc)[:80]}


def _feed_pilot(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_pilot_central import build_pilot_board

        doc = build_pilot_board(root)
        items = list(doc.get("items") or [])
        return {
            "id": "pilot",
            "label_de": "Pilot-Zentrale",
            "items": len(items),
            "current_id": doc.get("current_id"),
            "ok": True,
        }
    except Exception as exc:
        return {"id": "pilot", "label_de": "Pilot", "ok": False, "error_de": str(exc)[:80]}


def _feed_cockpit(root: Path) -> Dict[str, Any]:
    try:
        from analytics.local_app_urls import local_hub_url
        from analytics.r3_cockpit_lock import is_cockpit_running

        return {
            "id": "cockpit",
            "label_de": "Cockpit",
            "running": is_cockpit_running(),
            "entry_de": local_hub_url("/desktop"),
            "ok": True,
        }
    except Exception as exc:
        return {"id": "cockpit", "label_de": "Cockpit", "ok": False, "error_de": str(exc)[:80]}


def build_r3_central_status(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = load_central_policy(root)
    feeds = [
        _feed_trading_platform(root),
        _feed_t212_api(root),
        _feed_browser_data(root),
        _feed_t212_prognosis(root),
        _feed_cockpit(root),
        _feed_launch(root),
        _feed_daily_learning(root),
        _feed_h1(root),
        _feed_ki(root),
        _feed_pilot(root),
    ]
    ok_n = sum(1 for f in feeds if f.get("ok"))
    try:
        from analytics.local_app_urls import local_hub_url

        hub_base = local_hub_url("")
    except Exception:
        hub_base = str(policy.get("hub_base_de") or "http://127.0.0.1:17890")
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": str(policy.get("headline_de") or "R3 Zentrale"),
        "hub_base_de": hub_base.rstrip("/"),
        "default_entry_de": f"{hub_base.rstrip('/')}/desktop",
        "feeds_ok": ok_n,
        "feeds_total": len(feeds),
        "all_ok": ok_n == len(feeds),
        "feeds": feeds,
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "next_de": "bash tools/king_ops.sh r3-central",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_32b_r3_central_mandate(root: Path) -> str:
    doc = build_r3_central_status(root, persist=True)
    failing = [f for f in (doc.get("feeds") or []) if not f.get("ok")]
    lines = [
        "König-Mandat: R3 als zentrale Quelle fertigbauen — NUR König 32B.",
        f"Feeds {doc.get('feeds_ok')}/{doc.get('feeds_total')} OK.",
        f"Hub: {doc.get('hub_base_de')} · Einstieg {doc.get('default_entry_de')}.",
        "Policy: control/r3_central_source_policy.json.",
        "Ziel: R3 liefert finale T212-Tagesprognose — Active Alpha nur Engine. /api/r3/prognosis + Zentrale.",
        "Pflicht: analytics/r3_central_registry.py render_r3_central_section auf /desktop und /.",
        "Route: tools/preview_hub.py GET /api/r3/central → build_r3_central_status JSON.",
        "Lokale URLs nur (local_app_urls) — kein Tunnel-HTTPS in Zentral-Anzeige.",
        "Safety: fail-closed, dry_run, keine Orders, kein Champion-Wechsel.",
        "pytest: tests/test_r3_central_registry.py tests/test_local_app_urls.py -q",
        "finish wenn evidence/r3_central_latest.json all_ok und Sektion auf /desktop sichtbar.",
    ]
    for f in failing[:8]:
        lines.append(f"- Feed {f.get('id')}: {f.get('label_de')} — reparieren")
    text = " ".join(lines)
    Path(root / _MANDATE_REL).write_text(text, encoding="utf-8")
    return text


def render_r3_central_section(root: Path, status: Optional[Dict[str, Any]] = None) -> str:
    doc = status or build_r3_central_status(root, persist=False)
    rows = []
    for f in doc.get("feeds") or []:
        cls = "ok" if f.get("ok") else "fail"
        detail = (
            str(f.get("headline_de") or f.get("banner_de") or f.get("next_step_de") or f.get("entry_de") or "—")
        )[:100]
        rows.append(
            f'<div class="r3c-feed {cls}">'
            f'<span class="r3c-label">{html.escape(str(f.get("label_de") or ""))}</span>'
            f'<span class="r3c-detail">{html.escape(detail)}</span>'
            f"</div>"
        )
    hub = html.escape(str(doc.get("hub_base_de") or ""))
    entry = html.escape(str(doc.get("default_entry_de") or ""))
    return f"""
<section class="desktop-extra r3-central" id="r3-central" aria-label="R3 Zentrale">
  <h2>R3 Zentrale ({int(doc.get('feeds_ok') or 0)}/{int(doc.get('feeds_total') or 0)})</h2>
  <p class="r3c-hub">Hub: <a href="{entry}">{entry}</a> · Basis {hub}</p>
  <div class="r3c-grid">{''.join(rows)}</div>
</section>"""


R3_CENTRAL_CSS = """
.r3c-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; margin-top: 10px; }
@media (max-width: 720px) { .r3c-grid { grid-template-columns: 1fr 1fr; } }
.r3c-feed {
  padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line);
  background: rgba(127,127,127,.06); display: flex; flex-direction: column; gap: 4px;
}
.r3c-feed.ok { border-color: rgba(52,199,89,.35); }
.r3c-feed.fail { border-color: rgba(255,59,48,.35); }
.r3c-label { font-size: 12px; font-weight: 700; }
.r3c-detail { font-size: 10px; color: var(--muted); line-height: 1.35; }
.r3c-hub { font-size: 12px; color: var(--muted); margin: 0 0 4px; }
.r3c-hub a { color: var(--accent); }
"""
