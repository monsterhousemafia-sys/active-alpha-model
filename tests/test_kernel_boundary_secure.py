from __future__ import annotations

from pathlib import Path

from analytics.kernel_boundary_secure import (
    audit_kernel_boundary,
    is_forbidden_command,
    plan_sysctl_changes,
    run_kernel_boundary,
    write_apply_ack,
)


def test_forbidden_kernel_build() -> None:
    bad, _ = is_forbidden_command("cd /usr/src && make kernel -j32")
    assert bad is True
    ok, _ = is_forbidden_command("python3 tools/ai_kernel.py runtime-install")
    assert ok is False


def test_audit_writes_evidence(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "kernel_boundary_policy.json").write_text(
        '{"schema_version":1,"sysctl_whitelist":{},"forbidden_always_de":[]}',
        encoding="utf-8",
    )
    doc = audit_kernel_boundary(tmp_path)
    assert doc["ok"] is True
    assert (tmp_path / "evidence/kernel_boundary_audit_latest.json").is_file()


def test_apply_runtime_blocked_without_ack(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "linux_operator_scope.json").write_text(
        '{"approved_levels":["A","B"],"max_level":"B","levels":{"B":{"autonomous":true}}}',
        encoding="utf-8",
    )
    doc = run_kernel_boundary(tmp_path, mode="apply-runtime", dry_run=False)
    assert doc.get("ok") is False


def test_apply_runtime_dry_run(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "linux_operator_scope.json").write_text(
        '{"approved_levels":["A","B"],"max_level":"B","levels":{"B":{"autonomous":true}}}',
        encoding="utf-8",
    )
    doc = run_kernel_boundary(tmp_path, mode="apply-runtime", dry_run=True)
    assert doc.get("ok") is True
    assert doc.get("dry_run") is True


def test_plan_sysctl(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "kernel_boundary_policy.json").write_text(
        '{"schema_version":1,"sysctl_whitelist":{"vm.swappiness":{"min":0,"max":10,"reason_de":"test"}}}',
        encoding="utf-8",
    )
    doc = plan_sysctl_changes(tmp_path)
    assert doc["autonomous_apply"] is False
