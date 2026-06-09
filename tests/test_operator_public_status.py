from __future__ import annotations

import json
from pathlib import Path

from analytics.operator_public_status import build_public_status, publish_public_status


def test_publish_public_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "control").mkdir()
    (tmp_path / "control/active_alpha_public_capabilities.json").write_text(
        json.dumps({"can_do_de": ["learn"], "cannot_do_de": ["autotrade"], "how_to_see_de": ["terminal"]}),
        encoding="utf-8",
    )
    (tmp_path / "control/linux_operator_timers.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/linux_operator_scope.json").write_text(
        json.dumps({"approved_levels": ["A"], "max_level": "A", "levels": {}}),
        encoding="utf-8",
    )
    path = publish_public_status(tmp_path)
    assert path.is_file()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("can_do_de") == ["learn"]
    txt = (tmp_path / ".local/share/r3-os/operator_latest.txt").read_text(encoding="utf-8")
    assert "learn" in txt


def test_build_public_status_project() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_public_status(root)
    assert doc.get("agent_name") == "Auto"
    assert doc.get("can_do_de")
