"""Phase S7 — one-shot sector reference rollout (Wikipedia + ensure + verify + matrix smoke)."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = ROOT / ".venv" / "Scripts" / "python.exe"


def _run(cmd: list[str], *, cwd: Path) -> int:
    print(f"[RUN] {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=str(cwd), check=False).returncode


def main() -> int:
    p = argparse.ArgumentParser(description="Execute sector reference rollout S7.")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--skip-wikipedia", action="store_true", help="Skip membership rebuild (S7.1).")
    p.add_argument("--skip-ensure", action="store_true", help="Skip ensure_sector_reference_fresh (S7.2).")
    args = p.parse_args()
    root = args.root.resolve()
    py = str(PY if PY.is_file() else sys.executable)
    rc = 0

    if not args.skip_wikipedia:
        rc = _run([py, str(root / "build_sp500_membership_wikipedia.py")], cwd=root)
        if rc != 0:
            return rc

    if not args.skip_ensure:
        rc = _run([py, str(root / "tools" / "run_ensure_sector_reference.py"), "--root", str(root)], cwd=root)
        if rc != 0:
            print("[WARN] ensure_sector_reference exited non-zero — continuing verify", flush=True)
        from aa_config_env import load_aa_env
        from aa_ops_refresh import refresh_universe_if_needed

        env = load_aa_env(root)
        env["AA_TICKER_CACHE_MAX_AGE_DAYS"] = "0"
        env.setdefault("AA_PAPER_TICKER_SOURCE", "wikipedia_sp500")
        if refresh_universe_if_needed(root, env, log=print):
            print("[OK] Universe snapshot refreshed (sector_gics)", flush=True)

    rc_verify = _run(
        [
            py,
            str(root / "tools" / "verify_sector_reference_coverage.py"),
            "--root",
            str(root),
            "--write-evidence",
        ],
        cwd=root,
    )
    rc_smoke = _run(
        [
            py,
            str(root / "tools" / "check_sector_matrix_smoke.py"),
            "--root",
            str(root),
            "--write-evidence",
        ],
        cwd=root,
    )

    ok = rc_verify == 0 and rc_smoke == 0
    print(f"[S7] rollout {'PASS' if ok else 'INCOMPLETE'} (verify={rc_verify}, smoke={rc_smoke})", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
