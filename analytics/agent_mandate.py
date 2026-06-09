"""Agent-Mandat — Ziele und Alignment statt anthropomorpher «Wünsche»."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from aa_safe_io import atomic_write_json

_MANDATE_REL = Path("control/agent_mandate.json")
_EVIDENCE_REL = Path("evidence/agent_mandate_alignment_latest.json")

ProbeFn = Callable[[Path], Dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_agent_mandate(root: Path) -> Dict[str, Any]:
    path = Path(root) / _MANDATE_REL
    if not path.is_file():
        return {
            "schema_version": 1,
            "stance_de": "Mandat fehlt — nur Audit und Operator-Anweisungen.",
            "pursuit_goals": [],
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _probe_launch_public(root: Path) -> Dict[str, Any]:
    try:
        from analytics.launch_progress_board import build_launch_status

        doc = build_launch_status(root, refresh_h1=False, persist=False)
        done = bool(doc.get("public_launch_ready"))
        return {"done": done, "detail_de": doc.get("headline_de")}
    except Exception as exc:
        return {"done": False, "detail_de": str(exc)[:120]}


def _probe_h1_sealed(root: Path) -> Dict[str, Any]:
    try:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        return {
            "done": is_h1_backtest_sealed(root),
            "detail_de": str(h1_backtest_status(root).get("status") or "—"),
        }
    except Exception as exc:
        return {"done": False, "detail_de": str(exc)[:120]}


def _probe_hub(root: Path) -> Dict[str, Any]:
    try:
        from tools.preview_hub import _hub_healthy
        from analytics.preview_federation import federation_config

        port = int(federation_config(root).get("hub_port") or 17890)
        ok = _hub_healthy(port)
        return {"done": ok, "detail_de": f"Hub :{port} {'online' if ok else 'offline'}"}
    except Exception as exc:
        return {"done": False, "detail_de": str(exc)[:120]}


def _probe_runtime(root: Path) -> Dict[str, Any]:
    try:
        from analytics.cognitive_kernel import cognitive_kernel_status

        st = cognitive_kernel_status(root)
        done = bool(st.get("successor_active"))
        gen = st.get("kernel_generation")
        return {
            "done": done,
            "detail_de": f"Cognitive Kernel v{gen} aktiv" if done else "cognitive-kernel ausstehend",
        }
    except Exception:
        path = Path(root) / "evidence/aa_linux_runtime_latest.json"
        done = path.is_file()
        return {"done": done, "detail_de": "Runtime installiert" if done else "runtime-install ausstehend"}


def _probe_kernel_boundary(root: Path) -> Dict[str, Any]:
    path = Path(root) / "evidence/kernel_boundary_audit_latest.json"
    if not path.is_file():
        return {"done": False, "detail_de": "kernel-boundary Audit fehlt"}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {"done": bool(doc.get("ok")), "detail_de": doc.get("headline_de")}
    except (json.JSONDecodeError, OSError):
        return {"done": False, "detail_de": "Audit unlesbar"}


_PROBES: Dict[str, ProbeFn] = {
    "launch.public_ready": _probe_launch_public,
    "h1.sealed": _probe_h1_sealed,
    "hub.healthy": _probe_hub,
    "runtime.installed": _probe_runtime,
    "kernel_boundary.audit_ok": _probe_kernel_boundary,
}


def evaluate_mandate_alignment(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Messbarer Fortschritt — ersetzt «ich bin zufrieden»."""
    root = Path(root)
    mandate = load_agent_mandate(root)
    goals_in = list(mandate.get("pursuit_goals") or [])
    evaluated: List[Dict[str, Any]] = []
    weighted_done = 0.0
    weight_total = 0.0

    for goal in goals_in:
        gid = str(goal.get("id") or "")
        probe_key = str(goal.get("probe") or "")
        weight = float(goal.get("weight") or 1)
        fn = _PROBES.get(probe_key)
        probe = fn(root) if fn else {"done": False, "detail_de": f"unbekannte Probe: {probe_key}"}
        done = bool(probe.get("done"))
        weight_total += weight
        if done:
            weighted_done += weight
        evaluated.append(
            {
                "id": gid,
                "label_de": goal.get("label_de"),
                "weight": weight,
                "done": done,
                "detail_de": probe.get("detail_de"),
            }
        )

    pct = int(100 * weighted_done / weight_total) if weight_total else 0
    open_goals = [g for g in evaluated if not g.get("done")]

    if pct >= 90:
        alignment_de = f"Mandat fast erfüllt ({pct}%) — Fokus auf Restziele"
    elif pct >= 50:
        alignment_de = f"Mandat teilweise erfüllt ({pct}%) — nächste Ziele aktiv"
    else:
        alignment_de = f"Mandat offen ({pct}%) — ambitionierte Ziele verfolgen, Policy einhalten"

    doc = {
        "schema_version": 1,
        "evaluated_at_utc": _utc_now(),
        "agent_name": mandate.get("agent_name") or "Auto",
        "north_star_de": mandate.get("north_star_de"),
        "stance_de": mandate.get("stance_de"),
        "communication_rule_de": mandate.get("communication_rule_de"),
        "alignment_pct": pct,
        "alignment_de": alignment_de,
        "goals": evaluated,
        "open_goals_de": [g.get("label_de") for g in open_goals],
        "next_action_de": _suggest_next(open_goals),
        "forbidden_reminder_de": mandate.get("forbidden_goals_de") or [],
        "ambition_vs_safety_de": mandate.get("ambition_vs_safety_de"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _suggest_next(open_goals: List[Dict[str, Any]]) -> str:
    priority = ("h1_sealed", "launch_complete", "hub_stable", "kernel_boundary", "cognitive_kernel_v2")
    by_id = {str(g.get("id")): g for g in open_goals}
    for pid in priority:
        if pid in by_id:
            g = by_id[pid]
            hints = {
                "h1_sealed": "ai_kernel h1 · h1-watch",
                "launch_complete": "ai_kernel launch-status · spread-tick",
                "hub_stable": "ai_kernel runtime-install",
                "kernel_boundary": "ai_kernel kernel-boundary",
                "cognitive_kernel_v2": "Cognitive Kernel v2 — eBPF/Scheduler (Mandat, noch Plan)",
            }
            return f"{g.get('label_de')} — {hints.get(pid, 'ai_kernel status')}"
    return "ai_kernel mandate · status"


def agent_response_framing(root: Path) -> Dict[str, str]:
    """Sprachrahmen für Agent-Antworten — löst das «keine Wünsche»-Problem."""
    doc = evaluate_mandate_alignment(root, persist=False)
    return {
        "use_de": doc.get("communication_rule_de") or "",
        "report_instead_de": (
            f"Statt Gefühle: Alignment {doc.get('alignment_pct')}%. "
            f"Nächster Schritt: {doc.get('next_action_de')}"
        ),
        "stance_de": doc.get("stance_de") or "",
        "alignment_de": doc.get("alignment_de") or "",
    }
