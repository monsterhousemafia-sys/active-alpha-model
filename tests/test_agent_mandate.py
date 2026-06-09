from __future__ import annotations

import json
from pathlib import Path

from analytics.agent_mandate import (
    agent_response_framing,
    evaluate_mandate_alignment,
    load_agent_mandate,
)


def test_load_mandate(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control" / "agent_mandate.json").write_text(
        json.dumps({"pursuit_goals": [], "stance_de": "test"}),
        encoding="utf-8",
    )
    doc = load_agent_mandate(tmp_path)
    assert doc.get("stance_de") == "test"


def test_evaluate_writes_evidence(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "control" / "agent_mandate.json"
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "agent_mandate.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    doc = evaluate_mandate_alignment(tmp_path)
    assert "alignment_pct" in doc
    assert (tmp_path / "evidence/agent_mandate_alignment_latest.json").is_file()


def test_response_framing_no_feelings(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1] / "control" / "agent_mandate.json"
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "agent_mandate.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    frame = agent_response_framing(tmp_path)
    assert "Gefühle" in frame.get("report_instead_de", "") or "Alignment" in frame.get("report_instead_de", "")
