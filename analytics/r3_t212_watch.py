"""24/7 T212-Watch — Hintergrund-Sync + Prognose (API-coalesced, fail-closed)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_t212_watch_latest.json")
_POLICY_REL = Path("control/r3_t212_watch_policy.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_watch_policy(root: Path) -> Dict[str, Any]:
    path = Path(root) / _POLICY_REL
    if not path.is_file():
        return {
            "schema_version": 1,
            "enabled": True,
            "min_interval_s": 600,
            "run_prognosis_on_sync": True,
        }
    import json

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {"enabled": True, "min_interval_s": 600}


def tick_t212_watch(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Ein Watch-Tick — nur wenn Intervall abgelaufen und nicht pausiert."""
    root = Path(root)
    policy = load_watch_policy(root)
    if not policy.get("enabled", True):
        return {"ok": True, "skipped": True, "reason_de": "watch_disabled"}

    import json

    state_path = root / "control/r3_t212_watch_state.json"
    state: Dict[str, Any] = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}

    from datetime import datetime, timezone

    last = state.get("last_tick_utc")
    min_s = int(policy.get("min_interval_s") or 600)
    if last:
        try:
            ts = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age < min_s:
                return {"ok": True, "skipped": True, "reason_de": "interval", "age_s": round(age, 1)}
        except ValueError:
            pass

    out: Dict[str, Any] = {"ok": True, "steps": []}
    try:
        from analytics.r3_quote_keepalive import tick_quote_keepalive

        quotes = tick_quote_keepalive(root, force=False, owner="t212_watch", persist=True)
        out["quotes_ok"] = bool(quotes.get("ok"))
        out["steps"].append({"step": "quotes", "ok": bool(quotes.get("ok")), "skipped": quotes.get("skipped")})
    except Exception as exc:
        out["steps"].append({"step": "quotes", "ok": False, "error": str(exc)[:80]})

    force_prog = False
    if policy.get("force_sync_when_stale", True):
        try:
            from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

            trust = assess_t212_trust_from_root(root, persist=False)
            force_prog = not bool(trust.get("trusted"))
        except Exception:
            force_prog = True
    try:
        from analytics.r3_prognosis_pipeline import ensure_r3_prognosis_fresh

        prog = ensure_r3_prognosis_fresh(root, force=force_prog, persist=True)
        out["prognosis_ok"] = bool(prog.get("ok"))
        out["t212_trusted"] = prog.get("t212_trusted") or (prog.get("prognosis") or {}).get("t212_trusted")
        out["skipped_prognosis"] = bool(prog.get("skipped"))
        out["steps"].append({"step": "prognosis", "ok": bool(prog.get("ok"))})
    except Exception as exc:
        out["ok"] = False
        out["steps"].append({"step": "prognosis", "ok": False, "error": str(exc)[:80]})

    try:
        from analytics.alpha_model_background_engine import tick_alpha_model_background

        eng = tick_alpha_model_background(root, force=False)
        out["engine_ok"] = bool(eng.get("ok"))
        out["steps"].append({"step": "engine", "ok": bool(eng.get("ok"))})
    except Exception as exc:
        out["steps"].append({"step": "engine", "ok": False, "error": str(exc)[:80]})

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        **out,
        "headline_de": (
            "T212-Watch OK — Prognose aktuell"
            if out.get("ok") and out.get("t212_trusted")
            else "T212-Watch — Sync/Trust prüfen"
        ),
    }
    atomic_write_json(state_path, {"last_tick_utc": _utc_now(), "updated_at_utc": _utc_now()})
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
