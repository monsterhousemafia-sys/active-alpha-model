"""Build fail-closed test-only onefile EXE — NOT for V5R release submission."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SPEC = ROOT / "build" / "decision_cockpit" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.spec"
DIST_EXE = ROOT / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"


def _py() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def main() -> int:
    from aa_decision_cockpit_readonly_snapshot import write_v5r_fail_closed_test_snapshot
    from tools.generate_v5r_build_provenance import write_build_provenance

    py = _py()
    write_build_provenance(root=ROOT)
    snap_path = write_v5r_fail_closed_test_snapshot(ROOT)
    print(f"fail_closed_test_snapshot_written={snap_path}")
    proc = subprocess.run(
        [
            str(py),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            "dist",
            "--workpath",
            "build/decision_cockpit/work_fail_closed_test",
            str(SPEC),
        ],
        cwd=ROOT,
    )
    if proc.returncode != 0 or not DIST_EXE.is_file():
        raise SystemExit("Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe build failed")
    print(f"Built {DIST_EXE.name} — NOT for release submission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
