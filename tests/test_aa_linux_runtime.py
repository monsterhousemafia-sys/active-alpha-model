from __future__ import annotations

import json
from pathlib import Path

from analytics.aa_linux_runtime import build_runtime_status, runtime_h1_prep
from analytics.evidence_inotify_watch import run_evidence_watch_once
from analytics.runtime_api_server import dispatch


def test_dispatch_ping(tmp_path: Path) -> None:
    out = dispatch(tmp_path, {"cmd": "ping"})
    assert out["ok"] is True
    assert out["result"]["pong"] is True


def test_evidence_watch_writes_snapshot(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence" / "launch_readiness_latest.json").write_text(
        json.dumps({"ok": True}) + "\n",
        encoding="utf-8",
    )
    doc = run_evidence_watch_once(tmp_path)
    assert doc["schema_version"] == 1
    assert (tmp_path / "evidence/runtime_watch_latest.json").is_file()


def test_runtime_h1_prep_no_crash(tmp_path: Path) -> None:
    doc = runtime_h1_prep(tmp_path)
    assert "status" in doc


def test_build_runtime_status_no_crash(tmp_path: Path) -> None:
    doc = build_runtime_status(tmp_path)
    assert doc["schema_version"] == 1
