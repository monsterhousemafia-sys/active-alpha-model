"""R3 Ops — Gates Schritt 1–2 (H1-Monitor, Pilot live nach Test)."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from analytics.r3_pilot_central import (
    build_pilot_board,
    king_approve,
    load_board,
    save_board,
    submit_contribution,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _python_bin(root: Path) -> str:
    venv_py = Path(root) / ".venv/bin/python3"
    return str(venv_py) if venv_py.is_file() else "python3"


def run_pilot_test_suite(root: Path) -> Dict[str, Any]:
    root = Path(root)
    py = _python_bin(root)
    cmd = (
        f"{py} -m pytest tests/test_r3_system_plane.py tests/test_r3_ubuntu_closure.py "
        "tests/test_r3_native_apps.py tests/test_r3_pilot_central.py -q --tb=no"
    )
    proc = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True, timeout=300, check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode, "output_de": out.strip()[:3000], "cmd": cmd}


def promote_pilot_live(
    root: Path,
    *,
    item_id: str | None = None,
    mandate_de: str = "System Plane — BT · Display · Session · WLAN",
) -> Dict[str, Any]:
    """Test-Suite grün → Beitrag freigeben → live (Schritt 2)."""
    root = Path(root)
    test = run_pilot_test_suite(root)
    if not test.get("ok"):
        return {"ok": False, "step": "test", "reply_de": "Tests fehlgeschlagen — Pilot nicht live.", "test": test}

    board = load_board(root)
    items: List[Dict[str, Any]] = list(board.get("items") or [])
    iid = item_id or board.get("current_id")
    item = next((x for x in items if x.get("id") == iid), None)
    if not item:
        seeded = submit_contribution(root, mandate_de, author_de="R3 Ops")
        if not seeded.get("ok"):
            return {"ok": False, "reply_de": seeded.get("reply_de") or "Beitrag konnte nicht angelegt werden."}
        item = seeded.get("item") or {}
        iid = item.get("id")
        board = load_board(root)
        items = list(board.get("items") or [])
        item = next((x for x in items if x.get("id") == iid), item)
    if not item:
        return {"ok": False, "reply_de": "Kein Pilot-Beitrag auf dem Board."}

    item["mandate_de"] = mandate_de[:600]
    item["implement_de"] = "R3 System Plane: Bluetooth, Display, Session, WLAN-Connect, Bild-Vorschau"
    item["kernel_ok"] = True
    item["test_de"] = test.get("output_de", "")[:500]
    item["test_ok"] = True
    item["tested_at_utc"] = _utc_now()
    item["status"] = "wartet_freigabe"
    item["preview_de"] = item["implement_de"]

    for i, x in enumerate(items):
        if x.get("id") == item["id"]:
            items[i] = item
            break
    board["items"] = items
    board["current_id"] = item["id"]
    save_board(root, board)

    approved = king_approve(root, item["id"])
    board_doc = build_pilot_board(root)
    live_n = int((board_doc.get("counts") or {}).get("live") or 0)
    return {
        "ok": bool(approved.get("ok")),
        "step": "pilot_live",
        "live_count": live_n,
        "reply_de": approved.get("reply_de") or board_doc.get("headline_de"),
        "test": test,
        "approved": approved,
    }


def start_h1_monitor(root: Path, *, poll_seconds: int = 60) -> Dict[str, Any]:
    """Schritt 1 — H1-Pipeline im Monitor-Modus starten (Hintergrund)."""
    root = Path(root)
    try:
        from analytics.h1_migration_guard import ensure_h1_migration_healthy

        doc = ensure_h1_migration_healthy(root, auto_fix=True, poll_seconds=poll_seconds)
        mon = doc.get("monitor") or {}
        return {
            "ok": bool(doc.get("ok")),
            "pid": mon.get("pid"),
            "reply_de": str(doc.get("reply_de") or mon.get("reply_de") or "H1-Monitor"),
            "migration": doc,
        }
    except Exception as exc:
        return {"ok": False, "error_de": str(exc)[:200]}


def run_ops_sequence(root: Path) -> Dict[str, Any]:
    """Schritte 1–2: H1-Monitor + Pilot live nach Tests."""
    root = Path(root)
    h1 = start_h1_monitor(root)
    pilot = promote_pilot_live(root)
    from analytics.r3_step_a import evaluate_step_a

    step = evaluate_step_a(root)
    return {
        "ok": bool(h1.get("ok")) and bool(pilot.get("ok")),
        "h1_monitor": h1,
        "pilot": pilot,
        "step_a": step,
        "headline_de": (
            f"H1-Monitor: {'läuft' if h1.get('ok') else 'Fehler'} · "
            f"Pilot live: {pilot.get('live_count', 0)} · Schritt A: {step.get('step_a_percent')}%"
        ),
    }
