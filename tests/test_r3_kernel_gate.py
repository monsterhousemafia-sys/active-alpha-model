"""Weltneuheit nur mit Cognitive Kernel v2."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_launch_world import render_world_launch_page, world_launch_kernel_gate


def test_kernel_gate_allows_when_authoritative(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_launch_world.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "analytics.linux_runtime_unified.kernel_is_authoritative",
        lambda _root: True,
    )
    gate = world_launch_kernel_gate(tmp_path)
    assert gate.get("allowed") is True


def test_launch_page_blocked_without_kernel(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_launch_world.json").write_text(
        json.dumps({"linux_mainline_de": "vmlinuz bleibt"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.linux_runtime_unified.kernel_is_authoritative",
        lambda _root: False,
    )
    body = render_world_launch_page({"kernel_gate": world_launch_kernel_gate(tmp_path)}, tmp_path).decode(
        "utf-8"
    )
    assert "gesperrt" in body
    assert "vmlinuz" in body
