"""R3 Minimal-Scope — nur KI-Prognosen und tägliches Kurs-Lernen (Ubuntu macht den Rest)."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict

_POLICY_REL = Path("control/r3_minimal_scope_policy.json")
_LEARNING_REL = Path("evidence/public_learning_report_latest.json")

R3_LEARNING_CSS = """
.r3-learning {
  margin: 20px 0; padding: 18px 20px; border-radius: 16px;
  border: 1px solid var(--line); background: rgba(127,127,127,.06);
}
.r3-learning h2 { margin: 0 0 10px; font-size: 18px; font-weight: 700; }
.r3-learning-meta { margin: 0 0 12px; font-size: 12px; color: var(--muted); line-height: 1.45; }
.r3-learning-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 10px; }
@media (max-width: 720px) { .r3-learning-grid { grid-template-columns: 1fr; } }
.r3-learning-kv {
  padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line);
  background: rgba(127,127,127,.04);
}
.r3-learning-kv b { display: block; font-size: 11px; color: var(--muted); margin-bottom: 4px; }
.r3-learning-kv span { font-size: 14px; font-weight: 600; }
.r3-learning.ok { border-color: rgba(52,199,89,.35); }
.r3-learning.fail { border-color: rgba(255,59,48,.35); }
"""


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_minimal_scope_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def build_daily_learning_status(root: Path) -> Dict[str, Any]:
    """Read-only: tägliches Lernen aus Kursen (kein Trainings-Trigger)."""
    root = Path(root)
    report = _load_json(root / _LEARNING_REL)
    capture = report.get("capture") or {}
    metrics = (report.get("metrics") or {}).get("live") or {}
    cycle = report.get("daily_cycle") or {}
    return {
        "ok": bool(capture.get("learning_healthy")) and bool(cycle.get("all_ok")),
        "learning_active": bool(capture.get("learning_collection_active")),
        "eod_observations": capture.get("eod_close_observations"),
        "intraday_observations": capture.get("intraday_observations"),
        "broker_snapshots": capture.get("broker_daily_snapshots"),
        "last_eod_date": capture.get("last_eod_date"),
        "last_intraday_utc": capture.get("last_intraday_utc"),
        "ic_mean": metrics.get("ic_mean"),
        "hit_rate_pct": metrics.get("hit_rate_pct"),
        "headline_de": (
            f"Lernen aus Kursen · EOD {capture.get('last_eod_date') or '—'}"
            f" · {capture.get('eod_close_observations') or 0} Beobachtungen"
        ),
        "message_de": (
            "KI lernt täglich aus Kursen — Ergebnis erscheint als Handelsprognose auf R3"
        ),
    }


def render_daily_learning_section(root: Path, status: Dict[str, Any] | None = None) -> str:
    doc = status or build_daily_learning_status(root)
    ok = bool(doc.get("ok"))
    cls = "ok" if ok else "fail"
    ic = doc.get("ic_mean")
    hit = doc.get("hit_rate_pct")
    ic_s = html.escape(str(ic if ic is not None else "—"))
    hit_s = html.escape(str(hit if hit is not None else "—"))
    return f"""
<section class="r3-learning {cls}" id="r3-daily-learning" aria-label="Tägliches Lernen">
  <h2>KI lernt aus Kursen</h2>
  <p class="r3-learning-meta">{html.escape(str(doc.get('message_de') or ''))}</p>
  <div class="r3-learning-grid">
    <div class="r3-learning-kv"><b>EOD-Beobachtungen</b><span>{int(doc.get('eod_observations') or 0)}</span></div>
    <div class="r3-learning-kv"><b>Intraday</b><span>{int(doc.get('intraday_observations') or 0)}</span></div>
    <div class="r3-learning-kv"><b>Letztes EOD</b><span>{html.escape(str(doc.get('last_eod_date') or '—'))}</span></div>
    <div class="r3-learning-kv"><b>IC (live)</b><span>{ic_s}</span></div>
    <div class="r3-learning-kv"><b>Hit-Rate</b><span>{hit_s}%</span></div>
    <div class="r3-learning-kv"><b>Status</b><span>{'aktiv' if doc.get('learning_active') else 'aus'}</span></div>
  </div>
</section>"""
