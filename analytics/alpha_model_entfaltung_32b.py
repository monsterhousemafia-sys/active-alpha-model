"""Entfaltungsraum Ideal-32B — Tier-Profil, Preload, Banner."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/alpha_model_entfaltung_32b.json")
_EVIDENCE_REL = Path("evidence/alpha_model_entfaltung_32b_latest.json")

SOVEREIGN_MAX_STEPS = 128
SOVEREIGN_HARD_CAP = 256
SOVEREIGN_HISTORY_TURNS = 64


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


def load_tier_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {
        "tier_id": "ideal_32b",
        "build_kernel": {"model": "qwen2.5-coder:32b", "max_steps": SOVEREIGN_MAX_STEPS, "num_ctx": 8192},
    }


def is_sovereign_chamber() -> bool:
    try:
        from analytics.alpha_model_agent_home import is_agent_chamber_active

        return is_agent_chamber_active()
    except Exception:
        return os.environ.get("AA_AGENT_CHAMBER", "").strip().lower() in ("1", "true", "yes")


def resolve_steps_limit(*, configured: Optional[int] = None, role: str = "chat") -> int:
    """König im Entfaltungsraum: hohe Deckel, AA_AGENT_MAX_STEPS=0 → Hard-Cap 256."""
    env = os.environ.get("AA_AGENT_MAX_STEPS", "").strip().lower()
    if env in ("0", "unlimited", "none"):
        return SOVEREIGN_HARD_CAP
    if env.isdigit():
        return min(int(env), SOVEREIGN_HARD_CAP)
    fallback = int(configured or (SOVEREIGN_MAX_STEPS if role == "build" else SOVEREIGN_MAX_STEPS))
    if is_sovereign_chamber():
        return max(fallback, SOVEREIGN_MAX_STEPS)
    return int(configured or (14 if role == "build" else 12))


def tier_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    tier = load_tier_config(root)
    from analytics.local_llm_bridge import health_report
    from analytics.r3_model_synergy import resolve_ollama_role

    health = health_report(root)
    installed = set(health.get("installed_models") or [])
    build_pick = resolve_ollama_role(root, "", mode="build")
    chat_pick = resolve_ollama_role(root, "", mode="chat")
    pull_order = list(tier.get("pull_order") or [])
    missing = [m for m in pull_order if m not in installed]
    build_model = str(build_pick.get("model") or "")
    chat_model = str(chat_pick.get("model") or "")
    ideal_build = str((tier.get("build_kernel") or {}).get("model") or "qwen2.5-coder:32b")
    ideal_chat = str((tier.get("chat_agent") or {}).get("model") or ideal_build)
    return {
        "tier_id": tier.get("tier_id") or "ideal_32b",
        "tier_de": tier.get("tier_de"),
        "headline_de": tier.get("headline_de"),
        "ideal_build_model": ideal_build,
        "ideal_chat_model": ideal_chat,
        "resolved_build_model": build_model,
        "resolved_chat_model": chat_model,
        "build_32b_active": build_model == ideal_build,
        "chat_32b_active": chat_model == ideal_chat,
        "missing_models": missing,
        "tier_ready": not missing,
        "build_pick": build_pick,
        "chat_pick": chat_pick,
        "setup_command": tier.get("setup_command"),
        "operator_hints_de": tier.get("operator_hints_de") or [],
    }


def render_chamber_banner(root: Path) -> str:
    st = tier_status(root)
    tier = load_tier_config(root)
    tier_de = str(st.get("tier_de") or "Ideal-32B")
    chat = st.get("resolved_chat_model") or "?"
    build = st.get("resolved_build_model") or "?"
    if st.get("tier_ready"):
        mark = "✓"
        extra = f"Bash+Slash · {chat} · /h1-benchmark /könig-puls"
    else:
        mark = "⚠"
        miss = ", ".join(st.get("missing_models") or []) or "Modelle fehlen"
        extra = f"{st.get('setup_command')} — fehlt: {miss}"
    return f"König · {tier_de} {mark} · {extra} · /quit · /hilfe"


def preload_ollama_model(
    root: Path,
    model: str,
    *,
    num_ctx: Optional[int] = None,
    keep_alive: str = "15m",
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Lädt Modell in VRAM vor /bau (Coder-32B Cold-Start vermeiden)."""
    from analytics.local_llm_bridge import load_llm_config, resolve_model_options

    root = Path(root)
    cfg = load_llm_config(root)
    base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    model = str(model or "").strip()
    if not model:
        return {"ok": False, "error_de": "Modell fehlt"}
    ctx = int(num_ctx if num_ctx is not None else resolve_model_options(cfg, model).get("num_ctx") or 8192)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ok"}],
        "stream": False,
        "keep_alive": keep_alive,
        "options": {"num_ctx": ctx, "temperature": 0.1},
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{base.rstrip('/')}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        return {
            "ok": True,
            "model": model,
            "num_ctx": ctx,
            "keep_alive": keep_alive,
            "preloaded": True,
            "eval_count": (doc.get("eval_count") or 0),
        }
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"ok": False, "model": model, "error_de": str(exc)[:300]}


def preload_build_model(root: Path) -> Dict[str, Any]:
    tier = load_tier_config(root)
    bk = tier.get("build_kernel") or {}
    if bk.get("preload_before_bau") is False:
        return {"ok": True, "skipped": True}
    from analytics.r3_model_synergy import resolve_ollama_role

    pick = resolve_ollama_role(root, "", mode="build")
    model = str(pick.get("model") or bk.get("model") or "")
    return preload_ollama_model(
        root,
        model,
        num_ctx=pick.get("num_ctx") or bk.get("num_ctx"),
        keep_alive=str(bk.get("keep_alive") or "15m"),
        timeout_s=float(bk.get("preload_timeout_s") or 180.0),
    )


def apply_tier_to_llm_config(root: Path) -> Dict[str, Any]:
    """Synchronisiert local_llm.json mit Ideal-32B Profil."""
    root = Path(root)
    tier = load_tier_config(root)
    llm_path = root / "control/local_llm.json"
    llm = _load_json(llm_path)
    preserved = {
        k: llm[k]
        for k in (
            "context_files",
            "context_files_king",
            "bash_primary",
            "system_prompt_de",
            "max_context_chars",
            "agent_name",
            "layer",
            "matrix_ref",
            "network_ref",
        )
        if k in llm
    }
    roles = tier.get("role_models") or {}
    if roles:
        llm["role_models"] = {**(llm.get("role_models") or {}), **roles}
    llm["gpu_tier_de"] = tier.get("tier_id") or "ideal_32b"
    llm["hardware_note_de"] = tier.get("hardware_de")
    llm["note_de"] = tier.get("headline_de")
    llm["setup_command"] = tier.get("setup_command")
    bk = tier.get("build_kernel") or {}
    chat = tier.get("chat_agent") or {}
    opts = dict(llm.get("role_model_options") or {})
    build_m = str(bk.get("model") or "qwen2.5-coder:32b")
    chat_m = str(chat.get("model") or build_m)
    opts[build_m] = {
        "num_ctx": int(bk.get("num_ctx") or 8192),
        "temperature": float(bk.get("temperature") or 0.2),
        "max_steps": int(bk.get("max_steps") or SOVEREIGN_MAX_STEPS),
    }
    opts[chat_m] = {
        "num_ctx": int(chat.get("num_ctx") or 16384),
        "temperature": float(chat.get("temperature") or 0.25),
    }
    llm["role_model_options"] = opts
    llm["pull_models"] = list(tier.get("pull_order") or llm.get("pull_models") or [])
    llm.update(preserved)
    llm["upgraded_at_utc"] = _utc_now()
    llm["upgraded_by_de"] = "ideal_32b tier"
    atomic_write_json(llm_path, llm)
    chat_cfg_path = root / "control/alpha_model_chat_agent.json"
    chat_cfg = _load_json(chat_cfg_path)
    if chat_cfg and chat:
        chat_cfg["max_steps"] = int(chat.get("max_steps") or SOVEREIGN_MAX_STEPS)
        chat_cfg["history_turns"] = int(chat.get("history_turns") or SOVEREIGN_HISTORY_TURNS)
        chat_cfg["prefetch_kernel_in_chamber"] = False
        chat_cfg["free_unfold"] = bool(chat.get("free_unfold", True))
        atomic_write_json(chat_cfg_path, chat_cfg)
    doc = {"ok": True, "tier": tier_status(root), "ran_at_utc": _utc_now()}
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def chat_agent_limits(root: Path) -> Dict[str, Any]:
    tier = load_tier_config(root)
    chat = tier.get("chat_agent") or {}
    try:
        from analytics.alpha_model_chat_agent import load_chat_agent_config

        cfg = load_chat_agent_config(root)
    except Exception:
        cfg = {}
    configured_steps = int(chat.get("max_steps") or cfg.get("max_steps") or SOVEREIGN_MAX_STEPS)
    configured_history = int(chat.get("history_turns") or cfg.get("history_turns") or SOVEREIGN_HISTORY_TURNS)
    sovereign = is_sovereign_chamber()
    model = str(chat.get("model") or "qwen2.5-coder:32b")
    try:
        from analytics.r3_model_synergy import resolve_ollama_role

        model = str(resolve_ollama_role(root, "", mode="chat").get("model") or model)
    except Exception:
        pass
    return {
        "max_steps": resolve_steps_limit(configured=configured_steps, role="chat"),
        "history_turns": configured_history,
        "temperature": float(chat.get("temperature") or cfg.get("agent_temperature") or 0.25),
        "free_unfold": bool(chat.get("free_unfold", cfg.get("free_unfold", True))),
        "sovereign": sovereign,
        "model": model,
    }


def build_kernel_limits(root: Path) -> Dict[str, Any]:
    tier = load_tier_config(root)
    bk = tier.get("build_kernel") or {}
    from analytics.r3_build_kernel import load_kernel_config

    kcfg = load_kernel_config(root)
    configured_steps = int(bk.get("max_steps") or kcfg.get("max_steps") or SOVEREIGN_MAX_STEPS)
    return {
        "max_steps": resolve_steps_limit(configured=configured_steps, role="build"),
        "temperature": float(bk.get("temperature") or 0.2),
        "timeout_s": float(bk.get("timeout_s") or 420.0),
        "model": str(bk.get("model") or "qwen2.5-coder:32b"),
        "sovereign": is_sovereign_chamber(),
    }
