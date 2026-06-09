"""Entfaltungsraum Chat-Agent — Tool-Schleife für Freitext (lesen → antworten wie Cursor)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from aa_safe_io import atomic_write_json

from analytics.r3_build_kernel import execute_kernel_tool, load_kernel_config, parse_agent_step

_CONFIG_REL = Path("control/alpha_model_chat_agent.json")
_EVIDENCE_REL = Path("evidence/alpha_model_chat_agent_latest.json")
_ARCHIVE_NAME = "conversation_archive.jsonl"

_IDENT_RE = re.compile(r"\b[a-z][a-z0-9_]{4,}\b")
_PATH_RE = re.compile(
    r"(?:analytics|tools|control|tests|evidence|execution|docs)/[\w./_-]+\.(?:py|json|md|sh)"
)
_STOPWORDS = frozenset(
    {
        "alpha",
        "model",
        "bitte",
        "danke",
        "eine",
        "einer",
        "einem",
        "einen",
        "dieser",
        "diese",
        "dieses",
        "kannst",
        "können",
        "koennen",
        "machin",
        "machinax",
        "finde",
        "lies",
        "lese",
        "erkläre",
        "erklaere",
        "status",
        "kurz",
        "datei",
        "wo",
        "was",
        "wie",
        "und",
        "oder",
        "für",
        "fuer",
        "mit",
        "nach",
        "über",
        "ueber",
    }
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


def load_chat_agent_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {
        "enabled": True,
        "max_steps": 6,
        "min_chars_for_agent": 18,
        "prefetch_enabled": True,
        "kernel_allowlist": ["status", "warnings", "h1-status", "ready"],
    }


def extract_search_terms(text: str) -> List[str]:
    raw = str(text or "")
    terms: List[str] = []
    seen: Set[str] = set()
    for match in _PATH_RE.findall(raw):
        base = Path(match).stem
        if base and base not in seen:
            seen.add(base)
            terms.append(base)
    for match in _IDENT_RE.findall(raw.lower()):
        if match in _STOPWORDS or match in seen:
            continue
        seen.add(match)
        terms.append(match)
    return terms[:6]


def should_route_to_bau(text: str, *, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Coding-Aufträge → /bau statt Chat-Agent (max 12 Schritte, write)."""
    cfg = cfg or {}
    raw = str(text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    low = raw.lower()
    if len(low) < 20:
        return False
    skip = cfg.get("bau_skip_patterns_de") or []
    route = cfg.get("bau_route_patterns_de") or []
    has_route = any(p in low for p in route)
    if not has_route:
        return False
    has_skip = any(p in low for p in skip)
    strong_code = any(s in low for s in ("pytest", " def ", "class ", ".py", "test_", "fix "))
    if has_skip and not strong_code:
        return False
    return True


def should_use_chat_agent(text: str, *, cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg or {}
    if cfg.get("enabled") is False:
        return False
    raw = str(text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    if should_route_to_bau(raw, cfg=cfg):
        return False
    low = raw.lower()
    try:
        from analytics.alpha_model_entfaltung_32b import is_sovereign_chamber

        if is_sovereign_chamber() and cfg.get("free_unfold", True):
            for skip in cfg.get("skip_patterns_de") or []:
                if low == str(skip).strip().lower():
                    return False
            return True
    except Exception:
        pass
    if len(low) < int(cfg.get("min_chars_for_agent") or 18):
        return False
    for skip in cfg.get("skip_patterns_de") or []:
        if low == str(skip).strip().lower() or low.startswith(str(skip).strip().lower() + " "):
            return False
    triggers = cfg.get("trigger_patterns_de") or []
    if any(t in low for t in triggers):
        return True
    if "?" in raw:
        return True
    if re.search(r"\b(wie|warum|wann|welche|welcher|welches)\b", low):
        return True
    return len(raw.split()) >= 5


def prefetch_context(root: Path, text: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Vorab-Suche ohne LLM-Schritt — spart Schritte bei qwen2.5:7b."""
    if cfg.get("prefetch_enabled") is False:
        return {"enabled": False}
    root = Path(root)
    terms = extract_search_terms(text)
    max_terms = int(cfg.get("prefetch_max_terms") or 3)
    grep_hits: List[Dict[str, str]] = []
    for term in terms[:max_terms]:
        result = execute_kernel_tool(
            root,
            "grep",
            {"pattern": term, "path": ".", "glob": "*.py"},
            load_kernel_config(root),
        )
        matches = str(result.get("matches_de") or "")
        if result.get("ok") and matches and "(keine Treffer)" not in matches:
            grep_hits.append({"term": term, "matches_de": matches[:2500]})

    internet_hint: Optional[str] = None
    try:
        from analytics.r3_ki_web import is_internet_question, reply_internet_capabilities

        if is_internet_question(text):
            net = reply_internet_capabilities(root, text)
            internet_hint = str(net.get("reply_de") or "")
    except Exception:
        pass

    kernel_prefetch: Optional[Dict[str, Any]] = None
    low = text.lower()
    skip_kernel_prefetch = False
    try:
        from analytics.alpha_model_entfaltung_32b import is_sovereign_chamber

        skip_kernel_prefetch = is_sovereign_chamber() and cfg.get("prefetch_kernel_in_chamber") is False
    except Exception:
        pass
    if not skip_kernel_prefetch:
        allow = _kernel_allowlist(root, cfg)
        for kw, cmd in (cfg.get("prefetch_kernel_keywords") or {}).items():
            if cmd not in allow:
                continue
            if re.search(rf"\b{re.escape(str(kw).lower())}\b", low):
                kernel_prefetch = _tool_kernel(root, {"command": cmd}, cfg)
                break

    explicit_paths = _PATH_RE.findall(text)
    return {
        "enabled": True,
        "terms": terms[:max_terms],
        "grep_hits": grep_hits,
        "kernel": kernel_prefetch,
        "internet_hint": internet_hint,
        "explicit_paths": explicit_paths[:3],
    }


def _format_prefetch_block(prefetch: Dict[str, Any]) -> str:
    if not prefetch.get("enabled"):
        return ""
    parts: List[str] = ["=== PREFETCH (bereits gesucht, nutze diese Fakten) ==="]
    for hit in prefetch.get("grep_hits") or []:
        parts.append(f"grep `{hit.get('term')}`:\n{hit.get('matches_de')}")
    kern = prefetch.get("kernel") or {}
    if kern.get("ok") and kern.get("output_de"):
        parts.append(f"kernel `{kern.get('command')}`:\n{kern['output_de'][:3000]}")
    for path in prefetch.get("explicit_paths") or []:
        parts.append(f"expliziter Pfad: {path}")
    if prefetch.get("internet_hint"):
        parts.append(f"Internet:\n{prefetch['internet_hint']}")
    if len(parts) == 1:
        return ""
    parts.append("=== ENDE PREFETCH ===")
    return "\n\n".join(parts)


def _kernel_allowlist(root: Path, cfg: Dict[str, Any]) -> Set[str]:
    allowed = set(cfg.get("kernel_allowlist") or [])
    try:
        from analytics.alpha_model_agent_home import is_agent_chamber_active

        if is_agent_chamber_active():
            from analytics.alpha_model_chamber_resources import chamber_kernel_allowlist

            allowed = set(chamber_kernel_allowlist(root)) or allowed
    except Exception:
        pass
    return allowed


def _tool_kernel(root: Path, args: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.local_llm_bridge import run_kernel_command

    parts = str(args.get("command") or args.get("cmd") or "").strip().split()
    if not parts:
        return {"ok": False, "error_de": "Kernel-Befehl fehlt"}
    cmd = parts[0]
    allowed = _kernel_allowlist(root, cfg)
    if cmd not in allowed:
        return {
            "ok": False,
            "error_de": f"Kernel `{cmd}` nicht erlaubt. Erlaubt: {', '.join(sorted(allowed))}",
        }
    out = run_kernel_command(root, cmd)
    return {"ok": True, "command": cmd, "output_de": out[:8000]}


def _tool_reply(args: Dict[str, Any]) -> Dict[str, Any]:
    reply = str(args.get("reply_de") or args.get("content") or "").strip()
    if not reply:
        return {"ok": False, "error_de": "reply_de fehlt"}
    return {"ok": True, "finished": True, "reply_de": reply}


def _normalize_action(action: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(action)
    tool = str(doc.get("tool") or "").strip().lower()
    if tool in ("reply_de", "answer", "respond", "antwort"):
        doc["tool"] = "reply"
    args = doc.get("args") if isinstance(doc.get("args"), dict) else {}
    if doc["tool"] == "reply" and not args.get("reply_de"):
        for key in ("message_de", "content", "text", "summary_de"):
            if args.get(key):
                args["reply_de"] = args[key]
                break
        if not args.get("reply_de") and doc.get("thought_de"):
            args["reply_de"] = doc["thought_de"]
        doc["args"] = args
    return doc


def _extract_reply_from_raw(raw: str) -> str:
    text = str(raw or "").strip()
    action = parse_agent_step(text)
    if action:
        norm = _normalize_action(action)
        if norm.get("tool") == "reply":
            args = norm.get("args") if isinstance(norm.get("args"), dict) else {}
            reply = str(args.get("reply_de") or norm.get("thought_de") or "").strip()
            if reply:
                return reply
    if text.startswith("{") and text.endswith("}"):
        try:
            doc = json.loads(text)
            if isinstance(doc, dict):
                for key in ("reply_de", "message_de", "content", "thought_de"):
                    val = doc.get(key) or (doc.get("args") or {}).get(key)
                    if val:
                        return str(val).strip()
        except json.JSONDecodeError:
            pass
    return text


def _action_key(tool: str, args: Dict[str, Any]) -> str:
    return f"{tool}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


def _synthesize_from_prefetch(prefetch: Dict[str, Any], user_text: str) -> str:
    hits = prefetch.get("grep_hits") or []
    if not hits:
        return ""
    lines = [f"Zu deiner Frage «{user_text[:80]}» — Vorfund aus dem Arbeitsbaum:"]
    for hit in hits[:2]:
        lines.append(f"\n**{hit.get('term')}**:")
        lines.append(str(hit.get("matches_de") or "")[:1500])
    kern = prefetch.get("kernel") or {}
    if kern.get("output_de"):
        lines.append(f"\n**Kernel {kern.get('command')}** (Auszug):")
        lines.append(str(kern["output_de"])[:800])
    return "\n".join(lines)[:4000]


def _append_limits_footer(
    reply: str,
    cfg: Dict[str, Any],
    *,
    steps: int,
    finished: bool,
    steps_limit: int,
) -> str:
    if cfg.get("free_unfold") and cfg.get("step_limit_hint_de") in (None, "", False):
        return reply
    try:
        from analytics.alpha_model_entfaltung_32b import is_sovereign_chamber

        if is_sovereign_chamber() and cfg.get("free_unfold", True):
            return reply
    except Exception:
        pass
    if finished:
        return reply
    if steps < steps_limit:
        return reply
    tpl = str(cfg.get("step_limit_hint_de") or cfg.get("limits_footer_de") or "")
    if not tpl:
        return reply
    footer = tpl.format(steps=steps, limit=steps_limit)
    if footer in reply:
        return reply
    return f"{reply.rstrip()}\n\n{footer}"


def append_turn_to_archive(*, user_text: str, reply_de: str, meta: Optional[Dict[str, Any]] = None) -> None:
    dest = Path.home() / ".local/share/r3-os/conversation"
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / _ARCHIVE_NAME
    rows = [
        {"role": "user", "text": user_text[:2000], "at_utc": _utc_now(), "source": "entfaltungsraum"},
        {
            "role": "assistant",
            "text": reply_de[:4000],
            "at_utc": _utc_now(),
            "source": "chat_agent",
            "meta": meta or {},
        },
    ]
    with archive.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _normalize_tool_args(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(args) if isinstance(args, dict) else {}
    if tool == "read_file":
        if not doc.get("path"):
            for alt in ("file", "filename", "filepath"):
                if doc.get(alt):
                    doc["path"] = doc[alt]
                    break
    if tool == "grep":
        if not doc.get("pattern"):
            for alt in ("query", "term", "search"):
                if doc.get(alt):
                    doc["pattern"] = doc[alt]
                    break
        if not doc.get("path") and doc.get("files"):
            files = doc.get("files")
            if isinstance(files, list) and files:
                doc["path"] = str(files[0])
            elif isinstance(files, str):
                doc["path"] = files
    return doc


def execute_chat_tool(
    root: Path, tool: str, args: Dict[str, Any], cfg: Dict[str, Any]
) -> Dict[str, Any]:
    name = str(tool or "").strip().lower()
    if name in ("reply_de", "answer", "respond", "antwort"):
        name = "reply"
    args = _normalize_tool_args(name, args if isinstance(args, dict) else {})
    kernel_cfg = load_kernel_config(root)
    if name == "kernel":
        return _tool_kernel(root, args, cfg)
    if name == "reply":
        return _tool_reply(args)
    return execute_kernel_tool(root, name, args, kernel_cfg)


def run_chat_agent(
    root: Path,
    user_text: str,
    *,
    history: Optional[List[Dict[str, str]]] = None,
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """Liest Code/Evidence und antwortet in natürlicher Sprache."""
    root = Path(root)
    cfg = load_chat_agent_config(root)
    text = str(user_text or "").strip()
    if not text:
        return {"ok": False, "reply_de": "Leere Eingabe.", "agent": True}

    from analytics.local_llm_bridge import chat_completion, health_report

    health = health_report(root)
    if not health.get("ready"):
        return {
            "ok": False,
            "reply_de": "Ollama nicht bereit — `python3 tools/ai_kernel.py llm-setup`",
            "agent": True,
        }

    prefetch = prefetch_context(root, text, cfg)
    try:
        from analytics.alpha_model_entfaltung_32b import SOVEREIGN_HISTORY_TURNS, chat_agent_limits, resolve_steps_limit

        lim = chat_agent_limits(root)
        steps_limit = resolve_steps_limit(
            configured=int(max_steps or lim.get("max_steps") or cfg.get("max_steps") or 12),
            role="chat",
        )
        history_turns = int(lim.get("history_turns") or cfg.get("history_turns") or SOVEREIGN_HISTORY_TURNS)
        msg_cap = 8000 if lim.get("sovereign") or cfg.get("free_unfold") else 2000
    except Exception:
        steps_limit = int(max_steps or cfg.get("max_steps") or 12)
        history_turns = int(cfg.get("history_turns") or 12)
        msg_cap = 2000
    system = str(cfg.get("system_prompt_de") or "").strip()
    prefetch_block = _format_prefetch_block(prefetch)
    if prefetch_block:
        system += "\n\n" + prefetch_block

    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    if history:
        for msg in history[-history_turns:]:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": str(msg["role"]), "content": str(msg["content"])[:msg_cap]})
    messages.append({"role": "user", "content": text})

    trace: List[Dict[str, Any]] = []
    reply_de = ""
    finished = False
    failed_actions: Dict[str, int] = {}
    agent_temp = float(cfg.get("agent_temperature") or 0.25)

    for step in range(1, steps_limit + 1):
        try:
            from analytics.r3_model_synergy import resolve_ollama_role

            chat_pick = resolve_ollama_role(root, text, mode="chat")
            chat_model = str(chat_pick.get("model") or "")
            raw, _meta = chat_completion(
                root,
                messages,
                model=chat_model or None,
                timeout_s=180.0,
                temperature=agent_temp,
                num_ctx=chat_pick.get("num_ctx"),
                role="chat",
            )
        except Exception as exc:
            doc = _finalize(
                root,
                text,
                trace,
                ok=False,
                reply_de=f"Chat-Agent Fehler: {exc}"[:500],
                prefetch=prefetch,
            )
            return doc

        action = parse_agent_step(raw)
        if not action:
            nudges = failed_actions.get("_json_nudge", 0)
            has_prefetch = bool(prefetch.get("grep_hits") or prefetch.get("kernel") or prefetch.get("explicit_paths"))
            if step <= 3 and nudges < 3:
                failed_actions["_json_nudge"] = nudges + 1
                trace.append({"step": step, "json_nudge": True, "preview": raw[:200]})
                messages.append({"role": "assistant", "content": raw[:2000]})
                hint = "evidence/alpha_model_king_handoff_latest.json"
                paths = prefetch.get("explicit_paths") or []
                if paths:
                    hint = str(paths[0])
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "König-Modus: Antworte NUR mit JSON tool+args — kein Freitext. "
                            f"Schritt 1: read_file auf {hint} oder grep. "
                            'Beispiel: {"thought_de":"…","tool":"read_file",'
                            f'"args":{{"path":"{hint}","start_line":1,"end_line":40}}}}'
                        ),
                    }
                )
                continue
            if has_prefetch:
                synth = _synthesize_from_prefetch(prefetch, text)
                if synth:
                    reply_de = synth
                    finished = True
                    trace.append({"step": step, "prefetch_synth": True})
                    break
            reply_de = _extract_reply_from_raw(raw)
            finished = True
            trace.append({"step": step, "direct_reply": True, "preview": reply_de[:300]})
            break

        action = _normalize_action(action)
        tool = str(action.get("tool") or "")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        thought = str(action.get("thought_de") or "")
        result = execute_chat_tool(root, tool, args, cfg)
        entry = {
            "step": step,
            "thought_de": thought,
            "tool": tool,
            "args": args,
            "ok": bool(result.get("ok")),
        }
        if result.get("output_de"):
            entry["output_preview"] = str(result["output_de"])[:200]
        if result.get("matches_de"):
            entry["matches_preview"] = str(result["matches_de"])[:200]
        if result.get("content"):
            entry["content_preview"] = str(result["content"])[:200]
        trace.append(entry)

        if tool == "reply" or result.get("finished"):
            read_tools = ("grep", "read_file", "list_dir", "kernel")
            has_read = any(t.get("tool") in read_tools for t in trace if t.get("tool"))
            early_reply = not has_read
            if early_reply:
                failed_actions["_read_first"] = failed_actions.get("_read_first", 0) + 1
                if failed_actions["_read_first"] <= 3:
                    trace.append({"step": step, "reply_blocked": True, "reason": "read_first"})
                    hint_path = ""
                    for hit in prefetch.get("grep_hits") or []:
                        m = str(hit.get("matches_de") or "")
                        if ":" in m:
                            hint_path = m.split(":", 1)[0].strip()
                            break
                    if not hint_path:
                        paths = prefetch.get("explicit_paths") or []
                        hint_path = str(paths[0]) if paths else "evidence/alpha_model_king_handoff_latest.json"
                    messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "König-Regel: reply erst nach grep/read_file/list_dir/kernel. "
                                f'Nächster Schritt: read_file "{hint_path}" oder grep, dann reply.'
                            ),
                        }
                    )
                    continue
            finished = True
            reply_de = str(result.get("reply_de") or thought or raw).strip()
            break

        akey = _action_key(tool, args)
        if not result.get("ok"):
            failed_actions[akey] = failed_actions.get(akey, 0) + 1
            retry_cap = 12 if cfg.get("free_unfold") else 3
            if failed_actions[akey] >= retry_cap:
                synth = _synthesize_from_prefetch(prefetch, text)
                reply_de = synth or (
                    f"`{tool}` wiederholt fehlgeschlagen — ich bleibe in der Session. "
                    f"Nächster Schritt: präzisiere die Frage oder `/bau {text[:100]}`."
                )
                finished = True
                trace.append({"step": step, "loop_break": True})
                break

        messages.append({"role": "assistant", "content": json.dumps(action, ensure_ascii=False)})
        messages.append(
            {
                "role": "user",
                "content": "Tool-Ergebnis:\n" + json.dumps(result, ensure_ascii=False)[:12000],
            }
        )

    if not reply_de and trace:
        synth = _synthesize_from_prefetch(prefetch, text)
        if synth:
            reply_de = synth
        else:
            last = trace[-1]
            reply_de = str(last.get("thought_de") or "Ich konnte die Anfrage nicht vollständig bearbeiten.")[:4000]
    if not reply_de:
        reply_de = (
            "Ich bin noch da — formuliere die Frage genauer oder nutze `/bau` für Code. "
            "Die Session läuft weiter."
        )

    reply_de = _append_limits_footer(
        reply_de, cfg, steps=len(trace), finished=finished, steps_limit=steps_limit
    )

    doc = _finalize(
        root,
        text,
        trace,
        ok=finished or bool(trace),
        reply_de=reply_de,
        finished=finished,
        prefetch=prefetch,
    )
    try:
        append_turn_to_archive(
            user_text=text,
            reply_de=reply_de,
            meta={"steps": len(trace), "finished": finished, "prefetch_terms": prefetch.get("terms")},
        )
    except Exception:
        pass
    return doc


def _finalize(
    root: Path,
    user_text: str,
    trace: List[Dict[str, Any]],
    *,
    ok: bool,
    reply_de: str,
    finished: bool = False,
    prefetch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    doc = {
        "schema_version": 2,
        "agent": "alpha_model_chat_agent",
        "ok": ok,
        "finished": finished,
        "user_text": user_text[:300],
        "reply_de": reply_de[:12000],
        "steps": len(trace),
        "trace": trace[-10:],
        "prefetch_terms": (prefetch or {}).get("terms"),
        "prefetch_hits": len((prefetch or {}).get("grep_hits") or []),
        "completed_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def chat_agent_status(root: Path) -> Dict[str, Any]:
    cfg = load_chat_agent_config(root)
    latest = _load_json(root / _EVIDENCE_REL)
    return {
        "enabled": cfg.get("enabled", True),
        "max_steps": cfg.get("max_steps"),
        "prefetch_enabled": cfg.get("prefetch_enabled", True),
        "tools": cfg.get("tools") or [],
        "bau_route_patterns": len(cfg.get("bau_route_patterns_de") or []),
        "last_reply_preview": str(latest.get("reply_de") or "")[:200],
        "last_steps": latest.get("steps"),
        "last_prefetch_hits": latest.get("prefetch_hits"),
        "completed_at_utc": latest.get("completed_at_utc"),
    }
