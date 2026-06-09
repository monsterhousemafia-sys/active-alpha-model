"""Linux-Potenzial — Scan und sichere Anwendung."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.linux_potential import apply_linux_potential_safe, scan_linux_potential


def test_scan_linux_potential(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/linux_potential.json").write_text(
        (Path(__file__).resolve().parents[1] / "control/linux_potential.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_bind": "127.0.0.1", "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/stack_integrity_latest.json").write_text(
        json.dumps({"stack_ok": True}),
        encoding="utf-8",
    )
    doc = scan_linux_potential(tmp_path, persist=True)
    assert doc.get("potential_pct", 0) >= 0
    assert len(doc.get("dimensions") or []) >= 5
    assert (tmp_path / "evidence/linux_potential_latest.json").is_file()


def test_apply_safe_steps(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/linux_potential.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/r3_local_first_policy.json").write_text(
        json.dumps({"status": "AUTHORITATIVE", "apply_command_de": "test"}),
        encoding="utf-8",
    )
    (tmp_path / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_bind": "127.0.0.1", "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    (tmp_path / "control/preview_federation.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
    (tmp_path / "control/linux_nvme_storage.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
    out = apply_linux_potential_safe(tmp_path)
    assert "steps" in out
    assert (tmp_path / "evidence/linux_potential_apply_latest.json").is_file()
