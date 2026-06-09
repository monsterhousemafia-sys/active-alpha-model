"""Extended validation for persisted analysis (Fast-Path / GUI)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from aa_run_provenance import load_validated_run_dir, published_backtest_artifacts_ok, PUBLISH_ARTIFACTS


def validate_analytical_integrity(out_dir: Path) -> Tuple[bool, str, str]:
    """Return (ok, reason, run_id). Requires latest_validated_run.json with PASS integrity."""
    out_dir = Path(out_dir)
    pointer = out_dir / "latest_validated_run.json"
    if not pointer.is_file():
        return False, "keine validierte Analyse (latest_validated_run.json fehlt)", ""

    try:
        meta = json.loads(pointer.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"latest_validated_run.json unlesbar: {exc}", ""

    run_id = str(meta.get("run_id", "") or "")
    if str(meta.get("integrity_status", meta.get("status", ""))) != "PASS":
        return False, "gespeicherte Analyse ungültig – vollständiger Neulauf erforderlich", run_id

    run_dir = load_validated_run_dir(out_dir)
    out_dir_p = Path(out_dir)
    orphan_fallback = False
    if run_dir is None:
        pub_ok, pub_reason = published_backtest_artifacts_ok(out_dir_p)
        if not pub_ok:
            return False, "validierter Run-Ordner nicht gefunden", run_id
        run_dir = out_dir_p
        orphan_fallback = True
    elif run_dir.resolve() == out_dir_p.resolve():
        orphan_fallback = True

    integrity_path = run_dir / "integrity_report.json"
    if not integrity_path.is_file():
        if orphan_fallback and (out_dir_p / "integrity_status.json").is_file():
            return True, "ok (integrity_status in out_dir)", run_id
        return False, "integrity_report.json fehlt", run_id
    try:
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"integrity_report.json unlesbar: {exc}", run_id
    if str(integrity.get("status", "")) != "PASS":
        return False, "Integrity-Prüfung FAIL", run_id
    if (
        not orphan_fallback
        and run_id
        and str(integrity.get("run_id", run_id)) not in {"", run_id}
    ):
        return False, "Run-ID Inkonsistenz zwischen Pointer und Integrity-Report", run_id

    for name in ("strategy_daily_returns.csv", "backtest_report.txt", "latest_target_portfolio.csv"):
        if not (run_dir / name).is_file() and not (out_dir / name).is_file():
            return False, f"fehlende Datei: {name}", run_id

    try:
        import pandas as pd

        for label, candidate in (
            ("run_dir", run_dir / "strategy_daily_returns.csv"),
            ("model_output", out_dir / "strategy_daily_returns.csv"),
        ):
            if not candidate.is_file():
                continue
            returns = pd.read_csv(candidate, index_col=0, nrows=5000)
            if returns.empty:
                return False, f"strategy_daily_returns.csv ist leer ({label})", run_id
            if label == "model_output" and "CONTAMINATED" in candidate.name.upper():
                return False, "strategy_daily_returns verunreinigt — Phase B bereinigen", run_id
    except Exception as exc:
        return False, f"strategy_daily_returns.csv unlesbar: {exc}", run_id

    if orphan_fallback:
        return True, "ok (published in out_dir)", run_id
    return True, "ok", run_id


def assess_analytical_status(out_dir: Path) -> Tuple[str, str]:
    """Return (analytical_validity, run_id). PASS | INVALID | UNKNOWN."""
    ok, reason, run_id = validate_analytical_integrity(out_dir)
    if ok:
        return "PASS", run_id
    if "fehlt" in reason.lower() or "keine validierte" in reason.lower():
        return "UNKNOWN", run_id
    return "INVALID", run_id


INVALID_ANALYSIS_USER_MESSAGE = (
    "Gespeicherte Analyse ungültig – vollständiger Neulauf erforderlich. "
    "Performance-Kennzahlen (CAGR, Sharpe, Alpha) sind nicht freigegeben."
)
