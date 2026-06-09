from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.r3_external_advisor import (
    advisor_status,
    fetch_chatgpt_tip,
    handle_advisor_command,
    is_keyless_advisor,
)
from analytics.r3_model_synergy import resolve_local_model_for_openai_tier, resolve_openai_tier


def _write_advisor_cfg(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "r3_external_advisors.json").write_text(
        """{
  "enabled": true,
  "openai": {
    "enabled": true,
    "keyless_mode": true,
    "model": "gpt-4o-mini",
    "local_tier_models": {
      "fast": "qwen2.5:14b",
      "plan": "qwen2.5-coder:32b",
      "deep": "qwen2.5-coder:32b",
      "trading": "qwen2.5:14b"
    }
  },
  "system_prompt_de": "Test-Berater"
}""",
        encoding="utf-8",
    )
    (tmp_path / "control" / "local_llm.json").write_text(
        '{"default_model":"qwen2.5:14b","role_models":{"chat":"qwen2.5:14b","build_kernel":"qwen2.5-coder:32b"}}',
        encoding="utf-8",
    )


def test_keyless_enabled(tmp_path: Path) -> None:
    _write_advisor_cfg(tmp_path)
    assert is_keyless_advisor(tmp_path)


def test_local_tier_maps_deep_to_coder(tmp_path: Path) -> None:
    _write_advisor_cfg(tmp_path)
    tier = resolve_openai_tier(tmp_path, "Wie ersetzen wir den Kernel komplett?")
    assert tier.get("task") == "deep"
    pick = resolve_local_model_for_openai_tier(tmp_path, {**tier, "model": "gpt-4o"})
    assert pick.get("preferred") == "qwen2.5-coder:32b"
    assert pick.get("keyless") is True


def test_fetch_tipp_keyless(tmp_path: Path) -> None:
    _write_advisor_cfg(tmp_path)
    with patch("analytics.r3_external_advisor.resolve_openai_api_key", return_value=("", "")):
        with patch("analytics.local_llm_bridge.health_report", return_value={"ready": True}):
            with patch(
                "analytics.local_llm_bridge.chat_completion",
                return_value=("Lokaler Tipp", {"model": "qwen2.5:14b"}),
            ):
                out = fetch_chatgpt_tip(tmp_path, "Kurze Idee?")
    assert out.get("ok")
    assert out.get("keyless")
    assert out.get("provider") == "ollama_keyless"
    assert out.get("tip_de") == "Lokaler Tipp"


def test_handle_tipp_keyless(tmp_path: Path) -> None:
    _write_advisor_cfg(tmp_path)
    with patch(
        "analytics.r3_external_advisor.fetch_chatgpt_tip",
        return_value={
            "ok": True,
            "tip_de": "Antwort",
            "keyless": True,
            "local_model": "qwen2.5:14b",
            "model": "gpt-4o-mini",
        },
    ):
        out = handle_advisor_command(tmp_path, "/tipp Was nun?")
    assert out.get("ok")
    assert "kein Key" in str(out.get("reply_de") or "")


def test_advisor_status_keyless_configured(tmp_path: Path) -> None:
    _write_advisor_cfg(tmp_path)
    with patch("analytics.r3_external_advisor.resolve_openai_api_key", return_value=("", "")):
        with patch("analytics.local_llm_bridge.health_report", return_value={"ready": True, "resolved_model": "qwen2.5:14b"}):
            st = advisor_status(tmp_path)
    assert st.get("keyless_mode")
    assert st.get("configured")
