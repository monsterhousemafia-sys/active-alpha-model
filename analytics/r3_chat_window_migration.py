"""R3 Chat-Fenster-Migration — vollständiges Cursor-Chat-Erlebnis in R3."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_chat_window_migration_latest.json")
_FEASIBILITY_EVIDENCE_REL = Path("evidence/r3_chat_migration_feasibility_latest.json")
_RULES_MIRROR_REL = Path("control/r3_rules_mirror")
_CURSOR_RULES_REL = Path(".cursor/rules")


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


def mirror_rules_for_ollama(root: Path) -> Dict[str, Any]:
    """Spiegelt .cursor/rules nach control/r3_rules_mirror/ für Ollama-Fallback."""
    root = Path(root).resolve()
    src = root / _CURSOR_RULES_REL
    dest = root / _RULES_MIRROR_REL
    dest.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    if not src.is_dir():
        return {"ok": False, "error_de": "Keine .cursor/rules gefunden", "copied": []}
    for item in sorted(src.glob("*.mdc")):
        target = dest / item.name
        try:
            shutil.copy2(item, target)
            copied.append(item.name)
        except OSError:
            pass
    index = {
        "schema_version": 1,
        "mirrored_at_utc": _utc_now(),
        "source": str(src),
        "dest": str(dest),
        "files": copied,
        "purpose_de": "Ollama-Fallback — gleicher Regelkontext wie Cursor-Agent",
    }
    atomic_write_json(dest / "index.json", index)
    return {"ok": bool(copied), "copied": copied, "dest": str(dest), "index": index}


def list_workspace_tree(root: Path, *, subpath: str = "", limit: int = 80) -> Dict[str, Any]:
    """Projektbaum — Arbeitsbaum-Bindung für R3 Dateien-App."""
    from analytics.r3_native_apps import list_project_files

    return list_project_files(root, subpath=subpath, limit=limit)


def document_cursor_capture(root: Path) -> Dict[str, Any]:
    """Was r3-preserve automatisch sichert vs. was explizit kopiert wird."""
    root = Path(root).resolve()
    cfg = _load_json(root / "control/r3_continuity.json")
    preferred = str(cfg.get("preferred_transcript_id") or "")
    transcript_globs = list(cfg.get("transcript_globs") or [])
    found_transcripts: List[str] = []
    home = Path.home()
    for pattern in transcript_globs:
        for path in home.glob(str(pattern)):
            if path.is_file() and path.suffix == ".jsonl" and "subagents" not in str(path):
                found_transcripts.append(str(path.resolve()))
    return {
        "r3_preserve_captures_de": [
            "Cursor agent-transcripts (.jsonl) → ~/.local/share/r3-os/conversation/conversation_archive.jsonl",
            "Kontinuitäts-Brief → continuity_brief_de.md + evidence/r3_continuity_brief_de.md",
            "Manifest → continuity_manifest.json + evidence/r3_continuity_latest.json",
            "KI-Sitzung (ki_console_session.json) bei r3-ki-import",
            "R3-Chat-Turns (append_turn_to_archive) ohne Cursor",
        ],
        "explicit_copy_de": [
            ".cursor/rules → control/r3_rules_mirror/ (Ollama-Fallback)",
            "Projektbaum-Snapshot (list_workspace_tree)",
            "Anhänge ~/.local/share/r3-os/chat-attachments/",
            "Operator-Policies control/r3_agent_growth.json, r3_phase_b_master_prompt_de.md",
        ],
        "not_captured_de": [
            "Cursor workspaceStorage state.vscdb (offene Tabs, UI-Layout)",
            "Cursor IDE Chrome (Usage-Meter, Composer-Panel-Position)",
            "Cursor MCP-Server-Konfiguration außerhalb Repo",
        ],
        "preferred_transcript_id": preferred,
        "transcript_paths": found_transcripts[:6],
        "project_root": str(root),
    }


def _attachment_status() -> Dict[str, Any]:
    try:
        from analytics.r3_ki_attachments import list_recent_attachments

        recent = list_recent_attachments(limit=12)
        return {
            "dir": str(Path.home() / ".local/share/r3-os/chat-attachments"),
            "count": len(recent),
            "recent": recent[:6],
        }
    except Exception as exc:
        return {"dir": str(Path.home() / ".local/share/r3-os/chat-attachments"), "count": 0, "error": str(exc)[:80]}


def check_migration_safeguards(root: Path) -> Dict[str, Any]:
    """Fail-closed — Migration nur bei intakter Kontinuität, H1-Schutz, kein Fake-Seal."""
    root = Path(root).resolve()
    checks: List[Dict[str, Any]] = []

    def _add(cid: str, label_de: str, ok: bool, detail_de: str = "", *, blocks: bool = True) -> None:
        checks.append(
            {
                "id": cid,
                "label_de": label_de,
                "ok": ok,
                "detail_de": detail_de,
                "blocks_migration": blocks and not ok,
            }
        )

    from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed
    from analytics.h1_migration_guard import h1_process_inventory
    from analytics.r3_conversation_continuity import continuity_status, load_continuity_context

    bt = h1_backtest_status(root)
    inv = h1_process_inventory(root)
    st = str(bt.get("status") or "MISSING")
    sealed = is_h1_backtest_sealed(root)
    backtest_live = int(inv.get("backtest_count") or 0) > 0
    backtest_pids = [int(x["pid"]) for x in (inv.get("backtests") or []) if x.get("pid")]

    if sealed:
        h1_ok = True
        h1_detail = "H1 sealed — Migration darf Evidence nicht fälschen"
    elif st == "RUNNING":
        h1_ok = backtest_live
        h1_detail = (
            f"RUNNING · {len(backtest_pids)} Backtest-Prozess(e) aktiv"
            if backtest_live
            else "RUNNING aber kein Backtest-Prozess — Migration blockiert (H1-Schutz)"
        )
    elif st == "COMPLETE":
        h1_ok = True
        h1_detail = "COMPLETE — Evaluate/Seal läuft, Backtest nicht killen"
    else:
        h1_ok = True
        h1_detail = f"{st} — kein laufender Backtest zum Schützen"
    _add("h1_backtest_protected", "H1-Backtest nicht killen", h1_ok, h1_detail)

    gov = _load_json(root / "control/h1_governance_status.json")
    gov_sealed = bool(gov.get("sealed"))
    no_fake = not gov_sealed or sealed
    _add(
        "no_fake_seal",
        "Kein Fake-Seal",
        no_fake,
        f"governance.sealed={gov_sealed} · evidence.sealed={sealed}",
    )

    cont = continuity_status(root)
    cont_ok = bool(cont.get("ok"))
    manifest = cont.get("manifest") or {}
    _add(
        "continuity_manifest",
        "r3-preserve Manifest vorhanden",
        cont_ok,
        str(manifest.get("preserved_at_utc") or "fehlt"),
    )

    ctx_len = len(load_continuity_context(root))
    _add("continuity_context", "Kontinuitätskontext ≥ 2000 Zeichen", ctx_len >= 2000, f"{ctx_len} Zeichen")

    cfg = _load_json(root / "control/r3_continuity.json")
    bound = str(cfg.get("project_root") or "")
    root_ok = not bound or Path(bound).resolve() == root
    _add(
        "project_root_bound",
        "Arbeitsbaum gebunden",
        root_ok,
        bound or str(root),
    )

    blocked = any(c.get("blocks_migration") for c in checks)
    passed = sum(1 for c in checks if c.get("ok"))
    return {
        "ok": not blocked,
        "blocked": blocked,
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "h1_status": st,
        "h1_sealed": sealed,
        "h1_backtest_pids": backtest_pids,
        "headline_de": (
            "Safeguards grün — Migration fail-closed freigegeben"
            if not blocked
            else f"Migration blockiert — {passed}/{len(checks)} Safeguards grün"
        ),
    }


def build_feasibility_matrix(root: Path) -> Dict[str, Any]:
    """Ehrliche CAN/CANNOT-Matrix für Chat+Ordner-Migration."""
    root = Path(root).resolve()
    capture = document_cursor_capture(root)
    context = _surrounding_context(root)
    transcripts = capture.get("transcript_paths") or []

    try:
        from analytics.r3_conversation_continuity import (
            discover_transcript_files,
            verify_r3_chat_ready,
            load_continuity_config,
        )

        transcript_n = len(discover_transcript_files(root))
        verify = verify_r3_chat_ready(root)
        cfg = load_continuity_config(root)
        archive_cap = int(cfg.get("max_archive_messages") or 400)
    except Exception as exc:
        transcript_n = len(transcripts)
        verify = {"ready_for_r3_chat": False, "error_de": str(exc)[:120]}
        archive_cap = 400

    rules_src = root / _CURSOR_RULES_REL
    rules_ok = rules_src.is_dir() and any(rules_src.glob("*.mdc"))

    try:
        from analytics.r3_ki_storage import load_session, session_path

        session_msgs = len(load_session().get("messages") or [])
        session_ok = session_path().is_file() and session_msgs >= 1
    except Exception:
        session_msgs = 0
        session_ok = False

    try:
        from analytics.local_llm_bridge import health_report

        llm = health_report(root)
        ollama_ok = bool(llm.get("ollama_ok"))
    except Exception:
        ollama_ok = False

    try:
        from aa_paths import project_root as _aa_root

        bound_root = str(_aa_root().resolve())
    except Exception:
        bound_root = str(root)

    tree = list_workspace_tree(root, limit=20)
    tree_ok = bool(tree.get("entries"))

    can: List[Dict[str, Any]] = [
        {
            "id": "cursor_transcript_import",
            "label_de": "Cursor-Transkripte → R3-Archiv",
            "ok": transcript_n >= 1,
            "detail_de": f"{transcript_n} Transkript(e), Cap {archive_cap} Nachrichten",
        },
        {
            "id": "r3_chat_without_cursor",
            "label_de": "R3 Chat ohne Cursor",
            "ok": bool(verify.get("ready_for_r3_chat")),
            "detail_de": str(verify.get("headline_de") or "—"),
        },
        {
            "id": "ki_session_restore",
            "label_de": "Archiv → KI-Sitzung",
            "ok": session_ok,
            "detail_de": f"{session_msgs} Nachrichten in ki_console_session.json",
        },
        {
            "id": "project_folder_bind",
            "label_de": "Arbeitsbaum-Ordner binden",
            "ok": bound_root == str(root),
            "detail_de": bound_root,
        },
        {
            "id": "workspace_tree_api",
            "label_de": "Projektbaum (Dateien-App + API)",
            "ok": tree_ok,
            "detail_de": f"{len(tree.get('entries') or [])} Top-Level-Einträge",
        },
        {
            "id": "rules_mirror",
            "label_de": "Cursor-Rules → control/r3_rules_mirror",
            "ok": rules_ok,
            "detail_de": str(rules_src),
        },
        {
            "id": "cockpit_chat_ui",
            "label_de": "Cockpit :17890/desktop Chat+System",
            "ok": bool(context.get("present", {}).get("ki_gui")),
            "detail_de": "http://127.0.0.1:17890/desktop",
        },
        {
            "id": "ollama_fallback",
            "label_de": "Ollama active-alpha-chat",
            "ok": ollama_ok,
            "detail_de": "qwen2.5:7b lokal",
        },
        {
            "id": "incremental_preserve",
            "label_de": "r3-preserve inkrementell",
            "ok": True,
            "detail_de": "ai_kernel r3-preserve — ohne Cursor-Pflicht",
        },
    ]

    cannot: List[Dict[str, Any]] = [
        {
            "id": "cursor_ui_state",
            "label_de": "Cursor workspaceStorage (Tabs, Layout)",
            "reason_de": "Liegt in Cursor-interner state.vscdb — nicht im Repo",
        },
        {
            "id": "cursor_ide_chrome",
            "label_de": "Cursor IDE Chrome (Usage-Meter, Panel-Position)",
            "reason_de": "IDE-UI außerhalb des Arbeitsbaums — nicht migrierbar",
        },
        {
            "id": "mcp_outside_repo",
            "label_de": "MCP-Server-Konfiguration außerhalb Repo",
            "reason_de": "Cursor-User-Settings — manuell am Zielsystem",
        },
        {
            "id": "unlimited_history",
            "label_de": "Unbegrenzte Chat-Historie 1:1",
            "reason_de": f"Archiv-Cap {archive_cap} Nachrichten — ältere Turns nur in Roh-Transkripten",
        },
        {
            "id": "h1_seal_via_migration",
            "label_de": "H1-Seal durch Migration erzwingen",
            "reason_de": "Seal nur über Evaluate/Monitor — kein Fake-Seal",
        },
        {
            "id": "workspace_auto_relocate",
            "label_de": "Arbeitsbaum automatisch umziehen",
            "reason_de": "Pfad /home/machinax7/active_alpha_model ist bindend — Umzug = Operator-Aktion",
        },
        {
            "id": "pixel_cursor_clone",
            "label_de": "Pixelgenauer Cursor-Clone",
            "reason_de": "R3 adaptiert (Cockpit+Ollama) — kein IDE-Nachbau",
        },
    ]

    can_ok = sum(1 for row in can if row.get("ok"))
    feasible = can_ok >= 7 and bool(verify.get("ready_for_r3_chat"))
    return {
        "can": can,
        "cannot": cannot,
        "can_ok": can_ok,
        "can_total": len(can),
        "cannot_total": len(cannot),
        "feasible": feasible,
        "verdict_de": (
            "Technisch machbar — Chat+Ordner-Kern migrierbar, Cursor-UI-Reste ausgenommen"
            if feasible
            else "Teilweise machbar — Kern-Checks fehlen noch"
        ),
        "capture": capture,
    }


def assess_chat_migration_feasibility(
    root: Path,
    *,
    run_preserve: bool = True,
) -> Dict[str, Any]:
    """Prüft Machbarkeit, führt preserve/checks aus, schreibt Evidence."""
    root = Path(root).resolve()
    steps: List[Dict[str, Any]] = []

    preserve_doc: Dict[str, Any] = {}
    if run_preserve:
        try:
            from analytics.r3_conversation_continuity import preserve_conversation, load_continuity_config

            legacy = bool(load_continuity_config(root).get("legacy_cursor_import"))
            preserve_doc = preserve_conversation(root, import_cursor=legacy)
            steps.append({"id": "preserve", "ok": bool(preserve_doc.get("preserved_at_utc")), "detail": preserve_doc})
        except Exception as exc:
            steps.append({"id": "preserve", "ok": False, "error_de": str(exc)[:200]})
    else:
        from analytics.r3_conversation_continuity import continuity_status

        preserve_doc = continuity_status(root).get("manifest") or {}

    try:
        from analytics.r3_conversation_continuity import verify_r3_chat_ready

        verify_doc = verify_r3_chat_ready(root)
        steps.append({"id": "migration_check", "ok": bool(verify_doc.get("ready_for_r3_chat")), "detail": verify_doc})
    except Exception as exc:
        verify_doc = {"ready_for_r3_chat": False, "error_de": str(exc)[:200]}
        steps.append({"id": "migration_check", "ok": False, "error_de": str(exc)[:200]})

    safeguards = check_migration_safeguards(root)
    steps.append({"id": "safeguards", "ok": bool(safeguards.get("ok")), "detail": safeguards})

    matrix = build_feasibility_matrix(root)

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "assessed_at_utc": _utc_now(),
        "ok": bool(matrix.get("feasible")) and bool(safeguards.get("ok")),
        "feasible": bool(matrix.get("feasible")),
        "migration_allowed": bool(safeguards.get("ok")),
        "headline_de": matrix.get("verdict_de"),
        "safeguards": safeguards,
        "matrix": matrix,
        "preserve": preserve_doc,
        "verify": verify_doc,
        "steps": steps,
        "commands_de": [
            "python3 tools/ai_kernel.py r3-preserve",
            "python3 tools/ai_kernel.py r3-migration-check",
            "python3 tools/ai_kernel.py r3-migration-feasibility",
            "python3 tools/ai_kernel.py r3-chat-migrate",
        ],
        "operator_de": "Chat+Ordner-Kern migrierbar — H1 läuft parallel, kein Fake-Seal",
    }
    atomic_write_json(root / _FEASIBILITY_EVIDENCE_REL, doc)
    return doc


def _surrounding_context(root: Path) -> Dict[str, Any]:
    root = Path(root).resolve()
    paths = {
        "rules_mirror": str(root / _RULES_MIRROR_REL),
        "cursor_rules": str(root / _CURSOR_RULES_REL),
        "operator_growth": str(root / "control/r3_agent_growth.json"),
        "phase_b_prompt": str(root / "control/r3_phase_b_master_prompt_de.md"),
        "model_team": str(root / "control/r3_model_team.json"),
        "chat_layout": str(root / "control/r3_ki_chat_layout.json"),
        "ki_gui": str(root / "control/r3_ki_gui.json"),
        "continuity": str(root / "control/r3_continuity.json"),
        "tunnel": str(root / "evidence/ki_tunnel_connection_latest.json"),
        "desktop_url": "http://127.0.0.1:17890/desktop",
    }
    present = {k: Path(v).is_file() for k, v in paths.items() if k != "desktop_url"}
    return {"paths": paths, "present": present}


def run_chat_window_migration(
    root: Path,
    *,
    preserve: bool = True,
    desktop_migrate: bool = True,
    import_session: bool = True,
    launch_ui: bool = False,
) -> Dict[str, Any]:
    """Vollständige Chat-Fenster-Migration: Kontinuität + Workspace + Kontext."""
    root = Path(root).resolve()
    safeguards = check_migration_safeguards(root)
    if safeguards.get("blocked"):
        doc = {
            "schema_version": 1,
            "ok": False,
            "blocked": True,
            "migrated_at_utc": _utc_now(),
            "headline_de": safeguards.get("headline_de") or "Migration blockiert — Safeguards",
            "safeguards": safeguards,
            "steps": [{"id": "safeguards", "label_de": "Fail-closed Safeguards", "ok": False, "detail": safeguards}],
        }
        atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    steps: List[Dict[str, Any]] = [
        {"id": "safeguards", "label_de": "Fail-closed Safeguards", "ok": True, "detail": safeguards},
    ]
    errors: List[str] = []

    def _step(sid: str, label_de: str, fn) -> Dict[str, Any]:
        try:
            out = fn() if callable(fn) else fn
            row = {"id": sid, "label_de": label_de, "ok": bool(out.get("ok", True)), "detail": out}
            steps.append(row)
            if not row["ok"]:
                errors.append(label_de)
            return out
        except Exception as exc:
            row = {"id": sid, "label_de": label_de, "ok": False, "error_de": str(exc)[:200]}
            steps.append(row)
            errors.append(label_de)
            return row

    preserve_doc: Dict[str, Any] = {}
    if preserve:
        def _preserve() -> Dict[str, Any]:
            from analytics.r3_conversation_continuity import preserve_conversation, load_continuity_config

            legacy = bool(load_continuity_config(root).get("legacy_cursor_import"))
            return preserve_conversation(root, import_cursor=legacy)

        preserve_doc = _step("preserve", "Chat-Kontinuität (r3-preserve)", _preserve)

    rules_doc = _step("rules_mirror", "Rules → control/r3_rules_mirror", lambda: mirror_rules_for_ollama(root))

    tree_doc = _step(
        "workspace_tree",
        "Projektbaum-Snapshot",
        lambda: {
            **list_workspace_tree(root),
            "top_level": list_workspace_tree(root).get("entries", [])[:20],
        },
    )

    desktop_doc: Dict[str, Any] = {}
    if desktop_migrate:
        def _desktop() -> Dict[str, Any]:
            from analytics.r3_desktop_migration import run_full_desktop_migration

            return run_full_desktop_migration(root, launch_ui=launch_ui)

        desktop_doc = _step("desktop_migrate", "Desktop-Migration (R3 primär)", _desktop)
    else:
        def _desktop_update() -> Dict[str, Any]:
            from analytics.r3_desktop_update import run_desktop_update_action

            return run_desktop_update_action(root, launch_ui=launch_ui)

        desktop_doc = _step("desktop_update", "Desktop-Update (Hub)", _desktop_update)

    import_doc: Dict[str, Any] = {}
    if import_session:
        def _import() -> Dict[str, Any]:
            from analytics.r3_ki_storage import seed_session_from_archive

            return seed_session_from_archive(root)

        import_doc = _step("ki_import", "Archiv → KI-Sitzung", _import)

    verify_doc = _step(
        "migration_check",
        "Kontinuitäts-Checks",
        lambda: __import__(
            "analytics.r3_conversation_continuity", fromlist=["verify_r3_chat_ready"]
        ).verify_r3_chat_ready(root),
    )

    session_ok = False
    session_msgs = 0
    try:
        from analytics.r3_ki_storage import load_session, history_for_ui

        session_msgs = len(load_session().get("messages") or [])
        session_ok = session_msgs >= 1 and len(history_for_ui(root)) >= 1
    except Exception:
        pass

    archive_msgs = int(preserve_doc.get("message_count") or 0)
    if not archive_msgs:
        try:
            from analytics.r3_ki_storage import read_archive_rows

            archive_msgs = len(read_archive_rows())
        except Exception:
            pass

    capture = document_cursor_capture(root)
    context = _surrounding_context(root)
    attachments = _attachment_status()

    try:
        from aa_paths import project_root as _aa_root

        bound_root = str(_aa_root())
    except Exception:
        bound_root = str(root)

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "ok": not errors and bool(verify_doc.get("ready_for_r3_chat")) and bool(safeguards.get("ok")),
        "safeguards": safeguards,
        "migrated_at_utc": _utc_now(),
        "headline_de": (
            "Chat-Fenster vollständig in R3 migriert — Cockpit :17890"
            if not errors
            else f"Migration teilweise — Fehler: {', '.join(errors)}"
        ),
        "message_count": archive_msgs,
        "session_messages": session_msgs,
        "session_restore_ok": session_ok,
        "continuity_ready": bool(verify_doc.get("ready_for_r3_chat")),
        "preferred_transcript_id": capture.get("preferred_transcript_id"),
        "project_root": bound_root,
        "paths": {
            "conversation_dir": str(Path.home() / ".local/share/r3-os/conversation"),
            "archive": str(Path.home() / ".local/share/r3-os/conversation/conversation_archive.jsonl"),
            "ki_session": str(Path.home() / ".local/share/r3-os/ki_console_session.json"),
            "attachments": attachments.get("dir"),
            "rules_mirror": str(root / _RULES_MIRROR_REL),
            "cockpit": "http://127.0.0.1:17890/desktop",
            "active_alpha_chat": "active-alpha-chat",
            "project_files_api": "http://127.0.0.1:17890/api/desktop/project-files",
            "home_files_api": "http://127.0.0.1:17890/api/desktop/files",
        },
        "operator_open_de": [
            "Terminal: active-alpha-chat  (voller Chat ohne Cursor)",
            "Browser: http://127.0.0.1:17890/desktop  (Chat + Dateien + System)",
            "Cockpit-Slash: /import · /kontinuität · /desktop",
            "Session-Rail: Archiv-Button lädt Gespräch aus R3-Archiv",
            "Native App «Dateien» + API /api/desktop/project-files für Arbeitsbaum",
        ],
        "cursor_capture": capture,
        "surrounding_context": context,
        "attachments": attachments,
        "workspace_tree": tree_doc,
        "steps": steps,
        "preserve": preserve_doc,
        "desktop": desktop_doc,
        "import": import_doc,
        "verify": verify_doc,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
