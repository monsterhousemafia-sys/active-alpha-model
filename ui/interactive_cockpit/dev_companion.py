"""Dev companion — build info and Cursor context export (max dev efficiency)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from integrations.trading212.t212_credentials_ui_controller import credential_storage_summary
from integrations.trading212.t212_secret_redaction import redact_secrets


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _file_sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dev_mode_active() -> bool:
    return os.environ.get("AA_DEV_COCKPIT", "").strip() == "1"


def resolve_marktanalyse_exe_path(root: Path) -> Path:
    root = Path(root)
    sidecar = root / "Marktanalyse.exe.sha256"
    if sidecar.is_file():
        return root / "Marktanalyse.exe"
    from aa_paths import resolve_marktanalyse_exe

    return resolve_marktanalyse_exe(root)


def get_dev_runtime_info(root: Path) -> Dict[str, Any]:
    root = Path(root)
    exe_path = resolve_marktanalyse_exe_path(root)
    sha_sidecar = root / "Marktanalyse.exe.sha256"
    exe_sha = None
    if sha_sidecar.is_file():
        line = sha_sidecar.read_text(encoding="utf-8").strip().split()
        exe_sha = line[0] if line else None
    if not exe_sha:
        exe_sha = _file_sha256(exe_path)

    marker = root / "control" / "marktanalyse_runtime_layout.json"
    layout = {}
    if marker.is_file():
        try:
            layout = json.loads(marker.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            layout = {}

    return {
        "generated_at_utc": _utc_now(),
        "dev_mode": dev_mode_active(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "python_launch": not getattr(sys, "frozen", False),
        "runtime_root": str(root),
        "aa_project_root": os.environ.get("AA_PROJECT_ROOT", ""),
        "executable": str(exe_path),
        "executable_exists": exe_path.is_file(),
        "executable_sha256": exe_sha,
        "layout": layout,
        "credential_storage": credential_storage_summary(root),
    }


def format_cursor_handoff(
    root: Path,
    *,
    nav_view: str = "",
    state: Optional[Dict[str, Any]] = None,
    extra_note: str = "",
) -> str:
    """Plain-text bundle for pasting into Cursor chat — secrets redacted."""
    info = get_dev_runtime_info(root)
    broker = (state or {}).get("broker") or {}
    lines = [
        "=== Marktanalyse Dev-Kontext (für Cursor) ===",
        f"Zeit (UTC): {info.get('generated_at_utc')}",
        f"Laufart: {'EXE (frozen)' if info.get('frozen') else 'Python Dev-Launcher'}",
        f"Dev-Modus (AA_DEV_COCKPIT): {'ja' if info.get('dev_mode') else 'nein'}",
        f"Runtime-Root: {info.get('runtime_root')}",
        f"AA_PROJECT_ROOT: {info.get('aa_project_root') or '—'}",
        f"Aktive Nav-Ansicht: {nav_view or '—'}",
        "",
        "Build / EXE:",
        f"  Pfad: {info.get('executable')}",
        f"  Vorhanden: {'ja' if info.get('executable_exists') else 'nein'}",
        f"  SHA-256: {info.get('executable_sha256') or '—'}",
        "",
        "T212 (redigiert):",
        f"  credentials_configured: {broker.get('credentials_configured')}",
        f"  status: {broker.get('status')}",
        f"  environment: {broker.get('environment')}",
        f"  last_sync: {broker.get('last_successful_sync_utc')}",
        f"  cash_eur: {broker.get('cash_eur')}",
        f"  positions: {broker.get('positions_count')}",
        f"  last_error: {redact_secrets(str(broker.get('last_error') or ''))[:200] or '—'}",
        "",
        "Credential-Speicher:",
        f"  {info.get('credential_storage', {}).get('hint', '—')}",
        "",
    ]
    err = (state or {}).get("refresh_error")
    if err:
        lines.extend(["Letzter Refresh-Fehler:", f"  {redact_secrets(str(err))[:300]}", ""])
    if extra_note.strip():
        lines.extend(["Notiz:", extra_note.strip(), ""])
    lines.append("=== Ende Kontext ===")
    return redact_secrets("\n".join(lines))


def write_cursor_handoff_file(root: Path, text: str) -> Path:
    out = Path(root) / "evidence" / "cursor_dev_handoff_latest.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    return out
