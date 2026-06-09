from pathlib import Path
from unittest.mock import patch

from analytics.r3_full_refresh import run_r3_full_refresh


def test_r3_full_refresh_chain(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_full_refresh_policy.json").write_text("{}", encoding="utf-8")
    with patch("tools.preview_hub.ensure_hub_running", return_value=17890):
        with patch(
            "analytics.hub_runtime.build_health_report",
            return_value={"online": True, "port": 17890},
        ):
            with patch(
                "analytics.r3_runtime_upgrade.align_r3_surface",
                return_value={
                    "ok": True,
                    "headline_de": "Align OK",
                    "steps": [
                        {"step": "warm_cache", "ok": True, "bytes": 5000},
                        {"step": "sync_flow", "ok": True, "fluidity_pct": 100},
                    ],
                },
            ):
                with patch(
                    "analytics.desktop_shell_cache.warm_desktop_cache",
                    return_value=8000,
                ):
                    with patch(
                        "analytics.r3_mirror_state.build_exec_mirror_state",
                        return_value={"ok": True, "headline_de": "Mirror OK"},
                    ):
                        with patch(
                            "analytics.r3_ops_kernel.run_ops_pipeline",
                            return_value={
                                "ok": True,
                                "headline_de": "Surface OK",
                                "steps": [{"id": "quotes", "ok": True}, {"id": "daytrading_snapshot", "ok": True}],
                            },
                        ):
                            doc = run_r3_full_refresh(tmp_path, persist=True)
    assert doc.get("gui_ok") is True
    assert doc.get("steps_ok") == 5
    assert (tmp_path / "evidence/r3_full_refresh_latest.json").is_file()
