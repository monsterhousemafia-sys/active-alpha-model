"""32B Mandat — App-Konsolidierung (GPU/RAM/Redundanz)."""
from __future__ import annotations

from pathlib import Path

from analytics.local_apps_registry import build_local_apps_audit

_MANDATE_REL = Path("evidence/king_32b_consolidation_mandate.txt")


def build_32b_consolidation_mandate(root: Path) -> str:
    audit = build_local_apps_audit(root, persist=True, include_runtime=True)
    lines = [
        "König-Mandat: App-Konsolidierung — GPU/RAM/Port17890 entlasten.",
        f"Manifest v2: {audit.get('ok_count')}/{audit.get('total')} OK.",
        "Erledigt: Single-Instance Cockpit, Session hub-only, /desktop Standard, markt=1, system_panels=6→1.",
        "Prüfe: analytics/r3_cockpit_lock.py, control/local_apps_manifest.json, r3_session_autostart.sh.",
        "Kein zweites Qt-Fenster; welt→/launch im gleichen Cockpit; build-kernel nur king_32b_build_kernel.sh.",
        "Safety: fail-closed, dry_run, keine Orders, kein Champion-Wechsel.",
        "pytest: tests/test_r3_cockpit_lock.py tests/test_local_apps_registry.py tests/test_local_apps_runtime.py -q",
        "finish wenn Audit all_ok und kein paralleler Cockpit-Start möglich.",
    ]
    text = " ".join(lines)
    Path(root / _MANDATE_REL).write_text(text, encoding="utf-8")
    return text
