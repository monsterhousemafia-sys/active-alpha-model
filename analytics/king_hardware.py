"""Hard/Soft-Takt — Hardware-Snapshot, VRAM-Policy, Benchmark-ETA."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/king_hardware_policy.json")
_HARDWARE_EVIDENCE = Path("evidence/king_hardware_latest.json")


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


def load_hardware_policy(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _POLICY_REL)
    if doc:
        return doc
    return {
        "gpu": {"vram_min_mb_gpu_returns": 4096, "prefer_gpu_returns": True},
        "benchmark": {"eta_max_s_default": 4200, "eta_overrun_factor": 1.35, "hung_s": 5400},
    }


def ollama_ps_models(base_url: str = "http://127.0.0.1:11434") -> List[Dict[str, Any]]:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/ps", method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        return list(doc.get("models") or [])
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError, TimeoutError):
        return []


def ollama_unload_model(model: str, *, base_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
    """VRAM freigeben — keep_alive=0 (best-effort)."""
    name = str(model or "").strip()
    if not name:
        return {"ok": False, "reason_de": "kein Modell"}
    payload = json.dumps({"model": name, "keep_alive": 0}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
        return {"ok": True, "model": name, "action_de": "unload keep_alive=0"}
    except Exception as exc:
        return {"ok": False, "model": name, "error_de": str(exc)[:120]}


def _benchmark_pid(root: Path) -> Optional[int]:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "[.]venv/bin/python.*tools/generate_h1_naive_benchmark.py"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip().splitlines()
        if not line:
            return None
        return int(line[0].split()[0])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _benchmark_elapsed_s(pid: int) -> Optional[int]:
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "etimes="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode != 0:
            return None
        return int((proc.stdout or "").strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def resolve_gpu_returns_for_h1(
    root: Path,
    *,
    host: Optional[Dict[str, Any]] = None,
    ollama_models: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Soll H1 naive_gpu_returns nutzen? Hard/Soft abgestimmt."""
    root = Path(root)
    policy = load_hardware_policy(root)
    gpu_pol = policy.get("gpu") or {}
    min_vram = int(gpu_pol.get("vram_min_mb_gpu_returns") or 4096)
    prefer = gpu_pol.get("prefer_gpu_returns", True) is not False
    env_force = os.environ.get("AA_H1_GPU_RETURNS", "").strip().lower()
    if env_force in ("0", "false", "no"):
        return {"enabled": False, "reason_de": "AA_H1_GPU_RETURNS=0"}
    if env_force in ("1", "true", "yes"):
        return {"enabled": True, "reason_de": "AA_H1_GPU_RETURNS=1"}

    if host is None:
        try:
            from analytics.h1_king_runtime import detect_host_resources

            host = detect_host_resources()
        except Exception:
            host = {}
    if not host.get("gpu_available"):
        return {"enabled": False, "reason_de": host.get("gpu", {}).get("reason_de") or "GPU nicht verfügbar"}

    gpu = host.get("gpu") or {}
    free_mb = int(gpu.get("memory_free_mb") or 0)
    if ollama_models is None:
        ollama_models = ollama_ps_models()
    loaded_32b = any("32b" in str(m.get("name") or "").lower() for m in ollama_models)
    reserve = int(gpu_pol.get("vram_reserve_mb_ollama_32b") or 20000)
    if loaded_32b and free_mb < reserve:
        return {
            "enabled": False,
            "reason_de": f"Ollama 32B in VRAM — nur {free_mb} MB frei (Reserve {reserve})",
            "vram_policy_de": "ollama entladen vor H1",
        }
    if free_mb < min_vram:
        return {"enabled": False, "reason_de": f"VRAM zu knapp ({free_mb} MB < {min_vram})"}
    if not prefer:
        return {"enabled": False, "reason_de": "prefer_gpu_returns=false"}
    return {
        "enabled": True,
        "reason_de": f"CuPy Returns — {free_mb} MB VRAM frei",
        "gpu_name": gpu.get("name"),
        "memory_free_mb": free_mb,
    }


def vram_policy_for_phase(phase: str, *, gpu_resolve: Dict[str, Any], ollama_models: List[Dict[str, Any]]) -> str:
    loaded = [str(m.get("name") or "") for m in ollama_models if m.get("name")]
    if phase in ("observe", "execute"):
        if loaded:
            return f"H1-Phase {phase}: Ollama entladen ({', '.join(loaded)}) — VRAM für Benchmark"
        if gpu_resolve.get("enabled"):
            return f"H1-Phase {phase}: GPU-Returns aktiv ({gpu_resolve.get('reason_de')})"
        return f"H1-Phase {phase}: CPU-Returns ({gpu_resolve.get('reason_de')})"
    if phase in ("decide", "ready", "build"):
        if not loaded:
            return f"Phase {phase}: König/Cursor — Ollama preload OK (32B)"
        return f"Phase {phase}: Ollama geladen — Chat bereit"
    return f"Phase {phase}: Standard"


def benchmark_timing(root: Path, *, policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root)
    policy = policy or load_hardware_policy(root)
    bench = policy.get("benchmark") or {}
    eta_max = int(bench.get("eta_max_s_default") or 4200)
    hung_s = int(bench.get("hung_s") or 5400)
    overrun = float(bench.get("eta_overrun_factor") or 1.35)
    pid = _benchmark_pid(root)
    elapsed: Optional[int] = None
    running = pid is not None
    if pid is not None:
        elapsed = _benchmark_elapsed_s(pid)
    progress_path = root / "evidence/h1_benchmark_progress.json"
    progress_stale_s = int(bench.get("progress_stale_s") or 900)
    progress_stale = False
    progress_pct: Optional[int] = None
    if progress_path.is_file():
        try:
            prog = json.loads(progress_path.read_text(encoding="utf-8"))
            progress_pct = prog.get("progress_pct")
            updated = str(prog.get("updated_at_utc") or "")
            if updated:
                t0 = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - t0).total_seconds()
                progress_stale = age > progress_stale_s and running
        except (json.JSONDecodeError, OSError, ValueError):
            progress_stale = running
    elif running:
        progress_stale = bool(elapsed and elapsed > 120)

    over_eta = bool(running and elapsed is not None and elapsed > eta_max)
    over_eta_severe = bool(
        running and elapsed is not None and elapsed > int(eta_max * overrun)
    )
    hung = bool(running and elapsed is not None and elapsed > hung_s and progress_stale)

    return {
        "benchmark_running": running,
        "benchmark_pid": pid,
        "benchmark_elapsed_s": elapsed,
        "eta_max_s": eta_max,
        "benchmark_over_eta": over_eta,
        "benchmark_over_eta_severe": over_eta_severe,
        "benchmark_hung": hung,
        "progress_pct": progress_pct,
        "progress_stale": progress_stale,
    }


def prepare_h1_hardware(root: Path, *, phase: str = "execute", auto_unload: Optional[bool] = None) -> Dict[str, Any]:
    """Vor H1-Benchmark: VRAM-Policy anwenden (optional Ollama entladen)."""
    root = Path(root)
    policy = load_hardware_policy(root)
    if auto_unload is None:
        auto_unload = bool((policy.get("gpu") or {}).get("auto_unload_ollama_before_h1", True))
    env_unload = os.environ.get("AA_H1_UNLOAD_OLLAMA", "").strip().lower()
    if env_unload in ("0", "false", "no"):
        auto_unload = False
    elif env_unload in ("1", "true", "yes"):
        auto_unload = True
    ollama_models = ollama_ps_models()
    gpu_resolve = resolve_gpu_returns_for_h1(root, ollama_models=ollama_models)
    actions: List[Dict[str, Any]] = []
    chat_model = str((policy.get("ollama") or {}).get("chat_model") or "qwen2.5-coder:32b")
    if phase in ("observe", "execute") and ollama_models:
        for m in ollama_models:
            name = str(m.get("name") or "")
            if "32b" in name.lower() or auto_unload:
                if auto_unload or os.environ.get("AA_H1_UNLOAD_OLLAMA", "").strip() in ("1", "true", "yes"):
                    actions.append(ollama_unload_model(name))
                else:
                    actions.append(
                        {
                            "ok": False,
                            "skipped": True,
                            "model": name,
                            "action_de": "Ollama entladen empfohlen — AA_H1_UNLOAD_OLLAMA=1",
                        }
                    )
    out = {
        "ok": True,
        "prepared_at_utc": _utc_now(),
        "phase": phase,
        "gpu_returns": gpu_resolve,
        "vram_policy_de": vram_policy_for_phase(phase, gpu_resolve=gpu_resolve, ollama_models=ollama_models),
        "ollama_loaded": [str(m.get("name") or "") for m in ollama_models],
        "actions": actions,
        "env_hint_de": "AA_H1_GPU_RETURNS=1 · AA_H1_UNLOAD_OLLAMA=1 für maximale GPU-Nutzung",
    }
    if gpu_resolve.get("enabled"):
        os.environ["AA_H1_GPU_RETURNS"] = "1"
    return out


def heal_benchmark_progress(root: Path) -> Optional[Dict[str, Any]]:
    """Legacy-Jobs ohne brauchbare progress.json — Observability reparieren."""
    root = Path(root)
    timing = benchmark_timing(root)
    if not timing.get("benchmark_running"):
        return None
    progress_path = root / "evidence/h1_benchmark_progress.json"
    existing: Dict[str, Any] = {}
    if progress_path.is_file():
        try:
            existing = json.loads(progress_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        if existing.get("progress_pct") is not None and existing.get("phase") in ("prep", "returns", "starting"):
            return None

    elapsed = timing.get("benchmark_elapsed_s")
    doc = {
        "status": "running",
        "variant": "mom_1_top12",
        "phase": "legacy_unknown",
        "progress_pct": existing.get("progress_pct"),
        "benchmark_elapsed_s": elapsed,
        "note_de": (
            "Legacy-Job — Prep-Progress fehlte; "
            "vermutlich in Prep oder Returns ohne Meldung. Neustart mit king_ops h1-seal empfohlen."
        ),
        "lesson_de": "Background ohne progress + Prep ohne phase=prep (behoben ab 2026-06-07)",
        "updated_at_utc": _utc_now(),
    }
    if elapsed and elapsed > int((load_hardware_policy(root).get("benchmark") or {}).get("eta_max_s_default") or 4200):
        doc["over_eta"] = True
        doc["action_de"] = "Operator/König: status prüfen — nicht blind killen"
    atomic_write_json(progress_path, doc)
    try:
        from analytics.h1_benchmark_lessons import record_benchmark_lessons

        record_benchmark_lessons(root, trigger_de="heal_benchmark_progress")
    except Exception:
        pass
    return doc


def build_hardware_snapshot(root: Path, *, phase: str = "sync") -> Dict[str, Any]:
    root = Path(root)
    policy = load_hardware_policy(root)
    host: Dict[str, Any] = {}
    try:
        from analytics.h1_king_runtime import detect_host_resources

        host = detect_host_resources()
    except Exception as exc:
        host = {"error_de": str(exc)[:120]}
    ollama_models = ollama_ps_models()
    gpu_resolve = resolve_gpu_returns_for_h1(root, host=host, ollama_models=ollama_models)
    timing = benchmark_timing(root)
    nvme: Dict[str, Any] = {}
    try:
        from execution.linux_nvme_storage import storage_status

        nvme = storage_status(root)
    except Exception as exc:
        nvme = {"error_de": str(exc)[:120]}
    mem_gb: Optional[float] = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            lines = {ln.split(":")[0]: ln.split(":")[1].strip() for ln in fh if ":" in ln}
        avail = lines.get("MemAvailable") or lines.get("MemFree") or ""
        mem_gb = round(int(str(avail).split()[0]) / (1024 * 1024), 1)
    except (OSError, ValueError, IndexError):
        pass

    ram_warn = float((policy.get("ram") or {}).get("min_free_gb_warn") or 8.0)
    recommendations: List[str] = []
    if not nvme.get("mount"):
        recommendations.append("NVMe mount — bash tools/setup_nvme_storage.sh")
    if timing.get("benchmark_over_eta"):
        recommendations.append(
            f"Benchmark >ETA ({timing.get('benchmark_elapsed_s')}s) — Status prüfen, nicht blind killen"
        )
    if mem_gb is not None and mem_gb < ram_warn:
        recommendations.append(f"RAM knapp ({mem_gb} GB frei)")
    if phase in ("observe", "execute") and ollama_models:
        recommendations.append("Ollama aus VRAM entladen vor/during H1 — AA_H1_UNLOAD_OLLAMA=1")
    if phase in ("observe", "execute") and not gpu_resolve.get("enabled"):
        recommendations.append(f"GPU-Returns aus: {gpu_resolve.get('reason_de')}")

    out: Dict[str, Any] = {
        "ok": True,
        "schema_version": 1,
        "snapshot_at_utc": _utc_now(),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "phase": phase,
        "host": host,
        "gpu_returns": gpu_resolve,
        "ollama_loaded": [str(m.get("name") or "") for m in ollama_models],
        "nvme_mounted": bool(nvme.get("mount")),
        "nvme": nvme,
        "memory_available_gb": mem_gb,
        "benchmark": timing,
        "vram_policy_de": vram_policy_for_phase(phase, gpu_resolve=gpu_resolve, ollama_models=ollama_models),
        "recommendations_de": recommendations,
        "headline_de": (
            f"GPU={'ON' if gpu_resolve.get('enabled') else 'OFF'} · "
            f"VRAM-Policy: {vram_policy_for_phase(phase, gpu_resolve=gpu_resolve, ollama_models=ollama_models)[:80]}"
        ),
    }
    atomic_write_json(root / _HARDWARE_EVIDENCE, out)
    return out


def sync_hardware_with_phase(root: Path, *, phase: str) -> Dict[str, Any]:
    heal_benchmark_progress(root)
    return build_hardware_snapshot(root, phase=phase)


def enrich_king_status_doc(doc: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """Hard/Soft-Felder in king_status_latest.json — nach Bash-Basis."""
    root = Path(root)
    heal_benchmark_progress(root)
    timing = benchmark_timing(root)
    gpu = resolve_gpu_returns_for_h1(root)
    out = dict(doc)
    out["schema_version"] = 3
    out["hardware_policy_ref"] = str(_POLICY_REL).replace("\\", "/")
    out["benchmark_over_eta"] = bool(timing.get("benchmark_over_eta"))
    if timing.get("benchmark_hung"):
        out["benchmark_hung"] = True
    if timing.get("benchmark_elapsed_s") is not None:
        out["benchmark_elapsed_s"] = timing["benchmark_elapsed_s"]
    if timing.get("benchmark_pid") is not None:
        out["benchmark_pid"] = timing["benchmark_pid"]
    out["benchmark_running"] = bool(timing.get("benchmark_running"))
    out["progress_pct"] = timing.get("progress_pct")
    out["gpu_returns_enabled"] = bool(gpu.get("enabled"))
    out["gpu_reason_de"] = gpu.get("reason_de")
    try:
        from execution.linux_nvme_storage import storage_status

        out["nvme_mounted"] = bool(storage_status(root).get("mount"))
    except Exception:
        out["nvme_mounted"] = False

    seal_optional = False
    try:
        from analytics.h1_seal_policy import is_h1_seal_required

        seal_optional = not is_h1_seal_required(root)
        out["h1_seal_required"] = not seal_optional
    except Exception:
        pass
    if out.get("h1_sealed") or (seal_optional and str(out.get("h1_status") or "") == "COMPLETE"):
        out["next_action_de"] = (
            "/ready — H1 sealed"
            if out.get("h1_sealed")
            else "/ready — H1 COMPLETE; Seal optional · /predict"
        )
        out["next_layer"] = "koenig"
    elif out.get("benchmark_hung") or out.get("benchmark_over_eta"):
        out["next_action_de"] = "bash tools/king_ops.sh status — Benchmark prüfen (ETA/hung)"
        out["next_layer"] = "koenig"
    elif not out.get("benchmark_csv_ok") and out.get("benchmark_running"):
        out["next_action_de"] = "bash tools/king_ops.sh watch-bg"
        out["next_layer"] = "bash"
    return out
