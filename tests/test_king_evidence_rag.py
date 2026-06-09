"""Evidence-RAG — Policy, Build, Prompt-Kontext."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.king_evidence_rag import (
    build_evidence_rag,
    load_stufe_a_policy,
    rag_context_for_prompt,
)


def test_load_stufe_a_policy_defaults(tmp_path: Path) -> None:
    policy = load_stufe_a_policy(tmp_path)
    assert policy.get("enabled") is True
    assert int(policy.get("evidence_rag_max_chars") or 0) > 0
    assert policy.get("evidence_rag_paths")


def test_rag_truncates_to_max_chars(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/king_stufe_a_policy.json").write_text(
        json.dumps(
            {
                "evidence_rag_paths": ["evidence/king_network_pulse_latest.json"],
                "evidence_rag_max_chars": 80,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text(
        json.dumps({"phase": "x" * 200, "beat": 1, "headline_de": "long"}),
        encoding="utf-8",
    )
    doc = build_evidence_rag(tmp_path, persist=False)
    assert len(str(doc.get("rag_text") or "")) <= 80
    assert "truncated" in str(doc.get("rag_text") or "")


def test_rag_context_for_prompt_builds_when_missing(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/king_stufe_a_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text(
        json.dumps({"phase": "ready", "beat": 3}),
        encoding="utf-8",
    )
    text = rag_context_for_prompt(tmp_path)
    assert "Evidence-RAG" in text
    assert "ready" in text
    assert (tmp_path / "evidence/king_evidence_rag_latest.json").is_file()
