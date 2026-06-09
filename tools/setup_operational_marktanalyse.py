#!/usr/bin/env python3
"""DEPRECATED — use tools/build_v5r_standalone_exe.py (single Marktanalyse.exe at repo root)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESERVE = ROOT / "dist" / "codex_v5r_submission_preserve"
BUNDLE_EXE = ROOT / "Marktanalyse" / "Marktanalyse.exe"
SUBMISSION_FILES = (
    "Marktanalyse.exe",
    "Marktanalyse.exe.sha256",
    doc_rel("CODEX_V5R_STANDALONE_EXE_REPORT.md"),
    "codex_v5r_standalone_exe_review.zip",
    doc_rel("codex_v5r_standalone_exe_review.zip.sha256"),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _kill_marktanalyse() -> None:
    if sys.platform != "win32":
        return
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -Name 'Marktanalyse*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        check=False,
    )


def _preserve_submission() -> dict[str, str]:
    PRESERVE.mkdir(parents=True, exist_ok=True)
    meta: dict[str, str] = {}
    for name in SUBMISSION_FILES:
        src = ROOT / name
        if not src.is_file():
            continue
        dst = PRESERVE / name
        shutil.copy2(src, dst)
        if name.endswith(".exe"):
            meta["submission_exe_sha256"] = _sha256(src)
    (PRESERVE / "preserve_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def _restore_submission() -> None:
    for name in SUBMISSION_FILES:
        src = PRESERVE / name
        if src.is_file():
            shutil.copy2(src, ROOT / name)
    root_internal = ROOT / "_internal"
    if root_internal.exists() or root_internal.is_symlink():
        if sys.platform == "win32":
            subprocess.run(["cmd", "/c", "rmdir", str(root_internal)], check=False)
        else:
            root_internal.unlink(missing_ok=True)


def _build_operational() -> None:
    bat = ROOT / "build_active_alpha_launcher.bat"
    proc = subprocess.run(["cmd", "/c", str(bat)], cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"Operational build failed: exit={proc.returncode}")
    if not BUNDLE_EXE.is_file():
        raise SystemExit(f"Operational bundle missing: {BUNDLE_EXE}")


def _register_autostart() -> None:
    bat = ROOT / "setup_active_alpha_startup.bat"
    proc = subprocess.run(["cmd", "/c", str(bat)], cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"Autostart setup failed: exit={proc.returncode}")


def _register_scheduled_refresh() -> None:
    bat = ROOT / "setup_active_alpha_scheduled_refresh.bat"
    proc = subprocess.run(["cmd", "/c", str(bat)], cwd=ROOT)
    if proc.returncode != 0:
        print(f"[WARN] Scheduled refresh setup failed: exit={proc.returncode}", file=sys.stderr)


def _verify() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from aa_paths import resolve_submission_marktanalyse_exe

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    proc = subprocess.run([str(py), str(ROOT / "tools" / "smoke_test_launcher.py")], cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit("Operational smoke test failed")
    submission_hash = _sha256(resolve_submission_marktanalyse_exe(ROOT))
    preserved = json.loads((PRESERVE / "preserve_meta.json").read_text(encoding="utf-8"))
    expected = preserved.get("submission_exe_sha256", "")
    if expected and submission_hash != expected:
        raise SystemExit("Submission Marktanalyse.exe hash mismatch after restore")
    sidecar = ROOT / "Marktanalyse.exe.sha256"
    if sidecar.is_file():
        side_hash = sidecar.read_text(encoding="ascii").strip().split()[0]
        if side_hash != submission_hash:
            raise SystemExit("Submission sidecar hash mismatch")
    print(
        json.dumps(
            {
                "operational_exe": str(BUNDLE_EXE),
                "submission_exe_sha256": submission_hash,
                "autostart_target": "Marktanalyse\\Marktanalyse.exe",
                "pass": True,
            },
            indent=2,
        )
    )


def main() -> int:
    print(
        "[DEPRECATED] Onedir-Setup entfaellt. Bitte nur:\n"
        "  .venv\\Scripts\\python.exe tools\\build_v5r_standalone_exe.py\n"
        "Zentrale EXE: Marktanalyse.exe im Projektroot (siehe control/MARKTANALYSE_EXE.md)",
        file=sys.stderr,
    )
    return 2
    _kill_marktanalyse()
    meta = _preserve_submission()
    if not meta.get("submission_exe_sha256"):
        print("[WARN] No V5R submission EXE preserved — root Marktanalyse.exe will be replaced.", file=sys.stderr)
    _build_operational()
    _restore_submission()
    _register_autostart()
    _register_scheduled_refresh()
    _verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
