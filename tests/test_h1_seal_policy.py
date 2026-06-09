from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_seal_policy_optional() -> None:
    from analytics.h1_seal_policy import is_h1_benchmark_required, is_h1_seal_required, load_h1_seal_policy

    pol = load_h1_seal_policy(ROOT)
    assert pol.get("seal_required") is False
    assert is_h1_seal_required(ROOT) is False
    assert is_h1_benchmark_required(ROOT) is False


def test_experimental_blockers_empty_when_optional() -> None:
    from analytics.live_profile_governance import experimental_profile_blockers

    blockers = experimental_profile_blockers(ROOT)
    assert blockers == []
