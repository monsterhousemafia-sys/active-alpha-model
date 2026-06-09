"""Tests for V5R onefile PyInstaller spec."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "build" / "decision_cockpit" / "Marktanalyse.spec"

FORBIDDEN = (
    "aa_ops",
    "aa_ops_refresh",
    "aa_paper_startup",
    "paper_trading_engine",
    "aa_configured_backtest",
    "aa_auto_promotion",
    "aa_shadow_champion",
    "tools.active_alpha_launcher",
)


def test_spec_uses_readonly_launcher():
    text = SPEC.read_text(encoding="utf-8")
    assert "decision_cockpit_readonly_launcher.py" in text


def test_spec_onefile_no_collect():
    text = SPEC.read_text(encoding="utf-8")
    assert "onefile=True" in text
    assert "COLLECT(" not in text


def test_spec_no_forbidden_hidden_imports():
    text = SPEC.read_text(encoding="utf-8")
    for mod in FORBIDDEN:
        assert f'"{mod}"' not in text.split("hiddenimports")[1].split("excludes")[0]


def test_spec_forbidden_in_excludes():
    text = SPEC.read_text(encoding="utf-8")
    for mod in FORBIDDEN:
        assert mod in text


def test_spec_embeds_snapshot():
    text = SPEC.read_text(encoding="utf-8")
    assert "v5r_release_embed_snapshot.json" in text
