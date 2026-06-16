"""R3 — eine operative Oberfläche (EXEC_MIRROR_ONLY), keine Legacy-Bildschirme."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

SURFACE_RENDER_VERSION = "exec_mirror_v14"
CANONICAL_SURFACE_PATH = "/r3"
LEGACY_SURFACE_PATH = "/desktop"


def exec_mirror_mode(root: Path) -> bool:
    """Ein Schalter für EXEC_MIRROR_ONLY — schlanke UI, State, Polls, nur Paket-Button."""
    try:
        from analytics.local_apps_registry import is_exec_mirror_only

        return bool(is_exec_mirror_only(root))
    except Exception:
        return False


def is_exec_mirror_surface(root: Path) -> bool:
    return exec_mirror_mode(root)


def trading_functions_exec_only(root: Path) -> bool:
    """Kein Einzelaktien-Grid — nur Paket-Button im Exec-Spiegel."""
    return exec_mirror_mode(root)


def canonical_surface_path(root: Path) -> str:
    """Autoritative Hub-URL — immer /r3 im Spiegel-Modus."""
    if is_exec_mirror_surface(root):
        return CANONICAL_SURFACE_PATH
    try:
        from analytics.r3_runtime import default_surface_path as _legacy_default

        path = str(_legacy_default(root) or CANONICAL_SURFACE_PATH)
    except Exception:
        path = CANONICAL_SURFACE_PATH
    return path if path.startswith("/") else f"/{path}"


def resolve_hub_surface_path(root: Path, requested: str) -> str:
    """Legacy /desktop → /r3 im Spiegel-Modus."""
    req = str(requested or CANONICAL_SURFACE_PATH).strip() or CANONICAL_SURFACE_PATH
    if not req.startswith("/"):
        req = f"/{req}"
    if is_exec_mirror_surface(root) and req in (LEGACY_SURFACE_PATH, "/index.html", "/"):
        return CANONICAL_SURFACE_PATH
    return req


def surface_cache_meta(root: Path, *, fast: bool) -> Dict[str, Any]:
    return {
        "surface_render_version": SURFACE_RENDER_VERSION,
        "exec_mirror_only": exec_mirror_mode(root),
        "surface_path": canonical_surface_path(root),
        "fast": bool(fast),
    }


def surface_cache_valid(root: Path, meta: Dict[str, Any]) -> bool:
    if not meta:
        return False
    if str(meta.get("surface_render_version") or "") != SURFACE_RENDER_VERSION:
        return False
    if bool(meta.get("exec_mirror_only")) != is_exec_mirror_surface(root):
        return False
    expected = canonical_surface_path(root)
    if str(meta.get("surface_path") or "") not in ("", expected):
        return False
    return True
