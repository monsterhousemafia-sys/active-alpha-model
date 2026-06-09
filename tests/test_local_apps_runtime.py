from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.local_apps_runtime import build_runtime_audit, runtime_check_app


def test_runtime_marktanalyse_bash(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir(parents=True)
    sh = tmp_path / "tools/marktanalyse_bash.sh"
    sh.write_text("#!/bin/bash\ncase \"$1\" in help) exit 0;; esac\nexit 1\n", encoding="utf-8")
    sh.chmod(0o755)
    row = runtime_check_app(
        tmp_path,
        {"id": "marktanalyse_bash", "label_de": "Bash", "exec_rel": "tools/marktanalyse_bash.sh"},
    )
    assert row.get("runtime_ok") is True


def test_build_runtime_audit(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir(parents=True)
    sh = tmp_path / "tools/bash_gpt4o.sh"
    sh.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    sh.chmod(0o755)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/bash_gpt4o.json").write_text("{}", encoding="utf-8")
    apps = [{"id": "bash_gpt4o", "label_de": "GPT", "exec_rel": "tools/bash_gpt4o.sh"}]
    with patch("analytics.bash_gpt4o.bash_gpt4o_status", return_value={"ready": True, "display_model": "gpt-4o"}):
        with patch("analytics.local_apps_runtime._run", return_value=(True, "OK")):
            doc = build_runtime_audit(tmp_path, apps)
    assert doc["total"] == 1
    assert (tmp_path / "evidence/local_apps_runtime_latest.json").is_file()
