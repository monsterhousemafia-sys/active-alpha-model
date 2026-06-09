"""Tests for aa_doc_paths relocated documentation helpers."""
from __future__ import annotations

from pathlib import Path

from aa_doc_paths import ensure_root_doc_path, root_doc_path, write_root_doc_file


def test_write_root_doc_file_creates_parent_dirs(tmp_path: Path):
    path = write_root_doc_file(tmp_path, "P9_EXTERNAL_REVIEW_STATUS.md", "ok\n")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "ok\n"
    assert "docs" in path.as_posix()


def test_ensure_root_doc_path_idempotent(tmp_path: Path):
    p1 = ensure_root_doc_path(tmp_path, "CODEX_V4R_PROTECTED_HASHES_BEFORE.json")
    p2 = root_doc_path(tmp_path, "CODEX_V4R_PROTECTED_HASHES_BEFORE.json")
    assert p1 == p2
    assert p1.parent.is_dir()
