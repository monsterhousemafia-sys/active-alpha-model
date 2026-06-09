from __future__ import annotations

from pathlib import Path

from analytics.r3_kernel_roles import (
    build_kernel_roles_status,
    load_kernel_roles,
    render_roles_section,
    roles_context_de,
)


def test_load_kernel_roles() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_kernel_roles(root)
    assert "r3_kernel_de" in cfg
    assert "cursor_de" in cfg
    assert "Ollama" in str(cfg["r3_kernel_de"]["definition_de"])


def test_build_kernel_roles_status() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_kernel_roles_status(root)
    assert doc["r3_kernel"]["title_de"] == "R3 Kern"
    assert "Cursor" in doc["cursor"]["not_kernel_de"] or "Legacy" in doc["cursor"]["role_de"]
    assert len(doc["r3_kernel"]["components"]) == 4


def test_render_roles_section() -> None:
    root = Path(__file__).resolve().parents[1]
    html = render_roles_section(build_kernel_roles_status(root))
    assert "kernel-roles" in html
    assert "Bau-Werkzeug" in html or "Cursor" in html


def test_roles_context_de() -> None:
    root = Path(__file__).resolve().parents[1]
    ctx = roles_context_de(root)
    assert "Ollama" in ctx
    assert "Bau-Kernel" in ctx
