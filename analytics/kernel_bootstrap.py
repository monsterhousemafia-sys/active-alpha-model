"""AI Kernel control-plane bootstrap — policy load, safety checks, pre-session warnings."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

_EVIDENCE_REL = Path("evidence/ai_kernel_bootstrap_latest.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_kernel_policy(root: Path) -> Dict[str, Any]:
    from execution.linux_security_boundary import load_kernel_doc

    return load_kernel_doc(root)


def safety_checks(root: Path, kernel: Dict[str, Any]) -> Dict[str, Any]:
    from execution.linux_security_boundary import host_role_summary

    safety = kernel.get("safety") or {}
    host = host_role_summary()
    checks = {
        "no_auto_money": not bool(safety.get("auto_execute_real_money")),
        "gui_confirm_required": bool(safety.get("gui_confirm_required", True)),
        "native_host": bool(host.get("native_execution_host")),
        "kernel_doc": bool(kernel),
        "mode_linux_native": str(kernel.get("mode") or "") == "linux_native_pilot",
    }
    blockers = [k for k, ok in checks.items() if not ok]
    return {"checks": checks, "blockers": blockers, "ok": not blockers, "host": host}


def go_live_context(kernel: Dict[str, Any]) -> Dict[str, Any]:
    go_live = str(kernel.get("go_live_date") or kernel.get("learning", {}).get("go_live_date") or "")
    today = date.today()
    if not go_live:
        return {"go_live_date": "", "days_until": None, "is_go_live_day_or_later": False}
    try:
        target = date.fromisoformat(go_live)
    except ValueError:
        return {"go_live_date": go_live, "days_until": None, "is_go_live_day_or_later": False}
    delta = (target - today).days
    return {
        "go_live_date": go_live,
        "days_until": delta,
        "is_go_live_day_or_later": today >= target,
    }


def collect_session_warnings(root: Path, *, snap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from analytics.pilot_trading_day_warnings import collect_trading_day_warnings

    return collect_trading_day_warnings(root, snap=snap or {})


def run_kernel_bootstrap(
    root: Path,
    *,
    snap: Optional[Dict[str, Any]] = None,
    write_evidence: bool = True,
) -> Dict[str, Any]:
    """Single pre-launch control-plane pass for native Linux pilot."""
    root = Path(root)
    kernel = load_kernel_policy(root)
    safety = safety_checks(root, kernel)
    go_live = go_live_context(kernel)
    warnings = collect_session_warnings(root, snap=snap)

    critical_codes: List[str] = [
        str(w.get("code") or "")
        for w in (warnings.get("warnings") or [])
        if w.get("severity") == "critical"
    ]
    report: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "mode": kernel.get("mode"),
        "agent_role": kernel.get("agent_role"),
        "safety": safety,
        "go_live": go_live,
        "day_warnings": {
            "severity": warnings.get("severity"),
            "headline_de": warnings.get("headline_de"),
            "critical_count": warnings.get("critical_count"),
            "warn_count": warnings.get("warn_count"),
            "must_resolve_before_trading": warnings.get("must_resolve_before_trading"),
            "critical_codes": critical_codes,
        },
        "launch_allowed": safety["ok"],
        "trading_allowed": safety["ok"] and not warnings.get("must_resolve_before_trading"),
    }
    if write_evidence:
        out = root / _EVIDENCE_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def format_critical_dialog_de(report: Dict[str, Any]) -> str:
    dw = report.get("day_warnings") or {}
    lines = [str(dw.get("headline_de") or "Kritische Punkte vor dem Handelstag.")]
    for code in dw.get("critical_codes") or []:
        if code:
            lines.append(f"• {code}")
    return "\n".join(lines)[:3500]
