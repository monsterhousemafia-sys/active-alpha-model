"""Bash — ein einziges GPT-4o (Cloud-Key oder keyless via Ollama)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/bash_gpt4o.json")
_EVIDENCE_REL = Path("evidence/bash_gpt4o_latest.json")


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


def load_bash_gpt4o_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _CONFIG_REL)
    if doc:
        return doc
    return {
        "display_model": "gpt-4o",
        "openai_model": "gpt-4o",
        "local_ollama_model": "qwen2.5:14b",
        "keyless_ok": True,
    }


def bash_gpt4o_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_bash_gpt4o_config(root)
    has_key = False
    try:
        from analytics.alpha_model_advisor_bridge import resolve_advisor_key

        key, _src = resolve_advisor_key(root)
        has_key = bool(key)
    except Exception:
        has_key = False
    ollama_ready = False
    try:
        from analytics.local_llm_bridge import health_report

        ollama_ready = bool(health_report(root).get("ready"))
    except Exception:
        pass
    keyless = bool(cfg.get("keyless_ok")) and not has_key
    ready = has_key or (keyless and ollama_ready)
    mode = "openai_api" if has_key else ("ollama_keyless" if keyless and ollama_ready else "offline")
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "display_model": str(cfg.get("display_model") or "gpt-4o"),
        "ready": ready,
        "mode": mode,
        "ollama_ready": ollama_ready,
        "cloud_key": has_key,
        "local_model": str(cfg.get("local_ollama_model") or "qwen2.5:14b"),
        "headline_de": (
            f"GPT-4o bereit ({mode})"
            if ready
            else "GPT-4o offline — OPENAI_API_KEY oder Ollama (llm-setup)"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def bash_gpt4o_ask(root: Path, question: str, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_bash_gpt4o_config(root)
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "error_de": "Frage fehlt", "display_model": cfg.get("display_model")}
    status = bash_gpt4o_status(root)
    if not status.get("ready"):
        return {
            "ok": False,
            "error_de": status.get("headline_de") or "GPT-4o nicht bereit",
            "display_model": cfg.get("display_model"),
        }
    sys_prompt = str(cfg.get("system_prompt_de") or "GPT-4o Berater — Bash, Deutsch, fail-closed.")
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": q},
    ]
    display = str(cfg.get("display_model") or "gpt-4o")
    try:
        if status.get("mode") == "openai_api":
            from analytics.r3_external_advisor import _openai_chat

            answer, meta = _openai_chat(
                root,
                messages,
                model=str(cfg.get("openai_model") or "gpt-4o"),
                fallback_model=str(cfg.get("openai_model") or "gpt-4o"),
                max_tokens=int(cfg.get("max_tokens") or 1200),
                temperature=float(cfg.get("temperature") or 0.35),
            )
            provider = "openai"
            model_used = str(meta.get("model") or display)
        else:
            from analytics.local_llm_bridge import chat_completion

            local = str(cfg.get("local_ollama_model") or "qwen2.5:14b")
            answer, meta = chat_completion(
                root,
                messages,
                model=local,
                temperature=float(cfg.get("temperature") or 0.35),
                timeout_s=float(cfg.get("timeout_s") or 120.0),
            )
            provider = "ollama_keyless"
            model_used = display
        doc = {
            "ok": True,
            "question_de": q[:500],
            "answer_de": answer,
            "display_model": display,
            "model_used": model_used,
            "provider": provider,
            "updated_at_utc": _utc_now(),
        }
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, {**status, **doc})
        return doc
    except Exception as exc:
        return {
            "ok": False,
            "error_de": str(exc)[:300],
            "display_model": display,
            "question_de": q[:200],
        }


def format_bash_gpt4o_reply(doc: Dict[str, Any]) -> str:
    if not doc.get("ok"):
        return f"[GPT-4o] {doc.get('error_de') or 'Fehler'}"
    lines = [
        f"— GPT-4o ({doc.get('provider') or '—'}) —",
        str(doc.get("answer_de") or "").strip(),
        "—" * 44,
        "Bash-Berater — keine Orders.",
    ]
    return "\n".join(lines)
