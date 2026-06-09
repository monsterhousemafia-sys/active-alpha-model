"""R3 Mirror — Schichten State / View / API."""
from __future__ import annotations

from pathlib import Path

from analytics import r3_exec_mirror, r3_mirror_state, r3_mirror_view
from tests.r3_order_fixtures import seed_orders_stack


def test_public_api_reexports() -> None:
    assert r3_exec_mirror.build_exec_mirror_state is r3_mirror_state.build_exec_mirror_state
    assert r3_exec_mirror.render_r3_exec_mirror_page is r3_mirror_view.render_r3_exec_mirror_page


def test_state_has_no_html() -> None:
    src = Path(r3_mirror_state.__file__).read_text(encoding="utf-8")
    assert "<section" not in src
    assert "render_" not in src


def test_submission_mode_fail_closed_on_gate_error(monkeypatch) -> None:
    def _boom() -> bool:
        raise RuntimeError("gate down")

    monkeypatch.setattr(
        "execution.linux_security_boundary.live_order_submission_blocked",
        _boom,
    )
    from analytics.r3_mirror_state import resolve_submission_mode

    doc = resolve_submission_mode(Path("."))
    assert doc.get("live_submit") is False
    assert "Policy-Check fehlgeschlagen" in (doc.get("reasons_de") or [])


def test_view_builds_state_not_evidence_io(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    html = r3_mirror_view.render_results_panel(tmp_path).lower()
    assert "r3-mirror-results" in html
    assert "r3-pipeline-facts" not in html
    assert "r3-system-facts" not in html
    assert "r3-cycle-facts" not in html
