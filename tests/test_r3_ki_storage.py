from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_ki_attachments import save_upload, save_upload_b64
from analytics.r3_ki_storage import append_turn, history_for_ui, save_session, seed_session_from_archive
from analytics.r3_ki_web import (
    fetch_url_safe,
    handle_web_command,
    is_internet_question,
    is_web_command,
    normalize_fetch_url,
    reply_internet_capabilities,
)


def test_append_turn_and_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    msgs = append_turn([], user_text="Hallo", assistant_text="Hi")
    save_session(msgs)
    hist = history_for_ui(Path(__file__).resolve().parents[1])
    assert len(hist) == 2
    assert hist[0]["content"] == "Hallo"


def test_upload_text_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    out = save_upload(root, filename="note.txt", data=b"alpha test", mime="text/plain")
    assert out.get("ok")
    assert out.get("id")


def test_upload_b64(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    out = save_upload_b64(root, filename="cfg.json", content_b64="eyJhIjoxfQ==", mime="application/json")
    assert out.get("ok")


def test_web_command_internet() -> None:
    root = Path(__file__).resolve().parents[1]
    assert is_web_command("/internet")
    out = handle_web_command(root, "/internet")
    assert "reply_de" in out


def test_internet_question_detection() -> None:
    root = Path(__file__).resolve().parents[1]
    q = "Wie kannst du eine Anbindung zum Internet erreichen?"
    assert is_internet_question(q)
    assert not is_internet_question("/status")
    out = reply_internet_capabilities(root, q)
    assert out.get("ok")
    assert "/fetch" in out.get("reply_de", "")
    assert "kein Internet" not in out.get("reply_de", "").lower() or "ollama" in out.get("reply_de", "").lower()


def test_normalize_fetch_url() -> None:
    assert normalize_fetch_url("example.com").startswith("https://")
    assert normalize_fetch_url("http://127.0.0.1") is not None


def test_fetch_blocks_private_host() -> None:
    root = Path(__file__).resolve().parents[1]
    out = fetch_url_safe(root, "http://127.0.0.1/secret")
    assert out.get("ok") is False


def test_seed_session_from_archive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    conv = tmp_path / ".local/share/r3-os/conversation"
    conv.mkdir(parents=True)
    archive = conv / "conversation_archive.jsonl"
    archive.write_text(
        json.dumps({"role": "user", "text": "Neustart mit R3 KI"}) + "\n"
        + json.dumps({"role": "assistant", "text": "Chat übernommen."}) + "\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[1]
    doc = seed_session_from_archive(root)
    assert doc.get("session_messages", 0) >= 2
