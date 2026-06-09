"""AI Kernel ↔ König 32B ↔ Hardware — direkte Verknüpfung mit NVMe-Priorität."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/ai_kernel_hardware_bond_latest.json")
_POLICY_REL = Path("control/king_hardware_policy.json")
_TIER_REL = Path("control/alpha_model_entfaltung_32b.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def resolve_king_model(root: Path) -> str:
    tier = _load_json(Path(root) / _TIER_REL)
    chat = tier.get("chat_agent") or {}
    model = str(chat.get("model") or tier.get("role_models", {}).get("chat") or "")
    if model:
        return model
    try:
        from analytics.alpha_model_entfaltung_32b import tier_status

        return str(tier_status(root).get("resolved_chat_model") or "qwen2.5-coder:32b")
    except Exception:
        return "qwen2.5-coder:32b"


def hardware_context_for_king(root: Path) -> Dict[str, Any]:
    """Kompakter Hardware-Kontext für König-32B (Chat/System-Prompt)."""
    root = Path(root)
    snap = _load_json(root / _EVIDENCE_REL)
    if snap.get("king_model"):
        return {
            "kernel": "ai_kernel",
            "king_model": snap.get("king_model"),
            "nvme_mounted": snap.get("nvme_mounted"),
            "nvme_priority": snap.get("nvme_priority"),
            "gpu_returns_enabled": (snap.get("gpu_returns") or {}).get("enabled"),
            "gpu_reason_de": (snap.get("gpu_returns") or {}).get("reason_de"),
            "memory_available_gb": snap.get("memory_available_gb"),
            "ollama_loaded": snap.get("ollama_loaded") or [],
            "headline_de": snap.get("headline_de"),
        }
    bond = bond_kernel_to_king_32b(root, persist=False, preload=False)
    return {
        "kernel": "ai_kernel",
        "king_model": bond.get("king_model"),
        "nvme_mounted": bond.get("nvme_mounted"),
        "nvme_priority": bond.get("nvme_priority"),
        "gpu_returns_enabled": (bond.get("gpu_returns") or {}).get("enabled"),
        "gpu_reason_de": (bond.get("gpu_returns") or {}).get("reason_de"),
        "memory_available_gb": bond.get("memory_available_gb"),
        "ollama_loaded": bond.get("ollama_loaded") or [],
        "headline_de": bond.get("headline_de"),
    }


def bond_kernel_to_king_32b(
    root: Path,
    *,
    persist: bool = True,
    preload: bool = False,
    phase: str = "sync",
) -> Dict[str, Any]:
    """
    Verknüpft ai_kernel direkt mit König-32B und Hardware-Komponenten.
    NVMe-Konstantspeicher wird mit hoher Priorität aktiviert.
    """
    root = Path(root)
    try:
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(root)
    except Exception:
        pass

    nvme_env: Dict[str, str] = {}
    nvme_status: Dict[str, Any] = {}
    try:
        from execution.linux_nvme_storage import apply_nvme_constant_storage, storage_status

        nvme_env = apply_nvme_constant_storage(root)
        nvme_status = storage_status(root)
    except Exception as exc:
        nvme_status = {"error_de": str(exc)[:120]}

    hardware: Dict[str, Any] = {}
    try:
        from analytics.king_hardware import build_hardware_snapshot

        hardware = build_hardware_snapshot(root, phase=phase)
    except Exception as exc:
        hardware = {"error_de": str(exc)[:120], "nvme_mounted": False}

    tier: Dict[str, Any] = {}
    health: Dict[str, Any] = {}
    try:
        from analytics.alpha_model_entfaltung_32b import tier_status
        from analytics.local_llm_bridge import health_report

        tier = tier_status(root)
        health = health_report(root)
    except Exception:
        pass

    king_model = resolve_king_model(root)
    ollama_ready = bool(health.get("ready"))
    model_active = bool(tier.get("chat_32b_active") or tier.get("tier_ready"))
    nvme_mounted = bool(hardware.get("nvme_mounted") or nvme_status.get("constant_storage_active"))
    nvme_priority = os.environ.get("AA_NVME_PRIORITY") or nvme_status.get("constant_storage_priority")
    bonded = bool(king_model)
    runtime_ready = ollama_ready and model_active

    os.environ["AA_KERNEL_HARDWARE_BOND"] = "1" if bonded else "0"
    os.environ["AA_KING_MODEL"] = king_model
    if nvme_mounted:
        os.environ.setdefault("AA_NVME_PRIORITY", "high")

    preload_result: Optional[Dict[str, Any]] = None
    if preload and bonded:
        try:
            from analytics.alpha_model_entfaltung_32b import preload_ollama_model

            tier_cfg = _load_json(root / _TIER_REL).get("chat_agent") or {}
            preload_result = preload_ollama_model(
                root,
                king_model,
                num_ctx=tier_cfg.get("num_ctx"),
                keep_alive=str(tier_cfg.get("keep_alive") or "15m"),
            )
        except Exception as exc:
            preload_result = {"ok": False, "error_de": str(exc)[:120]}

    recommendations = list(hardware.get("recommendations_de") or [])
    if not nvme_mounted:
        recommendations.insert(0, "NVMe — bash tools/ai_kernel.py nvme-setup")

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "bonded_at_utc": _utc_now(),
        "ok": bonded,
        "runtime_ready": runtime_ready,
        "kernel": "ai_kernel",
        "king_cli": "alpha-model-agent",
        "king_model": king_model,
        "hardware_access": True,
        "hardware_policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "tier_ref": str(_TIER_REL).replace("\\", "/"),
        "nvme_mounted": nvme_mounted,
        "nvme_priority": nvme_priority,
        "nvme_storage": nvme_status,
        "nvme_env": nvme_env,
        "gpu_returns": hardware.get("gpu_returns") or {},
        "ollama_loaded": hardware.get("ollama_loaded") or [],
        "memory_available_gb": hardware.get("memory_available_gb"),
        "host": hardware.get("host") or {},
        "tier": {
            "tier_id": tier.get("tier_id"),
            "tier_ready": tier.get("tier_ready"),
            "resolved_chat_model": tier.get("resolved_chat_model"),
            "build_32b_active": tier.get("build_32b_active"),
        },
        "ollama_ready": ollama_ready,
        "preload": preload_result,
        "recommendations_de": recommendations,
        "headline_de": (
            f"Kernel ↔ 32B verbunden · {king_model}"
            + (f" · NVMe {nvme_priority}" if nvme_mounted else " · NVMe ausstehend")
            + ("" if runtime_ready else " · Ollama/Tier prüfen")
        ),
        "commands_de": [
            "python3 tools/ai_kernel.py kernel-bond",
            "python3 tools/ai_kernel.py storage",
            "bash tools/king_ops.sh nvme",
            "alpha-model-agent — König mit Hardware-Zugriff",
        ],
    }
    if persist:
        store = os.environ.get("AA_KERNEL_STORE")
        if store:
            atomic_write_json(Path(store) / "ai_kernel_hardware_bond_latest.json", doc)
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def load_hardware_bond(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)
