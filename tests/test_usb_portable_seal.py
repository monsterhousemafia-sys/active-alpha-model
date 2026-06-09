"""USB portable seal / Operator-Segnung."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.usb_portable_seal import bless_usb_portable_copy, verify_usb_portable_seal


def test_bless_blocked_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "USB_WEITERARBEITEN.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (tmp_path / "control").mkdir()
    (tmp_path / "control/usb_portable_autostart.json").write_text(
        json.dumps({"enabled": True, "auto_install_local": True}),
        encoding="utf-8",
    )
    (tmp_path / "control/usb_pip_freeze.txt").write_text("pandas==1.0\n" * 25, encoding="utf-8")
    (tmp_path / "requirements_active_alpha.txt").write_text("", encoding="utf-8")
    doc = bless_usb_portable_copy(tmp_path, persist=False)
    assert doc["status"] == "BLOCKED"
    assert doc["blessed"] is False


def test_verify_requires_manifest(tmp_path: Path) -> None:
    v = verify_usb_portable_seal(tmp_path)
    assert v["pass"] is False
    assert "usb_deploy_manifest" in v["blockers"]
