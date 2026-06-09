from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_hardware_policy_exists() -> None:
    doc = json.loads((ROOT / "control/king_hardware_policy.json").read_text(encoding="utf-8"))
    assert doc.get("schema_version") == 1
    assert "gpu" in doc
    assert "benchmark" in doc


def test_resolve_gpu_returns_structure() -> None:
    from analytics.king_hardware import resolve_gpu_returns_for_h1

    doc = resolve_gpu_returns_for_h1(ROOT)
    assert "enabled" in doc
    assert "reason_de" in doc


def test_benchmark_timing_structure() -> None:
    from analytics.king_hardware import benchmark_timing

    doc = benchmark_timing(ROOT)
    assert "benchmark_running" in doc
    assert "eta_max_s" in doc
    assert "benchmark_over_eta" in doc


def test_enrich_king_status_doc() -> None:
    from analytics.king_hardware import enrich_king_status_doc

    base = {"h1_sealed": False, "benchmark_running": False, "benchmark_csv_ok": False}
    out = enrich_king_status_doc(base, ROOT)
    assert out.get("schema_version") == 3
    assert "gpu_returns_enabled" in out
    assert "benchmark_over_eta" in out


def test_network_pulse_includes_hardware() -> None:
    from analytics.king_network import sync_network_pulse

    pulse = sync_network_pulse(ROOT, source_node="test")
    assert pulse.get("hardware_ref") == "evidence/king_hardware_latest.json"
    assert "gpu_returns_enabled" in pulse
    assert (ROOT / "evidence/king_hardware_latest.json").is_file()
