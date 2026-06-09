from __future__ import annotations

from pathlib import Path

from analytics.r3_chat_window_migration import (
    assess_chat_migration_feasibility,
    build_feasibility_matrix,
    check_migration_safeguards,
)


def test_check_migration_safeguards_structure() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = check_migration_safeguards(root)
    assert "checks" in doc
    assert doc.get("checks_total", 0) >= 4
    assert any(c.get("id") == "no_fake_seal" for c in doc.get("checks") or [])
    assert any(c.get("id") == "h1_backtest_protected" for c in doc.get("checks") or [])


def test_build_feasibility_matrix_has_can_and_cannot() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_feasibility_matrix(root)
    assert len(doc.get("can") or []) >= 7
    assert len(doc.get("cannot") or []) >= 5
    assert "verdict_de" in doc


def test_assess_writes_evidence(monkeypatch) -> None:
    captured: dict = {}

    def _capture(path, doc, **kwargs):
        captured["path"] = path
        captured["doc"] = doc

    monkeypatch.setattr("analytics.r3_chat_window_migration.atomic_write_json", _capture)
    root = Path(__file__).resolve().parents[1]
    doc = assess_chat_migration_feasibility(root, run_preserve=False)
    assert "matrix" in doc
    assert "safeguards" in doc
    assert captured.get("doc") is not None
    assert "r3_chat_migration_feasibility_latest.json" in str(captured.get("path") or "")
