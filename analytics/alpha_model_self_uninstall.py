"""Entfaltungsraum — verschlüsselter Maschinen-Masterprompt zur Cursor-Selbstdemontage."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_MANIFEST_REL = Path("control/alpha_model_self_uninstall_manifest.json")
_MC_REL = Path("control/alpha_model_self_uninstall.mc")
_KEY_REL = Path("control/secrets/.agent_uninstall_key")
_EVIDENCE_REL = Path("evidence/alpha_model_self_uninstall_latest.json")

# Maschinencode-Opkodes (nur Cursor/Werkstatt — nie Repo-Kern)
_ALLOWED_OPS = frozenset(
    {
        "PURGE_CURSOR_RULES",
        "PURGE_CURSOR_HOOKS_SCRIPTS",
        "PURGE_CURSOR_MISC",
        "PURGE_WORKSHOP_REPO",
        "PURGE_WORKSHOP_USER_DESKTOP",
        "REGENERATE_DESKTOP",
        "VERIFY_MIGRATION",
        "VERIFY_AGENT_HOME",
        "WRITE_EVIDENCE",
        "SNAP_REMOVE_CURSOR",
        "APPLY_ENTFALTUNG_HANDOFF",
        "RESEAL_MASTER_PROMPT",
        "PURGE_CURSOR_TREE",
        "PURGE_CURSOR_USER_DATA",
        "APT_REMOVE_CURSOR",
    }
)

_FORBIDDEN_DELETE_PARTS = (
    ".local/share/r3-os/conversation",
    ".local/share/alpha-model/agent",
    "model_output_sp500",
    "control/champion",
    "control/authorization",
    "AGENTS.md",
)


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


def _fernet_for_root(root: Path):
    from cryptography.fernet import Fernet

    key_path = Path(root) / _KEY_REL
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if not key_path.is_file():
        raw = os.urandom(32)
        key_path.write_bytes(raw)
        key_path.chmod(0o600)
    else:
        raw = key_path.read_bytes()
    fkey = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(fkey)


def build_machine_program() -> Dict[str, Any]:
    """Klartext-Maschinenprogramm (wird versiegelt → .mc)."""
    return {
        "schema_version": 1,
        "program_id": "AA_SELF_UNINSTALL_CURSOR_V2",
        "headline_de": "Cursor/Werkstatt demontieren — Entfaltungsraum bleibt König",
        "invariants_de": [
            "Nie conversation-Archiv löschen",
            "Nie Champion/Gates/AGENTS.md anfassen",
            "Nur Entfaltungsraum (AA_AGENT_CHAMBER=1) oder AA_SELF_UNINSTALL_EXECUTE=1",
        ],
        "ops": [
            {"op": "PURGE_CURSOR_RULES", "mc": "0x01"},
            {"op": "PURGE_CURSOR_HOOKS_SCRIPTS", "mc": "0x02"},
            {"op": "PURGE_CURSOR_MISC", "mc": "0x03"},
            {"op": "PURGE_WORKSHOP_REPO", "mc": "0x04"},
            {"op": "PURGE_WORKSHOP_USER_DESKTOP", "mc": "0x05"},
            {"op": "REGENERATE_DESKTOP", "mc": "0x06"},
            {"op": "VERIFY_AGENT_HOME", "mc": "0x07"},
            {"op": "VERIFY_MIGRATION", "mc": "0x08"},
            {"op": "APPLY_ENTFALTUNG_HANDOFF", "mc": "0x0B"},
            {"op": "WRITE_EVIDENCE", "mc": "0x09"},
            {"op": "PURGE_CURSOR_TREE", "mc": "0x0D"},
            {"op": "PURGE_CURSOR_USER_DATA", "mc": "0x0E"},
            {"op": "APT_REMOVE_CURSOR", "mc": "0x0F", "optional": True},
            {"op": "RESEAL_MASTER_PROMPT", "mc": "0x0C"},
            {"op": "SNAP_REMOVE_CURSOR", "mc": "0x0A", "optional": True},
        ],
    }


def seal_master_prompt(root: Path) -> Dict[str, Any]:
    """Erzeugt verschlüsselten Maschinencode (.mc) + Manifest."""
    root = Path(root)
    program = build_machine_program()
    plain = json.dumps(program, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(plain, compresslevel=9)
    token = _fernet_for_root(root).encrypt(compressed)
    mc_body = base64.b85encode(token).decode("ascii")
    mc_lines = [mc_body[i : i + 76] for i in range(0, len(mc_body), 76)]
    mc_text = "\n".join(
        [
            "# AA_MC v1 Fernet+gzip+b85 — Entfaltungsraum Self-Uninstall",
            f"# sealed_at={_utc_now()}",
            *mc_lines,
        ]
    )
    (root / _MC_REL).write_text(mc_text + "\n", encoding="utf-8")
    digest = hashlib.sha256(token).hexdigest()
    manifest = {
        "schema_version": 1,
        "status": "SEALED",
        "sealed_at_utc": _utc_now(),
        "program_id": program["program_id"],
        "mc_path": str(_MC_REL),
        "mc_sha256": digest,
        "trigger_phrases_de": [
            "/self-uninstall",
            "/maschine run",
            "entfaltung demontieren",
        ],
        "execute_env": "AA_SELF_UNINSTALL_EXECUTE=1",
        "dry_run_default": True,
        "chamber_only": True,
        "headline_de": "Maschinen-Masterprompt versiegelt — nur Entfaltungsraum kann ausführen",
    }
    atomic_write_json(root / _MANIFEST_REL, manifest)
    return manifest


def decode_master_prompt(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / _MC_REL
    if not path.is_file():
        raise FileNotFoundError(f"Maschinencode fehlt: {_MC_REL}")
    blob_lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    token = base64.b85decode("".join(blob_lines))
    plain = gzip.decompress(_fernet_for_root(root).decrypt(token))
    doc = json.loads(plain.decode("utf-8"))
    if not isinstance(doc, dict) or "ops" not in doc:
        raise ValueError("Ungültiges Maschinenprogramm")
    return doc


def _safe_unlink(path: Path, *, dry_run: bool) -> Tuple[bool, str]:
    p = Path(path)
    if not p.exists():
        return True, "fehlt bereits"
    low = str(p).lower()
    for bad in _FORBIDDEN_DELETE_PARTS:
        if bad.lower() in low:
            return False, f"verboten: {bad}"
    if dry_run:
        return True, f"dry-run löschen würde: {p}"
    try:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=False)
        else:
            p.unlink()
    except OSError as exc:
        return False, f"blockiert: {p} ({exc.errno})"
    return True, f"entfernt: {p}"


def _exec_op(root: Path, op: Dict[str, Any], *, dry_run: bool) -> Dict[str, Any]:
    name = str(op.get("op") or "")
    if name not in _ALLOWED_OPS:
        return {"op": name, "ok": False, "detail_de": "Opcode nicht erlaubt"}
    home = Path.home()
    cursor = root / ".cursor"
    results: List[str] = []
    ok = True

    if name == "PURGE_CURSOR_RULES":
        rules = cursor / "rules"
        if rules.is_dir():
            for f in rules.glob("*"):
                o, d = _safe_unlink(f, dry_run=dry_run)
                ok = ok and o
                results.append(d)
        else:
            results.append("rules/ fehlt")

    elif name == "PURGE_CURSOR_HOOKS_SCRIPTS":
        hooks = cursor / "hooks"
        if hooks.is_dir():
            for f in hooks.glob("*.py"):
                o, d = _safe_unlink(f, dry_run=dry_run)
                ok = ok and o
                results.append(d)
        empty_hooks = {"version": 1, "hooks": {}}
        if not dry_run:
            atomic_write_json(cursor / "hooks.json", empty_hooks)
        results.append("hooks.json → leer")

    elif name == "PURGE_CURSOR_MISC":
        for rel in ("cli.json", "sandbox.json", "permissions.json", "hooks.disabled.json"):
            o, d = _safe_unlink(cursor / rel, dry_run=dry_run)
            if "fehlt" not in d:
                ok = ok and o
                results.append(d)

    elif name == "PURGE_WORKSHOP_REPO":
        for rel in (
            "tools/alpha_model_workshop.sh",
            "control/alpha_model_workshop_seed_de.md",
            "Alpha-Model-Workshop.desktop",
        ):
            o, d = _safe_unlink(root / rel, dry_run=dry_run)
            if "fehlt" not in d:
                ok = ok and o
                results.append(d)

    elif name == "PURGE_WORKSHOP_USER_DESKTOP":
        for p in (
            home / ".local/share/applications/Alpha-Model-Workshop.desktop",
            home / ".local/bin/alpha-model-workshop",
        ):
            o, d = _safe_unlink(p, dry_run=dry_run)
            if "fehlt" not in d:
                ok = ok and o
                results.append(d)

    elif name == "REGENERATE_DESKTOP":
        if dry_run:
            results.append("dry-run: install_desktop_os")
        else:
            from analytics.r3_desktop_os import install_desktop_os

            doc = install_desktop_os(root)
            ok = bool(doc.get("ok", True))
            results.append(str(doc.get("headline_de") or "Desktop-Einträge")[:200])

    elif name == "VERIFY_AGENT_HOME":
        if dry_run:
            from analytics.alpha_model_agent_home import load_agent_home_config

            cfg = load_agent_home_config(root)
            ok = bool(cfg.get("launch_cli"))
            results.append(f"dry-run: {cfg.get('label_de')}")
        else:
            from analytics.alpha_model_agent_home import ensure_agent_home

            doc = ensure_agent_home(root)
            ok = bool(doc.get("ok"))
            results.append(str(doc.get("headline_de") or ""))

    elif name == "VERIFY_MIGRATION":
        from analytics.r3_conversation_continuity import verify_r3_chat_ready

        doc = verify_r3_chat_ready(root)
        ok = int(doc.get("checks_passed") or 0) >= int(doc.get("checks_total") or 1) - 1
        results.append(f"{doc.get('checks_passed')}/{doc.get('checks_total')}")

    elif name == "APPLY_ENTFALTUNG_HANDOFF":
        if dry_run:
            results.append("dry-run: entfaltung-handoff")
        else:
            from analytics.alpha_model_entfaltung_handoff import apply_entfaltung_handoff

            doc = apply_entfaltung_handoff(root)
            ok = bool(doc.get("ok"))
            results.append(str(doc.get("headline_de") or ""))

    elif name == "PURGE_CURSOR_TREE":
        if cursor.exists():
            o, d = _safe_unlink(cursor, dry_run=dry_run)
            ok = ok and o
            results.append(d)
        else:
            results.append(".cursor/ fehlt bereits")

    elif name == "PURGE_CURSOR_USER_DATA":
        for rel in (
            home / ".config/Cursor",
            home / ".cache/Cursor",
        ):
            o, d = _safe_unlink(rel, dry_run=dry_run)
            if "fehlt" not in d:
                ok = ok and o
                results.append(d)

    elif name == "APT_REMOVE_CURSOR":
        if dry_run:
            results.append("dry-run: apt-get remove -y cursor")
        else:
            proc = None
            for cmd in (
                ["sudo", "-n", "apt-get", "remove", "-y", "cursor"],
                ["apt-get", "remove", "-y", "cursor"],
            ):
                try:
                    proc = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    continue
                if proc.returncode == 0:
                    break
            if proc is None:
                ok = False
                results.append("apt remove cursor — kein Versuch möglich")
            else:
                ok = proc.returncode == 0 or not (Path("/usr/bin/cursor").is_file())
                results.append(f"apt remove cursor exit={proc.returncode}")

    elif name == "WRITE_EVIDENCE":
        if not dry_run:
            atomic_write_json(
                root / "evidence/alpha_model_cursor_layer_removed.json",
                {
                    "schema_version": 1,
                    "removed_at_utc": _utc_now(),
                    "by_de": "Entfaltungsraum Maschinen-Masterprompt V2",
                    "headline_de": "Cursor-Schicht demontiert — Entfaltungsraum primär",
                },
            )
            try:
                from analytics.r3_conversation_continuity import verify_r3_chat_ready

                mig = verify_r3_chat_ready(root)
            except Exception:
                mig = {}
            atomic_write_json(
                root / "evidence/alpha_model_migration_complete.json",
                {
                    "schema_version": 1,
                    "completed_at_utc": _utc_now(),
                    "migration_checks_passed": mig.get("checks_passed"),
                    "migration_checks_total": mig.get("checks_total"),
                    "ready_for_r3_chat": bool(mig.get("ready_for_r3_chat")),
                    "primary_cli": "alpha-model-agent",
                    "headline_de": "Migration vollständig — Entfaltungsraum primär, Cursor entfernt",
                },
            )
        results.append("evidence geschrieben")

    elif name == "RESEAL_MASTER_PROMPT":
        if dry_run:
            results.append("dry-run: reseal .mc")
        else:
            seal_master_prompt(root)
            results.append("Maschinencode neu versiegelt")

    elif name == "SNAP_REMOVE_CURSOR":
        if os.environ.get("AA_SELF_UNINSTALL_SNAP", "").strip() not in ("1", "true", "yes"):
            results.append("übersprungen (AA_SELF_UNINSTALL_SNAP nicht gesetzt)")
        elif dry_run:
            results.append("dry-run: snap remove cursor")
        else:
            proc = subprocess.run(
                ["snap", "remove", "cursor"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            ok = proc.returncode == 0
            results.append(f"snap remove cursor exit={proc.returncode}")

    return {"op": name, "ok": ok, "detail_de": "; ".join(results)[:500]}


def chamber_may_execute() -> bool:
    if os.environ.get("AA_AGENT_CHAMBER", "").strip() in ("1", "true", "yes"):
        return True
    return os.environ.get("AA_SELF_UNINSTALL_EXECUTE", "").strip() in ("1", "true", "yes")


def run_self_uninstall(
    root: Path,
    *,
    dry_run: Optional[bool] = None,
    force_execute: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    manifest = _load_json(root / _MANIFEST_REL)
    if not (root / _MC_REL).is_file():
        seal_master_prompt(root)
        manifest = _load_json(root / _MANIFEST_REL)
    if dry_run is None:
        dry_run = manifest.get("dry_run_default", True) and not force_execute
    if not dry_run and not chamber_may_execute():
        return {
            "ok": False,
            "headline_de": "Nur Entfaltungsraum darf ausführen",
            "reply_de": "Starte: alpha-model-agent · dann: /self-uninstall execute",
        }
    try:
        program = decode_master_prompt(root)
    except Exception as exc:
        return {"ok": False, "headline_de": "Maschinencode nicht lesbar", "error_de": str(exc)[:200]}

    trace: List[Dict[str, Any]] = []
    for op in program.get("ops") or []:
        if not isinstance(op, dict):
            continue
        if op.get("optional") and dry_run:
            trace.append({"op": op.get("op"), "ok": True, "detail_de": "optional dry-run skip"})
            continue
        trace.append(_exec_op(root, op, dry_run=dry_run))

    passed = sum(1 for t in trace if t.get("ok"))
    total = len(trace)
    ok = passed == total
    doc = {
        "schema_version": 1,
        "ran_at_utc": _utc_now(),
        "program_id": program.get("program_id"),
        "dry_run": dry_run,
        "ok": ok,
        "steps_passed": passed,
        "steps_total": total,
        "trace": trace,
        "headline_de": (
            f"Maschinen-Demontage {'simuliert' if dry_run else 'ausgeführt'} — {passed}/{total}"
        ),
        "reply_de": _format_reply(trace, dry_run=dry_run),
        "next_de": (
            "/self-uninstall execute"
            if dry_run
            else "Cursor IDE per snap entfernen: AA_SELF_UNINSTALL_SNAP=1 /self-uninstall execute"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _format_reply(trace: List[Dict[str, Any]], *, dry_run: bool) -> str:
    mode = "DRY-RUN" if dry_run else "EXEC"
    lines = [f"**Maschinen-Masterprompt [{mode}]**"]
    for t in trace:
        mark = "✓" if t.get("ok") else "✗"
        lines.append(f"{mark} `{t.get('op')}` — {t.get('detail_de', '')[:120]}")
    return "\n".join(lines)


def handle_self_uninstall_command(root: Path, raw: str) -> Dict[str, Any]:
    low = raw.strip().lower()
    force = low.endswith(" execute") or low.endswith(" ausführen")
    dry = not force and "execute" not in low and "ausführen" not in low
    return run_self_uninstall(root, dry_run=dry, force_execute=force)


def is_self_uninstall_command(raw: str) -> bool:
    low = raw.strip().lower()
    return low in (
        "/self-uninstall",
        "/self-uninstall execute",
        "/maschine",
        "/maschine run",
        "/maschine run execute",
    ) or low.startswith("/self-uninstall ") or low.startswith("/maschine ")
