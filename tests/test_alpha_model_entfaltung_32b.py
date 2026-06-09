from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_entfaltung_32b import (
    SOVEREIGN_MAX_STEPS,
    build_kernel_limits,
    chat_agent_limits,
    load_tier_config,
    render_chamber_banner,
    resolve_steps_limit,
    tier_status,
)


def test_load_tier_config() -> None:
    root = Path(__file__).resolve().parents[1]
    tier = load_tier_config(root)
    assert tier.get("tier_id") == "ideal_32b"
    assert (tier.get("build_kernel") or {}).get("model") == "qwen2.5-coder:32b"


def test_build_kernel_limits(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("AA_AGENT_CHAMBER", "1")
    lim = build_kernel_limits(root)
    assert lim.get("max_steps") >= SOVEREIGN_MAX_STEPS
    assert lim.get("model") == "qwen2.5-coder:32b"


def test_resolve_steps_limit_unlimited_env(monkeypatch) -> None:
    monkeypatch.setenv("AA_AGENT_MAX_STEPS", "0")
    assert resolve_steps_limit(configured=12, role="chat") == 256


def test_tier_status_missing_models() -> None:
    root = Path(__file__).resolve().parents[1]
    with patch("analytics.local_llm_bridge.list_ollama_models", return_value=["qwen2.5:7b"]):
        with patch("analytics.local_llm_bridge.ollama_available", return_value=True):
            st = tier_status(root)
    assert st.get("tier_id") == "ideal_32b"
    assert "qwen2.5-coder:32b" in (st.get("missing_models") or [])


def test_render_banner() -> None:
    root = Path(__file__).resolve().parents[1]
    banner = render_chamber_banner(root)
    assert "König" in banner
    assert "Ideal" in banner or "32" in banner
    assert "/quit" in banner


def test_chat_agent_limits(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("AA_AGENT_CHAMBER", "1")
    lim = chat_agent_limits(root)
    assert lim.get("max_steps") >= SOVEREIGN_MAX_STEPS
    assert lim.get("history_turns") >= 32
    assert lim.get("free_unfold") is True
