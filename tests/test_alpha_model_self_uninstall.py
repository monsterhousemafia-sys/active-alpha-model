from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from analytics.alpha_model_self_uninstall import (
    build_machine_program,
    decode_master_prompt,
    handle_self_uninstall_command,
    is_self_uninstall_command,
    run_self_uninstall,
    seal_master_prompt,
)


def test_machine_program_ops() -> None:
    prog = build_machine_program()
    assert prog.get("program_id") == "AA_SELF_UNINSTALL_CURSOR_V2"
    assert len(prog.get("ops") or []) >= 8


def test_seal_and_decode(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("AA_AGENT_CHAMBER", "1")
    seal_master_prompt(root)
    doc = decode_master_prompt(root)
    assert doc.get("program_id") == "AA_SELF_UNINSTALL_CURSOR_V2"
    assert (root / "control/alpha_model_self_uninstall.mc").is_file()


def test_dry_run_in_chamber() -> None:
    root = Path(__file__).resolve().parents[1]
    with mock.patch.dict(os.environ, {"AA_AGENT_CHAMBER": "1"}, clear=False):
        doc = run_self_uninstall(root, dry_run=True)
    assert doc.get("dry_run") is True
    assert doc.get("steps_total", 0) >= 8


def test_command_detection() -> None:
    assert is_self_uninstall_command("/self-uninstall")
    assert is_self_uninstall_command("/maschine run execute")
    assert not is_self_uninstall_command("/status")


def test_handle_execute_phrase() -> None:
    root = Path(__file__).resolve().parents[1]
    with mock.patch.dict(os.environ, {"AA_AGENT_CHAMBER": "1"}, clear=False):
        doc = handle_self_uninstall_command(root, "/self-uninstall")
    assert doc.get("dry_run") is True
