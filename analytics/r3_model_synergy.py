"""R3 — Modell-Synergie: Cloud-Berater + lokale Ollama-Rollen."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ADVISOR_REL = Path("control/r3_external_advisors.json")
_LLM_REL = Path("control/local_llm.json")

_DEEP_RE = re.compile(
    r"\b(architektur|refactor|strategie|warum|design|montag|pilot|fertig|"
    r"orchestrator|kernel|ersetzen|gesamt|roadmap|risiko|governance|h1)\b",
    re.IGNORECASE,
)
_PLAN_RE = re.compile(
    r"\b(bau|implement|code|test|pytest|fix|bug|schreib|datei|modul|api|ui|"
    r"cockpit|hub|kernel|refactor|debug)\b",
    re.IGNORECASE,
)
_TRADING_RE = re.compile(
    r"\b(aktie|aktien|trading|prognose|rebalance|portfolio|alpha|signal|t212|learn|steigen)\b",
    re.IGNORECASE,
)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def load_synergy_config(root: Path) -> Dict[str, Any]:
    adv = _load_json(Path(root) / _ADVISOR_REL)
    llm = _load_json(Path(root) / _LLM_REL)
    syn = adv.get("synergy") or {}
    return {
        "strategy_de": syn.get("strategy_de") or adv.get("primary_de"),
        "openai_tiers": syn.get("openai_tiers") or {},
        "ollama_roles": syn.get("ollama_roles") or llm.get("role_models") or {},
        "routing": syn.get("routing") or {},
        "pairs_de": syn.get("pairs_de") or [],
    }


def classify_task(question: str, *, mode: str = "tipp") -> str:
    q = str(question or "").strip()
    if not q:
        return "fast"
    if _DEEP_RE.search(q) or len(q) > 220:
        return "deep"
    if _TRADING_RE.search(q) and not _PLAN_RE.search(q):
        return "trading"
    if mode == "kombi" or _PLAN_RE.search(q):
        return "plan"
    return "fast"


def resolve_openai_tier(root: Path, question: str, *, mode: str = "tipp") -> Dict[str, Any]:
    root = Path(root)
    adv = _load_json(root / _ADVISOR_REL)
    oai = adv.get("openai") or {}
    tiers = (adv.get("synergy") or {}).get("openai_tiers") or {}
    task = classify_task(question, mode=mode)
    tier = tiers.get(task) or tiers.get("fast") or {}
    model = str(tier.get("model") or oai.get("model") or "gpt-4o-mini")
    fallback = str(
        tier.get("fallback")
        or oai.get("fallback_model")
        or ("gpt-4o" if model == "gpt-4o-mini" else "gpt-4o-mini")
    )
    return {
        "task": task,
        "tier": task,
        "model": model,
        "fallback_model": fallback,
        "role_de": str(tier.get("role_de") or _tier_label_de(task)),
        "max_tokens": int(tier.get("max_tokens") or oai.get("max_tokens") or 900),
        "temperature": float(tier.get("temperature") or oai.get("temperature") or 0.35),
    }


def _tier_label_de(task: str) -> str:
    return {
        "fast": "Schnell-Tipp (günstig)",
        "plan": "Bau-Planung (strukturiert)",
        "deep": "Tiefenanalyse (komplex)",
        "trading": "Trading-Strategie (Markt)",
    }.get(task, task)


def resolve_local_model_for_openai_tier(root: Path, tier: Dict[str, Any]) -> Dict[str, Any]:
    """Keyless GPT-4o: Cloud-Tier-Name bleibt, Ausführung über lokales Ollama-Modell."""
    root = Path(root)
    task = str(tier.get("task") or "fast")
    adv = _load_json(root / _ADVISOR_REL)
    oai = adv.get("openai") or {}
    local_map = dict(oai.get("local_tier_models") or {})
    defaults = {
        "fast": "qwen2.5:14b",
        "plan": "qwen2.5-coder:32b",
        "deep": "qwen2.5-coder:32b",
        "trading": "qwen2.5:14b",
    }
    role_by_task = {
        "fast": "chat",
        "plan": "build_kernel",
        "deep": "build_kernel",
        "trading": "trading_local",
    }
    preferred = str(local_map.get(task) or defaults.get(task) or defaults["fast"])
    role = role_by_task.get(task, "chat")
    llm = _load_json(root / _LLM_REL)
    resolved = preferred
    num_ctx: Optional[int] = None
    try:
        from analytics.local_llm_bridge import list_ollama_models, load_llm_config, resolve_model_options

        cfg = load_llm_config(root)
        base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
        installed = list_ollama_models(base)
        chain: List[str] = [preferred]
        role_fbs = (cfg.get("role_fallbacks") or {}).get(role) or []
        for fb in role_fbs:
            if fb and str(fb) not in chain:
                chain.append(str(fb))
        for fb in [llm.get("default_model"), *list(cfg.get("fallback_models") or [])]:
            if fb and str(fb) not in chain:
                chain.append(str(fb))
        for candidate in chain:
            if candidate in installed:
                resolved = candidate
                break
        if not resolved and installed:
            resolved = installed[0]
        opts = resolve_model_options(cfg, resolved or preferred)
        num_ctx = int(opts.get("num_ctx") or 0) or None
    except Exception:
        resolved = preferred
    return {
        "task": task,
        "role": role,
        "model": resolved or preferred,
        "preferred": preferred,
        "num_ctx": num_ctx,
        "display_model": str(tier.get("model") or "gpt-4o"),
        "keyless": True,
    }


def resolve_ollama_role(root: Path, question: str, *, mode: str = "chat") -> Dict[str, Any]:
    root = Path(root)
    llm = _load_json(root / _LLM_REL)
    roles = dict((_load_json(root / _ADVISOR_REL).get("synergy") or {}).get("ollama_roles") or {})
    roles.update(llm.get("role_models") or {})

    if mode == "kombi":
        role = "kombi_synthesis"
    elif mode == "build":
        role = "build_kernel"
    elif mode in ("trading", "trading_local"):
        role = "trading_local"
    else:
        task = classify_task(question, mode="chat")
        role = "trading_local" if task == "trading" else "chat"

    preferred = str(roles.get(role) or roles.get("chat") or llm.get("default_model") or "qwen2.5:7b")
    resolved = preferred
    num_ctx: Optional[int] = None
    try:
        from analytics.local_llm_bridge import list_ollama_models, load_llm_config, resolve_model_options

        cfg = load_llm_config(root)
        base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
        installed = list_ollama_models(base)
        chain: List[str] = []
        role_fbs = (cfg.get("role_fallbacks") or {}).get(role) or []
        if preferred:
            chain.append(preferred)
        for fb in role_fbs:
            if fb and fb not in chain:
                chain.append(str(fb))
        for fb in [roles.get("chat"), llm.get("default_model"), *list(cfg.get("fallback_models") or [])]:
            if fb and str(fb) not in chain:
                chain.append(str(fb))
        resolved = ""
        for candidate in chain:
            if candidate in installed:
                resolved = candidate
                break
        if not resolved and installed:
            resolved = installed[0]
        opts = resolve_model_options(cfg, resolved or preferred)
        num_ctx = int(opts.get("num_ctx") or 0) or None
    except Exception:
        resolved = preferred

    return {
        "role": role,
        "model": resolved or preferred,
        "preferred": preferred,
        "num_ctx": num_ctx,
        "role_de": {
            "chat": "Lokaler Chat + Kontext",
            "build_kernel": "Code schreiben/testen",
            "kombi_synthesis": "Cloud-Tipp + lokale Umsetzung",
            "trading_local": "Trading mit Evidence-Kontext",
        }.get(role, role),
    }


def build_synergy_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_synergy_config(root)
    tiers = cfg.get("openai_tiers") or {}
    roles = cfg.get("ollama_roles") or {}
    pairs = list(cfg.get("pairs_de") or [])
    if not pairs:
        pairs = [
            "Trading-Frage → DAILY_ALPHA_H1 (ML) + Ollama chat · Cloud nur Strategie",
            "Bau-Frage → Cloud plan (gpt-4o) → Ollama coder (qwen2.5-coder) ausführen",
            "Kurz-Tipp → gpt-4o-mini → Ollama qwen2.5:7b final (/kombi)",
            "Komplex → gpt-4o Berater → Ollama mit Evidence-Kontext",
        ]
    gem_tiers = (adv.get("synergy") or {}).get("gemini_tiers") or {}
    if not gem_tiers:
        gem_cfg = adv.get("gemini") or {}
        gem_tiers = {k: v.get("model") for k, v in (gem_cfg.get("tiers") or {}).items()}
    return {
        "strategy_de": cfg.get("strategy_de"),
        "gemini_tiers": gem_tiers,
        "openai_tiers": {k: v.get("model") if isinstance(v, dict) else v for k, v in tiers.items()},
        "ollama_roles": roles,
        "pairs_de": pairs,
        "why_not_only_mini_de": (
            "gpt-4o-mini war nur Default für Geschwindigkeit/Kosten — "
            "für Architektur, Pilot Day Trading und Bau-Pläne routet R3 jetzt auf gpt-4o; "
            "Ollama übernimmt Ausführung mit lokalem Projekt-Kontext."
        ),
    }


def format_synergy_reply_de(root: Path) -> str:
    st = build_synergy_status(root)
    lines = [
        "🔀 R3 Modell-Synergie",
        str(st.get("strategy_de") or ""),
        "",
        "Cloud (Gemini) — Rechenleistung, nicht Kernel:",
    ]
    for tier, model in (st.get("gemini_tiers") or {}).items():
        lines.append(f"  · {tier}: {model}")
    if st.get("openai_tiers"):
        lines.extend(["", "Fallback (OpenAI/keyless):"])
        for tier, model in (st.get("openai_tiers") or {}).items():
            lines.append(f"  · {tier}: {model}")
    lines.extend(["", "Lokal (Ollama) — Kernel + Ausführung:"])
    for role, model in (st.get("ollama_roles") or {}).items():
        lines.append(f"  · {role}: {model}")
    lines.extend(["", "Beste Paare:"])
    for p in st.get("pairs_de") or []:
        lines.append(f"  · {p}")
    lines.extend(["", str(st.get("why_not_only_mini_de") or "")])
    lines.extend(["", "Befehle: /kombi <frage> · /tipp <frage> · /geheimnis (ML, kein LLM)"])
    return "\n".join(lines)
