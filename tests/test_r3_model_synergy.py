from __future__ import annotations

from pathlib import Path

from analytics.r3_model_synergy import (
    classify_task,
    format_synergy_reply_de,
    resolve_openai_tier,
    resolve_ollama_role,
)


def test_classify_tasks() -> None:
    assert classify_task("Kurzer Status?") == "fast"
    assert classify_task("Pilot Day Trading Architektur montags") == "deep"
    assert classify_task("pytest fix in analytics") == "plan"
    assert classify_task("Welche Aktien steigen?") == "trading"


def test_openai_tier_routing() -> None:
    root = Path(__file__).resolve().parents[1]
    deep = resolve_openai_tier(root, "Wie ersetzen wir den Kernel komplett?")
    assert deep.get("model") == "gpt-4o"
    fast = resolve_openai_tier(root, "Kurz?")
    assert fast.get("model") == "gpt-4o-mini"


def test_ollama_roles() -> None:
    root = Path(__file__).resolve().parents[1]
    build = resolve_ollama_role(root, "fix test", mode="build")
    assert build.get("role") == "build_kernel"
    assert "coder" in str(build.get("preferred") or "")


def test_synergy_format() -> None:
    root = Path(__file__).resolve().parents[1]
    text = format_synergy_reply_de(root)
    assert "Synergie" in text
    assert "gpt-4o" in text
    assert "qwen" in text
