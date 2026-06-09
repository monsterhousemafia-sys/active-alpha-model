"""GUI-Oberflächen — Inventar und König-32B-Mandat für Neugestaltung."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_MANIFEST_REL = Path("control/gui_32b_rebuild_manifest.json")
_EVIDENCE_REL = Path("evidence/gui_32b_audit_latest.json")
_MANDATE_REL = Path("evidence/king_32b_gui_rebuild_mandate.txt")


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


def load_gui_manifest(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _MANIFEST_REL)


def audit_gui_surface(root: Path, surface: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    sid = str(surface.get("id") or "")
    label = str(surface.get("label_de") or sid)
    tier = str(surface.get("tier") or "hub")
    modules = [str(m) for m in (surface.get("modules") or []) if m]
    missing = [m for m in modules if not (root / m).is_file()]
    issues: List[str] = []
    ok = True
    if missing:
        ok = False
        issues.append(f"Module fehlen: {', '.join(missing[:3])}")
    hub_path = str(surface.get("path") or "").strip()
    if hub_path and tier == "hub":
        page_py = root / "analytics/preview_hub_page.py"
        if not page_py.is_file():
            ok = False
            issues.append("preview_hub_page.py fehlt")
    if sid == "hub_nav":
        ident = root / "control/r3_surface_identity.json"
        theme = root / "analytics/r3_surface_theme.py"
        if not ident.is_file() or not theme.is_file():
            ok = False
            issues.append("Theme/Identity fehlt")
    return {
        "id": sid,
        "tier": tier,
        "label_de": label,
        "path": hub_path or None,
        "ok": ok,
        "issues_de": issues,
        "detail_de": "OK" if ok and not issues else (issues[0] if issues else "Prüfen"),
    }


def build_gui_32b_audit(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    manifest = load_gui_manifest(root)
    surfaces_in = list(manifest.get("surfaces") or [])
    audited = [audit_gui_surface(root, row) for row in surfaces_in if isinstance(row, dict)]
    ok_n = sum(1 for a in audited if a.get("ok"))
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": manifest.get("headline_de"),
        "design_ref": manifest.get("design_ref"),
        "total": len(audited),
        "ok_count": ok_n,
        "fail_count": len(audited) - ok_n,
        "all_ok": ok_n == len(audited) and len(audited) > 0,
        "surfaces": audited,
        "tests_de": list(manifest.get("tests_de") or []),
        "next_de": "bash tools/king_ops.sh gui-rebuild",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_32b_gui_mandate(root: Path) -> str:
    root = Path(root)
    manifest = load_gui_manifest(root)
    audit = build_gui_32b_audit(root, persist=True)
    principles = list(manifest.get("principles_de") or [])
    tests = list(manifest.get("tests_de") or audit.get("tests_de") or [])
    surfaces = list(manifest.get("surfaces") or [])
    remaster_block = ""
    try:
        from analytics.gui_remaster_gate import build_remaster_mandate_block, verify_remaster_invariants

        verify_remaster_invariants(root)
        remaster_block = build_remaster_mandate_block(root)
    except Exception:
        remaster_block = "VERBINDLICH Remaster 2026 — siehe control/gui_remaster_2026_policy.json"
    primary = str(manifest.get("primary_surface_de") or "Exec-Spiegel /r3")
    lines = [
        "König-Mandat Remaster 2026: Optischer Bauprozess — NUR König 32B, NICHT Cursor.",
        remaster_block,
        f"PRIORITÄT: {primary}",
        f"Audit Module: {audit.get('ok_count')}/{audit.get('total')} vorhanden.",
        f"Lies control/gui_remaster_2026_policy.json, {manifest.get('design_ref') or 'control/r3_surface_identity.json'}, control/r3_pc_app_disposition.json, evidence/gui_32b_audit_latest.json.",
        "Ziel: Ein Look — Typo, Farben, Spacing auf /r3 Exec-Spiegel. Hub-HTML + Qt-native, kein zweites Design.",
        "VERBOTEN: Shell-Kacheln, Einzelaktien-Grid, Gutachter-UI — EXEC_MIRROR_ONLY.",
    ]
    for p in principles[:5]:
        lines.append(f"Prinzip: {p}")
    lines.append("Oberflächen (jede visuell vereinheitlichen):")
    for surf in surfaces:
        mods = ", ".join((surf.get("modules") or [])[:2])
        lines.append(f"- {surf.get('id')}: {surf.get('label_de')} — {mods}")
    mandatory = "tests/test_gui_remaster_2026_policy.py"
    lines.extend(
        [
            "Schreibe nur analytics/, tools/, ui/, tests/, control/, aa_dashboard_qt_window.py, aa_qt_render.py.",
            "PFLICHT: render_desktop_shell_page(fast=True) und analytics/desktop_shell_cache.py unangetastet lassen oder schneller machen.",
            "Nach jedem write_file: .venv/bin/python -m pytest tests/test_gui_remaster_2026_policy.py -q",
            "Nav und CSS nur aus analytics/r3_surface_theme.py (R3_CSS_ROOT) — forbidden_surface_words beachten.",
            f"Vor finish: pytest {mandatory} tests/test_desktop_shell_cache.py -q — evidence/gui_remaster_acceptance_latest.json ok=true.",
            "finish nur wenn Remaster-Invarianten grün. Cursor liefert keine GUI — nur Bridge-request_de.",
        ]
    )
    text = " ".join(lines)
    atomic_write_json(
        root / Path("evidence/gui_32b_rebuild_latest.json"),
        {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "mandate_de": text[:4000],
            "audit": {"ok_count": audit.get("ok_count"), "total": audit.get("total")},
        },
    )
    (root / _MANDATE_REL).write_text(text, encoding="utf-8")
    return text


def render_gui_rebuild_banner(root: Path) -> str:
    """Kurz-Hinweis auf /desktop — 32B GUI-Rebuild."""
    doc = build_gui_32b_audit(root, persist=False)
    ok_n = int(doc.get("ok_count") or 0)
    total = int(doc.get("total") or 0)
    return f"""
<div class="gui-32b-banner" id="gui-32b-rebuild" style="margin:12px 0;padding:12px 16px;border-radius:14px;border:1px solid rgba(94,92,230,.35);background:rgba(94,92,230,.08)">
  <strong>GUI-Neugestaltung (32B)</strong>
  <span style="color:var(--muted);margin-left:8px">{ok_n}/{total} Module bereit</span>
  <p style="margin:6px 0 0;font-size:12px;color:var(--muted)">König baut Remaster: <code>bash tools/king_ops.sh gui-rebuild</code></p>
</div>"""


GUI_REBUILD_BANNER_CSS = ".gui-32b-banner code { font-size: 11px; }"
