"""AI Kernel ↔ König 32B ↔ Hardware-Bond."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.ai_kernel_hardware_bond import (
    bond_kernel_to_king_32b,
    hardware_context_for_king,
    resolve_king_model,
)
from execution.linux_nvme_storage import apply_nvme_constant_storage, storage_status


def _seed_tier(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/alpha_model_entfaltung_32b.json").write_text(
        json.dumps(
            {
                "chat_agent": {"model": "qwen2.5-coder:32b", "preload_on_start": False},
                "role_models": {"chat": "qwen2.5-coder:32b"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/king_hardware_policy.json").write_text(
        json.dumps({"kernel_bond": {"enabled": True}}),
        encoding="utf-8",
    )


def test_resolve_king_model(tmp_path: Path) -> None:
    _seed_tier(tmp_path)
    assert resolve_king_model(tmp_path) == "qwen2.5-coder:32b"


def test_nvme_constant_storage_env(tmp_path: Path) -> None:
    mount = tmp_path / "nvme"
    mount.mkdir()
    data = mount / "active_alpha_fast_data"
    data.mkdir()
    (tmp_path / "control").mkdir(exist_ok=True)
    (tmp_path / "control/linux_nvme_storage.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "mount_candidates": [str(mount)],
                "data_subdir": "active_alpha_fast_data",
                "constant_storage": {
                    "priority": "high",
                    "env_dirs": {"AA_KERNEL_STORE": "kernel_store"},
                },
            }
        ),
        encoding="utf-8",
    )
    applied = apply_nvme_constant_storage(tmp_path)
    assert applied.get("AA_NVME_PRIORITY") == "high"
    assert (data / "kernel_store").is_dir()
    status = storage_status(tmp_path)
    assert status.get("constant_storage_active") is True


def test_bond_persists_evidence(tmp_path: Path) -> None:
    _seed_tier(tmp_path)
    (tmp_path / "evidence").mkdir(exist_ok=True)
    with patch("analytics.king_hardware.build_hardware_snapshot") as snap, patch(
        "analytics.local_llm_bridge.health_report",
        return_value={"ready": True, "installed_models": ["qwen2.5-coder:32b"]},
    ), patch(
        "analytics.alpha_model_entfaltung_32b.tier_status",
        return_value={
            "tier_ready": True,
            "chat_32b_active": True,
            "resolved_chat_model": "qwen2.5-coder:32b",
        },
    ):
        snap.return_value = {
            "nvme_mounted": False,
            "gpu_returns": {"enabled": False, "reason_de": "test"},
            "ollama_loaded": [],
            "memory_available_gb": 32.0,
            "host": {},
        }
        doc = bond_kernel_to_king_32b(tmp_path, persist=True, preload=False)
    assert doc.get("king_model") == "qwen2.5-coder:32b"
    assert doc.get("hardware_access") is True
    assert (tmp_path / "evidence/ai_kernel_hardware_bond_latest.json").is_file()
    ctx = hardware_context_for_king(tmp_path)
    assert ctx.get("king_model") == "qwen2.5-coder:32b"
