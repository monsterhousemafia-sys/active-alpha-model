from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_conversation_continuity import (
    build_continuity_brief,
    parse_transcript_jsonl,
    preserve_conversation,
    verify_migration,
)


def test_parse_transcript_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps(
            {
                "role": "user",
                "message": {"content": [{"type": "text", "text": "<user_query>Hallo R3</user_query>"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rows = parse_transcript_jsonl(p)
    assert rows and rows[0]["text"] == "Hallo R3"


def test_preserve_conversation_no_import(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    doc = preserve_conversation(root, import_cursor=False)
    assert doc.get("preserved_at_utc")
    assert (tmp_path / ".local/share/r3-os/conversation/continuity_manifest.json").is_file()


def test_brief_contains_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    brief = build_continuity_brief(root, [{"role": "user", "text": "Test"}])
    assert "active_alpha_model" in brief or "Arbeitsbaum" in brief


def test_verify_migration_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = verify_migration(root)
    assert "checks" in doc
    assert doc.get("checks_total", 0) >= 5
    assert "ready_for_new_chat" in doc
    assert any(c.get("id") == "step_a" for c in doc.get("checks") or [])
