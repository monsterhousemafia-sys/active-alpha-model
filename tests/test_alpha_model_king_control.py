from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_king_control import (
    ensure_king_control,
    force_king_env,
    format_king_gate_de,
    is_king_control_active,
    require_king_ready,
)


def test_force_king_env(monkeypatch) -> None:
    monkeypatch.delenv("AA_KING_CONTROL", raising=False)
    force_king_env()
    assert os.environ.get("AA_AGENT_CHAMBER") == "1"
    assert is_king_control_active()
    assert os.environ.get("AA_OPERATOR_CHANNEL") == "conversational"


def test_require_king_ready(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("AA_AGENT_CHAMBER", "1")
    force_king_env()
    fake_status = {
        "ok": True,
        "ready": True,
        "checks": [],
        "headline_de": "OK",
        "repaired": [],
    }
    with patch("analytics.alpha_model_king_control.king_control_status", return_value=fake_status):
        assert require_king_ready(root) is True


def test_ensure_king_repair_calls_transfer(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    force_king_env()
    with patch("analytics.alpha_model_agent_home.ensure_agent_home"):
        with patch(
            "analytics.alpha_model_king_resources.serve_king_resources",
            return_value={"applied": ["transfer", "tier"], "ok": True},
        ) as serve:
            with patch(
                "analytics.alpha_model_king_control.king_control_status",
                return_value={"ok": True, "checks": [], "headline_de": "OK"},
            ):
                doc = ensure_king_control(root, repair=True)
    serve.assert_called_once()
    assert "transfer" in (doc.get("repaired") or [])


def test_format_king_gate_de(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    with patch(
        "analytics.alpha_model_king_control.ensure_king_control",
        return_value={
            "headline_de": "Test",
            "checks": [{"ok": True, "label_de": "A", "detail_de": "x"}],
            "repaired": [],
            "ready": True,
        },
    ):
        text = format_king_gate_de(root)
    assert "Test" in text
    assert "✓" in text
