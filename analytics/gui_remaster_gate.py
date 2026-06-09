"""Remaster 2026 — Acceptance-Gate für König-32B-GUI (nicht Cursor)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/gui_remaster_2026_policy.json")
_ACCEPTANCE_REL = Path("evidence/gui_remaster_acceptance_latest.json")


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


def load_remaster_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def verify_remaster_invariants(root: Path) -> Dict[str, Any]:
    """Prüft verbindliche Remaster-2026-Invarianten — Gate vor/nach build-kernel."""
    root = Path(root)
    policy = load_remaster_policy(root)
    checks: List[Dict[str, Any]] = []

    def add(cid: str, label: str, ok: bool, detail: str) -> None:
        checks.append({"id": cid, "label_de": label, "ok": ok, "detail_de": detail})

    theme = root / "analytics/r3_surface_theme.py"
    ident = root / (policy.get("design_ref") or "control/r3_surface_identity.json")
    cache_py = root / (policy.get("cache_module") or "analytics/desktop_shell_cache.py")
    hub_page = root / "analytics/preview_hub_page.py"

    add("theme", "R3 Surface Theme", theme.is_file(), str(theme))
    add("identity", "Surface Identity", ident.is_file(), str(ident))
    add("cache", "Desktop Shell Cache", cache_py.is_file(), str(cache_py))

    fast_ok = False
    hub_handler = root / "tools/preview_hub.py"
    if hub_page.is_file() and cache_py.is_file():
        page_text = hub_page.read_text(encoding="utf-8", errors="ignore")
        hub_text = hub_handler.read_text(encoding="utf-8", errors="ignore") if hub_handler.is_file() else ""
        fast_ok = (
            "fast: bool = True" in page_text
            and ("get_desktop_html_for_hub" in hub_text or "desktop_shell_cache" in hub_text)
        )
    add("fast_render", "/desktop fast=True + cache", fast_ok, "preview_hub_page + preview_hub cache")

    bridge = _load_json(root / "evidence/alpha_model_cursor_king_bridge_latest.json")
    king_req = str((bridge.get("last_king_push") or {}).get("request_de") or "")
    add(
        "bridge_king",
        "Bridge: König führt GUI",
        "32B" in king_req or "build-kernel" in king_req or "GUI" in king_req,
        king_req[:120] or "request_de fehlt",
    )

    for mod in list(policy.get("mandatory_modules") or [])[:8]:
        p = root / str(mod)
        add(f"mod_{Path(mod).stem}", f"Modul {mod}", p.is_file(), "OK" if p.is_file() else "fehlt")

    safety_ok = True
    for rel in (
        "control/promotion_gate_config.yaml",
        "control/operational_champion.json",
    ):
        p = root / rel
        if not p.is_file():
            continue
        try:
            body = p.read_text(encoding="utf-8", errors="ignore").lower()
            if "auto_execute_real_money_enabled" in body and "true" in body.split("auto_execute_real_money_enabled")[-1][:40]:
                safety_ok = False
        except OSError:
            pass
    add("safety", "Safety fail-closed", safety_ok, "keine Real-Money-Auto-Flags")

    ok_n = sum(1 for c in checks if c.get("ok"))
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "edition_de": policy.get("edition_de") or "Remaster 2026",
        "owner_de": policy.get("owner_de"),
        "ok": ok_n == len(checks) and len(checks) > 0,
        "ok_count": ok_n,
        "total": len(checks),
        "checks": checks,
        "invariants_de": list(policy.get("invariants_de") or []),
        "finish_gate_de": policy.get("finish_gate_de"),
    }
    atomic_write_json(root / _ACCEPTANCE_REL, doc)
    return doc


def measure_desktop_render_ms(root: Path, *, fast: bool = True) -> float:
    from analytics.desktop_shell_cache import render_desktop_shell_html

    start = time.monotonic()
    render_desktop_shell_html(Path(root), fast=fast)
    return (time.monotonic() - start) * 1000.0


def build_remaster_mandate_block(root: Path) -> str:
    """Verbindlicher Textblock für build-kernel — König 32B only."""
    policy = load_remaster_policy(root)
    lines = [
        "VERBINDLICH Remaster 2026 — nur König 32B, nicht Cursor.",
        f"Policy: control/gui_remaster_2026_policy.json",
    ]
    for inv in policy.get("invariants_de") or []:
        lines.append(f"INVARIANT: {inv}")
    for forb in policy.get("forbidden_de") or []:
        lines.append(f"VERBOTEN: {forb}")
    lines.append(
        "Vor finish: run_command "
        + " ".join((policy.get("mandatory_tests") or ["tests/test_gui_remaster_2026_policy.py"])[:2])
        + " -q"
    )
    lines.append(str(policy.get("finish_gate_de") or ""))
    lines.append("Cursor: nur Diffs bei konkretem bridge last_king_push.request_de.")
    return " ".join(x for x in lines if x)
