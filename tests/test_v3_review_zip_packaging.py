"""Packaging validation for V3 review ZIP builder."""
from __future__ import annotations

from tools.build_v3_review_zip import INCLUDE, validate_include_paths


def test_no_duplicate_zip_paths():
    ok, dups = validate_include_paths(INCLUDE)
    assert ok, dups


def test_duplicate_detection():
    ok, dups = validate_include_paths(["a.txt", "b.txt", "a.txt"])
    assert not ok
    assert "a.txt" in dups
