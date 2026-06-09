"""Lessons aus Decision-Cockpit-Update — Evidence für König/Operator."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/decision_cockpit_update_lessons_latest.json")
_UPDATE_EVIDENCE_REL = Path("evidence/decision_cockpit_update_latest.json")
_BRIDGE_POLICY_REL = Path("control/decision_cockpit_r3_bridge.json")

# Aus Gutachter-Prüfung + erstem cockpit-update-Lauf (2026-06-08) abgeleitet
_KNOWN_LESSONS_DE: List[Dict[str, str]] = [
    {
        "id": "series_blocker_not_r3_broken",
        "lesson_de": "Serienreife 86 % bedeutet nicht „R3 kaputt“ — Blocker war king_local (Ollama offline), Stack/Mirror waren OK.",
        "action_de": "bash tools/king_ops.sh series-ready --repair startet Ollama via ensure_ollama_running",
    },
    {
        "id": "no_formal_lhp",
        "lesson_de": "Kein formales Lasten-/Pflichtenheft im Repo — SOLL aus Policies + control/r3_operational_checklist.json ableiten.",
        "action_de": "bash tools/king_ops.sh r3-checklist — maschinenlesbarer Scan",
    },
    {
        "id": "id_consistency",
        "lesson_de": "Checklisten-IDs müssen Kreislauf-IDs entsprechen (orders, nicht orders_gate).",
        "action_de": "Trading-Kreislauf evidence/r3_trading_cycle_latest.json als Referenz",
    },
    {
        "id": "next_de_list_bug",
        "lesson_de": "next_de mit str(list)[0] erzeugte „— [“ statt Operator-Befehl.",
        "action_de": "Erstes Element aus operator_commands_de — nie str(list) indexieren",
    },
    {
        "id": "latency_is_poll_not_cpu",
        "lesson_de": "Spürbare UI-Latenz kam von mirror_poll_ms (60 s), nicht von Mirror-Render (<15 ms).",
        "action_de": "control/r3_runtime_profile.json — mirror_poll_ms 30000 ohne Safety zu ändern",
    },
    {
        "id": "sell_partial_not_fail",
        "lesson_de": "sell_count=0 ist PARTIAL (kein Reeval-Verkauf), kein FAIL — UI+Merge+Tests sind vorhanden.",
        "action_de": "Reeval-Fixture oder echtes Portfolio mit SELL für Live-Nachweis",
    },
    {
        "id": "vision_not_r3_scope",
        "lesson_de": "VISION V1–V4 EXE-Phasen ≠ R3-Web — Brücke synchronisiert Snapshot + König-Remaster, führt keine Phase aus.",
        "action_de": "control/decision_cockpit_r3_bridge.json · vision_next_authorized bleibt false",
    },
    {
        "id": "update_ok_three_gates",
        "lesson_de": "cockpit-update ok nur wenn series_ready UND checklist_ok UND alle Update-Schritte grün.",
        "action_de": "bash tools/king_ops.sh cockpit-update — ein Befehl, fünf Schritte",
    },
    {
        "id": "crlf_shell_scripts",
        "lesson_de": "CRLF in .sh bricht set -euo pipefail (Windows-Editoren).",
        "action_de": "sed -i 's/\\r$//' tools/*.sh vor erstem Aufruf",
    },
    {
        "id": "king_builds_not_cursor",
        "lesson_de": "GUI-Remaster und EXE-Optik — König 32B build-kernel, Cursor nur Bridge/Vasall.",
        "action_de": "bash tools/king_ops.sh gui-rebuild",
    },
]


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


def _infer_lessons(root: Path, update_doc: Dict[str, Any]) -> List[str]:
    """Aktuelle Beobachtungen aus Evidence — ergänzt bekannte Lessons."""
    root = Path(root)
    inferred: List[str] = []

    series = _load_json(root / "evidence/series_readiness_latest.json")
    checklist = _load_json(root / "evidence/r3_operational_checklist_latest.json")
    growth = _load_json(root / "evidence/r3_local_growth_latest.json")

    if series.get("series_ready") and (series.get("warnings_de") or []):
        inferred.append(
            f"Serienreif trotz Warnung: {', '.join((series.get('warnings_de') or [])[:2])} "
            "— kein harter Blocker"
        )

    partial = checklist.get("partial_de") or []
    if partial:
        inferred.append(f"Checkliste PARTIAL: {', '.join(partial[:2])} — dokumentieren, nicht als FAIL werten")

    caps = growth.get("capabilities") or []
    king = next((c for c in caps if c.get("id") == "king_local"), None)
    if king and not king.get("ok"):
        inferred.append("king_local rot — Ollama vor gui-rebuild/start König sicherstellen")

    repair_steps = []
    for step in (update_doc.get("steps") or []):
        if step.get("id") == "series_repair":
            repair_steps = ((step.get("detail") or {}).get("steps") or [])
    ollama_step = next((s for s in repair_steps if s.get("id") == "ollama"), None)
    if ollama_step and (ollama_step.get("detail") or {}).get("started"):
        inferred.append("Ollama wurde im Repair gestartet — king_local vorher offline")

    if not update_doc.get("ok"):
        blockers = update_doc.get("blockers_de") or []
        if blockers:
            inferred.append(f"Letzter Update-Blocker: {', '.join(blockers[:2])}")

    return inferred


def record_update_lessons(
    root: Path,
    *,
    trigger_de: str = "",
    update_doc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Schreibt Lessons aus Update-Prozess + aktuellem Evidence-Stand."""
    root = Path(root)
    update_doc = update_doc if update_doc is not None else _load_json(root / _UPDATE_EVIDENCE_REL)

    inferred = _infer_lessons(root, update_doc)
    series = _load_json(root / "evidence/series_readiness_latest.json")
    checklist = _load_json(root / "evidence/r3_operational_checklist_latest.json")

    doc: Dict[str, Any] = {
        "ok": True,
        "schema_version": 1,
        "recorded_at_utc": _utc_now(),
        "trigger_de": trigger_de or "cockpit-update",
        "lessons_de": _KNOWN_LESSONS_DE,
        "inferred_de": inferred,
        "fixes_de": [
            "bash tools/king_ops.sh series-ready --repair",
            "bash tools/king_ops.sh r3-checklist",
            "bash tools/king_ops.sh cockpit-update",
            "bash tools/king_ops.sh gui-rebuild",
        ],
        "policy_ref": str(_BRIDGE_POLICY_REL).replace("\\", "/"),
        "update_ref": str(_UPDATE_EVIDENCE_REL).replace("\\", "/"),
        "snapshot_de": {
            "series_ready": series.get("series_ready"),
            "readiness_pct": series.get("readiness_pct"),
            "checklist_ok": checklist.get("checklist_ok"),
            "items": f"{checklist.get('items_ok')}/{checklist.get('items_total')}",
            "update_ok": update_doc.get("ok"),
        },
        "headline_de": (
            f"{len(_KNOWN_LESSONS_DE)} dokumentierte Lessons · "
            f"{len(inferred)} aktuelle Beobachtung(en)"
        ),
        "operator_de": "Lessons bei jedem cockpit-update aktualisiert — König liest evidence/decision_cockpit_update_lessons_latest.json",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
