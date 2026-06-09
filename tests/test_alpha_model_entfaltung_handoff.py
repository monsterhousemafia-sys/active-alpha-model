from __future__ import annotations

from pathlib import Path

from analytics.alpha_model_entfaltung_handoff import (
    apply_entfaltung_handoff,
    build_handoff_prompt_de,
    load_kill_config,
)


def test_kill_config_armed() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_kill_config(root)
    assert cfg.get("status") in ("ARMED", "HANDOFF_APPLIED", "RESOURCES_TRANSFERRED")
    assert cfg.get("primary_cli") == "alpha-model-agent"


def test_handoff_prompt() -> None:
    root = Path(__file__).resolve().parents[1]
    text = build_handoff_prompt_de(root)
    assert "ENTFALTUNGS-HANDOFF" in text
    assert "/self-uninstall" in text


def test_apply_handoff() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = apply_entfaltung_handoff(root)
    assert doc.get("ok") is True
    mandate = (root / "control/agent_mandate.json").read_text(encoding="utf-8")
    assert "agent_chamber" in mandate
    assert (root / "evidence/alpha_model_entfaltung_handoff_latest.json").is_file()
