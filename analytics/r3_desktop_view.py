"""R3 Desktop — read-only Anzeige aus Evidence. Keine Syncs/Builds beim Rendern."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_EVIDENCE_LOCAL = Path("evidence/r3_local_first_latest.json")
_EVIDENCE_BOND = Path("evidence/r3_t212_api_bond_latest.json")
_EVIDENCE_ENGINE = Path("evidence/alpha_model_background_engine_latest.json")
_EVIDENCE_INTERNET = Path("evidence/r3_internet_latest.json")
_EVIDENCE_CYCLE = Path("evidence/r3_trading_cycle_latest.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_desktop_status(root: Path) -> Dict[str, Any]:
    """Nur Evidence lesen — für /desktop und Cache."""
    root = Path(root)
    local = _load_json(root / _EVIDENCE_LOCAL)
    bond = _load_json(root / _EVIDENCE_BOND)
    engine = _load_json(root / _EVIDENCE_ENGINE)
    internet = _load_json(root / _EVIDENCE_INTERNET)
    cycle = _load_json(root / _EVIDENCE_CYCLE)
    chips: List[Dict[str, Any]] = []

    if cycle:
        chips.append(
            {
                "id": "cycle",
                "label_de": "Kreislauf",
                "ok": bool(cycle.get("closed")) or bool(cycle.get("runtime_closed")),
                "warn": bool(cycle.get("run_ok")) and not cycle.get("closed"),
                "detail_de": str(cycle.get("confirmation_de") or cycle.get("message_de") or "")[:80],
            }
        )
    if internet:
        chips.append(
            {
                "id": "internet",
                "label_de": "Internet",
                "ok": bool(internet.get("internet_ok")),
                "detail_de": str(internet.get("confirmation_de") or internet.get("message_de") or "")[:80],
            }
        )
    if local:
        chips.append(
            {
                "id": "local",
                "label_de": "Lokal",
                "ok": bool(local.get("ok", True)),
                "detail_de": str(local.get("confirmation_de") or "")[:80],
            }
        )
    if bond:
        chips.append(
            {
                "id": "t212",
                "label_de": "T212",
                "ok": bool(bond.get("bonded")) and bool(bond.get("connected")),
                "warn": bool(bond.get("bonded")) and not bond.get("connected"),
                "detail_de": str(bond.get("confirmation_de") or "")[:80],
            }
        )
    if engine:
        predict = engine.get("predict") or {}
        signal = str(
            predict.get("signal_date")
            or (engine.get("r3_display") or {}).get("signal_date")
            or "—"
        )
        chips.append(
            {
                "id": "engine",
                "label_de": "Modell",
                "ok": bool(engine.get("ok")) or bool((engine.get("r3_display") or {}).get("ok")),
                "detail_de": signal[:80],
            }
        )

    ok_n = sum(1 for c in chips if c.get("ok"))
    return {
        "schema_version": 1,
        "chips": chips,
        "chips_ok": ok_n,
        "chips_total": len(chips),
        "read_only": True,
    }


R3_DESKTOP_STATUS_CSS = """
.r3-status-bar {
  display: flex; flex-wrap: wrap; justify-content: center; gap: 8px;
  margin: 0 0 14px; padding: 8px 10px;
}
.r3-status-chip {
  font-size: 11px; font-weight: 600; padding: 5px 12px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--muted);
  background: rgba(127,127,127,.06);
}
.r3-status-chip.ok { border-color: rgba(50,215,76,.4); color: var(--ok, #32d74b); }
.r3-status-chip.warn { border-color: rgba(255,214,10,.4); color: var(--warn, #ffd60a); }
.r3-status-chip.fail { border-color: rgba(255,69,58,.4); color: var(--fail, #ff453a); }
"""


def render_r3_desktop_status(root: Path, status: Optional[Dict[str, Any]] = None) -> str:
    doc = status or load_desktop_status(root)
    chips_html = []
    for c in doc.get("chips") or []:
        state = "ok" if c.get("ok") else ("warn" if c.get("warn") else "fail")
        label = html.escape(str(c.get("label_de") or ""))
        detail = html.escape(str(c.get("detail_de") or ""))
        chips_html.append(
            f'<span class="r3-status-chip {state}" title="{detail}">{label}</span>'
        )
    return f'<div class="r3-status-bar" id="r3-status-bar">{"".join(chips_html)}</div>'


def run_r3_background_refresh(root: Path) -> Dict[str, Any]:
    """Prognose-first — leichter Kreislauf ohne parallele T212/Ingest-Schritte."""
    from analytics.r3_trading_cycle import run_trading_cycle

    doc = run_trading_cycle(root)
    return {
        "ok": bool(doc.get("run_ok")),
        "closed": bool(doc.get("closed")),
        "steps": doc.get("steps") or [],
        "cycle_pct": doc.get("cycle_pct"),
        "confirmation_de": doc.get("confirmation_de"),
    }
