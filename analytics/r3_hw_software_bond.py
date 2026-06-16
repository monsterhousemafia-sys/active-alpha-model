"""R3 Hardware↔Software-Bond — ein Resolver für Laufzeit, Cache und Start.

Architektur:
  king_hardware_policy + Host-IST (CPU/RAM/NVMe/GPU)
        ↓
  resolve_r3_runtime_tuning()  ←  control/r3_runtime_profile.json (Software-Intent)
        ↓
  Mirror-Poll · Cache · Startup · Warm-Prep
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_hw_software_bond_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _host_snapshot(root: Path) -> Dict[str, Any]:
    root = Path(root)
    preview: Dict[str, Any] = {}
    try:
        from analytics.preview_hardware_status import build_preview_hardware_status

        preview = build_preview_hardware_status(root)
    except Exception:
        preview = {}
    host: Dict[str, Any] = {}
    try:
        from analytics.h1_king_runtime import detect_host_resources

        host = detect_host_resources()
    except Exception:
        host = {}
    policy = _load_json(root / "control/king_hardware_policy.json")
    return {
        "preview": preview,
        "host": host,
        "policy_headline_de": str(policy.get("headline_de") or "")[:120],
        "host_profile_de": str(policy.get("host_profile_de") or ""),
    }


def _pressure_class(
    *,
    mem_gb: Optional[float],
    load_per_cpu: Optional[float],
    h1_running: bool,
) -> str:
    if h1_running:
        return "constrained"
    if mem_gb is not None and mem_gb < 8:
        return "constrained"
    if load_per_cpu is not None and load_per_cpu > 0.85:
        return "constrained"
    if mem_gb is not None and mem_gb >= 16 and (load_per_cpu is None or load_per_cpu < 0.55):
        return "fast"
    return "balanced"


def resolve_r3_runtime_tuning(root: Path) -> Dict[str, Any]:
    """Effektive R3-Laufzeit — Software-Profil moduliert durch Hardware-IST."""
    root = Path(root)
    from analytics.r3_runtime_upgrade import load_runtime_profile

    profile = load_runtime_profile(root)
    snap = _host_snapshot(root)
    preview = snap.get("preview") or {}
    mem_gb = preview.get("mem_available_gb")
    load_per_cpu = preview.get("load_per_cpu")
    h1 = preview.get("h1") or {}
    h1_running = bool(h1.get("running"))
    nvme = preview.get("nvme") or {}
    nvme_ok = bool(nvme.get("mount")) and not nvme.get("error")

    startup_delay = 8
    try:
        from analytics.r3_os_supremacy import load_supremacy

        startup_delay = int((load_supremacy(root).get("session") or {}).get("startup_delay_sec") or 8)
    except Exception:
        startup_delay = 8

    poll_ms = int(profile.get("mirror_poll_ms") or 45_000)
    cache_stale = float(profile.get("cache_stale_sec") or 120)
    soft_update = bool(profile.get("mirror_soft_update", True))
    exec_mirror = False
    try:
        from analytics.r3_surface import exec_mirror_mode

        exec_mirror = bool(exec_mirror_mode(root))
    except Exception:
        exec_mirror = False

    pressure = _pressure_class(mem_gb=mem_gb, load_per_cpu=load_per_cpu, h1_running=h1_running)
    warm_live_prep = True
    notes: list[str] = []

    if pressure == "constrained":
        poll_ms = int(poll_ms * 1.35)
        warm_live_prep = False
        startup_delay = min(20, startup_delay + 4)
        notes.append("Ressourcen knapp — langsamer Poll, kein Live-Prep")
    elif pressure == "fast" and nvme_ok:
        poll_ms = max(12_000, int(poll_ms * 0.85))
        startup_delay = max(4, startup_delay - 2)
        cache_stale = max(90.0, cache_stale * 0.9)
        notes.append("NVMe + freie Ressourcen — schnellerer Start/Poll")

    if exec_mirror:
        soft_update = True
        warm_live_prep = warm_live_prep and not h1_running

    poll_ms = max(12_000, min(120_000, poll_ms))
    startup_delay = max(3, min(24, startup_delay))
    cache_stale = max(60.0, min(600.0, cache_stale))

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "pressure_class": pressure,
        "exec_mirror_only": exec_mirror,
        "headline_de": f"HW/SW {pressure} — Poll {poll_ms // 1000}s · Start {startup_delay}s",
        "notes_de": notes,
        "hardware": {
            "mem_available_gb": mem_gb,
            "load_per_cpu": load_per_cpu,
            "h1_running": h1_running,
            "nvme_ok": nvme_ok,
            "ram_gb": (snap.get("host") or {}).get("ram_gb"),
            "logical_cores": (snap.get("host") or {}).get("logical_cores"),
            "gpu_available": (snap.get("host") or {}).get("gpu_available"),
            "policy_headline_de": snap.get("policy_headline_de"),
        },
        "software_profile_id": str(profile.get("profile_id") or "default"),
        "mirror": {
            "mirror_poll_ms": poll_ms,
            "mirror_soft_update": soft_update,
            "mirror_reload_on_evidence_change": bool(profile.get("mirror_reload_on_evidence_change", False)),
            "mirror_prep_every_n_polls": int(profile.get("mirror_prep_every_n_polls") or 4),
        },
        "cache": {
            "cache_stale_sec": cache_stale,
            "warm_live_prep": warm_live_prep,
        },
        "startup": {
            "startup_delay_sec": startup_delay,
            "cockpit_optional": exec_mirror,
        },
        "evidence_ref": str(_EVIDENCE_REL).replace("\\", "/"),
    }


def sync_r3_hw_software_bond(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    doc = resolve_r3_runtime_tuning(root)
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
