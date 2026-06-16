"""Legitimate ops pillar check — Gemini/spread, R3 quotes, champion, drawdown, tunnel."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/legitimate_ops_latest.json")
_DEBUG_LOG = Path(".cursor/debug-76ade0.log")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _agent_debug_log(
    *,
    location: str,
    message: str,
    data: Dict[str, Any],
    hypothesis_id: str,
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        root = Path(__file__).resolve().parents[1]
        path = root / _DEBUG_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": "76ade0",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion


def _pillar_gemini_spread(root: Path, *, run_spread: bool) -> Dict[str, Any]:
    from analytics.gemini_advisor_bridge import bridge_status, is_gemini_configured

    status = bridge_status(root)
    configured = is_gemini_configured(root)
    spread_doc: Dict[str, Any] = {}
    if run_spread:
        from analytics.google_world_spread import run_google_world_spread

        spread_doc = run_google_world_spread(root, use_gemini=True, force_export=True)
    copy_path = root / "evidence/spread_google_world_en.txt"
    provider = str((spread_doc.get("gemini") or {}).get("provider") or "")
    copy_ok = copy_path.is_file() and copy_path.stat().st_size > 20
    return {
        "ok": configured or copy_ok,
        "gemini_configured": configured,
        "gemini_provider": provider or None,
        "google_copy_path": str(copy_path.relative_to(root)).replace("\\", "/") if copy_ok else None,
        "copy_ok": copy_ok,
        "spread_ok": bool(spread_doc.get("spread_ok", spread_doc.get("ok"))),
        "spread_headline_de": spread_doc.get("headline_de"),
        "setup_de": None if configured else status.get("setup_de"),
        "message_de": (
            "Gemini Cloud aktiv"
            if provider == "gemini"
            else (
                f"Fallback-Copy ({provider or '—'}) — Key: bash tools/setup_gemini_key.sh --from-env"
                if copy_ok
                else "Kein Global-Copy — google-spread ausführen"
            )
        ),
    }


def _pillar_r3_quotes(root: Path, *, refresh: bool) -> Dict[str, Any]:
    from analytics.r3_live_quote_access_gate import check_live_quote_refresh_allowed

    gate = check_live_quote_refresh_allowed(root, owner="king_ops", operation="refresh")
    quote_doc: Dict[str, Any] = {"skipped": not refresh}
    if refresh and gate.get("allowed"):
        from analytics.r3_quote_keepalive import tick_quote_keepalive

        quote_doc = tick_quote_keepalive(root, force=False, owner="king_ops", persist=True)
    assess = quote_doc.get("assess_after") or {}
    return {
        "ok": bool(gate.get("allowed")) and (quote_doc.get("ok") is not False or not refresh),
        "gate_allowed": bool(gate.get("allowed")),
        "gate_message_de": gate.get("message_de"),
        "quote_status": assess.get("quote_status") or quote_doc.get("quote_status"),
        "price_latest": quote_doc.get("price_latest"),
        "message_de": gate.get("message_de") or quote_doc.get("headline_de") or "R3-Quotes geprüft",
    }


def _pillar_champion(root: Path) -> Dict[str, Any]:
    from analytics.champion_runtime_guard import verify_champion_runtime
    from aa_vision_review_gate import verify_champion_evidence

    runtime = verify_champion_runtime(root)
    evidence = verify_champion_evidence(root)
    ok = bool(runtime.ok)
    warnings: List[str] = list(runtime.warnings or [])
    if not evidence.get("ok"):
        warnings.append(str(evidence.get("error") or "champion_evidence_mismatch"))
    return {
        "ok": ok,
        "authoritative_champion": runtime.authoritative_champion,
        "runtime_ok": runtime.ok,
        "evidence_ok": evidence.get("ok"),
        "evidence_champion": evidence.get("champion"),
        "blockers": list(runtime.blockers or []),
        "warnings": warnings,
        "message_de": (
            runtime.status_de
            if ok and evidence.get("ok")
            else (
                f"{runtime.status_de} — Evidenz-Hinweis: {warnings[0]}"
                if ok
                else f"Champion rot — {'; '.join(runtime.blockers[:3])}"
            )
        ),
    }


def _pillar_drawdown(root: Path) -> Dict[str, Any]:
    from analytics.risk_drawdown_scenario import run_risk_drawdown_scenario

    doc = run_risk_drawdown_scenario(root)
    return {
        "ok": bool(doc.get("ok")),
        "historical_max_drawdown": doc.get("historical_max_drawdown"),
        "headline_de": doc.get("headline_de") or doc.get("message_de"),
        "evidence_ref": "evidence/risk_drawdown_scenario_latest.json",
    }


def _pillar_spread_tunnel(root: Path) -> Dict[str, Any]:
    from analytics.remote_hub_access import remote_access_status

    status = remote_access_status(root)
    world_zip = Path.home() / "world_worker_LITE.zip"
    return {
        "ok": bool(status.get("tunnel_pid_alive")) and world_zip.is_file(),
        "tunnel_alive": bool(status.get("tunnel_pid_alive")),
        "tunnel_stable": bool(status.get("tunnel_stable")),
        "public_base_url": status.get("public_base_url"),
        "world_zip": str(world_zip) if world_zip.is_file() else None,
        "message_de": (
            f"Tunnel {status.get('public_base_url') or '—'}"
            if status.get("tunnel_pid_alive")
            else "Tunnel tot — spread-remote / setup_cloudflare_tunnel_token.sh"
        ),
    }


def run_legitimate_ops_check(
    root: Path,
    *,
    refresh_quotes: bool = False,
    run_spread: bool = True,
    run_id: str = "pre-fix",
) -> Dict[str, Any]:
    root = Path(root)
    pillars = {
        "gemini_spread": _pillar_gemini_spread(root, run_spread=run_spread),
        "r3_quotes": _pillar_r3_quotes(root, refresh=refresh_quotes),
        "champion": _pillar_champion(root),
        "drawdown_scenario": _pillar_drawdown(root),
        "spread_tunnel": _pillar_spread_tunnel(root),
    }
    for pid, pdata in pillars.items():
        _agent_debug_log(
            location=f"legitimate_ops_check.py:pillar:{pid}",
            message=f"pillar {pid}",
            data={"ok": pdata.get("ok"), "message_de": pdata.get("message_de")},
            hypothesis_id="H4" if pid != "gemini_spread" else "H1",
            run_id=run_id,
        )

    ok_count = sum(1 for p in pillars.values() if p.get("ok"))
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok_count >= 3,
        "pillars_ok": ok_count,
        "pillars_total": len(pillars),
        "pillars": pillars,
        "operator_next_de": _operator_next(pillars),
        "headline_de": f"Legitimate Ops — {ok_count}/{len(pillars)} Säulen grün",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    _agent_debug_log(
        location="legitimate_ops_check.py:run",
        message="legitimate ops summary",
        data={"ok": doc["ok"], "pillars_ok": ok_count, "pillars_total": len(pillars)},
        hypothesis_id="H4",
        run_id=run_id,
    )
    return doc


def _operator_next(pillars: Dict[str, Dict[str, Any]]) -> List[str]:
    steps: List[str] = []
    gem = pillars.get("gemini_spread") or {}
    if not gem.get("gemini_configured"):
        steps.append("Gemini-Key: bash tools/setup_gemini_key.sh --from-env")
    tun = pillars.get("spread_tunnel") or {}
    if not tun.get("tunnel_alive"):
        steps.append("Tunnel: bash tools/setup_cloudflare_tunnel_token.sh")
    if not gem.get("copy_ok"):
        steps.append("Global-Copy: bash tools/king_ops.sh google-spread")
    ch = pillars.get("champion") or {}
    if not ch.get("ok"):
        steps.append(f"Champion prüfen: blockers={ch.get('blockers')}")
    return steps or ["Alle Säulen grün — optional: bash tools/king_ops.sh r3-quotes --force"]
