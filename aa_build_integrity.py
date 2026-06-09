"""EXE build integrity — SHA-256 ledger and optional Authenticode check."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent
EXE_NAMES = ("Marktanalyse.exe",)
HASH_FILE = ROOT / "Marktanalyse.exe.sha256"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_recorded_hash(root: Optional[Path] = None) -> Optional[str]:
    path = (root or ROOT) / "Marktanalyse.exe.sha256"
    if not path.is_file():
        return None
    line = path.read_text(encoding="utf-8").strip().splitlines()[0]
    return line.split()[0].lower() if line else None


def write_hash_sidecar(exe_path: Path, *, root: Optional[Path] = None) -> str:
    """Write Marktanalyse.exe.sha256 next to repo root; return hex digest."""
    digest = sha256_file(exe_path)
    sidecar = (root or ROOT) / "Marktanalyse.exe.sha256"
    sidecar.write_text(f"{digest}  {exe_path.name}\n", encoding="utf-8")
    return digest


def verify_exe_hash_consistency(*, root: Optional[Path] = None) -> Dict[str, Any]:
    """Fail-closed if sidecar hash != on-disk EXE."""
    root = root or ROOT
    from aa_paths import canonical_marktanalyse_exe

    exe = canonical_marktanalyse_exe(root)
    if not exe.is_file():
        return {"ok": False, "reason": "exe_missing", "path": str(exe)}
    actual = sha256_file(exe)
    recorded = read_recorded_hash(root)
    if recorded is None:
        return {"ok": False, "reason": "hash_sidecar_missing", "actual_sha256": actual}
    ok = actual.lower() == recorded.lower()
    return {
        "ok": ok,
        "actual_sha256": actual,
        "recorded_sha256": recorded,
        "reason": None if ok else "hash_mismatch",
    }


def authenticode_status(exe_path: Path) -> Dict[str, Any]:
    if sys.platform != "win32":
        return {"platform": sys.platform, "signed": None, "status": "NOT_WINDOWS"}
    ps = (
        f"(Get-AuthenticodeSignature -FilePath '{exe_path}').Status | ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
        )
        status = (proc.stdout or "").strip().strip('"')
        signed = status == "Valid"
        if status.isdigit():
            signed = int(status) == 0  # SignatureStatus.Valid
            status = {0: "Valid", 1: "HashMismatch", 2: "NotSigned", 3: "NotTrusted"}.get(int(status), status)
        return {"platform": "win32", "signed": signed, "status": status or "Unknown"}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"platform": "win32", "signed": False, "status": f"CHECK_FAILED:{exc}"[:80]}


def write_build_integrity_manifest(*, root: Optional[Path] = None, exe_path: Optional[Path] = None) -> Path:
    root = root or ROOT
    exe = exe_path or (root / "Marktanalyse.exe")
    doc = {
        "updated_at_utc": _utc_now(),
        "exe_path": str(exe.relative_to(root)).replace("\\", "/") if exe.is_file() else str(exe),
        "sha256": sha256_file(exe) if exe.is_file() else None,
        "authenticode": authenticode_status(exe) if exe.is_file() else {},
        "hash_sidecar": str(HASH_FILE.relative_to(root)).replace("\\", "/"),
    }
    out = root / "evidence" / "exe_build_integrity_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return out
