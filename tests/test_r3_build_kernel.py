from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_build_kernel import (
    build_kernel_status,
    execute_kernel_tool,
    load_kernel_config,
    parse_agent_step,
)


def test_parse_agent_step() -> None:
    text = '{"thought_de":"lesen","tool":"read_file","args":{"path":"analytics/x.py"}}'
    doc = parse_agent_step(text)
    assert doc and doc["tool"] == "read_file"


def test_parse_agent_step_codeblock() -> None:
    text = '```json\n{"tool":"finish","args":{"summary_de":"fertig"}}\n```'
    doc = parse_agent_step(text)
    assert doc and doc["tool"] == "finish"


def test_tool_read_file(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "analytics").mkdir(parents=True)
    (root / "analytics" / "a.py").write_text("line1\nline2\n", encoding="utf-8")
    cfg = load_kernel_config(Path(__file__).resolve().parents[1])
    out = execute_kernel_tool(root, "read_file", {"path": "analytics/a.py"}, cfg)
    assert out["ok"]
    assert "line1" in out["content"]


def test_tool_write_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "proj"
    root.mkdir()
    cfg = load_kernel_config(Path(__file__).resolve().parents[1])
    out = execute_kernel_tool(
        root,
        "write_file",
        {"path": "analytics/new.py", "content": "x=1\n"},
        cfg,
    )
    assert out["ok"]
    assert (root / "analytics/new.py").read_text() == "x=1\n"


def test_build_kernel_status() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_kernel_status(root)
    assert doc.get("is_build_kernel")
    assert "Coding-Kernel" in str(doc.get("name_de")) or "Bau-Kernel" in str(doc.get("name_de"))
