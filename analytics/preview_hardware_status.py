"""Hardware-Readiness für Preview Command Center + Worker."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _cpu_count() -> int:
    try:
        return int(os.cpu_count() or 1)
    except (TypeError, ValueError):
        return 1


def _load_avg() -> Optional[float]:
    try:
        la = os.getloadavg()
        return float(la[0]) if la else None
    except (AttributeError, OSError):
        return None


def _mem_available_gb() -> Optional[float]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            lines = {ln.split(":")[0]: ln.split(":")[1].strip() for ln in fh if ":" in ln}
        avail = lines.get("MemAvailable") or lines.get("MemFree") or ""
        kb = int(str(avail).split()[0])
        return round(kb / (1024 * 1024), 1)
    except (OSError, ValueError, IndexError):
        return None


def _disk_free_gb(path: Path) -> Optional[float]:
    try:
        st = os.statvfs(path)
        return round((st.f_bavail * st.f_frsize) / (1024**3), 1)
    except OSError:
        return None


def _ollama_active() -> bool:
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", "ollama.service"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return proc.stdout.strip() == "active"
    except Exception:
        return False


def build_preview_hardware_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cpus = _cpu_count()
    load = _load_avg()
    mem_gb = _mem_available_gb()
    load_per_cpu = round(load / cpus, 2) if load is not None and cpus else None

    try:
        from execution.linux_nvme_storage import storage_status

        nvme = storage_status(root)
    except Exception as exc:
        nvme = {"error": str(exc)[:120]}

    h1: Dict[str, Any] = {}
    try:
        from execution.h1_cpu_priority import find_h1_backtest_pids, h1_priority_profile, is_h1_yield_to_operator_hours

        pids = find_h1_backtest_pids(root)
        h1 = {
            "running": bool(pids),
            "pids": pids,
            "yield_hours": is_h1_yield_to_operator_hours(),
            "profile": h1_priority_profile(),
        }
    except Exception as exc:
        h1 = {"error": str(exc)[:120]}

    recommendations: List[str] = []
    score = 100

    migrated = nvme.get("migrated_dirs") or []
    on_nvme = sum(1 for d in migrated if d.get("on_nvme") or d.get("symlink"))
    if not nvme.get("mount"):
        score -= 25
        recommendations.append(
            "NVMe 1TB nicht eingehängt — udisksctl mount -b /dev/nvme0n1p1 oder mount_nvme_active_alpha.sh"
        )
    elif on_nvme < max(3, len(migrated) // 2):
        score -= 10
        recommendations.append("NVMe da — Migration fortsetzen: bash tools/setup_nvme_storage.sh")
    elif h1.get("running"):
        recommendations.append(
            "H1 läuft noch — validation_runs/model_output vollständig nach COMPLETE via setup_nvme_storage.sh"
        )

    if load_per_cpu is not None and load_per_cpu > 0.85:
        score -= 15
        recommendations.append(f"CPU-Auslastung hoch (Load/CPU {load_per_cpu}) — H1 nachts bevorzugen")
    elif h1.get("running") and not h1.get("yield_hours"):
        recommendations.append("H1 läuft nachts mit höherer Priorität — OK für Backtest-Geschwindigkeit")

    if mem_gb is not None and mem_gb < 8:
        score -= 20
        recommendations.append(f"Wenig RAM frei ({mem_gb} GB) — Preview+Ollama können stocken")
    elif mem_gb is not None and mem_gb >= 16:
        pass  # 60GB machine — excellent

    if not _ollama_active():
        score -= 5
        recommendations.append("Ollama user-service nicht aktiv — systemctl --user start ollama.service")

    disk_gb = _disk_free_gb(root)
    if disk_gb is not None and disk_gb < 30:
        score -= 10
        recommendations.append(f"Wenig Platte auf Projekt-Volume ({disk_gb} GB frei)")

    if h1.get("running") and h1.get("yield_hours"):
        recommendations.append("H1 tagsüber gedrosselt (nice/ionice) — Preview/Hub haben Vorrang")

    optimal = score >= 85 and bool(nvme.get("mount") or disk_gb and disk_gb > 100)

    return {
        "schema_version": 1,
        "optimal_for_preview_de": optimal,
        "score": max(0, min(100, score)),
        "cpu": {
            "logical": cpus,
            "load_1m": load,
            "load_per_cpu": load_per_cpu,
        },
        "memory_available_gb": mem_gb,
        "disk_free_gb": disk_gb,
        "nvme": nvme,
        "h1": h1,
        "ollama_user_service_active": _ollama_active(),
        "recommendations_de": recommendations,
        "headline_de": (
            "Hardware optimal für Preview"
            if optimal
            else f"Hardware OK mit {len(recommendations)} Optimierung(en)"
        ),
    }
