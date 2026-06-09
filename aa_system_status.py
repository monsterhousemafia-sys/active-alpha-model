"""Project-level health snapshot for Marktanalyse.exe (system_status.json)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

STATUS_FILE = "system_status.json"


@dataclass
class SystemStatus:
    last_run_utc: str = ""
    phase: str = "unknown"
    health: str = "unknown"
    operational_health: str = "unknown"
    analytical_validity: str = "unknown"
    validated_run_id: str = ""
    exit_code: int = 0
    price_date: Optional[str] = None
    signal_date: Optional[str] = None
    paper_mark_today: Optional[bool] = None
    preflight_status: str = "unknown"
    run_plan: str = "unknown"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def status_path(root: Path) -> Path:
    return Path(root) / STATUS_FILE


def read_system_status(root: Path) -> SystemStatus:
    path = status_path(root)
    if not path.is_file():
        return SystemStatus()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SystemStatus(
            last_run_utc=str(raw.get("last_run_utc", "") or ""),
            phase=str(raw.get("phase", "unknown") or "unknown"),
            health=str(raw.get("health", "unknown") or "unknown"),
            operational_health=str(raw.get("operational_health", raw.get("health", "unknown")) or "unknown"),
            analytical_validity=str(raw.get("analytical_validity", "unknown") or "unknown"),
            validated_run_id=str(raw.get("validated_run_id", "") or ""),
            exit_code=int(raw.get("exit_code", 0) or 0),
            price_date=raw.get("price_date"),
            signal_date=raw.get("signal_date"),
            paper_mark_today=raw.get("paper_mark_today"),
            preflight_status=str(raw.get("preflight_status", "unknown") or "unknown"),
            run_plan=str(raw.get("run_plan", "unknown") or "unknown"),
            message=str(raw.get("message", "") or ""),
            details=dict(raw.get("details") or {}),
        )
    except Exception:
        return SystemStatus()


def write_system_status(root: Path, status: SystemStatus) -> Path:
    path = status_path(root)
    payload = status.to_dict()
    if not payload.get("last_run_utc"):
        payload["last_run_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def health_label(health: str) -> str:
    key = str(health or "").upper()
    if key == "OK":
        return "Betriebsbereit"
    if key == "WARN":
        return "Einschränkung"
    if key == "ERROR":
        return "Prüfung nötig"
    return "Unbekannt"


def health_from_parts(*, preflight: str, data_ok: bool, exit_code: int = 0, ops_degraded: bool = False) -> str:
    """Operational health only (prices, preflight, exit code)."""
    pf = str(preflight or "").upper()
    if exit_code not in (0, None) and int(exit_code) != 0:
        return "ERROR"
    if pf == "ERROR":
        return "ERROR"
    if pf == "WARN" or not data_ok or ops_degraded:
        return "WARN"
    return "OK"


def combined_health(*, operational: str, analytical: str) -> str:
    op = str(operational or "").upper()
    an = str(analytical or "").upper()
    if op == "ERROR" or an == "INVALID":
        return "ERROR"
    if op == "WARN" or an in {"UNKNOWN", "WARN", "DATA_QUALITY_WARN"}:
        return "WARN"
    if an == "PASS" and op == "OK":
        return "OK"
    return op if op != "OK" else "WARN"
