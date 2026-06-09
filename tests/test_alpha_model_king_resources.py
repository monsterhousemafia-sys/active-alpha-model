from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_king_resources import (
    _resource_catalog,
    format_serve_de,
    handle_serve_command,
    serve_king_resources,
)


def test_catalog_has_core_resources() -> None:
    ids = {c["id"] for c in _resource_catalog()}
    assert "ollama_32b" in ids
    assert "cursor_bridge" in ids
    assert "kernel_slash" in ids


def test_serve_command(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control").mkdir()
    with patch("analytics.alpha_model_king_control.ensure_king_control", return_value={"ready": True}):
        with patch(
            "analytics.alpha_model_chamber_resources.verify_chamber_resources",
            return_value={"transfer_ok": True},
        ):
            with patch("analytics.local_llm_bridge.health_report", return_value={"ready": True, "resolved_model": "qwen2.5:14b"}):
                with patch("analytics.alpha_model_chamber_resources.transfer_all_resources"):
                    with patch("analytics.alpha_model_entfaltung_32b.apply_tier_to_llm_config"):
                        with patch("analytics.alpha_model_agent_home.ensure_agent_home"):
                            with patch("analytics.alpha_model_advisor_bridge.load_openai_key_into_env"):
                                with patch("analytics.alpha_model_cursor_bridge.seal_default_cursor_push"):
                                    with patch("analytics.alpha_model_king_handoff.seal_king_handoff"):
                                        with patch("analytics.alpha_model_cursor_bridge.push_cursor_to_king"):
                                            doc = serve_king_resources(tmp_path)
    assert doc.get("catalog_count") >= 6
    out = handle_serve_command(tmp_path, "/diene")
    assert out.get("serve")
    assert "Ressourcen" in str(out.get("reply_de") or "")
