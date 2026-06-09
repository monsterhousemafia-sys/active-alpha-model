"""R3 Minimal-Scope — nur Prognosen und Lernen, kein Ubuntu-Duplikat."""
from pathlib import Path

from analytics.r3_minimal_scope import (
    build_daily_learning_status,
    load_minimal_scope_policy,
    render_daily_learning_section,
)


def test_minimal_policy() -> None:
    policy = load_minimal_scope_policy(Path(__file__).resolve().parents[1])
    assert "Ubuntu" in str(policy.get("mission_de") or "")
    assert "ubuntu_shell_tiles" in (policy.get("forbidden_on_desktop_de") or [])


def test_learning_status() -> None:
    doc = build_daily_learning_status(Path(__file__).resolve().parents[1])
    assert "headline_de" in doc
    assert "eod_observations" in doc


def test_render_learning_section() -> None:
    html_out = render_daily_learning_section(Path(__file__).resolve().parents[1])
    assert "r3-daily-learning" in html_out
    assert "KI lernt aus Kursen" in html_out
