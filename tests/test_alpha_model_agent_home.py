from __future__ import annotations

from pathlib import Path

from analytics.alpha_model_agent_home import (
    ensure_agent_home,
    is_loopback_client,
    load_agent_home_config,
    render_chamber_local_gate_html,
)


def test_agent_home_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_agent_home_config(root)
    assert "Entfaltungsraum" in str(cfg.get("label_de") or "")
    assert cfg.get("local_only") is True


def test_ensure_agent_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    doc = ensure_agent_home(root)
    assert doc.get("ok") is True
    assert doc.get("local_only") is True
    assert (tmp_path / ".local/share/alpha-model/agent/manifest.json").is_file()


def test_growth_agent_label() -> None:
    root = Path(__file__).resolve().parents[1]
    from analytics.alpha_model_growth import agent_chamber_label

    assert "Entfaltungsraum" in agent_chamber_label(root)


def test_loopback_and_gate_html() -> None:
    root = Path(__file__).resolve().parents[1]
    assert is_loopback_client("127.0.0.1") is True
    assert is_loopback_client("10.0.0.5") is False
    remote = render_chamber_local_gate_html(root, remote=True)
    local = render_chamber_local_gate_html(root, remote=False)
    assert "alpha-model-agent" in remote
    assert "Terminal" in local
