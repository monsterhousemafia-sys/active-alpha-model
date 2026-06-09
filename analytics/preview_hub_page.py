"""Hub-Seiten — Preview-Report laden und Launch+Preview kombinieren."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


PREDICTION_SIGNAL_CSS = """
.pred-signal {
  margin-bottom: 22px; padding: 20px 22px; border-radius: var(--radius, 24px);
  border: 1px solid rgba(52,199,89,.22);
  background: linear-gradient(165deg, rgba(52,199,89,.08) 0%, var(--card) 55%);
}
.pred-signal h2 { margin: 0 0 8px; font-size: 20px; font-weight: 700; }
.pred-signal-meta { margin: 0 0 14px; font-size: 13px; color: var(--muted); }
.pred-signal table { width: 100%; border-collapse: collapse; font-size: 14px; }
.pred-signal th, .pred-signal td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--line); }
.pred-signal th { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.pred-signal tr:last-child td { border-bottom: 0; }
.pred-signal-warn { color: var(--warn); font-size: 13px; margin-top: 10px; }
.pred-signal-summary { margin: 0 0 12px; font-size: 13px; line-height: 1.45; color: var(--text); }
.pred-signal-engine { margin: 12px 0 0; font-size: 11px; color: var(--muted); }
.r3-only { border: none; background: transparent; padding: 0; margin: 0; }
"""


def render_prediction_signal_section(root: Path, *, desktop_only: bool = False) -> str:
    """R3 Handelsergebnis — auf /desktop nur R3, kein Engine-Hintergrund sichtbar."""
    try:
        from analytics.r3_t212_prognosis import render_r3_t212_prognosis_section

        return render_r3_t212_prognosis_section(root, desktop_only=desktop_only)
    except Exception:
        return ""


def _launch_doc_enriched(root: Path, *, fast: bool = True) -> Dict[str, Any]:
    from analytics.launch_progress_board import build_launch_status

    return build_launch_status(root, refresh_h1=not fast, persist=False)


def load_hub_preview_report(
    root: Path,
    *,
    port: int = 17890,
    request_host: Optional[str] = None,
    live_cockpit: bool = True,
) -> Dict[str, Any]:
    """Preview-Report für Hub — mit Manifest, Federation und Live-Cockpit."""
    root = Path(root)
    path = root / "evidence/gui_preview_latest.json"
    if path.is_file():
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                report = {}
        except (json.JSONDecodeError, OSError):
            report = {}
    else:
        report = {
            "overall_pass": False,
            "passed": 0,
            "total": 0,
            "report_de": "Noch kein Preview-Lauf — ai_kernel gui-preview",
        }

    try:
        from analytics.preview_manifest import load_preview_manifest

        report["manifest"] = load_preview_manifest(root)
    except Exception:
        pass

    try:
        from analytics.preview_federation import merge_federation_into_report

        report = merge_federation_into_report(root, report, request_host=request_host)
    except Exception:
        pass

    if live_cockpit:
        try:
            from analytics.preview_cockpit import build_preview_cockpit
            from ui.live_trading_dashboard.gui_preview_harness import _load_snap_for_gui

            snap = _load_snap_for_gui(root, None, allow_refresh=False)
            report["cockpit"] = build_preview_cockpit(root, snap=snap)
        except Exception:
            pass

    report["hub_port"] = int(port)
    return report


def render_world_launch_hub_page(
    root: Path,
    *,
    port: int = 17890,
) -> bytes:
    """Dedizierte Weltneuheit unter /launch."""
    from analytics.r3_launch_world import render_world_launch_page

    root = Path(root)
    return render_world_launch_page(_launch_doc_enriched(root), root, port=port)


def render_desktop_shell_page(
    root: Path,
    *,
    port: int = 17890,
    fast: bool = True,
) -> bytes:
    """Lokale R3-App — Spiegel der technischen Exekutive."""
    del fast
    from analytics.r3_exec_mirror import render_r3_exec_mirror_page

    return render_r3_exec_mirror_page(root, port=port)


def render_hub_launch_page(
    root: Path,
    *,
    port: int = 17890,
    request_host: Optional[str] = None,
) -> bytes:
    """Cockpit unter / — mit Weltneuheit-Hero oben."""
    from analytics.gui_preview_visual import render_gui_preview_html
    from analytics.hub_launch_ui import embed_launch_into_preview

    root = Path(root)
    launch_doc = _launch_doc_enriched(root)
    report = load_hub_preview_report(
        root, port=port, request_host=request_host, live_cockpit=False
    )
    preview_html = render_gui_preview_html(report, hub_port=port)
    html_out = embed_launch_into_preview(preview_html, launch_doc)
    return html_out.encode("utf-8")
