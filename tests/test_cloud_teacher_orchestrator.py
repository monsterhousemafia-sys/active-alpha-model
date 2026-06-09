"""Cloud-Teacher-Orchestrierung — Stufe A, KPI-Fragen."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.cloud_teacher_orchestrator import (
    build_teacher_question_from_kpis,
    run_cloud_teacher_consult,
    teacher_context_for_prompt,
)


def test_build_teacher_question_blockers() -> None:
    q = build_teacher_question_from_kpis({"blockers": ["prognosis_fresh"], "forschung_reif_ok": False})
    assert "prognosis_fresh" in q
    assert "king_ops" in q


def test_run_cloud_teacher_consult_mock(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    with patch(
        "analytics.r3_external_advisor.fetch_cloud_tip",
        return_value={"ok": True, "tip_de": "Tipp: stufe-a", "provider": "ollama_keyless", "model": "qwen"},
    ):
        with patch("analytics.r3_external_advisor.resolve_primary_cloud_provider", return_value="keyless"):
            out = run_cloud_teacher_consult(tmp_path, "Test?", persist=True)
    assert out.get("ok")
    assert (tmp_path / "evidence/king_cloud_teacher_latest.json").is_file()
    ctx = teacher_context_for_prompt(tmp_path)
    assert "stufe-a" in ctx
