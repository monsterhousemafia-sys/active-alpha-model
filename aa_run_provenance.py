"""Run provenance: run_id, isolated run directories, validated-run pointer."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from aa_config import BacktestConfig
from aa_integrity import IntegrityResult, write_integrity_reports
from aa_variant_id import resolve_canonical_variant_id
from aa_model_status import write_model_status

BEHAVIOR_FILE_NAMES = (
    "aa_backtest.py",
    "aa_backtest_ml.py",
    "aa_portfolio.py",
    "aa_models.py",
    "aa_features.py",
    "aa_reporting.py",
    "aa_risk_off.py",
    "aa_risk_off_reporting.py",
    "aa_config.py",
    "aa_runtime.py",
    "aa_integrity.py",
    "aa_run_provenance.py",
    "active_alpha_model.py",
    "run_active_alpha_model.bat",
    "run_active_alpha_launcher.bat",
    "load_active_alpha_config.bat",
    "active_alpha_settings.bat",
)

PUBLISH_ARTIFACTS = (
    "strategy_daily_returns.csv",
    "backtest_decisions.csv",
    "backtest_weights.csv",
    "constraint_binding_history.csv",
    "benchmark_daily_returns.csv",
    "backtest_report.txt",
    "integrity_report.json",
    "integrity_report.txt",
    "integrity_status.json",
    "run_manifest.json",
    "run_config_snapshot.txt",
    "latest_target_portfolio.csv",
)


def _hash_file(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def code_fingerprint(root: Optional[Path] = None) -> str:
    root = root or Path(__file__).resolve().parent
    parts: List[str] = []
    for name in BEHAVIOR_FILE_NAMES:
        p = root / name
        if p.is_file():
            parts.append(f"{name}:{_hash_file(p)}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:24]


def config_fingerprint(cfg: BacktestConfig) -> str:
    from aa_features import _prediction_config_fingerprint

    return _prediction_config_fingerprint(cfg)


def make_run_id(cfg: BacktestConfig, root: Optional[Path] = None) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
    variant = resolve_canonical_variant_id(cfg)
    cfg_fp = config_fingerprint(cfg)[:8]
    code_fp = code_fingerprint(root)[:8]
    slip = int(float(getattr(cfg, "slippage_bps", 0) or 0))
    impact = int(float(getattr(cfg, "market_impact_bps", 0) or 0))
    out_tag = hashlib.sha256(str(getattr(cfg, "out_dir", "") or "").encode("utf-8")).hexdigest()[:6]
    return f"{ts}_{variant}_{cfg_fp}_{code_fp}_s{slip}i{impact}_{out_tag}"


def run_directory(root: Path, run_id: str) -> Path:
    return Path(root) / "runs" / run_id


def write_run_manifest(
    run_dir: Path,
    *,
    run_id: str,
    cfg: BacktestConfig,
    output_files: Iterable[Path],
    integrity: Optional[IntegrityResult] = None,
    root: Optional[Path] = None,
) -> Path:
    root = root or Path(__file__).resolve().parent
    variant_id = resolve_canonical_variant_id(cfg)
    manifest: Dict[str, Any] = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "variant_id": variant_id,
        "status": integrity.status if integrity else "PENDING",
        "config_fingerprint": config_fingerprint(cfg),
        "code_fingerprint": code_fingerprint(root),
        "output_files": [str(p) for p in output_files],
        "file_hashes_sha256": {name: _hash_file(root / name) for name in BEHAVIOR_FILE_NAMES if (root / name).is_file()},
    }
    if integrity is not None:
        manifest["integrity_status"] = integrity.status
        manifest["integrity_errors"] = integrity.errors
    path = Path(run_dir) / "run_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def publish_validated_run(
    out_dir: Path,
    run_dir: Path,
    run_id: str,
    *,
    integrity: IntegrityResult,
    variant_id: str = "",
) -> bool:
    """Update latest_validated_run.json and sync key artifacts to out_dir. Returns True on PASS."""
    out_dir = Path(out_dir)
    run_dir = Path(run_dir)
    write_integrity_reports(run_dir, integrity)

    resolved_variant = (
        str(variant_id or "").strip()
        or resolve_canonical_variant_id_from_manifest(run_dir)
        or ""
    )

    pointer = {
        "run_id": run_id,
        "run_dir": str(run_dir.resolve()),
        "variant_id": resolved_variant,
        "integrity_status": integrity.status,
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    pointer_path = out_dir / "latest_validated_run.json"

    if not integrity.passed:
        pointer["status"] = "INVALID"
        # Do not overwrite a valid pointer with an invalid run.
        if pointer_path.is_file():
            try:
                prev = json.loads(pointer_path.read_text(encoding="utf-8"))
                if str(prev.get("integrity_status", "")) == "PASS":
                    invalid_note = out_dir / "last_invalid_run.json"
                    invalid_note.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
                    return False
            except Exception:
                pass
        pointer_path.write_text(json.dumps(pointer, indent=2, sort_keys=True), encoding="utf-8")
        write_model_status(out_dir, variant_id=resolved_variant)
        return False

    pointer["status"] = "PASS"
    pointer_path.write_text(json.dumps(pointer, indent=2, sort_keys=True), encoding="utf-8")

    for name in PUBLISH_ARTIFACTS:
        src = run_dir / name
        if src.is_file():
            dst = out_dir / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    write_model_status(out_dir, variant_id=resolved_variant)
    try:
        from aa_prediction_outcomes import sync_outcome_ledger_from_out_dir

        sync_outcome_ledger_from_out_dir(
            out_dir,
            run_id=run_id,
            variant_id=resolved_variant,
        )
    except Exception:
        pass
    try:
        from aa_control_plane import sync_control_plane, write_next_cursor_prompt

        root = out_dir.resolve().parent
        sync_control_plane(root, out_dir, run_id=run_id)
        write_next_cursor_prompt(root)
    except Exception:
        pass
    return True


def resolve_canonical_variant_id_from_manifest(run_dir: Path) -> Optional[str]:
    manifest = run_dir / "run_manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return str(data.get("variant_id", "") or "")
    except Exception:
        return None


def published_backtest_artifacts_ok(out_dir: Path) -> tuple[bool, str]:
    """True when canonical outputs exist under out_dir (orphan validated-run pointer)."""
    out_dir = Path(out_dir)
    required = ("strategy_daily_returns.csv", "backtest_report.txt", "latest_target_portfolio.csv")
    missing = [n for n in required if not (out_dir / n).is_file()]
    if missing:
        return False, "fehlende Dateien: " + ", ".join(missing)
    try:
        import pandas as pd

        returns = pd.read_csv(out_dir / "strategy_daily_returns.csv", index_col=0, nrows=5000)
        if returns.empty:
            return False, "strategy_daily_returns.csv ist leer"
        pf = pd.read_csv(out_dir / "latest_target_portfolio.csv")
        if pf.empty or "target_weight" not in pf.columns:
            return False, "latest_target_portfolio.csv ungültig"
    except Exception as exc:
        return False, f"Artefakte unlesbar: {exc}"
    status_path = out_dir / "integrity_status.json"
    if status_path.is_file():
        try:
            doc = json.loads(status_path.read_text(encoding="utf-8"))
            if str(doc.get("status", "")).upper() not in {"PASS", "OK"}:
                return False, "integrity_status.json nicht PASS"
        except Exception:
            pass
    if (out_dir / "backtest_report.txt").stat().st_size < 80:
        return False, "backtest_report.txt zu klein"
    return True, "ok (published in out_dir)"


def load_validated_run_dir(out_dir: Path) -> Optional[Path]:
    pointer = Path(out_dir) / "latest_validated_run.json"
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
        if str(data.get("integrity_status", data.get("status", ""))) != "PASS":
            return None
        run_dir = Path(str(data.get("run_dir", "")))
        if run_dir.is_dir():
            return run_dir
        out_dir = Path(out_dir)
        if published_backtest_artifacts_ok(out_dir)[0]:
            return out_dir
    except Exception:
        pass
    return None
