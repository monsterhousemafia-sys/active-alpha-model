"""R3 Mirror — kritische Fall-Alerts (Exec-Spiegel, kein Dekor-Panel)."""
from __future__ import annotations

import json
from pathlib import Path

from analytics import r3_mirror_view
from tests.r3_order_fixtures import seed_orders_stack


def test_mirror_shows_alert_only_on_confirmed_fall(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "evidence/prognosis_fall_watch_latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "fall_detected": True,
                "headline_de": "Fall bestätigt — Portfolio -1.2 %",
                "prior_close_date": "2026-06-09",
                "portfolio_return_pct": -1.2,
            }
        ),
        encoding="utf-8",
    )
    html = r3_mirror_view.render_results_panel(tmp_path)
    assert "r3-fall-watch" not in html
    assert "r3-alert-banner" in html
    assert "Fall bestätigt" in html


def test_mirror_hides_weak_fall_without_confirmation(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "evidence/prognosis_fall_watch_latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "fall_detected": False,
                "headline_de": "Schwäche — Portfolio -0.04 %",
                "portfolio_return_pct": -0.04,
            }
        ),
        encoding="utf-8",
    )
    html = r3_mirror_view.render_results_panel(tmp_path)
    assert "r3-fall-watch" not in html
    assert "r3-alert-banner" not in html
