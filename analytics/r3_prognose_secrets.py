"""Forschungszweig — Prognose-Geheimnisse im Chat (echte Signale, Mitmach-Anreiz)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_forschungszweig.json")
_SNAPSHOT_REL = Path("evidence/pilot_day_trading_snapshot_latest.json")
_EVIDENCE_REL = Path("evidence/r3_prognose_secrets_latest.json")

_QUERY_RE = re.compile(
    r"\b(aktie|aktien|kurs|kurse|prognose|geheimnis|alpha|signal|steigen|fallen|"
    r"kaufen|verkaufen|portfolio|rebalance|morgen|heute|us-?session|t212)\b",
    re.IGNORECASE,
)


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


def load_pilot_snapshot(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _SNAPSHOT_REL)


def _top_picks(snapshot: Dict[str, Any], *, limit: int = 8) -> List[Dict[str, Any]]:
    reeval = snapshot.get("reevaluation") or {}
    actions = list(reeval.get("recommended_actions") or [])
    if actions:
        return actions[:limit]
    playbook = snapshot.get("playbook") or {}
    rows = list(playbook.get("model_allocations") or playbook.get("allocations") or [])
    if rows:
        return rows[:limit]
    return []


def build_prognose_secrets_doc(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = _load_json(root / _CONFIG_REL)
    snap = load_pilot_snapshot(root)
    reeval = snap.get("reevaluation") or {}
    playbook = snap.get("playbook") or {}
    meta = reeval.get("model_meta") or {}
    picks = _top_picks(snap)

    pick_rows = []
    for i, p in enumerate(picks, 1):
        pick_rows.append(
            {
                "rank": i,
                "symbol": p.get("symbol"),
                "target_weight_pct": p.get("target_weight_pct"),
                "alpha_lcb": p.get("alpha_lcb"),
                "rank_score": p.get("rank_score"),
                "action_de": p.get("action_de"),
                "rationale_de": p.get("pick_rationale_de"),
                "gap_eur": p.get("gap_eur"),
            }
        )

    deferred = (snap.get("deferred_summary") or {}).get("pending") or []
    pending_symbols = [str(x.get("instrument") or "") for x in deferred[:5]]

    learn = _load_json(root / "evidence/public_learning_report_latest.json")
    metrics = (learn.get("metrics") or {}).get("live") or {}

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "share_in_chat": bool(cfg.get("chat_secrets", {}).get("enabled", True)),
        "signal_date": meta.get("signal_date") or (deferred[0].get("signal_date") if deferred else None),
        "champion_id": reeval.get("champion_id") or "DAILY_ALPHA_H1",
        "risk_on": meta.get("risk_on"),
        "regime_de": "Risk-on" if meta.get("risk_on") else "Risk-off",
        "headline_de": str(playbook.get("headline_de") or playbook.get("summary_de") or "")[:220],
        "primary_symbol": playbook.get("primary_symbol"),
        "pending_orders": pending_symbols,
        "top_picks": pick_rows,
        "learning_de": (
            f"IC {metrics.get('ic_mean', '—')} · Hit {metrics.get('hit_rate_pct', '—')}%"
            if metrics
            else None
        ),
        "disclaimer_de": str(
            (cfg.get("chat_secrets") or {}).get("disclaimer_de")
            or "Modell-Signale — keine Anlageberatung. Orders nur mit Bestätigung."
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def format_geheimnis_reply_de(doc: Dict[str, Any]) -> str:
    if not doc.get("top_picks"):
        return (
            "Noch kein Prognose-Geheimnis geladen — zuerst:\n"
            "python3 tools/ai_kernel.py trading-day\n"
            "oder python3 tools/ai_kernel.py refresh"
        )
    lines = [
        "🔮 Prognose-Geheimnis (Forschungszweig)",
        f"Signal-Datum: {doc.get('signal_date') or '—'} · {doc.get('champion_id')} · {doc.get('regime_de')}",
    ]
    if doc.get("headline_de"):
        lines.append(str(doc["headline_de"])[:200])
    lines.append("")
    lines.append("Top-Aktien (Modell erwartet relative Stärke):")
    for row in doc.get("top_picks") or []:
        sym = row.get("symbol") or "?"
        wt = row.get("target_weight_pct")
        alpha = row.get("alpha_lcb")
        act = row.get("action_de") or row.get("rationale_de") or ""
        lines.append(
            f"{row.get('rank')}. {sym} — Ziel {wt}% · Alpha {alpha} · {act}"
        )
    if doc.get("pending_orders"):
        lines.append("")
        lines.append("Vorgemerkt für Eröffnung: " + ", ".join(doc["pending_orders"]))
    if doc.get("primary_symbol"):
        lines.append(f"Primär-Fokus: {doc['primary_symbol']}")
    if doc.get("learning_de"):
        lines.append(f"Lernen: {doc['learning_de']}")
    lines.append("")
    lines.append(str(doc.get("disclaimer_de") or ""))
    return "\n".join(lines)


def build_chat_context_de(root: Path, *, max_chars: int = 3500) -> str:
    doc = build_prognose_secrets_doc(root)
    if not doc.get("share_in_chat"):
        return ""
    body = format_geheimnis_reply_de(doc)
    cfg = _load_json(root / _CONFIG_REL)
    policy = str((cfg.get("chat_secrets") or {}).get("policy_de") or "")
    prefix = f"{policy}\n\n" if policy else ""
    return (prefix + body)[:max_chars]


def is_prognose_query(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if raw.startswith("/geheimnis") or raw.startswith("/kurse") or raw.startswith("/alpha"):
        return True
    if raw.startswith("/prognose") and " " not in raw[9:].strip():
        return True
    return bool(_QUERY_RE.search(raw))


def handle_prognose_chat(root: Path, text: str) -> Dict[str, Any]:
    root = Path(root)
    doc = build_prognose_secrets_doc(root)
    reply = format_geheimnis_reply_de(doc)
    return {
        "ok": True,
        "reply_de": reply,
        "prognose": True,
        "secrets": doc,
        "share_in_chat": bool(doc.get("share_in_chat")),
    }
