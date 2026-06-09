"""Unified product identity — Alpha Model (KI lokal + Cockpit = one system)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_CONFIG_REL = Path("control/active_alpha_unified.json")
_KERNEL_REL = Path("control/AI_KERNEL.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_kernel_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _KERNEL_REL)


def load_unified_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = _load_json(root / _CONFIG_REL)
    kernel = load_kernel_config(root)
    if cfg:
        if kernel:
            cfg = {**cfg, "kernel": kernel}
        return cfg
    return {
        "product_name": "Alpha Model",
        "agent_name": "Auto",
        "tagline_de": "Quantitatives Entscheidungs-Cockpit — lokale KI und Handel in einem System.",
        "surfaces": {
            "r3_ki": {
                "label_de": "Alpha Model KI (lokal)",
                "role_de": "Gespräch, ai_kernel, Ollama",
            },
            "marktanalyse_app": {
                "label_de": "Alpha Model Cockpit",
                "role_de": "Live-Status, Orders mit Bestätigung",
            },
        },
        "window_title": "Alpha Model",
    }


def product_name(root: Path) -> str:
    return str(load_unified_config(root).get("product_name") or "Alpha Model")


def unified_intro_de(root: Path) -> str:
    cfg = load_unified_config(root)
    chat = (cfg.get("surfaces") or {}).get("r3_ki") or {}
    dash = (cfg.get("surfaces") or {}).get("marktanalyse_app") or {}
    name = product_name(root)
    lines = [
        f"{name} — {cfg.get('tagline_de', '')}",
        f"• {chat.get('label_de', 'R3 KI')}: {chat.get('role_de', '')}",
        f"• {dash.get('label_de', 'Dashboard')}: {dash.get('role_de', '')}",
    ]
    return "\n".join(lines)


def window_title(root: Path) -> str:
    return str(load_unified_config(root).get("window_title") or "Alpha Model")


def unified_rules(root: Path) -> List[str]:
    return list(load_unified_config(root).get("unified_rules_de") or [])


def status_line_de(root: Path, *, surface: str = "marktanalyse_app") -> str:
    cfg = load_unified_config(root)
    kernel = _load_json(root / _KERNEL_REL)
    agent = cfg.get("agent_name") or "Auto"
    product = product_name(root)
    role = kernel.get("agent_role") or "Lernen und vorbereiten"
    surf = (cfg.get("surfaces") or {}).get(surface) or {}
    return f"{product} · {surf.get('label_de', 'Dashboard')} · {agent}: {role}"
