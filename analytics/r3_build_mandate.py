"""R3 Bau-Mandate für König 32B — effizient, Evidence-first, post-build Abgleich."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_local_build_mandate_latest.json")
_POLICY_REL = Path("control/r3_runtime_upgrade_catalog.json")


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


def build_r3_local_mandate(root: Path, *, topic: str = "") -> Dict[str, Any]:
    """Effizientes Bau-Mandat aus R3-Laufzeitstand — für build-kernel / king_32b_r3_build.sh."""
    root = Path(root)
    topic = str(topic or "").strip().lower()

    try:
        from analytics.r3_runtime_upgrade import align_r3_surface, build_upgrade_status, load_runtime_profile

        profile = load_runtime_profile(root)
        upgrade = build_upgrade_status(root)
        align_r3_surface(root, scan_upgrades=True, warm_cache=False, persist=True)
    except Exception:
        profile = {}
        upgrade = {}

    pending = upgrade.get("pending") or {}
    has_pending = bool(upgrade.get("has_pending"))
    stack = _load_json(root / "evidence/stack_integrity_latest.json")

    steps: List[str] = [
        "Evidence lesen: evidence/r3_runtime_upgrade_latest.json, control/r3_runtime_profile.json",
        "Code lesen: analytics/r3_mirror_view.py, analytics/r3_runtime_upgrade.py, tools/r3_sync.sh",
        "Nur fehlende R3-Lokal-Anpassungen — kleine Diffs, kein Parallel-Design",
        "Tests: python3 -m pytest tests/test_r3_runtime_upgrade.py tests/test_r3_exec_mirror.py -q",
        "Abgleich: bash tools/r3_sync.sh --repair",
        "finish: Operator bestätigt Laufzeit-Update in http://127.0.0.1:17890/r3 (Übernehmen/Später) — kein Auto-Apply",
    ]
    if has_pending:
        steps.insert(
            2,
            f"Offenes Update: {pending.get('label_de')} — UI-Banner prüfen, Erklärung vollständig",
        )
    if topic in {"gui", "remaster", "oberfläche", "oberflaeche", "sichtbar", "visible"}:
        steps.insert(
            1,
            "GUI: analytics/r3_shell_brand.py design_tokens_css — Orange, r3-stack, einheitliche Abstände",
        )
        steps.insert(
            2,
            "Sichtbar: bash tools/king_ops.sh r3-apply — Cache neu, Operator Strg+Shift+R auf /r3",
        )
    if topic in {"prognosis", "prognose", "t212", "capital", "live_cash"}:
        steps.insert(
            1,
            "Prognose-Pipeline: analytics/r3_prognosis_pipeline.py, r3_t212_prognosis.py (König-Boost, Trust fail-closed)",
        )
        steps.insert(
            2,
            "Mirror /r3: analytics/r3_mirror_view.py _render_prognosis_section + r3_mirror_state prognosis-Block",
        )
        steps.insert(
            3,
            "Bash-Hooks: king_tune prognosis · r3_sync --repair · r3_trading_cycle prognosis-Schritt",
        )
        steps.insert(
            4,
            "Ausführen: bash tools/king_ops.sh t212-trust → prognosis run → r3-apply (nur wenn t212_trusted)",
        )

    mandate_de = (
        "R3 Lokal-Bau — effizient umsetzen (König 32B, nicht Cursor).\n"
        f"Profil aktiv: {profile.get('label_de') or profile.get('profile_id') or '—'}\n"
        f"Stack: {'OK' if stack.get('stack_ok') else 'prüfen'}\n"
        + (
            f"Update-Vorschlag offen: {pending.get('label_de')} — nur Anzeige+Bestätigung, nicht still übernehmen.\n"
            if has_pending
            else "Kein offener Update-Vorschlag — Stabilität und Tests absichern.\n"
        )
        + "Schritte:\n"
        + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    )

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "owner_de": "König 32B (build-kernel)",
        "headline_de": (
            f"Bau-Mandat: {pending.get('label_de')}"
            if has_pending
            else "Bau-Mandat: R3 Lokal abstimmen"
        ),
        "mandate_de": mandate_de,
        "topic": topic or "r3_local",
        "upgrade_pending": has_pending,
        "pending_proposal_id": pending.get("proposal_id"),
        "runtime_profile_id": profile.get("profile_id"),
        "stack_ok": bool(stack.get("stack_ok")),
        "efficient_path_de": "bash tools/king_ops.sh r3-bau",
        "steps_de": steps,
        "tests_de": [
            "tests/test_r3_runtime_upgrade.py",
            "tests/test_r3_exec_mirror.py",
            "tests/test_r3_t212_prognosis.py",
            "tests/test_r3_prognosis_pipeline.py",
        ],
        "post_build_de": "bash tools/r3_sync.sh --repair",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_mandate_context_block(root: Path, mandate_de: str = "") -> str:
    """Kompakter Kontext für build-kernel System-Prompt."""
    root = Path(root)
    doc = _load_json(root / _EVIDENCE_REL)
    if not doc:
        doc = build_r3_local_mandate(root)
    mlow = str(mandate_de or "").lower()
    r3_hit = any(
        k in mlow
        for k in (
            "r3",
            "lokal",
            "mirror",
            "runtime",
            "upgrade",
            "abgleich",
            "sync",
            "remaster",
            "gui",
        )
    )
    if not r3_hit and not doc.get("upgrade_pending"):
        return ""

    lines = [
        "=== R3 LOKAL-BAU (König 32B) ===",
        f"Mandat: {doc.get('headline_de')}",
        f"Profil: {doc.get('runtime_profile_id')}",
        "Regeln: kleine Schritte · pytest vor finish · bash tools/r3_sync.sh --repair am Ende",
        "VERBOTEN: Champion-Wechsel · auto_promote · Orders · stiller Runtime-Apply",
        "Operator-Freigabe: Laufzeit-Update nur via /r3 Banner (Übernehmen/Später)",
    ]
    if doc.get("upgrade_pending"):
        lines.append(f"Offenes Update: {doc.get('pending_proposal_id')} — nicht auto-bestätigen")
    for s in list(doc.get("steps_de") or [])[:6]:
        lines.append(f"• {s}")
    lines.append("=== ENDE R3 BAU ===")
    return "\n".join(lines)


def notify_king_build_handoff(root: Path, doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Evidence: König 32B übernimmt Bau autonom (kein Cursor-Standard)."""
    root = Path(root)
    doc = doc or build_r3_local_mandate(root)
    try:
        from analytics.alpha_model_cursor_bridge import push_cursor_to_king

        return push_cursor_to_king(
            root,
            summary_de=str(doc.get("headline_de") or "R3 Lokal-Bau — 32B übernimmt"),
            verified_facts_de=[
                f"Laufzeitprofil: {doc.get('runtime_profile_id')}",
                f"Stack: {'OK' if doc.get('stack_ok') else 'prüfen'}",
                f"Upgrade offen: {'ja' if doc.get('upgrade_pending') else 'nein'}",
                "Bau-Owner: König 32B autonom — control/king_32b_autonomous_build.json",
                "Cursor: kein Standard-Bau — nur Notfall-Fallback",
            ],
            tasks_for_king_de=[
                "bash tools/king_ops.sh r3-bau",
                "oder /bau R3 Lokal abstimmen (build-kernel)",
                "Nach Bau: r3_sync · Operator /r3 Update bestätigen",
            ],
            source="r3_build_mandate",
        )
    except Exception as exc:
        return {"ok": False, "error_de": str(exc)[:120]}


def post_build_r3_align(root: Path, *, mandate_de: str = "", build_ok: bool = True) -> Dict[str, Any]:
    """Nach erfolgreichem build-kernel: Cache + Stack abstimmen."""
    root = Path(root)
    if not build_ok:
        return {"ok": False, "skipped": True, "reason_de": "Build nicht OK"}

    out: Dict[str, Any] = {"ok": True, "steps": []}
    try:
        from analytics.r3_runtime_upgrade import align_r3_surface

        align = align_r3_surface(root, scan_upgrades=True, warm_cache=True, persist=True)
        out["steps"].append({"step": "align_r3_surface", "ok": bool(align.get("ok"))})
    except Exception as exc:
        out["steps"].append({"step": "align_r3_surface", "ok": False, "error_de": str(exc)[:120]})
        out["ok"] = False

    try:
        proc = subprocess.run(
            ["bash", "tools/r3_sync.sh", "--repair"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        out["steps"].append(
            {
                "step": "r3_sync",
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
            }
        )
        if proc.returncode != 0:
            out["ok"] = False
    except Exception as exc:
        out["steps"].append({"step": "r3_sync", "ok": False, "error_de": str(exc)[:120]})
        out["ok"] = False

    out["confirmation_de"] = (
        "Bau abgeschlossen — bitte http://127.0.0.1:17890/r3 öffnen und Update bestätigen"
        if _load_json(root / "evidence/r3_runtime_upgrade_latest.json").get("pending")
        else "Bau abgeschlossen — R3 abgestimmt"
    )
    atomic_write_json(
        root / Path("evidence/r3_build_post_align_latest.json"),
        {**out, "updated_at_utc": _utc_now(), "mandate_preview": str(mandate_de)[:200]},
    )
    return out
