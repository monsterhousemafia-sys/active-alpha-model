"""Restore validated-run pointers from last-known-good snapshots."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from aa_safe_io import atomic_write_json


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_last_known_good(control_dir: Path) -> Dict[str, Any]:
    path = Path(control_dir) / "last_known_good_state.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_last_known_good(control_dir: Path, payload: Dict[str, Any]) -> Path:
    return atomic_write_json(Path(control_dir) / "last_known_good_state.json", payload)


def build_last_known_good_snapshot(
    *,
    out_dir: Path,
    health: Dict[str, Any],
    run_id: str = "",
) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    pointer = {}
    pointer_path = out_dir / "latest_validated_run.json"
    if pointer_path.is_file():
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        except Exception:
            pointer = {}
    artifact_paths: Dict[str, str] = {}
    artifact_hashes: Dict[str, str] = {}
    artifacts: List[str] = []
    for name in (
        "latest_validated_run.json",
        "model_status.json",
        "integrity_status.json",
        "integrity_report.json",
        "strategy_daily_returns.csv",
        "backtest_report.txt",
        "latest_target_portfolio.csv",
    ):
        src = out_dir / name
        if src.is_file():
            artifacts.append(name)
            artifact_paths[name] = str(src.resolve())
            try:
                artifact_hashes[name] = file_sha256(src)
            except OSError:
                pass
    run_id_val = run_id or str(pointer.get("run_id", "") or "")
    variant_val = str(pointer.get("variant_id", "") or health.get("active_variant_label", ""))
    return {
        "saved_at_utc": health.get("checked_at_utc", ""),
        "validated_at_utc": health.get("checked_at_utc", ""),
        "run_id": run_id_val,
        "validated_run_id": run_id_val,
        "validated_model_id": str(pointer.get("variant_id", variant_val) or variant_val),
        "validated_signal_id": run_id_val,
        "validated_variant_id": variant_val,
        "variant_id": variant_val,
        "integrity_status": str(health.get("integrity_status", "") or "PASS"),
        "out_dir": str(out_dir.resolve()),
        "artifacts": artifacts,
        "artifact_paths": artifact_paths,
        "artifact_hashes": artifact_hashes,
        "pointer": pointer,
    }


def restore_last_known_good(root: Path, out_dir: Path) -> Tuple[bool, str]:
    """Copy recorded artifacts back into out_dir. Does not run backtests."""
    root = Path(root)
    out_dir = Path(out_dir)
    control_dir = root / "control"
    snapshot = load_last_known_good(control_dir)
    if not snapshot:
        return False, "last_known_good_state.json fehlt"
    recorded_out = Path(str(snapshot.get("out_dir", "") or out_dir))
    if not recorded_out.is_dir():
        return False, f"Aufzeichnungs-Output fehlt: {recorded_out}"

    restored: List[str] = []
    for name in snapshot.get("artifacts") or []:
        src = recorded_out / name
        dst = out_dir / name
        if not src.is_file():
            continue
        if src.resolve() == dst.resolve():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        restored.append(name)

    pointer = snapshot.get("pointer")
    if isinstance(pointer, dict) and pointer:
        atomic_write_json(out_dir / "latest_validated_run.json", pointer)

    if not restored:
        return False, "keine Artefakte wiederhergestellt"
    return True, f"wiederhergestellt: {', '.join(restored)}"
