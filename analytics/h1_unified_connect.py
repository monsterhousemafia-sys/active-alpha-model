"""H1 Unified Connect — König-Orchestrator verbindet lokalen mom_1-Seal-Pfad.

Architektur (hart):
- Orchestrator = König auf diesem RTX-Host (nicht „Bash weltweit“).
- mom_1_top12-Benchmark = lokal, pfadabhängig, nur König/Kernel.
- Federation/Legion = Zukunft (plan_only), löst mom_1-Seal NICHT.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/h1_unified_connect_latest.json")
_ORCHESTRATOR_REL = Path("control/h1_orchestrator_model.json")
_BENCHMARK_PATTERNS = (
    "generate_h1_naive_benchmark",
    "ai_kernel.py h1-benchmark",
    "run_benchmark_sync",
    "run_naive_momentum_baseline_full",
)

ORCHESTRATOR_HEADLINE_DE = (
    "Orchestrator = König auf diesem Host. "
    "Bash weltweit ist normal, aber ohne König-Orchestrierung nutzlos isoliert."
)
FEDERATION_SCOPE_DE = (
    "Federation/Legion = Zukunft für verteilte Path-Sim-Chunks — "
    "nicht der aktuelle mom_1_top12-Benchmark."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_orchestrator_model(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / _ORCHESTRATOR_REL
    if not path.is_file():
        return {
            "orchestrator_id": "king_rtx_host",
            "orchestrator_de": ORCHESTRATOR_HEADLINE_DE,
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _pgrep_lines(pattern: str) -> List[str]:
    try:
        proc = subprocess.run(
            ["pgrep", "-af", pattern],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode != 0:
            return []
        return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def detect_benchmark_processes() -> List[Dict[str, Any]]:
    """Lokale Benchmark-Prozesse (König, Kernel, Subprozess)."""
    seen_pids: set = set()
    out: List[Dict[str, Any]] = []
    for pattern in _BENCHMARK_PATTERNS:
        for line in _pgrep_lines(pattern):
            pid_s = line.split(None, 1)[0] if line else ""
            if not pid_s.isdigit() or pid_s in seen_pids:
                continue
            seen_pids.add(pid_s)
            out.append({"pid": int(pid_s), "pattern": pattern, "cmd": line[:240]})
    return out


def is_benchmark_generating_unified() -> bool:
    return bool(detect_benchmark_processes())


def _load_benchmark_evidence(root: Path) -> Dict[str, Any]:
    path = root / "evidence/h1_benchmark_latest.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _stale_generating(root: Path, *, generating_live: bool, bench_exists: bool) -> bool:
    if bench_exists or generating_live:
        return False
    ev = _load_benchmark_evidence(root)
    if str(ev.get("status") or "") not in {"started", "generating"}:
        return False
    try:
        ts = str(ev.get("updated_at_utc") or "")
        if not ts:
            return True
        t0 = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - t0).total_seconds()
        return age_s > 7200
    except Exception:
        return True


def _future_lane_snapshot(root: Path) -> Dict[str, Any]:
    """Federation/Legion nur als Zukunfts-Spur — nicht mom_1-Seal-Pfad."""
    out: Dict[str, Any] = {
        "active_for_mom_1_seal": False,
        "scope_de": FEDERATION_SCOPE_DE,
    }
    try:
        from analytics.h1_federation_dispatch import load_dispatch_config

        cfg = load_dispatch_config(root)
        out["federation_mode"] = str(cfg.get("mode") or "plan_only")
        out["federation_enabled"] = bool(cfg.get("enabled"))
    except Exception as exc:
        out["federation_error_de"] = str(exc)[:80]
    return out


def unified_h1_status(root: Path) -> Dict[str, Any]:
    """IST-Bild: König-Orchestrator + lokaler mom_1-Seal-Pfad."""
    root = Path(root)
    orch = load_orchestrator_model(root)
    h1_doc: Dict[str, Any] = {}
    bench_doc: Dict[str, Any] = {}
    sealed = False
    eval_doc: Dict[str, Any] = {}
    runtime_doc: Dict[str, Any] = {}

    try:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        h1_doc = h1_backtest_status(root)
        sealed = is_h1_backtest_sealed(root)
    except Exception as exc:
        h1_doc = {"status": "ERROR", "detail_de": str(exc)[:120]}

    try:
        from analytics.h1_benchmark import benchmark_status

        bench_doc = benchmark_status(root)
    except Exception as exc:
        bench_doc = {"ok": False, "error_de": str(exc)[:120]}

    processes = detect_benchmark_processes()
    generating_live = bool(processes)
    bench_exists = bool(bench_doc.get("exists"))
    stale = _stale_generating(root, generating_live=generating_live, bench_exists=bench_exists)

    if generating_live and not bench_exists:
        bench_state = "generating"
    elif bench_exists:
        bench_state = "ready"
    elif stale:
        bench_state = "stale"
    else:
        bench_state = str(bench_doc.get("status") or "missing")

    try:
        ev_path = root / "evidence/daily_alpha_h1_evaluation_latest.json"
        if ev_path.is_file():
            eval_doc = json.loads(ev_path.read_text(encoding="utf-8"))
    except Exception:
        pass

    try:
        from analytics.h1_king_runtime import detect_host_resources, king_h1_runtime_summary
        from aa_config import BacktestConfig

        cfg = BacktestConfig()
        runtime_doc = king_h1_runtime_summary(cfg, feature_gb=0.57, host=detect_host_resources())
    except Exception as exc:
        runtime_doc = {"error_de": str(exc)[:120]}

    next_step = _next_step_de(
        h1_status=str(h1_doc.get("status") or "MISSING"),
        bench_state=bench_state,
        sealed=sealed,
        generating_live=generating_live,
        root=root,
    )

    return {
        "ok": True,
        "schema_version": 2,
        "connected_at_utc": _utc_now(),
        "architecture_de": ORCHESTRATOR_HEADLINE_DE,
        "orchestrator": {
            "id": orch.get("orchestrator_id", "king_rtx_host"),
            "role_de": str(orch.get("orchestrator_de") or ORCHESTRATOR_HEADLINE_DE),
            "agent": "alpha-model-agent",
            "commands_de": (orch.get("mom_1_benchmark_lane") or {}).get("commands_de")
            or ["/h1-connect", "/h1-benchmark --wait", "/h1-watch"],
        },
        "mom_1_benchmark_lane": {
            "scope": "local_only",
            "path_dependent": True,
            "unified_state": bench_state,
            "generating_live": generating_live,
            "processes": processes,
            "benchmark_path": bench_doc.get("benchmark_path"),
            "exists": bench_exists,
            "stale_evidence": stale,
        },
        "future_lane": _future_lane_snapshot(root),
        "h1_backtest": h1_doc,
        "benchmark": {**bench_doc, "unified_state": bench_state, "stale_evidence": stale},
        "benchmark_processes": processes,
        "generating_live": generating_live,
        "sealed": sealed,
        "evaluation": eval_doc,
        "runtime": runtime_doc,
        "next_step_de": next_step,
        "headline_de": _headline_de(h1_doc, bench_state, sealed, generating_live, root=root),
    }


def _seal_optional_complete(root: Path, h1_doc: Dict, *, sealed: bool) -> bool:
    if sealed:
        return False
    try:
        from analytics.h1_seal_policy import is_h1_seal_required

        if is_h1_seal_required(root):
            return False
    except Exception:
        return False
    return str(h1_doc.get("status") or "") == "COMPLETE"


def _headline_de(
    h1_doc: Dict,
    bench_state: str,
    sealed: bool,
    generating_live: bool,
    *,
    root: Optional[Path] = None,
) -> str:
    st = str(h1_doc.get("status") or "MISSING")
    if sealed:
        return "König-Orchestrator: H1 SEALED"
    if root is not None and _seal_optional_complete(root, h1_doc, sealed=sealed):
        return "König-Orchestrator: H1 COMPLETE — Seal optional (mom_1 informativ)"
    if generating_live:
        return f"König-Orchestrator: mom_1-Benchmark läuft lokal ({bench_state})"
    if bench_state == "ready" and st == "COMPLETE":
        return "König-Orchestrator: Benchmark da → /h1-watch (Evaluate+Seal)"
    if bench_state == "stale":
        return "König-Orchestrator: Benchmark stale → /h1-benchmark --wait"
    return f"König-Orchestrator: H1 {st} · mom_1 {bench_state}"


def _next_step_de(
    *,
    h1_status: str,
    bench_state: str,
    sealed: bool,
    generating_live: bool,
    root: Optional[Path] = None,
) -> str:
    if sealed:
        return "/ready — Gates prüfen"
    if root is not None and h1_status == "COMPLETE":
        try:
            from analytics.h1_seal_policy import is_h1_seal_required

            if not is_h1_seal_required(root):
                return "/ready — H1 COMPLETE; Seal optional · /predict"
        except Exception:
            pass
    if h1_status != "COMPLETE":
        return "/h1-watch — Recovery/Status"
    if generating_live:
        return "König: Benchmark läuft lokal — warten, dann /h1-watch"
    if bench_state in {"missing", "stale"}:
        return "/h1-benchmark --wait — mom_1_top12 lokal (König, king_h1)"
    if bench_state == "ready":
        return "/h1-watch — Evaluate + Seal"
    return "/h1-connect — Orchestrator-Status"


def connect_h1_pipeline(root: Path, *, auto_execute: bool = False) -> Dict[str, Any]:
    """König-Orchestrator: lokalen mom_1-Pfad verbinden (nicht Federation)."""
    root = Path(root)
    status = unified_h1_status(root)
    actions: List[Dict[str, Any]] = []

    h1_st = str((status.get("h1_backtest") or {}).get("status") or "MISSING")
    bench_state = str((status.get("mom_1_benchmark_lane") or {}).get("unified_state") or "missing")
    sealed = bool(status.get("sealed"))
    generating_live = bool(status.get("generating_live"))

    bench_required = True
    try:
        from analytics.h1_seal_policy import is_h1_benchmark_required

        bench_required = is_h1_benchmark_required(root)
    except Exception:
        pass

    if auto_execute and not sealed and h1_st == "COMPLETE":
        if not bench_required:
            actions.append({"id": "seal_optional_sync", "status": "COMPLETE — Benchmark nicht erforderlich"})
        elif bench_state in {"missing", "stale"} and not generating_live:
            try:
                from analytics.h1_benchmark import ensure_h1_benchmark

                act = ensure_h1_benchmark(root, wait=False)
                actions.append({"id": "h1-benchmark-start", **act})
            except Exception as exc:
                actions.append({"id": "h1-benchmark-error", "error_de": str(exc)[:160]})
        elif bench_state == "ready":
            try:
                from analytics.h1_watch import run_h1_watch

                watch = run_h1_watch(root)
                actions.append({"id": "h1-watch", "sealed": watch.get("sealed"), "status": watch.get("status")})
                sealed = bool(watch.get("sealed"))
            except Exception as exc:
                actions.append({"id": "h1-watch-error", "error_de": str(exc)[:160]})
        elif generating_live:
            actions.append({"id": "benchmark_wait", "status": "generating_live"})

    status["actions_taken"] = actions
    status["sealed"] = sealed
    live_flag = generating_live or any(a.get("id") == "benchmark_wait" for a in actions)
    if not bench_required and h1_st == "COMPLETE":
        live_flag = False
    status["next_step_de"] = _next_step_de(
        h1_status=h1_st,
        bench_state=bench_state,
        sealed=sealed,
        generating_live=live_flag,
        root=root,
    )
    status["headline_de"] = _headline_de(
        status.get("h1_backtest") or {},
        bench_state,
        sealed,
        live_flag,
        root=root,
    )
    if not bench_required:
        status["generating_live"] = False
        lane = status.get("mom_1_benchmark_lane") or {}
        if isinstance(lane, dict):
            lane["generating_live"] = False
            lane["benchmark_optional"] = True
            status["mom_1_benchmark_lane"] = lane

    atomic_write_json(root / _EVIDENCE_REL, status)

    try:
        from analytics.king_sovereignty import sovereignty_model_de

        atomic_write_json(
            root / "evidence/king_sovereignty_latest.json",
            {
                "ok": True,
                "schema_version": 2,
                "pulsed_at_utc": _utc_now(),
                "sovereignty_de": sovereignty_model_de(),
                "architecture_de": ORCHESTRATOR_HEADLINE_DE,
                "h1_status": h1_st,
                "sealed": sealed,
                "actions_taken": actions,
                "next_action_de": status["next_step_de"],
                "orchestrator": "king_rtx_host",
                "mom_1_lane": "local_only",
                "federation_lane": "future_not_mom_1",
                "headline_de": status["headline_de"],
                "cursor_role_de": "Vasall — Orchestrator-Modell geliefert; König führt lokal",
            },
        )
    except Exception:
        pass

    try:
        from analytics.alpha_model_cursor_bridge import push_king_to_cursor

        push_king_to_cursor(
            root,
            status_de=status["headline_de"],
            request_de=status["next_step_de"],
        )
    except Exception:
        pass

    return status


def format_connect_de(root: Path) -> str:
    doc = connect_h1_pipeline(root, auto_execute=False)
    lines = [
        f"**{doc.get('headline_de')}**",
        str(doc.get("architecture_de") or ORCHESTRATOR_HEADLINE_DE),
        f"Nächster Schritt (König): {doc.get('next_step_de')}",
        f"H1: {(doc.get('h1_backtest') or {}).get('status')} · sealed={doc.get('sealed')}",
    ]
    lane = doc.get("mom_1_benchmark_lane") or {}
    lines.append(
        f"mom_1 lokal: {lane.get('unified_state')} · live={lane.get('generating_live')} · "
        f"pfad={lane.get('benchmark_path') or '—'}"
    )
    procs = doc.get("benchmark_processes") or []
    if procs:
        lines.append(f"Prozesse: {len(procs)} ({', '.join(str(p.get('pid')) for p in procs[:3])})")
    future = doc.get("future_lane") or {}
    lines.append(f"Federation/Legion: Zukunft ({future.get('federation_mode', 'plan_only')}) — nicht mom_1")
    for act in doc.get("actions_taken") or []:
        lines.append(f"• {act.get('id')}: {act.get('message_de') or act.get('status') or act.get('error_de') or '—'}")
    return "\n".join(lines)
