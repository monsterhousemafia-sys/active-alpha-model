"""R3 Aktien-App — nur DAILY_ALPHA_H1."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_aktien_app import build_aktien_status, launch_aktien_app, load_aktien_config, model_policy


def test_load_aktien_config_project() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_aktien_config(root)
    assert cfg.get("allowed_variant") == "DAILY_ALPHA_H1"


def test_model_policy_project() -> None:
    root = Path(__file__).resolve().parents[1]
    pol = model_policy(root)
    assert pol.get("allowed_variant") == "DAILY_ALPHA_H1"
    assert pol.get("active_profile") == "daily_alpha_h1"


def test_model_policy_rejects_wrong_profile(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_aktien_app.json").write_text(
        json.dumps({"allowed_profile": "daily_alpha_h1", "allowed_variant": "DAILY_ALPHA_H1"}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "active_profile": "r3_w075_production",
                "profiles": {"r3_w075_production": {"variant_key": "R3_w075_q065_noexit"}},
            }
        ),
        encoding="utf-8",
    )
    pol = model_policy(tmp_path)
    assert pol.get("ok") is False


def test_launch_rejects_wrong_model(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_aktien_app.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"active_profile": "other", "profiles": {"other": {"variant_key": "X"}}}),
        encoding="utf-8",
    )
    doc = launch_aktien_app(tmp_path)
    assert doc.get("ok") is False


def test_build_aktien_status_project() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_aktien_status(root)
    assert doc.get("aktien_model_de") == "DAILY_ALPHA_H1"
