"""R3 Bau-Werkstatt — Code und Befehle ohne Cursor (Ollama + sichere Ausführung)."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json, atomic_write_text

_CONFIG_REL = Path("control/r3_build_channel.json")
_QUEUE_NAME = "build_queue.json"
_LOG_NAME = "build_log.jsonl"
_EVIDENCE_REL = Path("evidence/r3_build_latest.json")

_BUILD_BLOCK_RE = re.compile(r"```r3-build\s*([\s\S]*?)```", re.IGNORECASE)
_BUILD_SYSTEM_DE = """Du bist der R3 Bau-Agent (ohne Cursor). Der Benutzer will am Arbeitsbaum bauen.
Antworte auf Deutsch mit kurzer Erklärung UND genau einem Block:

```r3-build
{"actions":[{"type":"write","path":"analytics/beispiel.py","content":"# code\\n"},{"type":"run","cmd":"python3 -m pytest tests/ -q -k beispiel"}]}
```

Regeln:
- paths unter: analytics/, tools/, control/, tests/, evidence/, docs/, execution/, aa_/
- keine .env, keine Secrets, kein .git
- type: write | run | plan (plan nur title_de + steps_de)
- kleine, fokussierte Änderungen
- run nur: pytest, python3 tools/ai_kernel.py, bash tools/"""


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


def load_build_config(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL) or {
        "title_de": "R3 Bau-Werkstatt",
        "write_prefixes": [
            "analytics/",
            "tools/",
            "control/",
            "tests/",
            "evidence/",
            "docs/",
            "execution/",
            "aa_",
        ],
        "write_forbidden_substrings": [".env", "credentials", "secret", ".git/"],
        "run_allowlist_prefixes": [
            "python3 -m pytest ",
            "python3 tools/ai_kernel.py ",
            ".venv/bin/python -m pytest ",
            "bash tools/",
        ],
    }
    # Legacy keys in control/r3_build_channel.json
    if not doc.get("write_prefixes") and doc.get("allowed_paths"):
        doc["write_prefixes"] = list(doc["allowed_paths"])
    if not doc.get("run_allowlist_prefixes") and doc.get("allow_run_patterns"):
        doc["run_allowlist_prefixes"] = list(doc["allow_run_patterns"])
    return doc


def build_share_dir() -> Path:
    return Path.home() / ".local/share/r3-os/build"


def _queue_path() -> Path:
    return build_share_dir() / _QUEUE_NAME


def _log_path() -> Path:
    return build_share_dir() / _LOG_NAME


def _append_log(entry: Dict[str, Any]) -> None:
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_queue() -> Dict[str, Any]:
    return _load_json(_queue_path()) or {"actions": [], "updated_at_utc": None}


def save_queue(doc: Dict[str, Any]) -> None:
    dest = build_share_dir()
    dest.mkdir(parents=True, exist_ok=True)
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(_queue_path(), doc)


def clear_queue() -> Dict[str, Any]:
    doc = {"actions": [], "updated_at_utc": _utc_now(), "cleared_at_utc": _utc_now()}
    save_queue(doc)
    return doc


def queue_actions(actions: List[Dict[str, Any]], *, source: str = "") -> Dict[str, Any]:
    cfg_limit = 12
    doc = load_queue()
    pending = list(doc.get("actions") or [])
    for action in actions[:cfg_limit]:
        if isinstance(action, dict) and action.get("type"):
            action = dict(action)
            action["queued_at_utc"] = _utc_now()
            if source:
                action["source"] = source
            pending.append(action)
    doc["actions"] = pending[-cfg_limit:]
    doc["source"] = source or doc.get("source")
    save_queue(doc)
    return doc


def resolve_safe_path(root: Path, rel: str, cfg: Dict[str, Any]) -> Tuple[Optional[Path], str]:
    root = Path(root).resolve()
    rel = str(rel or "").strip().lstrip("/")
    if not rel or ".." in Path(rel).parts:
        return None, "Pfad ungültig"
    low = rel.lower()
    for bad in cfg.get("write_forbidden_substrings") or []:
        if bad.lower() in low:
            return None, f"Pfad verboten ({bad})"
    allowed = False
    for prefix in cfg.get("write_prefixes") or []:
        if rel.startswith(str(prefix).lstrip("/")):
            allowed = True
            break
    if not allowed:
        return None, "Pfad außerhalb der erlaubten Bereiche"
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None, "Pfad außerhalb des Arbeitsbaums"
    return target, ""


def validate_run_command(cmd: str, cfg: Dict[str, Any]) -> Tuple[bool, str]:
    text = str(cmd or "").strip()
    if not text or "\n" in text:
        return False, "Befehl leer oder mehrzeilig"
    low = text.lower()
    for bad in cfg.get("run_forbidden_substrings") or []:
        if bad.lower() in low:
            return False, f"Befehl verboten ({bad})"
    for prefix in cfg.get("run_allowlist_prefixes") or []:
        if text.startswith(prefix):
            return True, ""
    return False, "Befehl nicht in der Allowlist"


def parse_r3_build_blocks(text: str) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for match in _BUILD_BLOCK_RE.finditer(str(text or "")):
        raw = match.group(1).strip()
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(doc, list):
            actions.extend([a for a in doc if isinstance(a, dict)])
        elif isinstance(doc, dict):
            chunk = doc.get("actions") or [doc]
            actions.extend([a for a in chunk if isinstance(a, dict)])
    return actions


def execute_action(root: Path, action: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    atype = str(action.get("type") or "").strip().lower()
    if atype == "plan":
        return {
            "ok": True,
            "type": "plan",
            "title_de": action.get("title_de"),
            "steps_de": action.get("steps_de") or [],
            "detail_de": "Plan notiert",
        }
    if atype == "write":
        rel = str(action.get("path") or "")
        content = str(action.get("content") or "")
        max_b = int(cfg.get("max_write_bytes") or 120000)
        if len(content.encode("utf-8")) > max_b:
            return {"ok": False, "type": "write", "path": rel, "error_de": "Inhalt zu groß"}
        target, err = resolve_safe_path(root, rel, cfg)
        if not target:
            return {"ok": False, "type": "write", "path": rel, "error_de": err}
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, content)
        _append_log({"at_utc": _utc_now(), "type": "write", "path": str(target), "bytes": len(content)})
        return {"ok": True, "type": "write", "path": str(target), "detail_de": f"Geschrieben: {rel}"}
    if atype == "run":
        cmd = str(action.get("cmd") or "").strip()
        ok, err = validate_run_command(cmd, cfg)
        if not ok:
            return {"ok": False, "type": "run", "cmd": cmd, "error_de": err}
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        _append_log(
            {
                "at_utc": _utc_now(),
                "type": "run",
                "cmd": cmd,
                "exit_code": proc.returncode,
            }
        )
        return {
            "ok": proc.returncode == 0,
            "type": "run",
            "cmd": cmd,
            "exit_code": proc.returncode,
            "output_de": out.strip()[:4000],
            "detail_de": "OK" if proc.returncode == 0 else f"Exit {proc.returncode}",
        }
    return {"ok": False, "error_de": f"Unbekannter Typ: {atype}"}


def apply_queue(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_build_config(root)
    doc = load_queue()
    actions = list(doc.get("actions") or [])
    if not actions:
        return {"ok": False, "headline_de": "Warteschlange leer", "results": []}
    results = [execute_action(root, a, cfg) for a in actions]
    ok = all(r.get("ok") for r in results)
    evidence = {
        "schema_version": 1,
        "applied_at_utc": _utc_now(),
        "ok": ok,
        "action_count": len(results),
        "results": results,
        "headline_de": "Bau-Werkstatt angewendet" if ok else "Bau-Werkstatt — Fehler bei mindestens einer Aktion",
    }
    atomic_write_json(root / _EVIDENCE_REL, evidence)
    clear_queue()
    try:
        from analytics.r3_dev_trail import record_dev_change

        titles = [str(r.get("path") or r.get("cmd") or r.get("type"))[:60] for r in results[:3]]
        record_dev_change(
            root,
            title_de="Bau-Werkstatt ausgeführt",
            detail_de=" · ".join(titles),
            status="done" if ok else "active",
        )
    except Exception:
        pass
    return evidence


def build_from_task(root: Path, task_de: str) -> Dict[str, Any]:
    """Ollama erzeugt Bau-Aktionen aus natürlicher Sprache."""
    root = Path(root)
    task = str(task_de or "").strip()
    if not task:
        return {"ok": False, "reply_de": "Aufgabe fehlt — z.B. /bau Test für r3_build_channel hinzufügen"}

    from analytics.local_llm_bridge import chat_completion, health_report

    health = health_report(root)
    if not health.get("ready"):
        return {
            "ok": False,
            "reply_de": "Ollama nicht bereit — python3 tools/ai_kernel.py llm-setup",
        }

    messages = [
        {"role": "system", "content": _BUILD_SYSTEM_DE},
        {"role": "user", "content": task},
    ]
    try:
        reply, _meta = chat_completion(root, messages, timeout_s=240.0)
    except Exception as exc:
        return {"ok": False, "reply_de": str(exc)[:300]}

    actions = parse_r3_build_blocks(reply)
    if not actions:
        return {
            "ok": True,
            "reply_de": reply[:3000],
            "queued": 0,
            "hint_de": "Kein r3-build Block — formuliere konkreter oder nutze /bau run …",
        }

    q = queue_actions(actions, source="build_from_task")
    count = len(q.get("actions") or [])
    summary = (
        f"{count} Aktion(en) in der Warteschlange.\n"
        f"/bau status — anzeigen\n"
        f"/bau apply — ausführen\n"
        f"/bau clear — verwerfen\n\n"
        f"{reply[:2000]}"
    )
    return {
        "ok": True,
        "reply_de": summary,
        "queued": count,
        "actions_preview": actions[:6],
        "hint_de": "/bau apply zum Ausführen",
    }


def build_help_de() -> str:
    return (
        "R3 Bau-Kernel — Nachbau der Cursor-Bauwerkstatt.\n"
        "/bau <Aufgabe> — Agent-Schleife (liest, schreibt, testet — wie Cursor)\n"
        "/bau kernel <Aufgabe> — explizit Bau-Kernel\n"
        "/bau plan <Aufgabe> — nur planen (Warteschlange, ohne Auto-Lauf)\n"
        "/bau apply — Warteschlange manuell ausführen\n"
        "/bau status — letzter Kernel-Lauf + Warteschlange\n"
        "/bau run <befehl> — einzelner Allowlist-Befehl\n"
        "/bau clear — Warteschlange leeren"
    )


def handle_build_command(root: Path, text: str) -> Dict[str, Any]:
    root = Path(root)
    raw = str(text or "").strip()
    low = raw.lower()
    if low in ("/bau", "/build", "/bau hilfe", "/build help", "/bau help"):
        return {"ok": True, "reply_de": build_help_de(), "help": True}

    if low in ("/bau status", "/build status"):
        from analytics.r3_build_kernel import build_kernel_status

        ks = build_kernel_status(root)
        q = load_queue()
        actions = q.get("actions") or []
        parts = [str(ks.get("help_de") or "")]
        latest = ks.get("latest") or {}
        if latest.get("completed_at_utc"):
            parts.append(
                f"Letzter Kernel: {latest.get('summary_de') or '—'} "
                f"({latest.get('steps')} Schritte, ok={latest.get('ok')})"
            )
        if actions:
            parts.append("Warteschlange:")
            parts.extend(
                f"{i+1}. {a.get('type')}: {a.get('path') or a.get('cmd')}"
                for i, a in enumerate(actions)
            )
        else:
            parts.append("Warteschlange: leer")
        return {"ok": True, "reply_de": "\n".join(parts), "kernel": ks, "actions": actions}

    if low in ("/bau clear", "/build clear"):
        clear_queue()
        return {"ok": True, "reply_de": "Warteschlange geleert."}

    if low in ("/bau apply", "/build apply"):
        doc = apply_queue(root)
        lines = []
        for r in doc.get("results") or []:
            mark = "OK" if r.get("ok") else "FEHLER"
            lines.append(f"[{mark}] {r.get('type')}: {r.get('detail_de') or r.get('error_de')}")
            if r.get("output_de"):
                lines.append(str(r["output_de"])[:800])
        return {
            "ok": bool(doc.get("ok")),
            "reply_de": "\n".join(lines) or doc.get("headline_de", ""),
            "applied": True,
            "results": doc.get("results"),
        }

    if low.startswith("/bau run ") or low.startswith("/build run "):
        cmd = raw.split(maxsplit=2)[2] if low.startswith("/bau run ") else raw.split(maxsplit=2)[2]
        cfg = load_build_config(root)
        ok, err = validate_run_command(cmd, cfg)
        if not ok:
            return {"ok": False, "reply_de": err}
        result = execute_action(root, {"type": "run", "cmd": cmd}, cfg)
        out = str(result.get("output_de") or result.get("detail_de") or "")
        return {
            "ok": bool(result.get("ok")),
            "reply_de": out[:5000] or result.get("error_de", ""),
            "run": True,
        }

    if low.startswith("/bau plan ") or low.startswith("/build plan "):
        task = raw.split(maxsplit=2)[2] if " " in raw[5:] else ""
        return build_from_task(root, task)

    task = raw
    for prefix in ("/bau kernel ", "/build kernel "):
        if low.startswith(prefix):
            from analytics.r3_build_kernel import run_build_kernel

            task = raw[len(prefix) :].strip()
            return run_build_kernel(root, task)
    for prefix in ("/bau ", "/build "):
        if low.startswith(prefix):
            task = raw[len(prefix) :].strip()
            break

    from analytics.r3_build_kernel import run_build_kernel

    return run_build_kernel(root, task)


def enrich_ki_reply(root: Path, reply: str) -> Tuple[str, int]:
    actions = parse_r3_build_blocks(reply)
    if not actions:
        return reply, 0
    queue_actions(actions, source="ki_reply")
    count = len(actions)
    note = (
        f"\n\n—\n**Bau-Werkstatt:** {count} Aktion(en) vorgemerkt. "
        f"`/bau status` anzeigen · `/bau apply` ausführen"
    )
    return reply + note, count


def build_channel_status(root: Path) -> Dict[str, Any]:
    from analytics.r3_build_kernel import build_kernel_status

    ks = build_kernel_status(root)
    q = load_queue()
    actions = q.get("actions") or []
    ks["queue_count"] = len(actions)
    ks["queue_preview"] = [
        {"type": a.get("type"), "path": a.get("path"), "cmd": (str(a.get("cmd") or ""))[:80]}
        for a in actions[:5]
    ]
    return ks


def render_build_section(status: Dict[str, Any]) -> str:
    from analytics.r3_build_kernel import render_build_kernel_section

    return render_build_kernel_section(status)
