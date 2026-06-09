from __future__ import annotations

import json
from pathlib import Path

from analytics.local_apps_registry import (
    audit_local_app,
    build_local_apps_audit,
    exec_mirror_route_allowed,
    is_exec_mirror_only,
    load_local_apps_manifest,
    render_local_apps_section,
)


def test_manifest_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = load_local_apps_manifest(root)
    assert doc.get("status") == "EXEC_MIRROR_ONLY"
    apps = doc.get("apps") or []
    assert len(apps) == 1
    assert apps[0].get("id") == "r3_exec_mirror"
    assert is_exec_mirror_only(root) is True


def test_exec_mirror_route_allowlist() -> None:
    assert exec_mirror_route_allowed("GET", "/r3") is True
    assert exec_mirror_route_allowed("GET", "/api/r3/freigabe") is True
    assert exec_mirror_route_allowed("GET", "/api/r3/operator-readiness") is True
    assert exec_mirror_route_allowed("GET", "/api/system/status") is True
    assert exec_mirror_route_allowed("POST", "/api/r3/order") is True
    assert exec_mirror_route_allowed("GET", "/join") is True
    assert exec_mirror_route_allowed("GET", "/api/federation") is True
    assert exec_mirror_route_allowed("POST", "/api/worker/contribute") is True
    assert exec_mirror_route_allowed("GET", "/launch") is False
    assert exec_mirror_route_allowed("GET", "/api/desktop/quality") is False


def test_audit_core_launcher(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir(parents=True)
    sh = tmp_path / "tools/r3_cockpit.sh"
    sh.write_text("#!/bin/bash\ntrue\n", encoding="utf-8")
    sh.chmod(0o755)
    row = audit_local_app(tmp_path, {"id": "cockpit", "tier": "core", "label_de": "Cockpit", "exec_rel": "tools/r3_cockpit.sh"})
    assert row["ok"] is True


def test_audit_missing_launcher(tmp_path: Path) -> None:
    row = audit_local_app(
        tmp_path,
        {"id": "cockpit", "tier": "core", "label_de": "Cockpit", "exec_rel": "tools/missing.sh"},
    )
    assert row["ok"] is False
    assert row["issues_de"]


def test_build_audit_persists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps(
            {
                "apps": [
                    {"id": "x", "tier": "core", "label_de": "X", "exec_rel": "tools/x.sh"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/x.sh").write_text("#!/bin/bash\ntrue\n", encoding="utf-8")
    (tmp_path / "tools/x.sh").chmod(0o755)
    doc = build_local_apps_audit(tmp_path, persist=True)
    assert (tmp_path / "evidence/local_apps_audit_latest.json").is_file()
    assert doc["total"] == 1
    html = render_local_apps_section(tmp_path, doc)
    assert "local-apps" in html
    assert "Lokale Anwendungen" in html
