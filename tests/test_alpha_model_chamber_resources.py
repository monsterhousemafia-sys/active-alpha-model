from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from analytics.alpha_model_chamber_resources import (
    chamber_kernel_allowlist,
    load_chamber_resources,
    transfer_all_resources,
    verify_chamber_resources,
)


def test_registry_has_allowlist() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_chamber_resources(root)
    assert len(chamber_kernel_allowlist(root)) >= 15
    assert "entfaltung-handoff" in chamber_kernel_allowlist(root)


def test_transfer_and_verify() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = transfer_all_resources(root)
    assert doc.get("ok") is True
    v = verify_chamber_resources(root)
    assert v.get("transfer_ok") is True
    assert v.get("transfer_pct") == 100
    assert (root / "tools/active_alpha_chat_chamber.sh").is_file()


def test_chamber_expanded_kernel_allowlist() -> None:
    root = Path(__file__).resolve().parents[1]
    with mock.patch.dict(os.environ, {"AA_AGENT_CHAMBER": "1"}, clear=False):
        from analytics.local_llm_bridge import run_kernel_command

        out = run_kernel_command(root, "chamber-resources")
    assert "Unbekannter Befehl" not in out or "headline" in out.lower() or "schema" in out
