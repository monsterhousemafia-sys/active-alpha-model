"""Prognose-Freischaltung — Bash-automatisierbar (Live-Cash → Prognose → Funktionen)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_prognosis_pipeline_latest.json")
_POLICY_REL = Path("control/r3_prognosis_automation.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def load_automation_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "schema_version": 1,
            "enabled": True,
            "force_t212_sync": True,
            "rebuild_plan_on_live_cash": True,
            "warm_desktop_cache": True,
            "prepare_freigabe": True,
            "auto_refresh_on_display": True,
            "max_stale_prognosis_s": 300,
            "refresh_on_mirror_poll": True,
        }
    return doc


def _prognosis_age_seconds(doc: Dict[str, Any]) -> Optional[float]:
    ts = doc.get("updated_at_utc")
    if not ts:
        return None
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except ValueError:
        return None


def ensure_r3_prognosis_fresh(root: Path, *, force: bool = False, persist: bool = True) -> Dict[str, Any]:
    """R3-Prognose aktuell halten — bei Stale oder fehlenden Kaufzeilen Pipeline anstoßen."""
    root = Path(root)
    policy = load_automation_policy(root)
    if not policy.get("enabled", True):
        return {"ok": False, "skipped": True, "reason_de": "automation disabled"}

    prognosis = _load_json(root / Path("evidence/r3_t212_prognosis_latest.json"))
    max_stale = int(policy.get("max_stale_prognosis_s") or 300)
    age = _prognosis_age_seconds(prognosis)
    quotes_stale = False
    try:
        from analytics.r3_quote_keepalive import assess_quote_freshness

        quotes_stale = bool(assess_quote_freshness(root).get("needs_refresh"))
    except Exception:
        quotes_stale = False

    needs_refresh = (
        force
        or quotes_stale
        or not prognosis
        or age is None
        or age > max_stale
        or not prognosis.get("worthwhile_buys")
        or (
            int(prognosis.get("worthwhile_buy_count") or 0) == 0
            and int(prognosis.get("positions") or 0) > 0
        )
    )
    if not needs_refresh and policy.get("auto_refresh_on_display", True):
        return {
            "ok": bool(prognosis.get("ok")),
            "skipped": True,
            "age_s": round(age or 0, 1),
            "prognosis": prognosis,
            "headline_de": prognosis.get("headline_de") or prognosis.get("message_de"),
        }

    if not policy.get("auto_refresh_on_display", True) and not force:
        return {"ok": bool(prognosis.get("ok")), "skipped": True, "prognosis": prognosis}

    return run_prognosis_automation(root, persist=persist)


def run_prognosis_automation(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """
    Freischaltungs-Kette (ohne Orders):
    T212 live → Plan/lohnende Zeilen → Prognose → Trading-Funktionen → Freigabe → Cache
    """
    root = Path(root)
    policy = load_automation_policy(root)
    steps: List[Dict[str, Any]] = []

    try:
        from analytics.r3_t212_operator_api import operator_api_gate_block
        from analytics.r3_operator_surface_text import OPERATOR_API_ENTER

        block = operator_api_gate_block(
            root,
            headline_de=OPERATOR_API_ENTER,
            steps=[{"step": "operator_api_setup", "ok": False}],
        )
        if block:
            doc = {"schema_version": 1, "updated_at_utc": _utc_now(), **block}
            if persist:
                atomic_write_json(root / _EVIDENCE_REL, doc)
            return doc
    except Exception:
        pass

    from analytics.r3_t212_sync_coordinator import record_t212_sync, resolve_t212_sync_force

    try:
        from analytics.r3_ops_kernel import resolve_sync_owner

        sync_owner = resolve_sync_owner(root, owner="prognosis_pipeline")
    except Exception:
        sync_owner = "prognosis_pipeline"
    t212_force = resolve_t212_sync_force(root, owner=sync_owner, force=bool(policy.get("force_t212_sync", False)))

    capital: Dict[str, Any] = {}
    if policy.get("rebuild_plan_on_live_cash", True):
        try:
            from analytics.r3_live_capital import compute_worthwhile_positions

            capital = compute_worthwhile_positions(
                root, force_sync=t212_force, persist=True, sync_owner=sync_owner
            )
            steps.append(
                {
                    "step": "live_capital",
                    "ok": bool(capital.get("ok")),
                    "investable_eur": (capital.get("capital_basis") or {}).get("investable_eur"),
                    "buys": capital.get("worthwhile_buy_count"),
                    "t212_force": t212_force,
                }
            )
            record_t212_sync(root, owner=sync_owner, ok=bool(capital.get("ok")), throttled=not t212_force)
        except Exception as exc:
            steps.append({"step": "live_capital", "ok": False, "error": str(exc)[:120]})
    else:
        try:
            from analytics.r3_live_capital import sync_live_capital_basis

            capital = sync_live_capital_basis(
                root, force=t212_force, sync_owner=sync_owner
            )
            steps.append({"step": "live_capital", "ok": bool(capital.get("ok")), "t212_force": t212_force})
            record_t212_sync(root, owner=sync_owner, ok=bool(capital.get("ok")), throttled=not t212_force)
        except Exception as exc:
            steps.append({"step": "live_capital", "ok": False, "error": str(exc)[:120]})

    prognosis: Dict[str, Any] = {}
    try:
        from analytics.r3_t212_prognosis import refresh_r3_daily_prognosis

        prognosis = refresh_r3_daily_prognosis(root, persist=True, live_capital=capital)
        steps.append(
            {
                "step": "prognosis",
                "ok": bool(prognosis.get("ok")),
                "positions": prognosis.get("positions"),
                "t212_trusted": prognosis.get("t212_trusted"),
            }
        )
    except Exception as exc:
        steps.append({"step": "prognosis", "ok": False, "error": str(exc)[:120]})

    functions: Dict[str, Any] = {}
    try:
        from analytics.r3_trading_functions import build_r3_trading_functions

        functions = build_r3_trading_functions(root, persist=True)
        steps.append(
            {
                "step": "trading_functions",
                "ok": int(functions.get("functions_active") or 0) > 0,
                "primary": functions.get("primary_function_id"),
            }
        )
    except Exception as exc:
        steps.append({"step": "trading_functions", "ok": False, "error": str(exc)[:120]})

    freigabe: Dict[str, Any] = {}
    if policy.get("prepare_freigabe", True):
        try:
            from analytics.r3_freigabe import auto_prepare_freigabe_for_desktop

            freigabe = auto_prepare_freigabe_for_desktop(root)
            steps.append(
                {"step": "freigabe", "ok": bool(freigabe.get("package_ready")), "ready": freigabe.get("package_ready")}
            )
        except Exception as exc:
            steps.append({"step": "freigabe", "ok": False, "error": str(exc)[:120]})

    if policy.get("warm_desktop_cache", True):
        try:
            from analytics.desktop_shell_cache import warm_desktop_cache

            warm_desktop_cache(root, fast=True, block=False)
            steps.append({"step": "desktop_cache", "ok": True})
        except Exception as exc:
            steps.append({"step": "desktop_cache", "ok": False, "error": str(exc)[:80]})

    core_ok = bool(prognosis.get("ok")) and bool(prognosis.get("t212_trusted"))
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": core_ok,
        "headline_de": prognosis.get("headline_de")
        or prognosis.get("message_de")
        or ("Prognose-Freischaltung OK" if core_ok else "Prognose-Freischaltung — siehe steps"),
        "prognosis_ref": "evidence/r3_t212_prognosis_latest.json",
        "package_ready": freigabe.get("package_ready"),
        "investable_eur": prognosis.get("investable_eur"),
        "worthwhile_buys": prognosis.get("worthwhile_buy_count"),
        "t212_trusted": prognosis.get("t212_trusted"),
        "steps": steps,
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "bash_de": "bash tools/king_ops.sh prognosis run",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
