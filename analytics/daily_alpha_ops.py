"""Daily Alpha Ops — delegiert an R3 Ops Kernel (harmonisierte Schnittstelle)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_DAILY_EVIDENCE = Path("evidence/daily_alpha_ops_latest.json")
_KERNEL_POLICY = Path("control/r3_ops_kernel_policy.json")


def load_daily_alpha_policy(root: Path) -> Dict[str, Any]:
    from analytics.r3_ops_kernel import load_ops_policy

    return load_ops_policy(root)


def rank_top_picks(worthwhile: Dict[str, Any], *, max_picks: int = 12, min_score: float = 8.0):
    from analytics.r3_ops_kernel import rank_top_picks as _rank

    return _rank(worthwhile, max_picks=max_picks, min_score=min_score)


def run_daily_alpha_ops(
    root: Path,
    *,
    phase: str = "pre_us",
    force: bool = False,
    persist: bool = True,
) -> Dict[str, Any]:
    from analytics.r3_ops_kernel import run_ops_pipeline

    doc = run_ops_pipeline(
        root,
        phase=phase,
        force=force,
        persist=False,
        source="daily_alpha_ops",
    )
    phase_key = doc.get("phase") or phase
    doc["bash_de"] = f"bash tools/king_ops.sh daily-alpha {str(phase_key).replace('_', '-')}"
    doc["policy_ref"] = str(_KERNEL_POLICY).replace("\\", "/")
    if persist:
        atomic_write_json(Path(root) / _DAILY_EVIDENCE, doc)
    return doc
