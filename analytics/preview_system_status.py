"""Unified system status for Preview Command Center — H1, Kernel, Launch, Operator."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def _status_class(ok: Optional[bool], *, warn: bool = False) -> str:
    if ok is True:
        return "ok"
    if warn:
        return "warn"
    return "fail"


def build_preview_system_status(
    root: Path,
    *,
    refresh_h1: bool = False,
    fast: bool = False,
) -> Dict[str, Any]:
    """Single source for Apple-style status board in Preview Hub."""
    root = Path(root)

    h1: Dict[str, Any] = {}
    try:
        if refresh_h1:
            from analytics.h1_governance_status import sync_h1_governance_status

            h1 = sync_h1_governance_status(root, write_readiness=False)
        else:
            from analytics.h1_governance_status import load_h1_governance_status

            h1 = load_h1_governance_status(root)
    except Exception:
        h1 = _load_json(root / "control/h1_governance_status.json")

    cognitive: Dict[str, Any] = {}
    if fast:
        cognitive = _load_json(root / "evidence/cognitive_kernel_latest.json")
        iface = cognitive.get("interface") if isinstance(cognitive.get("interface"), dict) else {}
        if not iface:
            try:
                from analytics.alpha_model_interface_kernel import interface_stack_status

                iface = interface_stack_status(root)
                cognitive["interface"] = iface
            except Exception:
                iface = {}
        gen = int((cognitive.get("manifest") or {}).get("kernel_generation") or cognitive.get("kernel_generation") or 1)
        cognitive.setdefault("kernel_generation", gen)
        cognitive.setdefault("successor_active", gen >= 2)
        cognitive.setdefault("active_interface", iface.get("active_interface"))
    else:
        try:
            from analytics.cognitive_kernel import cognitive_kernel_status

            cognitive = cognitive_kernel_status(root)
        except Exception:
            cognitive = {}

    launch: Dict[str, Any] = {}
    if fast:
        launch = _load_json(root / "evidence/launch_progress_latest.json")
        if not launch:
            try:
                from analytics.launch_progress_board import build_launch_status

                launch = build_launch_status(root, refresh_h1=False, persist=False)
            except Exception:
                launch = {}
    else:
        try:
            from analytics.launch_progress_board import build_launch_status

            launch = build_launch_status(root, refresh_h1=False, persist=False)
        except Exception:
            launch = {}

    operator: Dict[str, Any] = {}
    if fast:
        pub = _load_json(root / "evidence/operator_public_latest.json")
        operator = pub if pub else _load_json(root / "evidence/operator_visibility_latest.json")
    else:
        try:
            from analytics.operator_visibility import build_visibility_snapshot

            operator = build_visibility_snapshot(root)
        except Exception:
            operator = {}

    preview_doc = _load_json(root / "evidence/gui_preview_latest.json")
    passed = int(preview_doc.get("passed") or 0)
    total = int(preview_doc.get("total") or 0)
    preview_pct = int(round(100 * passed / max(total, 1)))
    preview_ok = bool(preview_doc.get("overall_pass"))

    lean: Dict[str, Any] = _load_json(root / "evidence/aa_lean_mode_latest.json")
    lean_active = bool(lean.get("active"))

    h1_pct = int(h1.get("progress_pct") or 0)
    h1_sealed = bool(h1.get("sealed"))
    h1_status = str(h1.get("status") or "—")
    launch_overall = int(launch.get("overall_pct") or 0)
    successor = bool(cognitive.get("successor_active"))
    iface = cognitive.get("interface") or {}
    active_iface = str(iface.get("active_interface") or "—")

    supremacy_de = ""
    try:
        from analytics.linux_runtime_unified import kernel_supremacy_status

        supremacy_de = str(kernel_supremacy_status(root).get("supremacy_de") or "")
    except Exception:
        pass

    r3_op: Dict[str, Any] = {}
    try:
        from analytics.r3_operator_readiness import build_r3_operator_readiness

        r3_op = build_r3_operator_readiness(root, persist=False)
        if not r3_op.get("operational_pct") and not fast:
            from analytics.r3_operator_readiness import sync_r3_operator_readiness

            r3_op = sync_r3_operator_readiness(root, persist=True)
    except Exception:
        r3_op = _load_json(root / "evidence/r3_operator_readiness_latest.json")

    r3_op_pct = int(r3_op.get("operational_pct") or 0)
    r3_op_ok = bool(r3_op.get("operational_ok"))

    tiles: List[Dict[str, Any]] = [
        {
            "id": "r3_operator",
            "label_de": "R3 Betrieb",
            "value_de": f"{r3_op_pct}%",
            "detail_de": (
                f"{r3_op.get('channels_de') or '—'} · "
                f"SR {r3_op.get('series_readiness_pct') or 0}% · "
                f"Wachstum {r3_op.get('growth_pct') or 0}%"
            )[:140],
            "ok": r3_op_ok,
            "status_class": _status_class(r3_op_ok, warn=r3_op_pct >= 75 and not r3_op_ok),
        },
        {
            "id": "kernel",
            "label_de": "R3 Kern",
            "value_de": "Ollama · Hub · Evidence",
            "detail_de": (
                str(iface.get("r3_kernel_headline_de") or "")
                or "Ollama + Hub + Evidence — nicht Cursor"
            )[:140],
            "ok": successor,
            "status_class": _status_class(successor, warn=not successor),
        },
        {
            "id": "interface",
            "label_de": "Kanal",
            "value_de": {
                "build_kernel": "Bau-Kernel",
                "r3_ki": "R3 KI",
                "build_tool": "Cursor Legacy",
                "cursor_chat": "Cursor Legacy",
                "ollama_local": "R3 KI",
                "degraded": "Eingeschränkt",
            }.get(active_iface, active_iface),
            "detail_de": str(iface.get("headline_de") or "—")[:120],
            "ok": active_iface in ("build_kernel", "r3_ki", "ollama_local"),
            "status_class": _status_class(
                active_iface in ("build_kernel", "r3_ki", "ollama_local"),
                warn=active_iface == "r3_ki" and not successor,
            ),
        },
        {
            "id": "h1",
            "label_de": "H1 Backtest",
            "value_de": "Sealed" if h1_sealed else f"{h1_pct}%",
            "detail_de": str(h1.get("banner_de") or h1.get("detail_de") or "—")[:140],
            "ok": h1_sealed,
            "status_class": _status_class(
                h1_sealed,
                warn=h1_status in ("RUNNING", "COMPLETE") and not h1_sealed,
            ),
        },
        {
            "id": "preview",
            "label_de": "Preview",
            "value_de": f"{passed}/{total}" if total else "—",
            "detail_de": f"{preview_pct}% · {'Bereit' if preview_ok else 'Prüfen'}",
            "ok": preview_ok,
            "status_class": _status_class(preview_ok, warn=not preview_ok and passed > 0),
        },
        {
            "id": "launch",
            "label_de": "Launch",
            "value_de": f"{launch_overall}%",
            "detail_de": str(launch.get("headline_de") or "—")[:120],
            "ok": launch_overall >= 92,
            "status_class": _status_class(launch_overall >= 92, warn=launch_overall >= 40),
        },
        {
            "id": "lean",
            "label_de": "Lean-Modus",
            "value_de": "Aktiv" if lean_active else "Aus",
            "detail_de": str(lean.get("mode") or lean.get("detail_de") or "Normalbetrieb")[:80],
            "ok": not lean_active or str(lean.get("mode") or "") in ("turbo", "maximum"),
            "status_class": "warn" if lean_active else "ok",
        },
    ]

    from analytics.r3_local_surface import collect_ki_next_steps, filter_launch_tiles_for_king

    launch_tiles = filter_launch_tiles_for_king(list(launch.get("tiles") or []), root)
    blockers = list(launch.get("blockers_de") or [])
    if not blockers and h1_status == "RUNNING" and not h1_sealed:
        blockers = [str(h1.get("banner_de") or "H1 läuft — Seal ausstehend")]

    composite = int(round((launch_overall * 0.35) + (preview_pct * 0.25) + (h1_pct * 0.4)))
    if not fast:
        try:
            from analytics.r3_step_b import is_step_b_released
            from analytics.r3_ubuntu_closure import evaluate_ubuntu_closure

            if is_step_b_released(root) and int(evaluate_ubuntu_closure(root).get("closure_percent") or 0) >= 100:
                composite = max(composite, 95 if preview_ok else 90)
        except Exception:
            pass
    if h1_sealed and preview_ok:
        composite = max(composite, 88)
    if h1_sealed and preview_ok and launch.get("public_launch_ready"):
        composite = 100

    headline = str(operator.get("headline_de") or launch.get("headline_de") or "Systemstatus")
    if successor and supremacy_de:
        headline = supremacy_de
    elif h1.get("banner_de") and h1_status in ("RUNNING", "COMPLETE", "ZOMBIE"):
        headline = str(h1.get("banner_de"))

    ki_next: List[Dict[str, Any]] = []
    pilot_board: Dict[str, Any] = {}
    forschungszweig: Dict[str, Any] = {}
    ki_health: Dict[str, Any] = {}
    dev_trail: Dict[str, Any] = {}
    if not fast:
        ki_next = collect_ki_next_steps(
            root,
            report={
                "chat_evolution": preview_doc.get("chat_evolution") or {},
                "blockers": blockers,
                "system_status": {
                    "cognitive": {
                        "successor_active": successor,
                        "headline_de": cognitive.get("headline_de"),
                        "active_interface": active_iface,
                    },
                    "operator": {
                        "chat_next_de": operator.get("chat_evolution_next_de"),
                        "cockpit_next_step_de": operator.get("cockpit_next_step_de"),
                    },
                    "blockers_de": blockers,
                },
            },
        )
        try:
            from analytics.r3_pilot_central import build_pilot_board

            pilot_board = build_pilot_board(root)
        except Exception:
            pass
        try:
            from analytics.r3_forschungszweig import build_forschungszweig_status

            forschungszweig = build_forschungszweig_status(root)
        except Exception:
            pass
        try:
            from analytics.r3_ki_console import ki_health

            ki_health = ki_health(root)
        except Exception:
            ki_health = {}
        try:
            from analytics.r3_dev_trail import build_dev_trail

            dev_trail = build_dev_trail(root)
        except Exception:
            dev_trail = {}

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": headline[:200],
        "composite_pct": composite,
        "phase": str(launch.get("phase") or "unknown"),
        "tiles": tiles,
        "launch_tiles": launch_tiles,
        "blockers_de": blockers[:4],
        "h1": {
            "status": h1_status,
            "progress_pct": h1_pct,
            "sealed": h1_sealed,
            "banner_de": h1.get("banner_de"),
            "detail_de": h1.get("detail_de"),
        },
        "cognitive": {
            "successor_active": successor,
            "kernel_generation": cognitive.get("kernel_generation"),
            "headline_de": cognitive.get("headline_de"),
            "active_interface": active_iface,
        },
        "preview": {
            "passed": passed,
            "total": total,
            "score_pct": preview_pct,
            "overall_pass": preview_ok,
        },
        "operator": {
            "headline_de": operator.get("headline_de"),
            "last_action_de": (operator.get("operator_actions_de") or [None])[-1],
            "circle_headline_de": operator.get("circle_headline_de"),
            "chat_next_de": operator.get("chat_evolution_next_de"),
            "cockpit_next_step_de": operator.get("cockpit_next_step_de"),
        },
        "r3_operator_readiness": r3_op,
        "launch_overall_pct": launch_overall,
        "milestones": list(launch.get("milestones") or []),
        "kernel_supremacy_de": supremacy_de or None,
        "kernel_authoritative": successor,
        "ki_next": ki_next,
        "ki_health": ki_health,
        "dev_trail": dev_trail,
        "pilot_board": pilot_board,
        "forschungszweig": forschungszweig,
    }
