"""Static Marktanalyse.exe verification — never launches the EXE."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = "CODEX_V5_STATIC_EXE_VERIFICATION.md"
MODULE_MARKERS = (
    b"aa_decision_cockpit_viewmodel",
    b"aa_decision_cockpit_gui",
    b"aa_decision_cockpit_export",
    b"aa_dashboard_qt_window",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pe_machine(path: Path) -> str:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        return "UNKNOWN"
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_off + 6 >= len(data):
        return "UNKNOWN"
    machine = struct.unpack_from("<H", data, pe_off + 4)[0]
    return {0x8664: "AMD64", 0x014C: "I386"}.get(machine, f"0x{machine:04X}")


def _scan_markers(root: Path) -> dict[str, bool]:
    found = {m.decode(): False for m in MODULE_MARKERS}
    targets = [root / "Marktanalyse.exe", root / "Marktanalyse" / "_internal"]
    for base in targets:
        if base.is_file():
            blob = base.read_bytes()
            for m in MODULE_MARKERS:
                if m in blob:
                    found[m.decode()] = True
        elif base.is_dir():
            for f in base.rglob("*"):
                if not f.is_file() or f.suffix not in {".pyc", ".pyz", ".dll", ".pyd", ""}:
                    continue
                try:
                    if f.stat().st_size > 50_000_000:
                        continue
                    blob = f.read_bytes()
                except OSError:
                    continue
                for m in MODULE_MARKERS:
                    if m in blob:
                        found[m.decode()] = True
    return found


def main() -> int:
    exe = ROOT / "Marktanalyse.exe"
    if not exe.is_file():
        print("[STATIC FAIL] Marktanalyse.exe missing", file=sys.stderr)
        return 1
    digest = _sha256(exe)
    size = exe.stat().st_size
    arch = _pe_machine(exe)
    markers = _scan_markers(ROOT)
    internal = ROOT / "Marktanalyse" / "_internal"
    bundle_ok = internal.is_dir() and any(internal.iterdir())
    lines = [
        "# CODEX V5 Static EXE Verification",
        "",
        f"Generated: {_utc_now()}",
        "",
        f"- EXE path: `{exe}`",
        f"- EXE SHA-256: `{digest}`",
        f"- EXE size bytes: {size}",
        f"- PE architecture: {arch}",
        f"- Onedir bundle present: {bundle_ok}",
        f"- PyInstaller onedir layout: Marktanalyse/_internal",
        "",
        "## Embedded module markers (static string scan)",
        "",
    ]
    for name, ok in markers.items():
        lines.append(f"- {name}: {'FOUND' if ok else 'NOT FOUND'}")
    preexisting = {}
    pre_path = doc_path("CODEX_V5_PREEXISTING_EXE_BASELINE.json")
    if pre_path.is_file():
        preexisting = json.loads(pre_path.read_text(encoding="utf-8"))
    pre_hash = str(preexisting.get("sha256", "")).lower()
    hash_changed = bool(pre_hash and digest.lower() != pre_hash)
    mtime_newer = exe.stat().st_mtime > 0
    if preexisting.get("last_write_time_utc"):
        from datetime import datetime

        try:
            pre_dt = datetime.fromisoformat(str(preexisting["last_write_time_utc"]).replace("Z", "+00:00"))
            mtime_newer = datetime.fromtimestamp(exe.stat().st_mtime, tz=timezone.utc) > pre_dt
        except ValueError:
            pass
    lines += [
        "",
        "## Pre-existing EXE comparison",
        "",
        f"- Pre-existing SHA-256: `{pre_hash or 'N/A'}`",
        f"- Hash changed from pre-existing: {hash_changed}",
        f"- Timestamp newer than pre-existing baseline: {mtime_newer}",
        f"- PREEXISTING_EXE_REUSED_AS_BUILD_EVIDENCE: {'NO' if hash_changed else 'YES'}",
        "",
        "EXE_EXECUTED: NO",
        f"STATIC_EXE_VERIFICATION: {'PASS' if hash_changed and bundle_ok else 'BLOCKED'}",
    ]
    if pre_hash and not hash_changed:
        print("[STATIC FAIL] EXE hash unchanged from pre-existing baseline", file=sys.stderr)
        return 1
    report_path = doc_path(REPORT)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sidecar = ROOT / "Marktanalyse.exe.sha256"
    sidecar.write_text(f"{digest}  Marktanalyse.exe\n", encoding="utf-8")
    if not bundle_ok:
        print("[STATIC FAIL] onedir bundle missing", file=sys.stderr)
        return 1
    if not any(markers.values()):
        print("[STATIC WARN] no cockpit module markers found in static scan", file=sys.stderr)
    print(f"[STATIC OK] {exe.name} sha256={digest} size={size} arch={arch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
