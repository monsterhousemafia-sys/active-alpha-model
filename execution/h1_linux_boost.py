"""Linux I/O + NUMA-Hinweise für H1-Backtest."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List


def numa_exec_prefix() -> List[str]:
    """numactl --interleave=all wenn verfügbar (gleichmäßiger RAM auf Mehr-Socket)."""
    if not shutil.which("numactl"):
        return []
    try:
        proc = subprocess.run(
            ["numactl", "--hardware"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if proc.returncode != 0 or "available:" not in (proc.stdout or "").lower():
            return []
    except (OSError, subprocess.TimeoutExpired):
        return []
    return ["numactl", "--interleave=all"]


def warm_run_artifacts(root: Path, run_dir: str | None) -> Dict[str, Any]:
    """vmtouch für große Artefakte — best effort."""
    root = Path(root)
    out: Dict[str, Any] = {"ok": False, "warmed": []}
    if not shutil.which("vmtouch"):
        out["note_de"] = "vmtouch nicht installiert — optional apt install vmtouch"
        return out
    if not run_dir:
        return out
    run = root / run_dir
    targets = [
        run / "features.parquet",
        run / "prediction_cache.pkl",
        run / "path_sim_checkpoint.pkl",
    ]
    for path in targets:
        if not path.is_file():
            continue
        try:
            proc = subprocess.run(
                ["vmtouch", "-t", str(path)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode == 0:
                out["warmed"].append(str(path.relative_to(root)))
        except (OSError, subprocess.TimeoutExpired):
            pass
    out["ok"] = bool(out["warmed"])
    return out
