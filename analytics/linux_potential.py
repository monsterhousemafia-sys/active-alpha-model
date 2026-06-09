"""Linux-Potenzial — Scan, sichere Anwendung, Evidence für R3."""
from __future__ import annotations

import json
import os
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/linux_potential.json")
_EVIDENCE_REL = Path("evidence/linux_potential_latest.json")


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


def load_linux_potential_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _ollama_ready(root: Path) -> bool:
    runtime = _load_json(Path(root) / "control/alpha_model_local_runtime.json")
    base = str(runtime.get("ollama_base_url") or "http://127.0.0.1:11434")
    try:
        from urllib.parse import urlparse

        p = urlparse(base)
        with socket.create_connection((p.hostname or "127.0.0.1", int(p.port or 11434)), timeout=0.6):
            return True
    except OSError:
        return False


def _gpu_ready(root: Path) -> Dict[str, Any]:
    hw = _load_json(Path(root) / "evidence/king_hardware_latest.json")
    prep = _load_json(Path(root) / "evidence/h1_network_prep_latest.json")
    gpu_on = bool((hw.get("gpu_returns") or {}).get("enabled"))
    mem = hw.get("memory_available_gb")
    hung = bool((hw.get("benchmark") or {}).get("benchmark_hung"))
    ok = bool(prep.get("ok")) and not hung and (mem is None or float(mem) >= 8.0)
    return {
        "ok": ok or gpu_on,
        "gpu_returns": gpu_on,
        "memory_gb": mem,
        "prep_ok": bool(prep.get("ok")),
        "detail_de": str(prep.get("headline_de") or hw.get("headline_de") or "H1-Prep prüfen")[:100],
    }


def _check_dimension(root: Path, dim_id: str) -> Dict[str, Any]:
    root = Path(root)
    ok = False
    detail = "—"
    if dim_id == "local_runtime":
        rt = _load_json(root / "control/alpha_model_local_runtime.json")
        ok = rt.get("local_only") is True and str(rt.get("hub_bind") or "") == "127.0.0.1"
        detail = str(rt.get("hub_url") or "")
    elif dim_id == "r3_stack":
        stack = _load_json(root / "evidence/stack_integrity_latest.json")
        ok = bool(stack.get("stack_ok"))
        detail = "OK" if ok else ", ".join((stack.get("failures_de") or [])[:2]) or "prüfen"
    elif dim_id == "cognitive_v2":
        try:
            from analytics.linux_runtime_unified import cognitive_v2_active, control_plane_mode

            ok = bool(cognitive_v2_active(root)) and control_plane_mode(root) == "v2"
            detail = "Cognitive Kernel v2"
        except Exception as exc:
            detail = str(exc)[:60]
    elif dim_id == "session_autostart":
        try:
            from analytics.r3_community_stealth import (
                community_stealth_enabled,
                session_autostart_path,
            )

            path = session_autostart_path(root)
            ok = path.is_file()
            label = "Stealth" if community_stealth_enabled(root) else "R3"
            detail = f"{label}: {path}" if ok else "fehlt — bash tools/king_ops.sh r3-stealth"
        except Exception:
            path = Path.home() / ".config/autostart/r3-os-session.desktop"
            ok = path.is_file()
            detail = str(path) if ok else "fehlt — install_r3_app.sh"
    elif dim_id == "ollama_local":
        ok = _ollama_ready(root)
        detail = "127.0.0.1:11434" if ok else "offline"
    elif dim_id == "nvme_tier":
        try:
            from execution.linux_nvme_storage import storage_status

            st = storage_status(root)
            ok = bool(st.get("constant_storage_active"))
            detail = str(st.get("mount") or "nicht gemountet")
        except Exception as exc:
            detail = str(exc)[:60]
    elif dim_id == "gpu_ready":
        g = _gpu_ready(root)
        ok = bool(g.get("ok"))
        detail = str(g.get("detail_de") or "")
    elif dim_id == "maintain_ok":
        ready = _load_json(root / "evidence/aa_ready_latest.json")
        ok = bool(ready.get("ok", True)) if ready else True
        detail = str(ready.get("headline_de") or "maintain")[:80]
    elif dim_id == "lean_mode":
        lean = _load_json(root / "evidence/aa_lean_mode_latest.json")
        ok = bool(lean.get("enabled_at_utc"))
        detail = str(lean.get("mode") or "—")
    return {"id": dim_id, "ok": ok, "detail_de": detail[:100]}


def scan_linux_potential(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = load_linux_potential_policy(root)
    dims = list(policy.get("dimensions") or [])
    states: List[Dict[str, Any]] = []
    weight_ok = weight_total = 0
    for dim in dims:
        if not isinstance(dim, dict):
            continue
        did = str(dim.get("id") or "")
        w = int(dim.get("weight") or 10)
        weight_total += w
        st = _check_dimension(root, did)
        st["label_de"] = str(dim.get("label_de") or did)
        st["weight"] = w
        if st.get("ok"):
            weight_ok += w
        states.append(st)

    pct = int(round(100 * weight_ok / weight_total)) if weight_total else 0
    open_dims = [s for s in states if not s.get("ok")]
    next_de = (
        f"Linux ausbauen: {open_dims[0].get('label_de')} — {open_dims[0].get('detail_de')}"
        if open_dims
        else "Linux-Potenzial voll — R3 nutzt die Umgebung"
    )
    if any(s.get("id") == "nvme_tier" and not s.get("ok") for s in states):
        next_de = (
            "NVMe freischalten: bash tools/king_ops.sh nvme "
            "(einmalig Passwort: bash tools/install_active_alpha_sudoers.sh)"
        )

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "potential_pct": pct,
        "dimensions_ok": sum(1 for s in states if s.get("ok")),
        "dimensions_total": len(states),
        "dimensions": states,
        "headline_de": f"Linux {pct}% — {sum(1 for s in states if s.get('ok'))}/{len(states)} Dimensionen",
        "next_de": next_de,
        "local_only": True,
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def apply_linux_potential_safe(root: Path) -> Dict[str, Any]:
    """Sichere Schritte ohne sudo — volles lokales Potenzial wo möglich."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    def _step(sid: str, label: str, fn) -> None:
        try:
            out = fn()
            steps.append({"id": sid, "label_de": label, "ok": bool(out.get("ok", True)), "detail": out})
        except Exception as exc:
            steps.append({"id": sid, "label_de": label, "ok": False, "error_de": str(exc)[:120]})

    _step(
        "local_first",
        "R3 lokal-first",
        lambda: __import__("analytics.r3_local_first", fromlist=["apply_r3_local_first"]).apply_r3_local_first(root),
    )
    _step(
        "nvme_symlinks",
        "NVMe-Symlinks reparieren",
        lambda: {
            "ok": True,
            **__import__("execution.linux_nvme_storage", fromlist=["repair_migrated_symlinks"]).repair_migrated_symlinks(root),
        },
    )

    def _nvme_env() -> Dict[str, Any]:
        from execution.linux_nvme_storage import apply_nvme_constant_storage, apply_nvme_storage_env, storage_status

        st = storage_status(root)
        env = apply_nvme_storage_env(root)
        if st.get("mount"):
            env.update(apply_nvme_constant_storage(root))
        return {"ok": True, "env": env, "mount": st.get("mount")}

    _step("nvme_env", "NVMe-Umgebung", _nvme_env)

    _step(
        "timer_catalog",
        "Timer-Katalog v2",
        lambda: __import__("analytics.linux_runtime_unified", fromlist=["sync_operator_timer_catalog"]).sync_operator_timer_catalog(root),
    )

    _step(
        "hub",
        "Hub sicherstellen",
        lambda: {
            "ok": True,
            "port": __import__("analytics.hub_runtime", fromlist=["ensure_running"]).ensure_running(root),
        },
    )

    _step(
        "r3_align",
        "R3 Abgleich",
        lambda: __import__("analytics.r3_runtime_upgrade", fromlist=["align_r3_surface"]).align_r3_surface(
            root, scan_upgrades=True, warm_cache=True, sync_flow=False, persist=True
        ),
    )

    _step(
        "growth",
        "R3 Wachstum",
        lambda: __import__("analytics.r3_local_growth", fromlist=["scan_local_growth"]).scan_local_growth(
            root, persist=True, force=True, fast=False
        ),
    )

    _step(
        "community_stealth",
        "Community-Stealth Autostart",
        lambda: __import__(
            "analytics.r3_community_stealth", fromlist=["install_community_stealth"]
        ).install_community_stealth(root, persist=True),
    )

    scan = scan_linux_potential(root, persist=True)
    ok_n = sum(1 for s in steps if s.get("ok"))
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok_n == len(steps),
        "steps": steps,
        "potential_pct": scan.get("potential_pct"),
        "headline_de": scan.get("headline_de"),
        "next_de": scan.get("next_de"),
        "confirmation_de": f"Linux-Potenzial {scan.get('potential_pct')}% — {ok_n}/{len(steps)} Schritte OK",
    }
    atomic_write_json(root / Path("evidence/linux_potential_apply_latest.json"), doc)
    return doc
