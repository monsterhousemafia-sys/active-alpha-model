"""Alpha Model growth surfaces — Runtime (Produkt) vs. Workshop (Cursor-Entwicklung)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_CONFIG_REL = Path("control/alpha_model_growth.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_growth_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _CONFIG_REL)
    if doc:
        return doc
    return {
        "product_name": "Alpha Model",
        "variant": "growth_v1",
        "surfaces": {
            "runtime": {"label_de": "Alpha Model", "wm_class": "AlphaModel"},
            "workshop": {"label_de": "Alpha Model — Werkstatt", "wm_class": "AlphaModelWorkshop"},
            "agent_chamber": {"label_de": "Alpha Model — Entfaltungsraum", "wm_class": "AlphaModelAgent"},
        },
    }


def surface(root: Path, surface_id: str) -> Dict[str, Any]:
    cfg = load_growth_config(root)
    surfaces = cfg.get("surfaces") or {}
    raw = surfaces.get(surface_id)
    return dict(raw) if isinstance(raw, dict) else {}


def product_name(root: Path) -> str:
    cfg = load_growth_config(root)
    return str(cfg.get("product_name") or "Alpha Model")


def runtime_label(root: Path) -> str:
    return str(surface(root, "runtime").get("label_de") or product_name(root))


def workshop_label(root: Path) -> str:
    return str(surface(root, "workshop").get("label_de") or f"{product_name(root)} — Werkstatt")


def agent_chamber_label(root: Path) -> str:
    return str(
        surface(root, "agent_chamber").get("label_de")
        or "Alpha Model — Entfaltungsraum"
    )


def wm_class(root: Path, surface_id: str) -> str:
    return str(surface(root, surface_id).get("wm_class") or "AlphaModel")


def growth_headline_de(root: Path) -> str:
    return str(load_growth_config(root).get("headline_de") or "")


def cursor_chat_purpose_de(root: Path) -> str:
    cfg = load_growth_config(root)
    return str(
        cfg.get("cursor_chat_purpose_de")
        or "Alpha Model Werkstatt — Entwicklung & Wachstum"
    )
