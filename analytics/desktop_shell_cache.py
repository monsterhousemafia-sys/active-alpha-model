"""Schneller Desktop-Render + HTML-Cache für sichtbare /desktop-Oberfläche."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from aa_safe_io import atomic_write_bytes

_LOG = logging.getLogger(__name__)

_CACHE_REL = Path("evidence/desktop_shell_page_latest.html")
_META_REL = Path("evidence/desktop_shell_cache_meta.json")
_STALE_SEC = 300.0
def _mirror_evidence_paths() -> tuple[str, ...]:
    from analytics.r3_mirror_state import (
        EVIDENCE_BATCH,
        EVIDENCE_BOND,
        EVIDENCE_CYCLE,
        EVIDENCE_ENGINE,
        EVIDENCE_LOOP,
        EVIDENCE_ORDERS,
        EVIDENCE_PLAN,
        EVIDENCE_PREP,
        EVIDENCE_REEVAL,
        EVIDENCE_REFRESH,
        EVIDENCE_SCORE,
        EVIDENCE_SNAP,
        EVIDENCE_STACK,
    )

    return (
        str(EVIDENCE_PLAN),
        str(EVIDENCE_SNAP),
        str(EVIDENCE_REEVAL),
        str(EVIDENCE_PREP),
        str(EVIDENCE_ORDERS),
        str(EVIDENCE_BOND),
        str(EVIDENCE_BATCH),
        str(EVIDENCE_CYCLE),
        str(EVIDENCE_LOOP),
        str(EVIDENCE_ENGINE),
        str(EVIDENCE_SCORE),
        str(EVIDENCE_REFRESH),
        str(EVIDENCE_STACK),
        "evidence/king_trading_assist_latest.json",
        "evidence/r3_trading_functions_latest.json",
    )
_refresh_lock = threading.Lock()
_refreshing = False


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def cache_paths(root: Path) -> tuple[Path, Path]:
    root = Path(root)
    return root / _CACHE_REL, root / _META_REL


def mirror_evidence_max_mtime(root: Path) -> float:
    """Neueste Änderung an Mirror-Evidence (Live-Daten nach Neustart wieder sichtbar)."""
    root = Path(root)
    latest = 0.0
    for rel in _mirror_evidence_paths():
        path = root / rel
        if not path.is_file():
            continue
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def cache_stale_vs_evidence(root: Path) -> bool:
    """True wenn Evidence neuer ist als der HTML-Cache."""
    root = Path(root)
    cache_path, _ = cache_paths(root)
    if not cache_path.is_file():
        return True
    ev_mtime = mirror_evidence_max_mtime(root)
    if ev_mtime <= 0:
        return False
    try:
        return ev_mtime > cache_path.stat().st_mtime + 0.001
    except OSError:
        return True


def _cache_stale_sec(root: Path) -> float:
    try:
        from analytics.r3_runtime_upgrade import load_runtime_profile

        return float(load_runtime_profile(root).get("cache_stale_sec") or _STALE_SEC)
    except Exception:
        return _STALE_SEC


def read_cached_desktop_html(root: Path, *, max_age_sec: Optional[float] = None) -> Optional[bytes]:
    root = Path(root)
    if max_age_sec is None:
        max_age_sec = _cache_stale_sec(root)
    cache_path, meta_path = cache_paths(root)
    if not cache_path.is_file():
        return None
    meta = _load_json(meta_path)
    try:
        age = time.time() - cache_path.stat().st_mtime
    except OSError:
        return None
    if age > float(max_age_sec):
        return None
    if cache_stale_vs_evidence(root):
        return None
    try:
        body = cache_path.read_bytes()
    except OSError:
        return None
    return body if len(body) >= 120 else None


def write_desktop_cache(root: Path, body: bytes, *, fast: bool) -> None:
    root = Path(root)
    cache_path, meta_path = cache_paths(root)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(cache_path, body)
    from aa_safe_io import atomic_write_json

    atomic_write_json(
        meta_path,
        {
            "updated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "bytes": len(body),
            "fast": bool(fast),
            "evidence_max_mtime": mirror_evidence_max_mtime(root),
        },
    )


def render_desktop_shell_html(root: Path, *, port: int = 17890, fast: bool = True) -> bytes:
    from analytics.preview_hub_page import render_desktop_shell_page
    from analytics.r3_crash_guard import render_mirror_fallback_page

    try:
        body = render_desktop_shell_page(root, port=port, fast=fast)
        return body if isinstance(body, bytes) and len(body) >= 120 else render_mirror_fallback_page(
            "Leerer Desktop-Render", port=port
        )
    except Exception as exc:
        _LOG.exception("render_desktop_shell_html failed: %s", exc)
        return render_mirror_fallback_page(str(exc), port=port)


def warm_desktop_cache(
    root: Path,
    *,
    port: int = 17890,
    fast: bool = True,
    block: bool = False,
    live_prep: bool = False,
) -> int:
    """Desktop-HTML vorwärmen — Cockpit sieht sofort Inhalt."""

    def _run() -> None:
        global _refreshing
        with _refresh_lock:
            if _refreshing:
                return
            _refreshing = True
        try:
            if live_prep:
                try:
                    from analytics.r3_freigabe import auto_prepare_freigabe_for_desktop

                    auto_prepare_freigabe_for_desktop(root)
                except Exception as exc:
                    _LOG.warning("live_prep failed during warm: %s", exc)
            body = render_desktop_shell_html(root, port=port, fast=fast)
            if body:
                write_desktop_cache(root, body, fast=fast)
        except Exception as exc:
            _LOG.exception("warm_desktop_cache failed: %s", exc)
        finally:
            with _refresh_lock:
                _refreshing = False

    if block:
        _run()
        cache_path, _ = cache_paths(root)
        try:
            return len(cache_path.read_bytes()) if cache_path.is_file() else 0
        except OSError:
            return 0
    threading.Thread(target=_run, name="desktop-shell-warm", daemon=True).start()
    return 0


def get_desktop_html_for_hub(
    root: Path,
    *,
    port: int = 17890,
    fast: bool = True,
    allow_stale: bool = True,
    live_prep: bool = False,
) -> bytes:
    """Hub /r3|/desktop — schnelle Antwort; live_prep nur im Hintergrund (warm_desktop_cache)."""
    root = Path(root)
    if live_prep:
        try:
            from analytics.r3_freigabe import auto_prepare_freigabe_for_desktop

            auto_prepare_freigabe_for_desktop(root)
        except Exception as exc:
            _LOG.warning("live_prep failed on hub request: %s", exc)
        allow_stale = False

    if allow_stale:
        cached = read_cached_desktop_html(root)
        if cached:
            warm_desktop_cache(root, port=port, fast=fast, block=False, live_prep=False)
            return cached
        stale_path, _ = cache_paths(root)
        if stale_path.is_file() and not cache_stale_vs_evidence(root):
            try:
                stale = stale_path.read_bytes()
                if len(stale) >= 120:
                    warm_desktop_cache(root, port=port, fast=fast, block=False, live_prep=False)
                    return stale
            except OSError:
                pass
    try:
        body = render_desktop_shell_html(root, port=port, fast=fast)
        if body:
            write_desktop_cache(root, body, fast=fast)
        return body
    except Exception as exc:
        _LOG.exception("get_desktop_html_for_hub failed: %s", exc)
        from analytics.r3_crash_guard import render_mirror_fallback_page

        return render_mirror_fallback_page(str(exc), port=port)
