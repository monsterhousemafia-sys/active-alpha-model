"""USB-Portable Finalize — Pfade, Manifest, Verify."""
from __future__ import annotations

import json
from pathlib import Path

from tools.usb_portable_finalize import (
    finalize_usb_copy,
    patch_control_paths,
    verify_portable_copy,
)


def test_patch_control_paths_rewrites_project_root(tmp_path: Path) -> None:
    old = "/home/old/active_alpha_model"
    new = str(tmp_path.resolve())
    (tmp_path / "control").mkdir()
    (tmp_path / "control/r3_continuity.json").write_text(
        json.dumps({"project_root": old}),
        encoding="utf-8",
    )
    changed = patch_control_paths(tmp_path, new_root=tmp_path, old_roots=[old])
    assert "control/r3_continuity.json" in changed
    doc = json.loads((tmp_path / "control/r3_continuity.json").read_text(encoding="utf-8"))
    assert doc["project_root"] == new


def test_finalize_usb_copy_writes_manifest_and_verify(tmp_path: Path) -> None:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    for rel in (
        "USB_WEITERARBEITEN.sh",
        "tools/king_ops.sh",
        "tools/ai_kernel.py",
        "control/prediction_operations.json",
        "requirements_active_alpha.txt",
        "control/usb_pip_freeze.txt",
    ):
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")
    (dest / "control/r3_continuity.json").write_text(
        json.dumps({"project_root": str(src.resolve())}),
        encoding="utf-8",
    )
    out = finalize_usb_copy(
        dest,
        source_root=src,
        deploy_target="test-usb",
        excludes=("__pycache__/",),
    )
    assert (dest / "control/usb_deploy_manifest.json").is_file()
    assert out["manifest"]["source_project_root"] == str(src.resolve())
    assert out["verify"]["missing_files"] == []
    assert out["verify"]["venv_ok"] is False  # kein echtes venv in Fixture
