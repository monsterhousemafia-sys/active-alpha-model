from __future__ import annotations

from pathlib import Path

from analytics.alpha_model_cursor_bridge import (
    bridge_status,
    handle_cursor_bridge_command,
    pull_cursor_context_for_king,
    push_cursor_to_king,
    push_king_to_cursor,
)


def test_cursor_king_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control").mkdir()
    push_cursor_to_king(
        tmp_path,
        summary_de="Test-Push",
        verified_facts_de=["Fakt A"],
        tasks_for_king_de=["Auftrag 1"],
    )
    push_king_to_cursor(tmp_path, complaint_de="Schrott im Diagramm")
    ctx = pull_cursor_context_for_king(tmp_path)
    assert "CURSOR ↔ KÖNIG BRIDGE" in ctx
    assert "Test-Push" in ctx
    assert "Schrott" in ctx
    st = bridge_status(tmp_path)
    assert st.get("active")


def test_handle_cursor_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    push_cursor_to_king(tmp_path, summary_de="vorhanden")
    doc = handle_cursor_bridge_command(tmp_path, "/cursor")
    assert doc.get("cursor_bridge")
    assert "Bridge" in str(doc.get("reply_de") or "")
