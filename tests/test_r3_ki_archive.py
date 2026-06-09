from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_ki_storage import append_turn_to_archive, read_archive_rows, seed_session_from_archive


def test_append_and_read_archive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    append_turn_to_archive(user_text="Hallo R3", assistant_text="Willkommen.")
    rows = read_archive_rows()
    assert len(rows) == 2
    assert rows[0]["text"] == "Hallo R3"


def test_seed_from_r3_archive_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    conv = tmp_path / ".local/share/r3-os/conversation"
    conv.mkdir(parents=True)
    (conv / "conversation_archive.jsonl").write_text(
        json.dumps({"role": "user", "text": "Aus Archiv"}) + "\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[1]
    doc = seed_session_from_archive(root)
    assert doc.get("session_messages", 0) >= 1
    assert doc.get("source") == "r3_archive"
