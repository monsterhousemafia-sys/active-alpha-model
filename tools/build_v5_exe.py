"""V5 controlled Windows EXE build — PyInstaller only, never launches EXE."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = doc_rel("CODEX_V5_BUILD_LOG.txt")


def _py() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def main() -> int:
    py = _py()
    lines: list[str] = []
    icon_script = ROOT / "tools" / "generate_r3_icon.py"
    spec = ROOT / "build" / "launcher" / "Marktanalyse.spec"
    post = ROOT / "tools" / "post_build_marktanalyse.py"
    smoke = ROOT / "tools" / "smoke_test_launcher.py"

    def run(cmd: list[str], label: str) -> None:
        lines.append(f"\n=== {label} ===\n")
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        lines.append(proc.stdout or "")
        if proc.stderr:
            lines.append(proc.stderr)
        lines.append(f"\nexit_code={proc.returncode}\n")
        if proc.returncode != 0:
            (ROOT / LOG).write_text("".join(lines), encoding="utf-8")
            raise SystemExit(f"{label} failed with code {proc.returncode}")

    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "pyinstaller", "PySide6"], "pip deps")
    run([str(py), str(icon_script)], "generate icon")
    run(
        [str(py), "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", ".", "--workpath", "build/launcher", str(spec)],
        "pyinstaller",
    )
    run([str(py), str(post)], "post_build")
    if not (ROOT / "Marktanalyse.exe").is_file():
        raise SystemExit("Marktanalyse.exe not produced")
    run([str(py), str(smoke)], "smoke_test_launcher (no EXE execution)")
    lines.append("\n[OK] Build complete — EXE not launched\n")
    (ROOT / LOG).write_text("".join(lines), encoding="utf-8")
    print("V5 build OK — Marktanalyse.exe created, not executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
