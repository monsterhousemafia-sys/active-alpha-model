#!/usr/bin/env python3
"""GUI Preview — stabiler Tages-Check (Backend + Chat + Offscreen-GUI)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(
        description="R3 GUI Preview — Cockpit-Report (kein T212-Refresh ohne Grund)"
    )
    p.add_argument("--backend-only", action="store_true", help="Nur Daten/Evidence, kein Qt/Chat")
    p.add_argument(
        "--refresh",
        action="store_true",
        help="T212/Quote-Snapshot erzwingen (langsamer, nur bei Bedarf)",
    )
    p.add_argument("--screenshot", action="store_true", help="PNG nach evidence/gui_preview_screenshot.png")
    p.add_argument(
        "--open",
        action="store_true",
        help="Nach den Tests echtes Dashboard-Fenster öffnen (braucht DISPLAY)",
    )
    p.add_argument("--json", action="store_true", help="Nur JSON ausgeben")
    p.add_argument("--skip-chat", action="store_true", help="Kein Ollama-Chat (nur evolve)")
    p.add_argument(
        "--force",
        action="store_true",
        help="Preview auch wenn letzter Lauf <20 min (Dedup aus)",
    )
    p.add_argument(
        "--open-html",
        action="store_true",
        help="Command Center im Browser öffnen (Hub + interaktive Aktionen)",
    )
    p.add_argument(
        "--hub",
        action="store_true",
        help="Preview-Hub starten (mit --open-html Standard)",
    )
    p.add_argument("--no-hub", action="store_true", help="Nur statische HTML-Datei (ohne Aktionen)")
    p.add_argument("--hub-port", type=int, default=17890)
    p.add_argument(
        "--hub-url-path",
        default="/",
        help="Hub-Pfad nach Start (z.B. /launch für Weltneuheit)",
    )
    args = p.parse_args()

    root = Path(os.environ.get("AA_PROJECT_ROOT", "").strip() or ROOT)
    from analytics.preview_freshness import mark_gui_preview_done, should_skip_gui_preview
    from ui.live_trading_dashboard.gui_preview_harness import run_full_gui_preview

    skip, cached = should_skip_gui_preview(root, force=args.force)
    if skip and cached:
        cached = dict(cached)
        cached["skipped"] = True
        cached["skip_reason_de"] = "Letzter Preview <20 min — Dedup (mit --force erneut)"
        if args.json:
            print(json.dumps(cached, indent=2, ensure_ascii=False))
        else:
            print(cached.get("report_de") or "")
            print(f"\n[SKIP] {cached['skip_reason_de']}")
            print(f"Evidence: {root / 'evidence/gui_preview_latest.json'}")
            vp = cached.get("visual_paths") or {}
            if vp.get("html"):
                print(f"Visual:  {vp['html']}")
        if args.open_html:
            _open_preview_html(root, cached, hub=not args.no_hub, hub_port=args.hub_port)
        return 0

    # Stabil: kein Netzwerk-Refresh unless --refresh
    refresh_snap = bool(args.refresh)

    report = run_full_gui_preview(
        root,
        backend_only=args.backend_only,
        refresh_snap=refresh_snap,
        screenshot=args.screenshot,
        skip_chat=args.skip_chat,
        mode="stable",
    )
    if report.get("overall_pass"):
        mark_gui_preview_done(root, mode="stable")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(report.get("report_de") or "")
        print(f"\nEvidence: {root / 'evidence/gui_preview_latest.json'}")
        vp = report.get("visual_paths") or {}
        if vp.get("html"):
            print(f"Visual:  {vp['html']}")
        if vp.get("home_html"):
            print(f"Öffnen:  file://{vp['home_html']}")

    if args.open_html:
        _open_preview_html(
            root,
            report,
            hub=not args.no_hub,
            hub_port=args.hub_port,
            hub_path=str(args.hub_url_path or "/"),
        )

    if args.open:
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            print("\n[--open] Kein DISPLAY — übersprungen.")
        else:
            print("\n[--open] Dashboard-Fenster öffnen …")
            from aa_pilot_launch import bootstrap_live_trading_runtime, launch_ui

            bootstrap_live_trading_runtime(root)
            os.environ.pop("AA_GUI_PREVIEW", None)
            return launch_ui(root)

    return 0 if report.get("overall_pass") else 1


def _open_preview_html(
    root: Path,
    report: dict,
    *,
    hub: bool = True,
    hub_port: int = 17890,
    hub_path: str = "/",
) -> None:
    import subprocess

    vp = report.get("visual_paths") or {}
    if not vp.get("html"):
        try:
            from analytics.gui_preview_visual import write_gui_preview_html

            vp = write_gui_preview_html(root, report)
        except Exception:
            pass

    if hub:
        try:
            from analytics.preview_federation import is_worker_bundle, resolve_worker_hub_url

            if is_worker_bundle(root):
                king = resolve_worker_hub_url(root) or f"http://127.0.0.1:{hub_port}"
                print(f"\n[Hub] Worker — König: {king}")
                subprocess.run(["xdg-open", f"{king.rstrip('/')}/"], check=False, timeout=5)
                return
            from tools.preview_hub import ensure_hub_running

            port = ensure_hub_running(root, port=hub_port)
            path = hub_path if str(hub_path).startswith("/") else f"/{hub_path}"
            url = f"http://127.0.0.1:{port}{path}"
            print(f"\n[R3] {url}")
            try:
                from analytics.r3_paths import is_r3_native_session
                from analytics.r3_local_cockpit import launch_session_cockpit

                if is_r3_native_session():
                    doc = launch_session_cockpit(root, hub_path=path, port=port)
                    if doc.get("ok"):
                        return
            except Exception:
                pass
            subprocess.run(["xdg-open", url], check=False, timeout=5)
            return
        except Exception as exc:
            print(f"\n[Hub] Fallback statische HTML: {exc}")

    path = vp.get("home_html") or vp.get("html") or str(root / "evidence/gui_preview_latest.html")
    if not Path(path).is_file():
        try:
            from analytics.gui_preview_visual import write_gui_preview_html

            vp = write_gui_preview_html(root, report)
            path = vp.get("home_html") or vp.get("html") or path
        except Exception:
            pass
    try:
        subprocess.run(["xdg-open", str(path)], check=False, timeout=5)
    except Exception:
        print(f"\n[HTML] {path}")


if __name__ == "__main__":
    raise SystemExit(main())
