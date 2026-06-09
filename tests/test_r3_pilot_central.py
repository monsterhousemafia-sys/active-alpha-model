from __future__ import annotations

from pathlib import Path

from analytics.r3_pilot_central import (
    build_pilot_board,
    handle_pilot_command,
    king_approve,
    king_reject,
    load_board,
    submit_contribution,
)


def test_submit_and_board(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    sub = submit_contribution(root, "Cockpit-Tile für Entwicklungsspur", author_de="Tester")
    assert sub.get("ok")
    board = build_pilot_board(root)
    assert board.get("current")
    assert "Cockpit" in board["headline_de"]


def test_king_approve_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("analytics.r3_pilot_central.is_king", lambda _r: True)
    root = Path(__file__).resolve().parents[1]
    sub = submit_contribution(root, "Kleine UI-Änderung")
    item_id = sub["item"]["id"]
    board = load_board(root)
    for i, x in enumerate(board["items"]):
        if x["id"] == item_id:
            board["items"][i] = {**x, "status": "wartet_freigabe", "test_ok": True, "kernel_ok": True}
    from analytics.r3_pilot_central import save_board

    save_board(root, board)
    out = king_approve(root, item_id)
    assert out.get("ok")
    assert out["item"]["status"] == "live"


def test_king_reject(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("analytics.r3_pilot_central.is_king", lambda _r: True)
    root = Path(__file__).resolve().parents[1]
    sub = submit_contribution(root, "Abgelehnt")
    out = king_reject(root, sub["item"]["id"])
    assert out.get("ok")


def test_handle_board_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    submit_contribution(root, "Board test")
    out = handle_pilot_command(root, "/board")
    assert out.get("ok")
    assert "Board" in out.get("reply_de", "") or "baust" in out.get("reply_de", "").lower()
