from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from analytics.local_llm_bridge import run_kernel_command


def test_run_kernel_command_passes_king_ops_subcommand(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    calls: list[list[str]] = []

    def _fake_run(argv, **kwargs):
        calls.append(list(argv))
        class _P:
            returncode = 0
            stdout = '{"ok": true}'
            stderr = ""

        return _P()

    with patch.dict(os.environ, {"AA_AGENT_CHAMBER": "1"}, clear=False):
        with patch(
            "analytics.alpha_model_chamber_resources.chamber_kernel_allowlist",
            return_value=["king-ops", "king-tune"],
        ):
            with patch("subprocess.run", side_effect=_fake_run):
                out = run_kernel_command(root, "king-ops pipeline")
    assert calls
    assert "pipeline" in calls[0]
    assert calls[0][-2:] == ["king-ops", "pipeline"]
    assert "ok" in out or "{" in out
