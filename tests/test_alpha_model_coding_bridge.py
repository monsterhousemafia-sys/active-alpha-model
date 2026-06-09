from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from analytics.alpha_model_coding_bridge import (
    coding_bridge_status,
    handle_coding_command,
    is_agent_chamber,
    try_auto_coding,
)


def test_coding_configs_present() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "control/r3_build_kernel.json").is_file()
    assert (root / "control/r3_build_channel.json").is_file()
    st = coding_bridge_status(root)
    assert st.get("bridge") == "alpha_model_coding"
    assert st.get("max_steps") >= 128


def test_coding_blocked_outside_chamber() -> None:
    root = Path(__file__).resolve().parents[1]
    with mock.patch.dict(os.environ, {"AA_AGENT_CHAMBER": ""}, clear=False):
        doc = handle_coding_command(root, "/bau status")
    assert doc.get("ok") is False
    assert "Entfaltungsraum" in str(doc.get("reply_de") or "")


def test_auto_coding_only_with_prefix_in_chamber() -> None:
    root = Path(__file__).resolve().parents[1]
    with mock.patch.dict(os.environ, {"AA_AGENT_CHAMBER": "1"}, clear=False):
        assert try_auto_coding(root, "hallo welt") is None
        doc = try_auto_coding(root, "bau zeige /bau status ohne kernel lauf")
    assert doc is not None
    assert doc.get("coding") is True


def test_is_agent_chamber_env() -> None:
    with mock.patch.dict(os.environ, {"AA_AGENT_CHAMBER": "1"}, clear=False):
        assert is_agent_chamber() is True
