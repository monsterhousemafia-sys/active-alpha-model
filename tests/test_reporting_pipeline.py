from __future__ import annotations

import json
from pathlib import Path

import pytest

import active_alpha_model as aam


def test_reporting_pipeline_records_error_and_json(tmp_path: Path):
    pipeline = aam.ReportingPipeline(tmp_path, fail_on_error=False)

    def _boom() -> str:
        raise RuntimeError("boom")

    result = pipeline.run_step("broken_step", _boom, "fallback")
    assert result == "fallback"
    assert len(pipeline.errors) == 1
    assert pipeline.errors[0]["step"] == "broken_step"

    pipeline.finalize()
    assert (tmp_path / "reporting_progress.txt").exists()
    assert (tmp_path / "reporting_errors.txt").exists()
    payload = json.loads((tmp_path / "reporting_errors.json").read_text(encoding="utf-8"))
    assert payload["count"] == 1


def test_reporting_pipeline_fail_on_error_raises(tmp_path: Path):
    pipeline = aam.ReportingPipeline(tmp_path, fail_on_error=True)

    def _boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        pipeline.run_step("broken_step", _boom, None)
