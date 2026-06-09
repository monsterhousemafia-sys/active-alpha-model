"""Decision Cockpit Update — R3-Web ↔ EXE-Vision Brücke (read-only, fail-closed)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/decision_cockpit_update_latest.json")
_SNAPSHOT_REL = Path("control/review_snapshot/v5r_decision_cockpit_snapshot.json")
_BRIDGE_POLICY_REL = Path("control/decision_cockpit_r3_bridge.json")


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


def kickoff_decision_cockpit_update(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """
    Antizipierter Update-Prozess (control/decision_cockpit_r3_bridge.json):
    1. Serienreife reparieren (Hub, Stack, Ollama, Wachstum)
    2. R3-Checkliste A–G scannen
    3. Decision-Cockpit-Snapshot aus Live-Quellen
    4. König-Bridge + Netzwerk-Puls (keine V1–V4-Phasenausführung)
    """
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    def _step(step_id: str, label_de: str, fn) -> None:
        try:
            result = fn()
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else bool(result)
            steps.append({"id": step_id, "label_de": label_de, "ok": ok, "detail": result})
        except Exception as exc:
            steps.append({"id": step_id, "label_de": label_de, "ok": False, "error_de": str(exc)[:160]})

    _step(
        "series_repair",
        "Serienreife reparieren",
        lambda: __import__(
            "analytics.series_readiness", fromlist=["apply_series_readiness_repair"]
        ).apply_series_readiness_repair(root),
    )

    _step(
        "r3_checklist",
        "R3 Betriebs-Checkliste",
        lambda: __import__(
            "analytics.r3_operational_checklist", fromlist=["scan_operational_checklist"]
        ).scan_operational_checklist(root, persist=True),
    )

    def _refresh_snapshot() -> Dict[str, Any]:
        from aa_decision_cockpit_readonly_snapshot import refresh_live_review_snapshot

        path = refresh_live_review_snapshot(root)
        snap = _load_json(path)
        return {
            "ok": path.is_file(),
            "path": str(path),
            "build_status": snap.get("build_status"),
            "generated_at_utc": snap.get("generated_at_utc"),
        }

    _step("cockpit_snapshot", "Decision-Cockpit-Snapshot", _refresh_snapshot)

    series = _load_json(root / "evidence/series_readiness_latest.json")
    checklist = _load_json(root / "evidence/r3_operational_checklist_latest.json")
    growth = _load_json(root / "evidence/r3_local_growth_latest.json")
    cycle = _load_json(root / "evidence/r3_trading_cycle_latest.json")
    operator_readiness = _load_json(root / "evidence/r3_operator_readiness_latest.json")
    if not operator_readiness.get("operational_pct"):
        try:
            from analytics.r3_operator_readiness import sync_r3_operator_readiness

            operator_readiness = sync_r3_operator_readiness(root, persist=True)
        except Exception:
            pass
    automation = _load_json(root / "control/vision_automation/automation_state.json")
    bridge_policy = _load_json(root / _BRIDGE_POLICY_REL)

    bridge_de = {
        "policy_ref": str(_BRIDGE_POLICY_REL).replace("\\", "/"),
        "r3_series_ready": bool(series.get("series_ready")),
        "r3_readiness_pct": series.get("readiness_pct"),
        "r3_checklist_ok": bool(checklist.get("checklist_ok")),
        "r3_checklist_items": f"{checklist.get('items_ok')}/{checklist.get('items_total')}",
        "r3_growth_pct": growth.get("growth_pct"),
        "r3_cycle_closed": bool(cycle.get("closed")),
        "r3_operator_pct": operator_readiness.get("operational_pct"),
        "r3_operator_ok": bool(operator_readiness.get("operational_ok")),
        "r3_operator_ref": "evidence/r3_operator_readiness_latest.json",
        "r3_operator_surface_de": operator_readiness.get("surface_de") or "http://127.0.0.1:17890/desktop",
        "r3_surface_de": series.get("local_surface_de") or "http://127.0.0.1:17890/r3",
        "vision_executed_phase": automation.get("current_executed_phase"),
        "vision_execution_status": automation.get("execution_status"),
        "vision_next_authorized": automation.get("next_phase_authorized"),
        "forbidden_de": bridge_policy.get("forbidden_de") or [],
        "note_de": bridge_policy.get("mission_de")
        or (
            "R3-Web operativ — EXE-VISION V1–V4 bleibt extern review-gated; "
            "Update synchronisiert Snapshot + König-Remaster, keine Phasenausführung."
        ),
    }

    king_tasks = [
        "bash tools/king_ops.sh gui-rebuild — R3 Exec-Spiegel ↔ Decision Cockpit Optik",
        "Lies control/decision_cockpit_r3_bridge.json und evidence/decision_cockpit_update_latest.json",
        "pytest tests/test_gui_remaster_2026_policy.py -q vor finish",
    ]
    bridge_push: Dict[str, Any] = {"ok": False}
    try:
        from analytics.alpha_model_cursor_bridge import push_cursor_to_king

        bridge_push = push_cursor_to_king(
            root,
            summary_de="Decision-Cockpit-Update — R3-Web an Vision-Kette angebunden",
            verified_facts_de=[
                f"Serienreife {series.get('readiness_pct')}% — ready={series.get('series_ready')}",
                f"Checkliste {checklist.get('items_ok')}/{checklist.get('items_total')} — ok={checklist.get('checklist_ok')}",
                f"R3 Wachstum {growth.get('growth_pct')}% — Kreislauf closed={cycle.get('closed')}",
                f"Operator-Readiness {operator_readiness.get('operational_pct')}% — /r3 ohne Prozent-Anzeige",
                f"Vision: {automation.get('current_executed_phase')}",
                f"Snapshot: {_SNAPSHOT_REL.as_posix()}",
            ],
            tasks_for_king_de=king_tasks,
            source="decision_cockpit_update",
        )
    except Exception as exc:
        bridge_push = {"ok": False, "error_de": str(exc)[:120]}

    _step("king_bridge", "König-Bridge", lambda: bridge_push)

    pulse: Dict[str, Any] = {"ok": False}
    try:
        from analytics.king_network import sync_network_pulse

        pulse = sync_network_pulse(root, source_node="decision_cockpit_update")
    except Exception as exc:
        pulse = {"ok": False, "error_de": str(exc)[:120]}

    _step("network_pulse", "Netzwerk-Takt", lambda: pulse)

    steps_ok = sum(1 for s in steps if s.get("ok"))
    series_ready = bool(series.get("series_ready"))
    checklist_ok = bool(checklist.get("checklist_ok"))
    all_steps_ok = steps_ok == len(steps)
    blockers: List[str] = []
    if not series_ready:
        blockers.extend(series.get("blockers_de") or ["Serienreife"])
    if not checklist_ok:
        blockers.extend(checklist.get("blockers_de") or ["R3-Checkliste"])
    if not all_steps_ok:
        blockers.append("Update-Schritte unvollständig")

    update_ok = series_ready and checklist_ok and all_steps_ok

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": update_ok,
        "series_ready": series_ready,
        "checklist_ok": checklist_ok,
        "readiness_pct": series.get("readiness_pct"),
        "steps_ok": steps_ok,
        "steps_total": len(steps),
        "steps": steps,
        "blockers_de": blockers,
        "r3_vision_bridge_de": bridge_de,
        "bridge_policy_ref": str(_BRIDGE_POLICY_REL).replace("\\", "/"),
        "cockpit_snapshot_ref": str(_SNAPSHOT_REL).replace("\\", "/"),
        "checklist_ref": "evidence/r3_operational_checklist_latest.json",
        "vision_program_ref": "VISION_DECISION_COCKPIT_EXECPLAN.md",
        "gui_rebuild_de": "bash tools/king_ops.sh gui-rebuild",
        "headline_de": (
            "Decision Cockpit Update OK — Serienreife + Checkliste + Snapshot"
            if update_ok
            else f"Decision Cockpit Update — Blocker: {', '.join(blockers[:2])}"
        ),
        "next_de": (
            "bash tools/king_ops.sh gui-rebuild — König 32B baut EXE/R3-Optik"
            if update_ok
            else "bash tools/king_ops.sh cockpit-update --repair"
            if not series_ready
            else "bash tools/king_ops.sh r3-checklist --repair"
        ),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
        try:
            from analytics.decision_cockpit_update_lessons import record_update_lessons

            lessons = record_update_lessons(root, trigger_de="cockpit-update", update_doc=doc)
            doc["lessons_ref"] = "evidence/decision_cockpit_update_lessons_latest.json"
            doc["lessons_headline_de"] = lessons.get("headline_de")
            atomic_write_json(root / _EVIDENCE_REL, doc)
        except Exception:
            pass
    return doc
