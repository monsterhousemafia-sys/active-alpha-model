"""Chat evolution drive in GUI preview."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.chat_evolution_preview import (
    build_evolution_chat_context,
    run_chat_evolution_drive,
)


def test_build_evolution_context(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/public_learning_report_latest.json").write_text(
        json.dumps({"evolution": {"stage_id": "sportwagen"}}),
        encoding="utf-8",
    )
    ctx = build_evolution_chat_context(tmp_path)
    assert "sportwagen" in ctx or "Evolution" in ctx


def test_run_chat_evolution_mocked(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/local_llm.json").write_text(
        json.dumps({"system_prompt_de": "Test", "default_model": "qwen2.5:7b"}),
        encoding="utf-8",
    )
    (tmp_path / "control/evolution_track.json").write_text(
        json.dumps({"stages": [], "governance": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.local_llm_bridge.health_report",
        lambda r: {"ready": True, "resolved_model": "qwen2.5:7b"},
    )
    monkeypatch.setattr(
        "analytics.local_llm_bridge.chat_completion",
        lambda r, m, **k: (
            "1) IST: Kreis 1/6\n3) NÄCHSTER SCHRITT: Montag Rebalance GUI\n",
            {"model": "qwen2.5:7b"},
        ),
    )
    monkeypatch.setattr(
        "analytics.evolution_stage_runner.run_evolution_cycle",
        lambda r, **k: {"ok": True, "message_de": "Evolution OK", "applied": []},
    )
    monkeypatch.setattr(
        "analytics.closed_loop_score.refresh_closed_loop_score",
        lambda r, **k: {},
    )
    doc = run_chat_evolution_drive(tmp_path)
    assert doc.get("ok")
    assert "Montag" in str(doc.get("next_step_de") or doc.get("chat_reply_de"))
    assert (tmp_path / "evidence/chat_evolution_preview_latest.json").is_file()


def test_preview_chat_steps_skip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.evolution_stage_runner.run_evolution_cycle",
        lambda r, **k: {"ok": True, "message_de": "evolve skip"},
    )
    from ui.live_trading_dashboard.gui_preview_harness import run_chat_preview_steps

    with patch("analytics.local_llm_bridge.health_report", return_value={"ready": True, "resolved_model": "x"}):
        steps, doc = run_chat_preview_steps(tmp_path, skip_chat=True)
    assert len(steps) == 2
    assert all(s.get("pass") for s in steps)
