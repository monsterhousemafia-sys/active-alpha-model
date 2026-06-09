"""Minimal invest launch must not raise NameError on import os."""
from __future__ import annotations

import ast
from pathlib import Path


def test_aa_pilot_launch_ui_defines_os_usage_safely() -> None:
    src = (Path(__file__).resolve().parents[1] / "aa_pilot_launch.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert "import os" in src or "from os" in src


def test_minimal_invest_window_imports() -> None:
    import ui.minimal_invest_window as m

    assert hasattr(m, "MinimalInvestWindow")
    assert hasattr(m, "launch_minimal_invest_app")
