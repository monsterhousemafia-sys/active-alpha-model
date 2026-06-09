"""Canonical M1 entry hints."""
from __future__ import annotations

import os

from tools.r0_migration_m1_control import M1_ENTRY, m1_hints


def test_m1_hints_single_resume_entry():
    h = m1_hints()
    assert h["primary_entry"] == M1_ENTRY
    assert h["resume_hint"] == M1_ENTRY
    assert h["resume_hint"] == h["primary_entry"]
    if os.name == "nt":
        assert "python" in M1_ENTRY.lower()
    else:
        assert "wsl_conductor" in M1_ENTRY
