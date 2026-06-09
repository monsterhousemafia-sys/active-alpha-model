"""R3 Bau-Kernel — Ollama /bau-Fallback im Cockpit (kein paralleler Cursor-Nachbau)."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json, atomic_write_text

from analytics.r3_build_channel import (
    execute_action,
    load_build_config,
    resolve_safe_path,
    validate_run_command,
)

_CONFIG_REL = Path("control/r3_build_kernel.json")
_EVIDENCE_REL = Path("evidence/r3_build_kernel_latest.json")
_SESSION_NAME = "kernel_session.json"

_AGENT_JSON_RE = re.compile(r"\{[\s\S]*\}")

_KERNEL_SYSTEM_DE = """Du bist der R3 Bau-Kernel — Ollama-Fallback für /bau im Cockpit wenn Cursor-Composer nicht aktiv.
Du entwickelst am Arbeitsbaum autonom in Schritten mit Tools. Kein Cursor-Klon.

Antworte NUR mit einem JSON-Objekt (kein Markdown drumherum):
{"thought_de":"kurz was du tust","tool":"TOOLNAME","args":{...}}

Tools:
- read_file: {"path":"analytics/datei.py"} optional start_line, end_line
- grep: {"pattern":"def foo","path":"analytics","glob":"*.py"}
- list_dir: {"path":"analytics"}
- write_file: {"path":"analytics/datei.py","content":"vollständiger Inhalt"}
- run_command: {"cmd":"python3 -m pytest tests/test_x.py -q"}
- finish: {"summary_de":"was erledigt wurde","next_de":"optional nächster Schritt"}

Regeln:
- kleine Schritte, erst lesen dann schreiben
- write nur unter analytics/, tools/, control/, tests/, docs/
- run nur pytest und ai_kernel
- finish wenn Aufgabe erledigt oder blockiert
"""


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


def load_kernel_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {
        "name_de": "R3 Bau-Kernel",
        "max_steps": 12,
        "tools": ["read_file", "write_file", "run_command", "finish"],
    }


def kernel_share_dir() -> Path:
    return Path.home() / ".local/share/r3-os/build"


def _session_path() -> Path:
    return kernel_share_dir() / _SESSION_NAME


def load_session() -> Dict[str, Any]:
    return _load_json(_session_path()) or {"runs": []}


def save_session(doc: Dict[str, Any]) -> None:
    dest = kernel_share_dir()
    dest.mkdir(parents=True, exist_ok=True)
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(_session_path(), doc)


def _resolve_read_path(root: Path, rel: str, cfg: Dict[str, Any]) -> Tuple[Optional[Path], str]:
    root = Path(root).resolve()
    rel = str(rel or ".").strip().lstrip("/")
    if ".." in Path(rel).parts:
        return None, "Pfad ungültig"
    low = rel.lower()
    for bad in cfg.get("read_forbidden_substrings") or []:
        if bad.lower() in low:
            return None, f"Lesen verboten ({bad})"
    target = (root / rel).resolve() if rel != "." else root
    try:
        target.relative_to(root)
    except ValueError:
        return None, "Außerhalb des Arbeitsbaums"
    return target, ""


def parse_agent_step(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE):
        try:
            doc = json.loads(block.strip())
            if isinstance(doc, dict) and doc.get("tool"):
                return doc
        except json.JSONDecodeError:
            continue
    match = _AGENT_JSON_RE.search(raw)
    if not match:
        return None
    try:
        doc = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return doc if isinstance(doc, dict) and doc.get("tool") else None


def _tool_read_file(root: Path, cfg: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    path, err = _resolve_read_path(root, str(args.get("path") or ""), cfg)
    if not path or not path.is_file():
        return {"ok": False, "error_de": err or "Datei nicht gefunden"}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200]}
    start = max(1, int(args.get("start_line") or 1))
    end = int(args.get("end_line") or 0) or len(lines)
    chunk = "\n".join(f"{i+1}|{line}" for i, line in enumerate(lines[start - 1 : end]))
    max_c = int(cfg.get("max_read_chars") or 32000)
    if len(chunk) > max_c:
        chunk = chunk[:max_c] + "\n…(gekürzt)"
    return {"ok": True, "path": str(path), "content": chunk, "lines": len(lines)}


def _tool_list_dir(root: Path, cfg: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    path, err = _resolve_read_path(root, str(args.get("path") or "."), cfg)
    if not path or not path.is_dir():
        return {"ok": False, "error_de": err or "Verzeichnis nicht gefunden"}
    entries = []
    for child in sorted(path.iterdir())[:80]:
        kind = "dir" if child.is_dir() else "file"
        entries.append({"name": child.name, "type": kind})
    return {"ok": True, "path": str(path), "entries": entries}


def _tool_grep(root: Path, cfg: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    import fnmatch

    pattern = str(args.get("pattern") or "").strip()
    if not pattern:
        return {"ok": False, "error_de": "pattern fehlt"}
    base, err = _resolve_read_path(root, str(args.get("path") or "."), cfg)
    if not base:
        return {"ok": False, "error_de": err}
    glob_pat = str(args.get("glob") or "*")
    max_m = int(cfg.get("max_grep_matches") or 40)
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return {"ok": False, "error_de": f"Ungültiges Pattern: {exc}"[:200]}
    matches: List[str] = []
    scan_root = base if base.is_dir() else base.parent
    for fpath in sorted(scan_root.rglob("*")):
        if not fpath.is_file():
            continue
        if not fnmatch.fnmatch(fpath.name, glob_pat):
            continue
        try:
            rel = fpath.relative_to(root)
        except ValueError:
            continue
        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                matches.append(f"{rel}:{i}:{line[:200]}")
                if len(matches) >= max_m:
                    break
        if len(matches) >= max_m:
            break
    out = "\n".join(matches).strip()[:8000]
    return {"ok": True, "matches_de": out or "(keine Treffer)"}


def execute_kernel_tool(root: Path, tool: str, args: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    name = str(tool or "").strip().lower()
    args = args if isinstance(args, dict) else {}
    channel_cfg = load_build_config(root)

    if name == "read_file":
        return _tool_read_file(root, cfg, args)
    if name == "list_dir":
        return _tool_list_dir(root, cfg, args)
    if name == "grep":
        return _tool_grep(root, cfg, args)
    if name == "write_file":
        return execute_action(
            root,
            {"type": "write", "path": args.get("path"), "content": args.get("content")},
            channel_cfg,
        )
    if name == "run_command":
        return execute_action(root, {"type": "run", "cmd": args.get("cmd")}, channel_cfg)
    if name == "finish":
        return {
            "ok": True,
            "finished": True,
            "summary_de": args.get("summary_de"),
            "next_de": args.get("next_de"),
        }
    return {"ok": False, "error_de": f"Unbekanntes Tool: {name}"}


def run_build_kernel(root: Path, mandate_de: str, *, max_steps: Optional[int] = None) -> Dict[str, Any]:
    """Cursor-ähnliche Agenten-Schleife — Kern zum Bauen ohne Cursor."""
    root = Path(root)
    cfg = load_kernel_config(root)
    mandate = str(mandate_de or "").strip()
    if not mandate:
        return {"ok": False, "headline_de": "Mandat fehlt", "reply_de": "Aufgabe angeben"}

    from analytics.local_llm_bridge import chat_completion, health_report

    health = health_report(root)
    if not health.get("ready"):
        return {
            "ok": False,
            "headline_de": "Ollama nicht bereit",
            "reply_de": "python3 tools/ai_kernel.py llm-setup",
        }

    try:
        from analytics.alpha_model_entfaltung_32b import build_kernel_limits, preload_build_model

        limits = build_kernel_limits(root)
        preload_build_model(root)
    except Exception:
        limits = {"max_steps": cfg.get("max_steps") or 14, "temperature": 0.2, "timeout_s": 420.0}

    try:
        from analytics.alpha_model_entfaltung_32b import resolve_steps_limit

        steps_limit = resolve_steps_limit(
            configured=int(max_steps or limits.get("max_steps") or cfg.get("max_steps") or 14),
            role="build",
        )
    except Exception:
        steps_limit = int(max_steps or limits.get("max_steps") or cfg.get("max_steps") or 14)
    build_temp = float(limits.get("temperature") or cfg.get("build_temperature") or 0.2)
    timeout_s = float(limits.get("timeout_s") or 420.0)
    system = str(cfg.get("system_prompt_de") or "").strip() or _KERNEL_SYSTEM_DE
    mlow = mandate.lower()
    if "remaster" in mlow or ("gui" in mlow and "einheitlich" in mlow):
        try:
            from analytics.gui_remaster_gate import build_remaster_mandate_block

            block = build_remaster_mandate_block(root)
            if block:
                system = f"{system}\n\n{block}"
        except Exception:
            pass
    try:
        from analytics.r3_build_mandate import build_mandate_context_block

        r3_block = build_mandate_context_block(root, mandate)
        if r3_block:
            system = f"{system}\n\n{r3_block}"
    except Exception:
        pass
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": mandate},
    ]
    trace: List[Dict[str, Any]] = []
    finished = False
    summary = ""
    next_de = ""

    for step in range(1, steps_limit + 1):
        try:
            from analytics.r3_model_synergy import resolve_ollama_role

            build_pick = resolve_ollama_role(root, mandate, mode="build")
            build_model = str(build_pick.get("model") or "")
            reply, _meta = chat_completion(
                root,
                messages,
                model=build_model or None,
                timeout_s=timeout_s,
                temperature=build_temp,
                num_ctx=build_pick.get("num_ctx"),
                role="build",
            )
        except Exception as exc:
            doc = _finalize_run(root, mandate, trace, ok=False, error_de=str(exc)[:300])
            return doc

        action = parse_agent_step(reply)
        if not action:
            messages.append({"role": "assistant", "content": reply})
            messages.append(
                {
                    "role": "user",
                    "content": "Ungültiges Format. Antworte nur mit JSON: thought_de, tool, args.",
                }
            )
            trace.append({"step": step, "parse_error": True, "raw": reply[:500]})
            continue

        tool = str(action.get("tool") or "")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        thought = str(action.get("thought_de") or "")
        result = execute_kernel_tool(root, tool, args, cfg)
        entry = {
            "step": step,
            "thought_de": thought,
            "tool": tool,
            "args": args,
            "result": {k: v for k, v in result.items() if k != "content"},
        }
        if result.get("content"):
            entry["result_preview"] = str(result["content"])[:400]
        trace.append(entry)

        if tool == "finish" or result.get("finished"):
            finished = True
            summary = str(result.get("summary_de") or thought or "Fertig")
            next_de = str(result.get("next_de") or "")
            break

        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": "Tool-Ergebnis:\n" + json.dumps(result, ensure_ascii=False)[:12000],
            }
        )

    ok = finished or any(t.get("tool") == "write_file" and (t.get("result") or {}).get("ok") for t in trace)
    doc = _finalize_run(
        root,
        mandate,
        trace,
        ok=ok,
        finished=finished,
        summary_de=summary,
        next_de=next_de,
        steps=len(trace),
    )
    if ok and any(k in mlow for k in ("r3", "lokal", "mirror", "runtime", "upgrade", "sync", "abgleich", "remaster")):
        try:
            from analytics.r3_build_mandate import post_build_r3_align

            doc["post_align"] = post_build_r3_align(root, mandate_de=mandate, build_ok=ok)
            if doc["post_align"].get("confirmation_de"):
                doc["next_de"] = doc["post_align"]["confirmation_de"]
        except Exception:
            pass
    doc["reply_de"] = _format_run_reply(doc)
    return doc


def _finalize_run(
    root: Path,
    mandate: str,
    trace: List[Dict[str, Any]],
    *,
    ok: bool,
    finished: bool = False,
    summary_de: str = "",
    next_de: str = "",
    steps: int = 0,
    error_de: str = "",
) -> Dict[str, Any]:
    cfg = load_kernel_config(root)
    doc = {
        "schema_version": 1,
        "kernel": "r3_build_kernel",
        "name_de": cfg.get("name_de"),
        "headline_de": (
            "Bau-Kernel abgeschlossen"
            if finished
            else ("Bau-Kernel lief" if ok else "Bau-Kernel — Fehler oder unvollständig")
        ),
        "ok": ok,
        "finished": finished,
        "mandate_de": mandate[:500],
        "summary_de": summary_de,
        "next_de": next_de,
        "steps": steps,
        "trace": trace[-20:],
        "completed_at_utc": _utc_now(),
        "error_de": error_de or None,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    sess = load_session()
    runs = list(sess.get("runs") or [])
    runs.insert(
        0,
        {
            "at_utc": doc["completed_at_utc"],
            "mandate_de": mandate[:120],
            "ok": ok,
            "finished": finished,
            "steps": steps,
            "summary_de": summary_de[:200],
        },
    )
    sess["runs"] = runs[:30]
    save_session(sess)
    try:
        from analytics.r3_dev_trail import record_dev_change

        record_dev_change(
            root,
            title_de="Bau-Kernel Lauf",
            detail_de=summary_de[:160] or mandate[:160],
            status="done" if finished else "active",
        )
    except Exception:
        pass
    return doc


def _format_run_reply(doc: Dict[str, Any]) -> str:
    lines = [str(doc.get("headline_de") or "Bau-Kernel")]
    if doc.get("summary_de"):
        lines.append(str(doc["summary_de"]))
    if doc.get("next_de"):
        lines.append(f"Als Nächstes: {doc['next_de']}")
    for t in doc.get("trace") or []:
        mark = "OK" if (t.get("result") or {}).get("ok", True) else "—"
        lines.append(f"[{mark}] {t.get('tool')}: {t.get('thought_de', '')[:100]}")
    if doc.get("error_de"):
        lines.append(str(doc["error_de"]))
    return "\n".join(lines)[:8000]


def build_kernel_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_kernel_config(root)
    latest = _load_json(root / _EVIDENCE_REL)
    sess = load_session()
    from analytics.local_llm_bridge import health_report

    ollama = health_report(root)
    last_run = (sess.get("runs") or [{}])[0] if sess.get("runs") else {}
    return {
        "schema_version": 1,
        "checked_at_utc": _utc_now(),
        "name_de": cfg.get("name_de"),
        "headline_de": cfg.get("headline_de"),
        "replaces_de": cfg.get("replaces_de"),
        "engine_de": cfg.get("engine_de"),
        "is_build_kernel": True,
        "ollama_ready": bool(ollama.get("ready")),
        "last_run": last_run,
        "latest": {
            "ok": latest.get("ok"),
            "finished": latest.get("finished"),
            "summary_de": latest.get("summary_de"),
            "steps": latest.get("steps"),
            "completed_at_utc": latest.get("completed_at_utc"),
        },
        "tools": cfg.get("tools") or [],
        "help_de": (
            "/bau <Aufgabe> — Bau-Kernel (Agent-Schleife wie Cursor)\n"
            "/bau kernel <Aufgabe> — explizit\n"
            "/bau status — letzter Lauf"
        ),
        "ok": bool(ollama.get("ready")),
    }


def render_build_kernel_section(status: Dict[str, Any]) -> str:
    import html

    esc = lambda t: html.escape(str(t or ""), quote=True)
    if not status:
        return ""
    ready = "Bereit" if status.get("ollama_ready") else "Ollama Setup"
    last = status.get("last_run") or {}
    last_line = esc(last.get("summary_de") or last.get("mandate_de") or "—")
    return f"""
<section class="r3-build-kernel" id="r3-build-kernel" aria-label="Bau-Kernel">
  <div class="rbk-head">
    <div class="rbk-eyebrow">Kernel · Cursor-Nachbau</div>
    <h2 class="rbk-title">{esc(status.get('name_de'))}</h2>
    <p class="rbk-meta">{esc(ready)} · liest · schreibt · testet autonom</p>
    <p class="rbk-replaces">{esc(status.get('replaces_de'))}</p>
    <p class="rbk-last"><strong>Zuletzt:</strong> {last_line}</p>
  </div>
  <p class="rbk-cmd"><code>/bau &lt;Aufgabe&gt;</code> startet den Bau-Kernel</p>
</section>"""
