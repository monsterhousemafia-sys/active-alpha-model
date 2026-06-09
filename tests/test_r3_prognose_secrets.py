from __future__ import annotations

from pathlib import Path

from analytics.r3_prognose_secrets import (
    build_prognose_secrets_doc,
    format_geheimnis_reply_de,
    handle_prognose_chat,
    is_prognose_query,
)


def test_is_prognose_query() -> None:
    assert is_prognose_query("/geheimnis")
    assert is_prognose_query("Welche Aktien steigen morgen?")
    assert not is_prognose_query("Cockpit verbessern")


def test_build_and_format() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_prognose_secrets_doc(root)
    assert doc.get("share_in_chat") is True
    reply = format_geheimnis_reply_de(doc)
    if doc.get("top_picks"):
        assert "Top-Aktien" in reply
        assert doc["top_picks"][0].get("symbol") in reply


def test_handle_prognose_chat() -> None:
    root = Path(__file__).resolve().parents[1]
    out = handle_prognose_chat(root, "/geheimnis")
    assert out.get("ok")
    assert out.get("prognose")
    assert "Prognose" in out.get("reply_de", "")
