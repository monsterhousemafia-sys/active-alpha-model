from __future__ import annotations

import json
from pathlib import Path

from analytics.aa_linux_runtime import install_linux_runtime


def test_install_linux_runtime_slice_mode_skips_authoritative_delegate(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []

    def _boom(*_a, **_k):
        calls.append("authoritative")
        return {"ok": False}

    monkeypatch.setattr(
        "analytics.linux_runtime_unified.install_authoritative_runtime",
        _boom,
    )
    monkeypatch.setattr(
        "analytics.linux_runtime_unified.kernel_is_authoritative",
        lambda _root: True,
    )
    monkeypatch.setattr(
        "analytics.aa_linux_runtime._unit_dir",
        lambda: tmp_path / "systemd",
    )

    out = install_linux_runtime(tmp_path, enable=False, _slice_install_only=True)
    assert calls == []
    assert isinstance(out, dict)
