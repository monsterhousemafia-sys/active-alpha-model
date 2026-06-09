"""M1 matrix variant order and serial execution guard."""
from __future__ import annotations

from tools.run_validation_matrix import (
    M1_PHASE_MATRIX_KEYS,
    _is_m1_phase_matrix,
    _order_m1_phase_variants,
)


def test_m1_phase_order():
    variants = [
        {"key": "M1_MOM_BLEND_MATCHED_CONTROLS"},
        {"key": "R3_w075_q065_noexit"},
        {"key": "R0_LEGACY_ENSEMBLE"},
    ]
    assert _is_m1_phase_matrix(variants)
    ordered = _order_m1_phase_variants(variants)
    assert [v["key"] for v in ordered] == list(M1_PHASE_MATRIX_KEYS)


def test_m1_phase_parallel_jobs_not_forced_to_one():
    import inspect

    src = inspect.getsource(__import__("tools.run_validation_matrix", fromlist=["run_matrix"]).run_matrix)
    assert "parallel-jobs forced to 1" not in src
