"""V5R onefile standalone release EXE build — neutral snapshot, never launches EXE."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LOG = doc_rel("CODEX_V5R_BUILD_LOG.txt")
SPEC = ROOT / "build" / "decision_cockpit" / "Marktanalyse.spec"
DIST_EXE = ROOT / "dist" / "Marktanalyse.exe"
OUT_EXE = ROOT / "Marktanalyse.exe"


def _py() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def main() -> int:
    from aa_decision_cockpit_readonly_snapshot import write_v5r_neutral_release_snapshot
    from tools.generate_v5r_build_provenance import write_build_provenance

    py = _py()
    lines: list[str] = []

    def run(cmd: list[str], label: str) -> None:
        lines.append(f"\n=== {label} ===\n")
        print(f"\n=== {label} ===", flush=True)
        print("Bitte warten (typ. 2–5 Min. bei PyInstaller) …", flush=True)
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        lines.append(f"\nexit_code={proc.returncode}\n")
        if proc.returncode != 0:
            (ROOT / LOG).write_text("".join(lines), encoding="utf-8")
            log_path = ROOT / LOG
            print(f"\n[FEHLER] {label} — Code {proc.returncode}", flush=True)
            print(f"Log: {log_path}", flush=True)
            raise SystemExit(f"{label} failed with code {proc.returncode}")

    provenance = write_build_provenance(root=ROOT)
    lines.append(f"build_provenance={provenance}\n")
    snap_path = write_v5r_neutral_release_snapshot(ROOT, provenance=provenance)
    lines.append(f"neutral_release_snapshot_written={snap_path}\n")

    legacy_dir = ROOT / "Marktanalyse"
    if legacy_dir.is_dir():
        shutil.rmtree(legacy_dir)
        lines.append(f"removed_legacy_onedir={legacy_dir}\n")

    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "pyinstaller", "PySide6"], "pip deps")
    run(
        [
            str(py),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            "dist",
            "--workpath",
            "build/decision_cockpit/work",
            str(SPEC),
        ],
        "pyinstaller onefile",
    )
    if not DIST_EXE.is_file():
        raise SystemExit("dist/Marktanalyse.exe not produced")
    shutil.copy2(DIST_EXE, OUT_EXE)
    try:
        DIST_EXE.unlink()
        lines.append(f"removed_duplicate={DIST_EXE}\n")
    except OSError:
        lines.append(f"warn_could_not_remove={DIST_EXE}\n")
    from aa_build_integrity import (
        verify_exe_hash_consistency,
        write_build_integrity_manifest,
        write_hash_sidecar,
    )

    digest = write_hash_sidecar(OUT_EXE, root=ROOT)
    manifest = write_build_integrity_manifest(root=ROOT, exe_path=OUT_EXE)
    verify = verify_exe_hash_consistency(root=ROOT)
    if not verify.get("ok"):
        raise SystemExit(f"post-build hash verify failed: {verify}")
    lines.append(f"\n[OK] sha256={digest}\n")
    lines.append(f"[OK] integrity_manifest={manifest}\n")
    lines.append(f"\n[OK] Canonical EXE: {OUT_EXE} (only copy; dist duplicate removed)\n")
    (ROOT / LOG).write_text("".join(lines), encoding="utf-8")
    print(f"V5R onefile build OK — {OUT_EXE.name} created, not executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
