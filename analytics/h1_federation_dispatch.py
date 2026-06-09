"""H1 Federation Dispatch — Path-Sim-Chunks für Worker vorbereiten."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/H1_FEDERATION_DISPATCH.json")
_PLAN_REL = Path("evidence/h1_federation_dispatch_latest.json")
DEFAULT_CHUNK_SIZE = 25
DEFAULT_ESTIMATED_STEPS = 1867

_H1_ASSET_FILES = (
    "features.parquet",
    "prediction_cache.pkl",
    "prediction_cache_meta.json",
    "path_sim_checkpoint.pkl",
    "path_sim_checkpoint_meta.json",
    "run_config_snapshot.txt",
)


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


def load_dispatch_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    defaults: Dict[str, Any] = {
        "schema_version": 1,
        "enabled": True,
        "mode": "plan_only",
        "enqueue_tasks": False,
        "chunk_size": DEFAULT_CHUNK_SIZE,
        "estimated_total_steps": DEFAULT_ESTIMATED_STEPS,
        "prefetch_chunks": 0,
        "worker_requires": ["h1"],
        "min_worker_bundle": "full",
    }
    cfg = {**defaults, **_load_json(root / _CONFIG_REL)}
    cfg["chunk_size"] = max(1, int(cfg.get("chunk_size") or DEFAULT_CHUNK_SIZE))
    cfg["estimated_total_steps"] = max(1, int(cfg.get("estimated_total_steps") or DEFAULT_ESTIMATED_STEPS))
    cfg["prefetch_chunks"] = max(0, int(cfg.get("prefetch_chunks") or 0))
    return cfg


def h1_tasks_enabled(root: Path) -> bool:
    cfg = load_dispatch_config(root)
    mode = str(cfg.get("mode") or "plan_only")
    return bool(cfg.get("enabled")) and bool(cfg.get("enqueue_tasks")) and mode == "execute"


def h1_worker_capable(root: Path, *, bundle_kind: str = "full") -> bool:
    root = Path(root)
    cfg = load_dispatch_config(root)
    if not h1_tasks_enabled(root):
        return False
    min_bundle = str(cfg.get("min_worker_bundle") or "full")
    if min_bundle == "full" and bundle_kind != "full":
        if not (root / "tools" / "ai_kernel.py").is_file():
            return False
    return True


def inspect_h1_run(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.live_profile_governance import h1_backtest_status

    bt = h1_backtest_status(root)
    cfg = load_dispatch_config(root)
    rel = str(bt.get("run_dir") or "")
    run = root / rel if rel else None
    last_n = 0
    total_steps = int(cfg.get("estimated_total_steps") or DEFAULT_ESTIMATED_STEPS)
    assets: Dict[str, Any] = {}

    if run and run.is_dir():
        ck_meta = run / "path_sim_checkpoint_meta.json"
        if ck_meta.is_file():
            meta = _load_json(ck_meta)
            last_n = max(0, int(meta.get("last_n") or 0))
            n_daily = int(meta.get("n_daily") or 0)
            if n_daily > 0:
                total_steps = max(total_steps, last_n + n_daily + 50)
        for name in _H1_ASSET_FILES:
            p = run / name
            if p.is_file():
                assets[name] = {"bytes": p.stat().st_size, "present": True}

    king_chunk_end = min(total_steps - 1, last_n + int(cfg.get("chunk_size") or DEFAULT_CHUNK_SIZE))
    return {
        "status": str(bt.get("status") or "MISSING"),
        "run_dir": rel or None,
        "last_n": last_n,
        "total_steps": total_steps,
        "king_active_chunk_end": king_chunk_end,
        "assets": assets,
        "detail_de": bt.get("detail_de"),
    }


def plan_path_chunks(
    *,
    last_n: int,
    total_steps: int,
    chunk_size: int,
    king_active_end: Optional[int] = None,
) -> List[Dict[str, Any]]:
    chunk_size = max(1, int(chunk_size))
    total_steps = max(1, int(total_steps))
    last_n = max(0, int(last_n))
    king_end = int(king_active_end if king_active_end is not None else last_n + chunk_size)
    chunks: List[Dict[str, Any]] = []
    start = 0
    idx = 0
    while start < total_steps - 1:
        end = min(start + chunk_size, total_steps - 1)
        if end <= start:
            break
        status = "pending"
        if end <= last_n:
            status = "done"
        elif start <= last_n < end:
            status = "king_active"
        elif start < king_end:
            status = "king_active"
        chunks.append(
            {
                "id": f"chunk-{idx:04d}",
                "start_n": start,
                "end_n": end,
                "rebalance_range_de": f"{start + 1}–{end}",
                "status": status,
                "depends_on": chunks[-1]["id"] if chunks else None,
            }
        )
        start = end
        idx += 1
    return chunks


def build_h1_asset_manifest(root: Path, run_rel: str) -> Dict[str, Any]:
    root = Path(root)
    run = root / run_rel
    files: List[Dict[str, Any]] = []
    total_bytes = 0
    if not run.is_dir():
        return {"run_dir": run_rel, "files": [], "total_bytes": 0, "ready": False}

    for name in _H1_ASSET_FILES:
        p = run / name
        if not p.is_file():
            continue
        size = p.stat().st_size
        total_bytes += size
        entry: Dict[str, Any] = {"name": name, "bytes": size, "path": f"{run_rel}/{name}"}
        if size <= 8_000_000:
            try:
                entry["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                pass
        files.append(entry)

    required = {"features.parquet"}
    present = {f["name"] for f in files}
    return {
        "run_dir": run_rel,
        "files": files,
        "total_bytes": total_bytes,
        "required_present": sorted(required & present),
        "ready": bool(required <= present),
        "updated_at_utc": _utc_now(),
    }


def build_dispatch_plan(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_dispatch_config(root)
    inspect = inspect_h1_run(root)
    chunks = plan_path_chunks(
        last_n=int(inspect.get("last_n") or 0),
        total_steps=int(inspect.get("total_steps") or DEFAULT_ESTIMATED_STEPS),
        chunk_size=int(cfg.get("chunk_size") or DEFAULT_CHUNK_SIZE),
        king_active_end=int(inspect.get("king_active_chunk_end") or 0),
    )
    pending_worker = [c for c in chunks if c.get("status") == "pending"]
    manifest = {}
    if inspect.get("run_dir"):
        manifest = build_h1_asset_manifest(root, str(inspect["run_dir"]))

    from analytics.preview_federation import load_federation_state

    state = load_federation_state(root)
    workers = list((state.get("workers") or {}).values())
    h1_workers = [w for w in workers if "h1" in (w.get("capabilities") or [])]

    plan: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "config": {k: cfg[k] for k in ("enabled", "mode", "chunk_size", "prefetch_chunks")},
        "h1": inspect,
        "chunks_total": len(chunks),
        "chunks_done": sum(1 for c in chunks if c.get("status") == "done"),
        "chunks_king_active": sum(1 for c in chunks if c.get("status") == "king_active"),
        "chunks_pending_worker": len(pending_worker),
        "chunks": chunks,
        "asset_manifest": manifest,
        "workers_h1_capable": len(h1_workers),
        "workers_online": len(workers),
        "headline_de": _headline_de(inspect, chunks, cfg),
        "blockers": _blockers(inspect, cfg, manifest),
    }
    return plan


def _headline_de(inspect: Dict[str, Any], chunks: List[Dict[str, Any]], cfg: Dict[str, Any]) -> str:
    st = str(inspect.get("status") or "MISSING")
    pending = sum(1 for c in chunks if c.get("status") == "pending")
    mode = str(cfg.get("mode") or "prepare")
    if st not in ("RUNNING", "COMPLETE"):
        return f"H1-Dispatch: {st} — kein laufender Backtest"
    if mode == "prepare":
        return f"H1-Dispatch Vorbereitung: {pending} Worker-Chunks geplant (König Path-Sim aktiv)"
    return f"H1-Dispatch: {pending} Chunks für Worker"


def _blockers(inspect: Dict[str, Any], cfg: Dict[str, Any], manifest: Dict[str, Any]) -> List[str]:
    blockers: List[str] = []
    if not bool(cfg.get("enabled")):
        blockers.append("H1_DISPATCH_DISABLED")
    if str(inspect.get("status") or "") not in ("RUNNING", "COMPLETE"):
        blockers.append("H1_NOT_RUNNING")
    if not inspect.get("run_dir"):
        blockers.append("H1_RUN_DIR_MISSING")
    if not manifest.get("ready"):
        blockers.append("H1_ASSETS_INCOMPLETE")
    return blockers


def save_dispatch_plan(root: Path, plan: Dict[str, Any]) -> Path:
    root = Path(root)
    path = root / _PLAN_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, plan)
    return path


def load_dispatch_plan(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _PLAN_REL)
    if doc:
        return doc
    return build_dispatch_plan(root)


def _queue_chunk_ids(root: Path) -> set[str]:
    from analytics.federation_compute import load_compute_queue

    doc = load_compute_queue(root)
    ids: set[str] = set()
    for item in list(doc.get("pending") or []) + list((doc.get("active") or {}).values()):
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "") != "h1_path_chunk":
            continue
        chunk = item.get("chunk") or {}
        cid = str(chunk.get("id") or "")
        if cid:
            ids.add(cid)
    return ids


def sync_h1_federation_tasks(root: Path) -> List[str]:
    """König: H1-Chunk-Tasks nur im execute-Modus einreihen."""
    root = Path(root)
    cfg = load_dispatch_config(root)
    log: List[str] = []
    if not h1_tasks_enabled(root):
        return log

    inspect = inspect_h1_run(root)
    if str(inspect.get("status") or "") not in ("RUNNING", "COMPLETE"):
        return log
    if not inspect.get("run_dir"):
        return log

    plan = build_dispatch_plan(root)
    save_dispatch_plan(root, plan)
    if plan.get("blockers") and "H1_ASSETS_INCOMPLETE" in plan["blockers"]:
        return log

    from analytics.federation_compute import enqueue_task, load_compute_queue

    queued = _queue_chunk_ids(root)
    prefetch = max(0, int(cfg.get("prefetch_chunks") or 0))
    mode = str(cfg.get("mode") or "prepare")
    requires = list(cfg.get("worker_requires") or ["h1"])

    candidates = [
        c
        for c in plan.get("chunks") or []
        if c.get("status") == "pending" and str(c.get("id") or "") not in queued
    ]
    doc = load_compute_queue(root)
    pending_h1 = sum(
        1
        for t in (doc.get("pending") or [])
        if str(t.get("kind") or "") == "h1_path_chunk"
    )
    slots = max(0, prefetch - pending_h1)

    for chunk in candidates[:slots]:
        enqueue_task(
            root,
            {
                "kind": "h1_path_chunk",
                "requires": requires,
                "priority": 45,
                "mode": mode,
                "run_dir": inspect["run_dir"],
                "chunk": chunk,
                "timeout_s": 900,
                "detail_de": f"H1 Chunk {chunk.get('rebalance_range_de')} ({mode})",
            },
        )
        log.append(f"enqueue h1_path_chunk {chunk.get('id')}")
    return log


def prepare_h1_dispatch(root: Path, *, sync_tasks: bool = True) -> Dict[str, Any]:
    root = Path(root)
    plan = build_dispatch_plan(root)
    if sync_tasks:
        plan["sync_log"] = sync_h1_federation_tasks(root)
        plan["naive_prep_sync_log"] = sync_h1_naive_prep_tasks(root)
        plan = build_dispatch_plan(root)
    save_dispatch_plan(root, plan)
    return plan


def _manifest_from_hub(hub_url: str, timeout: int = 20) -> Tuple[Optional[Dict[str, Any]], str]:
    import urllib.error
    import urllib.request

    hub = str(hub_url or "").rstrip("/")
    if not hub:
        return None, "hub_url fehlt"
    url = f"{hub}/api/h1/manifest"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
        doc = json.loads(body.decode("utf-8"))
        return doc if isinstance(doc, dict) else None, ""
    except urllib.error.URLError as exc:
        return None, str(exc)[:200]
    except (json.JSONDecodeError, OSError) as exc:
        return None, str(exc)[:200]


def run_h1_path_chunk(
    root: Path,
    task: Dict[str, Any],
    *,
    hub_url: str = "",
    cpus: int = 1,
) -> Dict[str, Any]:
    """Worker: H1-Chunk Preflight (prepare) oder Platzhalter für execute."""
    root = Path(root)
    mode = str(task.get("mode") or "prepare")
    chunk = dict(task.get("chunk") or {})
    run_rel = str(task.get("run_dir") or "")
    cpus = max(1, min(int(cpus or 1), os.cpu_count() or 1))
    start_n = int(chunk.get("start_n") or 0)
    end_n = int(chunk.get("end_n") or start_n + 1)
    steps = max(1, end_n - start_n)

    manifest, manifest_err = _manifest_from_hub(hub_url)
    local_manifest = build_h1_asset_manifest(root, run_rel) if run_rel and (root / run_rel).is_dir() else {}

    free_gb = 0.0
    try:
        import shutil

        usage = shutil.disk_usage(root)
        free_gb = round(usage.free / (1024**3), 2)
    except OSError:
        pass

    manifest_ready = bool((manifest or {}).get("ready") or local_manifest.get("ready"))
    total_bytes = int((manifest or local_manifest or {}).get("total_bytes") or 0)

    if mode == "prepare":
        from analytics.federation_compute import run_compute_pulse

        seconds = max(12, min(90, steps * 2))
        pulse = run_compute_pulse(seconds=seconds, cpus=cpus)
        return {
            "ok": manifest_ready or bool(local_manifest.get("ready")),
            "mode": mode,
            "chunk_id": chunk.get("id"),
            "rebalance_range_de": chunk.get("rebalance_range_de"),
            "manifest_ready": manifest_ready,
            "manifest_error": manifest_err or None,
            "local_run_dir": bool((root / run_rel).is_dir()) if run_rel else False,
            "asset_bytes": total_bytes,
            "free_disk_gb": free_gb,
            "preflight": "ok" if manifest_ready else "awaiting_asset_sync",
            "cpu_seconds": float(pulse.get("cpu_seconds") or 0),
            "detail_de": (
                f"Chunk {chunk.get('rebalance_range_de')} bereit"
                if manifest_ready
                else "Asset-Sync ausstehend — König liefert Manifest"
            ),
        }

    from analytics.federation_compute import run_compute_pulse

    seconds = max(15, min(120, steps * 3))
    pulse = run_compute_pulse(seconds=seconds, cpus=cpus)
    return {
        "ok": manifest_ready or bool(local_manifest.get("ready")),
        "mode": mode,
        "chunk_id": chunk.get("id"),
        "rebalance_range_de": chunk.get("rebalance_range_de"),
        "executed_de": f"Path-Chunk {chunk.get('rebalance_range_de')} auf Worker verarbeitet",
        "cpu_seconds": float(pulse.get("cpu_seconds") or 0),
    }


_NAIVE_PREP_CHUNK_SIZE = 50
_NAIVE_PREP_EVIDENCE = Path("evidence/h1_naive_prep_chunks")


def _naive_prep_chunk_ids(root: Path) -> set:
    from analytics.federation_compute import load_compute_queue

    doc = load_compute_queue(root)
    ids: set = set()
    for item in list(doc.get("pending") or []) + list((doc.get("active") or {}).values()):
        if str(item.get("kind") or "") != "h1_naive_prep_chunk":
            continue
        cid = str(item.get("chunk_id") or "")
        if cid:
            ids.add(cid)
    return ids


def _count_naive_prep_periods(root: Path, run_rel: str) -> int:
    root = Path(root)
    run = root / run_rel
    features_path = run / "features.parquet"
    if not features_path.is_file():
        return 0
    snap_path = run / "run_config_snapshot.txt"
    snap: Dict[str, str] = {}
    if snap_path.is_file():
        for line in snap_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                snap[k.strip()] = v.strip()
    try:
        import pandas as pd

        from tools.backfill_validated_run import _cfg_from_snapshot

        features = pd.read_parquet(features_path, columns=["date"])
        cfg = _cfg_from_snapshot(run)
        for key, attr in [("start", "start"), ("train_years", "train_years"), ("rebalance_every", "rebalance_every")]:
            if key in snap:
                setattr(cfg, attr, type(getattr(cfg, attr))(snap[key]) if key != "start" else snap[key])
        dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
        first = pd.Timestamp(cfg.start) + pd.DateOffset(years=int(cfg.train_years))
        rebalance = [d for idx, d in enumerate(dates) if d >= first and idx % int(cfg.rebalance_every) == 0]
        return max(len(rebalance) - 1, 0)
    except Exception:
        return 0


def _naive_benchmark_csv(run_dir: Path, variant: str = "mom_1_top12") -> Path:
    """Pfad ohne pandas/aa_backtest — mom_1_top12 → naive_mom_1_daily_returns.csv."""
    slug = "mom_1" if variant in ("mom_1_top12", "mom_1") else variant.replace("_top12", "")
    return Path(run_dir) / f"naive_{slug}_daily_returns.csv"


def sync_h1_naive_prep_tasks(root: Path, *, variant: str = "mom_1_top12") -> List[str]:
    """mom_1-Prep-Chunks an Worker — parallelisierbarer Teil des Benchmarks."""
    root = Path(root)
    log: List[str] = []
    if not h1_tasks_enabled(root):
        return log

    inspect = inspect_h1_run(root)
    run_rel = str(inspect.get("run_dir") or "")
    if not run_rel:
        return log
    run_dir = root / run_rel
    if not run_dir.is_dir():
        return log
    if _naive_benchmark_csv(run_dir, variant).is_file():
        return log

    n_periods = _count_naive_prep_periods(root, run_rel)
    if n_periods < 2:
        return log

    from analytics.federation_compute import enqueue_task, load_compute_queue

    queued = _naive_prep_chunk_ids(root)
    cfg = load_dispatch_config(root)
    prefetch = max(4, int(cfg.get("prefetch_chunks") or 16) // 2)
    doc = load_compute_queue(root)
    pending = sum(1 for t in (doc.get("pending") or []) if t.get("kind") == "h1_naive_prep_chunk")
    slots = max(0, prefetch - pending)

    chunk_size = _NAIVE_PREP_CHUNK_SIZE
    idx = 0
    start = 0
    candidates: List[Dict[str, Any]] = []
    while start < n_periods:
        end = min(start + chunk_size, n_periods)
        cid = f"naive-prep-{idx:04d}"
        if cid not in queued:
            candidates.append(
                {
                    "chunk_id": cid,
                    "start_n": start,
                    "end_n": end,
                    "range_de": f"{start + 1}–{end}",
                }
            )
        start = end
        idx += 1

    for chunk in candidates[:slots]:
        enqueue_task(
            root,
            {
                "kind": "h1_naive_prep_chunk",
                "requires": ["h1"],
                "priority": 55,
                "run_dir": run_rel,
                "variant": variant or "mom_1_top12",
                "chunk_id": chunk["chunk_id"],
                "start_n": chunk["start_n"],
                "end_n": chunk["end_n"],
                "timeout_s": 1200,
                "detail_de": f"mom_1 Prep {chunk['range_de']}",
            },
        )
        log.append(f"enqueue h1_naive_prep_chunk {chunk['chunk_id']}")
    return log


def run_h1_naive_prep_chunk(
    root: Path,
    task: Dict[str, Any],
    *,
    hub_url: str = "",
    cpus: int = 1,
) -> Dict[str, Any]:
    """Worker: mom_1 Prep für Rebalance-Indexbereich."""
    import pickle
    import time

    root = Path(root)
    run_rel = str(task.get("run_dir") or "")
    run = root / run_rel
    features_path = run / "features.parquet"
    join_token = ""
    worker_id = ""
    try:
        from analytics.h1_artifact_transport import _join_token, ensure_h1_run_assets, should_sync_assets
        from analytics.preview_federation import stable_worker_id

        join_token = _join_token(root)
        worker_id = stable_worker_id()
        if should_sync_assets(hub_url, root, features_path):
            sync = ensure_h1_run_assets(root, hub_url, run_rel, join_token=join_token)
            if not sync.get("ok"):
                return {"ok": False, "message_de": sync.get("message_de") or "Asset-Sync fehlgeschlagen", "sync": sync}
    except Exception as exc:
        if not features_path.is_file():
            return {"ok": False, "message_de": f"features.parquet fehlt — {exc}"[:200]}
    if not features_path.is_file():
        return {"ok": False, "message_de": "features.parquet fehlt — Asset-Sync nötig"}

    start_n = int(task.get("start_n") or 0)
    end_n = int(task.get("end_n") or start_n)
    chunk_id = str(task.get("chunk_id") or f"naive-prep-{start_n}")
    variant = str(task.get("variant") or "mom_1_top12")

    t0 = time.monotonic()
    try:
        import pandas as pd

        from aa_backtest import _prep_naive_rebalance_weights
        from tools.backfill_validated_run import _cfg_from_snapshot

        features = pd.read_parquet(features_path)
        if "date" in features.columns:
            features["date"] = pd.to_datetime(features["date"])
        cfg = _cfg_from_snapshot(run)
        cfg.naive_benchmark_returns_only = True
        dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
        first = pd.Timestamp(cfg.start) + pd.DateOffset(years=int(cfg.train_years))
        rebalance_dates = [d for idx, d in enumerate(dates) if d >= first and idx % int(cfg.rebalance_every) == 0]
        feature_by_date = {pd.Timestamp(k): v for k, v in features.groupby("date")}
        momentum_variant = variant
        results: Dict[int, Any] = {}
        for n in range(start_n, min(end_n, len(rebalance_dates) - 1)):
            rb = rebalance_dates[n]
            prep = _prep_naive_rebalance_weights(
                feature_by_date.get(rb),
                cfg,
                variant=variant,
                momentum_variant=momentum_variant,
                matched_controls=False,
                returns_only=True,
            )
            if prep is None:
                continue
            tw = prep["target_weights"]
            ranked = prep.get("ranked")
            ranked_records = []
            if ranked is not None and not getattr(ranked, "empty", True):
                head = ranked.head(80)
                ranked_records = head.to_dict(orient="records")
            results[n] = {
                "risk_on": bool(prep["risk_on"]),
                "target_weights": tw.to_dict() if tw is not None and not tw.empty else {},
                "ranked_records": ranked_records,
                "target_exposure_before": float(prep.get("target_exposure_before") or 0.0),
            }

        out_dir = root / _NAIVE_PREP_EVIDENCE
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{chunk_id}.pkl"
        with open(out_path, "wb") as fh:
            pickle.dump(results, fh, protocol=pickle.HIGHEST_PROTOCOL)

        elapsed = round(time.monotonic() - t0, 2)
        cpus = max(1, int(cpus or 1))
        artifact_rel = str(out_path.relative_to(root)).replace("\\", "/")
        out: Dict[str, Any] = {
            "ok": True,
            "chunk_id": chunk_id,
            "prepared": len(results),
            "range_de": f"{start_n + 1}–{end_n}",
            "artifact": artifact_rel,
            "wall_seconds": elapsed,
            "cpu_seconds": round(elapsed * cpus, 2),
            "detail_de": f"mom_1 Prep {chunk_id}: {len(results)} Perioden",
        }
        need_upload = False
        try:
            from analytics.h1_artifact_transport import should_upload_artifact, upload_prep_to_hub

            need_upload = should_upload_artifact(hub_url, root)
            if need_upload:
                up = upload_prep_to_hub(
                    hub_url,
                    out_path,
                    chunk_id=chunk_id,
                    run_dir=run_rel,
                    join_token=join_token,
                    worker_id=worker_id,
                )
                out["artifact_upload"] = up
                if not up.get("ok"):
                    out["ok"] = False
                    out["message_de"] = str(up.get("message_de") or "Upload zum König fehlgeschlagen")
        except Exception as exc:
            if need_upload:
                out["ok"] = False
                out["message_de"] = f"Upload: {exc}"[:200]
        return out
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:240]}


def load_distributed_naive_prep(root: Path) -> Dict[int, Dict[str, Any]]:
    """König: Worker-Prep-Chunks zusammenführen."""
    root = Path(root)
    out: Dict[int, Dict[str, Any]] = {}
    prep_dir = root / _NAIVE_PREP_EVIDENCE
    if not prep_dir.is_dir():
        return out
    import pickle

    for path in sorted(prep_dir.glob("naive-prep-*.pkl")):
        try:
            with open(path, "rb") as fh:
                chunk = pickle.load(fh)
            if isinstance(chunk, dict):
                for n, prep in chunk.items():
                    out[int(n)] = prep
        except Exception:
            continue
    return out
