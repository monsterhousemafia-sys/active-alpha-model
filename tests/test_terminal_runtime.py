from __future__ import annotations

from analytics.terminal_runtime import bootstrap_graphical_env, detect_runtime_context


def test_bootstrap_sets_display(monkeypatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)
    doc = bootstrap_graphical_env()
    assert doc.get("display") == ":0"
    assert "DISPLAY=:0" in doc.get("applied", [])


def test_detect_runtime_context_shape() -> None:
    ctx = detect_runtime_context()
    assert "source" in ctx
    assert "can_auto_send" in ctx
    assert "headline_de" in ctx
