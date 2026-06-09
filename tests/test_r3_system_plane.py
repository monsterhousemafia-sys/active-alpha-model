from __future__ import annotations

from pathlib import Path

from analytics.r3_system_plane import (
    display_panel,
    get_network_state,
    load_plane_config,
    plane_action,
    plane_status,
    session_panel,
    _parse_nmcli_wifi,
    _parse_xrandr_outputs,
)


def test_load_plane_config_no_audio_bluetooth() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_plane_config(root)
    assert cfg.get("title_de")
    domains = list(cfg.get("domains") or [])
    assert "network" in domains
    assert "audio" not in domains
    assert "bluetooth" not in domains


def test_parse_nmcli_wifi() -> None:
    raw = "yes:HomeNet:82\nno:Guest:40\n"
    rows = _parse_nmcli_wifi(raw)
    assert len(rows) == 2
    assert rows[0]["active"] is True
    assert rows[0]["ssid"] == "HomeNet"
    assert rows[0]["signal_pct"] == 82


def test_plane_status_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = plane_status(root)
    assert doc.get("ok") is True
    assert doc.get("plane_ui") is True
    assert "stack" in doc
    assert "network" in doc
    assert "audio" not in doc
    assert "bluetooth" not in doc
    assert "session" in doc


def test_network_state_ok_or_missing() -> None:
    doc = get_network_state()
    assert "headline_de" in doc
    if doc.get("ok"):
        assert "wifi_enabled" in doc
        assert isinstance(doc.get("wifi_networks"), list)


def test_plane_action_unknown() -> None:
    root = Path(__file__).resolve().parents[1]
    out = plane_action(root, {"action": "nope"})
    assert out.get("ok") is False


def test_plane_action_volume_delegates_ubuntu() -> None:
    root = Path(__file__).resolve().parents[1]
    out = plane_action(root, {"action": "volume", "pct": 50})
    assert out.get("ok") is False
    assert "Ubuntu" in str(out.get("error_de") or "")
    assert out.get("delegate_exec")


def test_display_panel_plane_ui() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = display_panel(root)
    assert doc.get("plane_ui") is True
    assert "outputs" in doc


def test_session_panel() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = session_panel(root)
    assert doc.get("plane_ui") is True


def test_parse_xrandr() -> None:
    raw = "HDMI-1 connected 1920x1080+0+0 (normal left inverted right x axis y axis)\n"
    outs = _parse_xrandr_outputs(raw)
    assert outs[0]["name"] == "HDMI-1"
    assert outs[0]["connected"] is True


def test_plane_wifi_connect_unknown() -> None:
    root = Path(__file__).resolve().parents[1]
    out = plane_action(root, {"action": "wifi_connect", "ssid": ""})
    assert out.get("ok") is False
