from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.stable_server import kill_duplicate_hubs, list_hub_pids


def test_list_hub_pids_empty(tmp_path: Path) -> None:
    with patch("analytics.stable_server.subprocess.run") as run:
        run.return_value.stdout = ""
        run.return_value.returncode = 1
        assert list_hub_pids(tmp_path) == []
