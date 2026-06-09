"""Route heavy compute to WSL native; live broker ops stay on Windows."""
from __future__ import annotations
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

EVIDENCE_REL = Path("evidence/linux_compute_router_latest.json")
WSL_NATIVE = "$HOME/active_alpha_model"
WINDOWS_ONLY = frozenset({"predict","live_mark","live_rebalance","price_tail_merge","t212","competition_shadow"})
LINUX_JOBS = frozenset({"h1_backtest","m3_daily","m1_matrix","validation_matrix","wsl_setup"})

def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def windows_mount(root: Path) -> str:
    d = root.drive.rstrip(":").lower()
    return f"/mnt/{d}/{str(root.relative_to(root.anchor)).replace(chr(92),'/')}"

def wsl_ok() -> bool:
    try:
        r = subprocess.run(["wsl","bash","-lc","echo ok"], capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False

def native_ready() -> bool:
    if not wsl_ok(): return False
    r = subprocess.run(["wsl","bash","-lc", f"test -x {WSL_NATIVE}/.venv/bin/python3"], capture_output=True, timeout=60)
    return r.returncode == 0

def workdir(root: Path) -> str:
    return WSL_NATIVE if native_ready() else windows_mount(root)

def build_cmd(root: Path, conductor: str, *, sync: bool = True) -> List[str]:
    mount, native = windows_mount(root), WSL_NATIVE
    if sync and native_ready():
        body = f'''set -euo pipefail
rsync -a --exclude .venv --exclude __pycache__ --exclude .git/objects "{mount}/" "{native}/" 2>/dev/null || true
cd "{native}" && bash tools/wsl_conductor.sh {conductor}'''
    else:
        body = f'cd "{workdir(root)}" && bash tools/wsl_conductor.sh {conductor}'
    return ["wsl","bash","-lc", body]

def run_linux(root: Path, conductor: str, *, sync: bool = True, background: bool = False):
    cmd = build_cmd(root, conductor, sync=sync)
    kw = dict(cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    return subprocess.Popen(cmd, **kw) if background else subprocess.run(cmd, check=False, **kw)

def run_wsl_setup(root: Path) -> Dict[str, Any]:
    m = windows_mount(root)
    r = subprocess.run(["wsl","bash","-lc", f'cd "{m}" && bash tools/wsl_conductor.sh setup'],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"ok": r.returncode==0, "returncode": r.returncode, "stdout_tail": (r.stdout or "")[-3000:]}

def routing_doc(root: Path) -> Dict[str, Any]:
    return {"schema_version":1, "generated_at_utc":_utc_now(), "wsl_available":wsl_ok(),
        "wsl_native_ready":native_ready(), "linux_workdir":workdir(root),
        "windows_mount":windows_mount(root), "windows_only":sorted(WINDOWS_ONLY), "linux_jobs":sorted(LINUX_JOBS)}

def write_evidence(root: Path) -> Path:
    p = Path(root)/EVIDENCE_REL; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(routing_doc(root), indent=2)+"\n", encoding="utf-8"); return p
