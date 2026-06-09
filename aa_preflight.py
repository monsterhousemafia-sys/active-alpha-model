"""Launcher preflight — operational checks before expensive model runs."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from aa_data_freshness import DailyDataReport

LogFn = Callable[[str], None]


@dataclass
class PreflightReport:
    status: str = "OK"
    errors: int = 0
    warnings: int = 0
    blocking: bool = False
    checks: List[Dict[str, str]] = field(default_factory=list)
    log_lines: List[str] = field(default_factory=list)


def _disk_free_gb(path: Path) -> Optional[float]:
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024**3)
    except Exception:
        return None


def run_launcher_preflight(
    root: Path,
    env: Mapping[str, str],
    *,
    log: Optional[LogFn] = None,
    data_report: Optional["DailyDataReport"] = None,
) -> PreflightReport:
    from aa_data_freshness import assess_daily_data
    from aa_ops_refresh import resolve_out_dir

    lines: List[str] = []
    checks: List[Dict[str, str]] = []
    errors = 0
    warnings = 0

    def emit(level: str, item: str, detail: str) -> None:
        nonlocal errors, warnings
        checks.append({"level": level, "item": item, "detail": detail})
        tag = {"OK": "[OK]", "WARN": "[WARN]", "ERROR": "[ERROR]"}.get(level, "[INFO]")
        line = f"{tag} Preflight {item}: {detail}"
        lines.append(line)
        if log is not None:
            log(line)
        if level == "ERROR":
            errors += 1
        elif level == "WARN":
            warnings += 1

    lines.append("[INFO] Preflight-Check …")
    if log is not None:
        log(lines[-1])

    required = [
        "active_alpha_model.py",
        "paper_trading_engine.py",
        "check_active_alpha_core.py",
        "requirements_active_alpha.txt",
    ]
    for name in required:
        if (root / name).is_file():
            emit("OK", name, "vorhanden")
        else:
            emit("ERROR", name, "fehlt")

    membership = str(env.get("AA_MEMBERSHIP_FILE", "ticker_membership.csv") or "ticker_membership.csv")
    membership_path = Path(membership) if Path(membership).is_absolute() else root / membership
    if membership_path.is_file():
        emit("OK", "membership_file", str(membership_path))
    else:
        emit("ERROR", "membership_file", f"fehlt: {membership_path}")

    asset_master = str(env.get("AA_ASSET_MASTER_FILE", "asset_master.csv") or "asset_master.csv")
    asset_path = Path(asset_master) if Path(asset_master).is_absolute() else root / asset_master
    if asset_path.is_file():
        emit("OK", "asset_master_file", str(asset_path))
    else:
        emit("WARN", "asset_master_file", f"fehlt: {asset_path}")

    out_dir = resolve_out_dir(root, env)
    if out_dir.exists():
        emit("OK", "backtest_out_dir", str(out_dir))
    else:
        emit("WARN", "backtest_out_dir", f"wird angelegt: {out_dir}")

    free_gb = _disk_free_gb(root)
    if free_gb is not None and free_gb < 2.0:
        emit("ERROR", "disk_space", f"weniger als 2 GB frei ({free_gb:.1f} GB)")
    elif free_gb is not None and free_gb < 5.0:
        emit("WARN", "disk_space", f"nur {free_gb:.1f} GB frei")
    elif free_gb is not None:
        emit("OK", "disk_space", f"{free_gb:.1f} GB frei")

    data = data_report if data_report is not None else assess_daily_data(root, env)
    if data.price_current:
        emit("OK", "price_data", f"Stand {data.price_latest}")
    else:
        emit("WARN", "price_data", "nicht tagesaktuell")

    if data.signal_date is None:
        emit("WARN", "signal_data", "kein Modell-Signal")
    elif data.signal_current:
        emit("OK", "signal_data", str(data.signal_date))
    else:
        emit("WARN", "signal_data", f"veraltet ({data.signal_date})")

    status = "ERROR" if errors else ("WARN" if warnings else "OK")
    blocking = errors > 0
    summary = f"[{'OK' if status == 'OK' else 'WARN' if status == 'WARN' else 'ERROR'}] Preflight: {status}"
    lines.append(summary)
    if log is not None:
        log(summary)

    report = PreflightReport(
        status=status,
        errors=errors,
        warnings=warnings,
        blocking=blocking,
        checks=checks,
        log_lines=lines,
    )
    control_dir = root / "control_output"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "launcher_preflight.json").write_text(
        json.dumps(
            {
                "status": status,
                "errors": errors,
                "warnings": warnings,
                "checks": checks,
                "data_ok": data.ok,
                "price_date": data.price_latest.isoformat() if data.price_latest else None,
                "signal_date": data.signal_date.isoformat() if data.signal_date else None,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return report
