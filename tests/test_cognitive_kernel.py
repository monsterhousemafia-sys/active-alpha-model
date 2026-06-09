from __future__ import annotations

from pathlib import Path

from analytics.cognitive_kernel import (
    cognitive_kernel_status,
    record_operator_succession,
)


def test_succession_ack(tmp_path: Path) -> None:
    doc = record_operator_succession(tmp_path, approved_by="user")
    assert doc["ok"] is True
    assert (tmp_path / "evidence/kernel_succession_operator_ack.json").is_file()


def test_status_before_v2(tmp_path: Path) -> None:
    doc = cognitive_kernel_status(tmp_path)
    assert doc["kernel_generation"] == 1
