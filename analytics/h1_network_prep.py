"""H1 Hard/Soft-Netzwerk — Prep vor execute/observe (NVMe, GPU, Ollama, Pulse)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/h1_network_prep_latest.json")


def run_h1_network_prep(root: Path, *, phase: str = "execute") -> Dict[str, Any]:
    """Ein Takt: NVMe-Env → Ollama-Unload → GPU-Policy → Netzwerk-Pulse."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    nvme_doc: Dict[str, Any] = {}
    try:
        from execution.linux_nvme_storage import apply_nvme_storage_env, storage_status

        nvme_doc = storage_status(root)
        applied = apply_nvme_storage_env(root)
        steps.append(
            {
                "step": "nvme",
                "ok": bool(nvme_doc.get("mount")),
                "mount": nvme_doc.get("mount"),
                "applied_env": applied,
                "message_de": (
                    "NVMe aktiv — Cache auf SSD"
                    if nvme_doc.get("mount")
                    else "NVMe offline — bash tools/king_ops.sh nvme nach Mount"
                ),
            }
        )
    except Exception as exc:
        steps.append({"step": "nvme", "ok": False, "error_de": str(exc)[:120]})

    hw_doc: Dict[str, Any] = {}
    try:
        from analytics.king_hardware import prepare_h1_hardware

        hw_doc = prepare_h1_hardware(root, phase=phase)
        steps.append(
            {
                "step": "hardware",
                "ok": bool(hw_doc.get("ok")),
                "gpu_returns": hw_doc.get("gpu_returns"),
                "actions": hw_doc.get("actions"),
                "vram_policy_de": hw_doc.get("vram_policy_de"),
            }
        )
    except Exception as exc:
        steps.append({"step": "hardware", "ok": False, "error_de": str(exc)[:120]})

    pulse: Dict[str, Any] = {}
    try:
        from analytics.king_network import sync_network_pulse

        pulse = sync_network_pulse(root, source_node="bash")
        steps.append({"step": "network_pulse", "ok": True, "phase": pulse.get("phase"), "beat": pulse.get("beat")})
    except Exception as exc:
        steps.append({"step": "network_pulse", "ok": False, "error_de": str(exc)[:120]})

    gpu_ready = bool((hw_doc.get("gpu_returns") or {}).get("enabled"))
    blockers: List[str] = []
    if not nvme_doc.get("mount"):
        blockers.append("NVMe nicht gemountet — I/O langsamer (optional)")
    if not gpu_ready:
        blockers.append(str((hw_doc.get("gpu_returns") or {}).get("reason_de") or "GPU-Returns aus"))

    out: Dict[str, Any] = {
        "ok": True,
        "phase": phase,
        "prep_ready_de": gpu_ready,
        "gpu_ready": bool((hw_doc.get("gpu_returns") or {}).get("enabled")),
        "nvme_mounted": bool(nvme_doc.get("mount")),
        "blockers_de": blockers,
        "steps": steps,
        "hardware": hw_doc,
        "nvme": nvme_doc,
        "pulse": pulse,
        "next_action_de": (
            "bash tools/king_ops.sh h1-seal"
            if (hw_doc.get("gpu_returns") or {}).get("enabled")
            else "bash tools/king_ops.sh h1-prep — GPU/VRAM prüfen"
        ),
        "headline_de": (
            f"H1-Prep · GPU={'ON' if (hw_doc.get('gpu_returns') or {}).get('enabled') else 'OFF'} · "
            f"NVMe={'ja' if nvme_doc.get('mount') else 'nein'}"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out
