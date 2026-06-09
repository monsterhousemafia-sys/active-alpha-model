from __future__ import annotations

from aa_runtime_profile import (
    PROFILES,
    get_profile,
    resolve_effective_profile,
    usable_cpu_cores,
    variant_worker_budget,
)


def test_usable_cpu_cores_respects_reserve():
    assert usable_cpu_cores(16, 4) == 12
    assert usable_cpu_cores(16, 0) == 16
    assert usable_cpu_cores(2, 6) == 1


def test_validation_profile_reserves_cores():
    spec = get_profile("validation")
    jobs, per = variant_worker_budget(16, 3, profile=spec)
    assert jobs == 3
    assert per == 4  # (16 - 4 reserve) // 3


def test_background_when_interactive_active():
    spec = resolve_effective_profile("validation", interactive_active=True)
    assert spec.name == "background"
    jobs, _ = variant_worker_budget(16, 3, profile=spec)
    assert jobs == 1


def test_exe_profile_uses_threads():
    assert PROFILES["exe"].parallel_backend == "thread"
