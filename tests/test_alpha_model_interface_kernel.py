from __future__ import annotations

from pathlib import Path

import pytest

from analytics.alpha_model_interface_kernel import (
    interface_stack_status,
    load_foundation,
    should_use_ollama_fallback,
)


def test_foundation_local_primary() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = load_foundation(root)
    assert doc.get("primary_interface") in ("r3_ki", "agent_chamber")
    assert doc.get("fallback_interface") == "ollama_local"


def test_local_primary_uses_ollama_when_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "control/alpha_model_interface.json"
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/alpha_model_interface.json").write_text(
        src.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.alpha_model_interface_kernel._ollama_ready",
        lambda root: {"ready": True, "ollama_ok": True},
    )
    monkeypatch.setattr(
        "analytics.alpha_model_interface_kernel._workshop_session_active",
        lambda root=None: False,
    )
    primary = load_foundation(tmp_path).get("primary_interface")
    if primary in ("r3_ki", "ollama_local"):
        assert should_use_ollama_fallback(tmp_path) is True
    doc = interface_stack_status(tmp_path)
    assert doc["primary_interface"] == primary
    assert doc["active_interface"] in ("r3_ki", "ollama_local", "degraded")
    assert doc["active_interface"] not in ("workshop", "cursor_chat")


def test_workshop_never_becomes_primary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "control/alpha_model_interface.json"
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/alpha_model_interface.json").write_text(
        src.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.alpha_model_interface_kernel._ollama_ready",
        lambda root: {"ready": True, "ollama_ok": True},
    )
    monkeypatch.setattr(
        "analytics.alpha_model_interface_kernel._workshop_session_active",
        lambda root=None: True,
    )
    doc = interface_stack_status(tmp_path)
    assert doc["primary_interface"] == load_foundation(tmp_path).get("primary_interface")
    assert doc["active_interface"] == "ollama_local"
    assert doc["active_interface"] != "workshop"
