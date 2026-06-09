from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_build_channel import (
    build_help_de,
    clear_queue,
    execute_action,
    handle_build_command,
    load_build_config,
    parse_r3_build_blocks,
    queue_actions,
    resolve_safe_path,
    validate_run_command,
)


def test_parse_r3_build_blocks() -> None:
    text = 'Plan:\n```r3-build\n{"actions":[{"type":"write","path":"analytics/x.py","content":"# x"}]}\n```'
    actions = parse_r3_build_blocks(text)
    assert len(actions) == 1
    assert actions[0]["path"] == "analytics/x.py"


def test_resolve_safe_path_blocks_escape(tmp_path: Path) -> None:
    cfg = load_build_config(Path(__file__).resolve().parents[1])
    bad, err = resolve_safe_path(tmp_path, "../etc/passwd", cfg)
    assert bad is None
    assert err
    ok, _ = resolve_safe_path(tmp_path, "analytics/foo.py", cfg)
    assert ok == tmp_path / "analytics/foo.py"


def test_validate_run_command() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_build_config(root)
    ok, _ = validate_run_command("python3 -m pytest tests/ -q", cfg)
    assert ok
    bad, err = validate_run_command("sudo rm -rf /", cfg)
    assert not bad
    assert err


def test_write_and_queue(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "proj"
    root.mkdir()
    cfg = {
        "write_prefixes": ["analytics/"],
        "write_forbidden_substrings": [".env"],
        "max_write_bytes": 1000,
        "run_allowlist_prefixes": [],
        "run_forbidden_substrings": ["sudo"],
    }
    result = execute_action(root, {"type": "write", "path": "analytics/t.py", "content": "x=1\n"}, cfg)
    assert result["ok"]
    assert (root / "analytics/t.py").read_text() == "x=1\n"

    clear_queue()
    queue_actions([{"type": "plan", "title_de": "Test"}])
    out = handle_build_command(root, "/bau status")
    assert out.get("ok")
    assert "plan" in out.get("reply_de", "").lower() or "Warteschlange" in out.get("reply_de", "")


def test_build_help() -> None:
    assert "/bau apply" in build_help_de()
