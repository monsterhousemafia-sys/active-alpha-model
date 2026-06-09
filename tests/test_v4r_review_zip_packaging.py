"""Packaging validation for V4R review ZIP builder."""
from __future__ import annotations

from aa_doc_paths import write_root_doc_file

import json
from pathlib import Path

from tools.build_v4r_review_zip import INCLUDE, validate_include_paths, validate_protected_hashes


def test_no_duplicate_zip_paths():
    ok, dups = validate_include_paths(INCLUDE)
    assert ok, dups


def test_duplicate_detection():
    ok, dups = validate_include_paths(["a.txt", "b.txt", "a.txt"])
    assert not ok
    assert "a.txt" in dups


def test_incomplete_after_hashes_block_packaging(tmp_path: Path):
    before = {"a.json": "abc", "b.json": "def"}
    write_root_doc_file(tmp_path, "CODEX_V4R_PROTECTED_HASHES_BEFORE.json", json.dumps(before))
    write_root_doc_file(tmp_path, "CODEX_V4R_PROTECTED_HASHES_AFTER.json", json.dumps({"a.json": "abc"}))
    ok, errors = validate_protected_hashes(tmp_path)
    assert not ok
    assert any("before_after_path_sets_differ" in e or "missing_after" in e for e in errors)


def test_matching_hash_sets_pass(tmp_path: Path):
    hashes = {"a.json": "abc", "b.json": "def"}
    write_root_doc_file(tmp_path, "CODEX_V4R_PROTECTED_HASHES_BEFORE.json", json.dumps(hashes))
    write_root_doc_file(tmp_path, "CODEX_V4R_PROTECTED_HASHES_AFTER.json", json.dumps(hashes))
    ok, errors = validate_protected_hashes(tmp_path)
    assert ok, errors
