from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.local_llm_bridge import (
    build_project_context,
    health_report,
    load_llm_config,
    run_kernel_command,
)


def test_load_llm_config_project() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_llm_config(root)
    assert cfg.get("provider") == "ollama"
    assert cfg.get("default_model")


def test_build_project_context(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/local_llm.json").write_text(
        json.dumps({"context_files": [], "max_context_chars": 1000}),
        encoding="utf-8",
    )
    ctx = build_project_context(tmp_path)
    assert isinstance(ctx, str)


def test_run_kernel_command_allowed(tmp_path: Path) -> None:
    out = run_kernel_command(tmp_path, "status")
    assert "Unbekannter" in out or "kernel" in out.lower() or "{" in out


def test_health_report_offline() -> None:
    root = Path(__file__).resolve().parents[1]
    with patch("analytics.local_llm_bridge.ollama_available", return_value=False):
        h = health_report(root)
    assert h.get("ollama_ok") is False
