from __future__ import annotations

import json
from pathlib import Path

from analytics.alpha_model_chat_agent import (
    _kernel_allowlist,
    execute_chat_tool,
    extract_search_terms,
    load_chat_agent_config,
    prefetch_context,
    run_chat_agent,
    should_route_to_bau,
    should_use_chat_agent,
)


def test_should_use_chat_agent_triggers() -> None:
    cfg = load_chat_agent_config(Path(__file__).resolve().parents[1])
    assert should_use_chat_agent("Finde wo agent_home definiert ist", cfg=cfg)
    assert should_use_chat_agent("Was ist der H1-Status?", cfg=cfg)
    assert not should_use_chat_agent("ok", cfg=cfg)
    assert not should_use_chat_agent("hi", cfg=cfg)


def test_should_route_to_bau() -> None:
    cfg = load_chat_agent_config(Path(__file__).resolve().parents[1])
    assert should_route_to_bau("Implementiere einen neuen Test für alpha_model_agent_home", cfg=cfg)
    assert not should_route_to_bau("Erkläre was alpha_model_agent_home macht", cfg=cfg)
    assert not should_use_chat_agent("Implementiere einen neuen Test für foo", cfg=cfg)


def test_extract_search_terms() -> None:
    terms = extract_search_terms("Finde analytics/alpha_model_agent_home.py und erkläre")
    assert "alpha_model_agent_home" in terms


def test_prefetch_finds_file() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_chat_agent_config(root)
    pf = prefetch_context(root, "Wo ist alpha_model_agent_home definiert?", cfg)
    assert pf.get("enabled")
    assert pf.get("grep_hits") or pf.get("terms")


def test_prefetch_synth_when_no_json(monkeypatch) -> None:
    from analytics.alpha_model_chat_agent import _synthesize_from_prefetch

    pf = {
        "grep_hits": [
            {
                "term": "tier_ready",
                "matches_de": "analytics/alpha_model_entfaltung_32b.py:92: tier_ready",
            }
        ]
    }
    out = _synthesize_from_prefetch(pf, "Was ist tier_ready?")
    assert "tier_ready" in out
    assert "alpha_model_entfaltung_32b" in out


def test_sovereign_should_use_chat_agent_short_text(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_chat_agent_config(root)
    monkeypatch.setenv("AA_AGENT_CHAMBER", "1")
    assert should_use_chat_agent("hi", cfg=cfg) is False
    assert should_use_chat_agent("go", cfg=cfg) is True


def test_chamber_kernel_allowlist_expanded(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_chat_agent_config(root)
    monkeypatch.setenv("AA_AGENT_CHAMBER", "1")
    allowed = _kernel_allowlist(root, cfg)
    assert "learn" in allowed
    assert "evolve" in allowed
    assert "h1-watch" in allowed
    assert len(allowed) >= 20


def test_prefetch_tier_ready_does_not_trigger_ready_kernel(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_chat_agent_config(root)

    def boom(*_a, **_k):
        raise AssertionError("kernel ready should not run for tier_ready")

    monkeypatch.setattr("analytics.alpha_model_chat_agent._tool_kernel", boom)
    pf = prefetch_context(root, "Wo ist tier_ready definiert?", cfg)
    assert pf.get("enabled")
    assert pf.get("kernel") is None


def test_tool_reply() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_chat_agent_config(root)
    out = execute_chat_tool(root, "reply", {"reply_de": "Antwort fertig."}, cfg)
    assert out["ok"]
    assert out["finished"]
    assert "Antwort" in out["reply_de"]


def test_tool_kernel_allowlist() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_chat_agent_config(root)
    bad = execute_chat_tool(root, "kernel", {"command": "rm-everything"}, cfg)
    assert not bad["ok"]


def test_run_chat_agent_reads_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "proj"
    (root / "analytics").mkdir(parents=True)
    (root / "analytics" / "alpha_model_agent_home.py").write_text(
        "# Agent Home\nLABEL = 'Entfaltungsraum'\n",
        encoding="utf-8",
    )
    (root / "control").mkdir()
    (root / "control" / "alpha_model_chat_agent.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "max_steps": 4,
                "prefetch_enabled": False,
                "kernel_allowlist": ["status"],
            }
        ),
        encoding="utf-8",
    )

    calls = {"n": 0}

    def fake_chat(_root, messages, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return (
                '{"thought_de":"lesen","tool":"read_file","args":{"path":"analytics/alpha_model_agent_home.py"}}',
                {},
            )
        return (
            '{"thought_de":"fertig","tool":"reply","args":{"reply_de":"Die Datei definiert LABEL Entfaltungsraum."}}',
            {},
        )

    monkeypatch.setattr("analytics.local_llm_bridge.chat_completion", fake_chat)
    monkeypatch.setattr("analytics.local_llm_bridge.health_report", lambda _r: {"ready": True})
    monkeypatch.setattr(
        "analytics.r3_model_synergy.resolve_ollama_role",
        lambda *_a, **_k: {"model": "qwen2.5:7b"},
    )
    monkeypatch.setattr("analytics.alpha_model_chat_agent.append_turn_to_archive", lambda **_k: None)

    doc = run_chat_agent(root, "Finde und erkläre alpha_model_agent_home.py")
    assert doc.get("ok")
    assert "Entfaltungsraum" in doc.get("reply_de", "")
