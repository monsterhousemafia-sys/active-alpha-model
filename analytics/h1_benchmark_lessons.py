"""Lessons from H1 benchmark runs — Evidence für König/Operator."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/h1_benchmark_lessons_latest.json")

# Aus Legacy-Lauf PID 34334 (2026-06-07) abgeleitet
_KNOWN_LESSONS_DE: List[str] = [
    "Background-Start ohne progress.json → blindes Warten (behoben: sofortiger Progress bei Start)",
    "Prep-Phase meldete nichts → 75+ Min bei 100% CPU ohne % (behoben: phase=prep, prep_done)",
    "Progress erst im Returns-Loop → ETA irreführend wenn Prep lang (behoben: 0–50% Prep, 50–100% Returns)",
    "GPU-Returns nur wenn AA_H1_GPU_RETURNS=1 und VRAM frei (Legacy: CPU-only trotz 3090)",
    "Über ETA ohne progress_pct → Operator blind (behoben: benchmark_over_eta + phase decide)",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def record_benchmark_lessons(root: Path, *, trigger_de: str = "") -> Dict[str, Any]:
    """Schreibt Lessons aus aktuellem Benchmark-Stand + bekannte Fixes."""
    root = Path(root)
    progress: Dict[str, Any] = {}
    progress_path = root / "evidence/h1_benchmark_progress.json"
    if progress_path.is_file():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            progress = {}

    timing: Dict[str, Any] = {}
    try:
        from analytics.king_hardware import benchmark_timing

        timing = benchmark_timing(root)
    except Exception:
        pass

    inferred: List[str] = []
    if timing.get("benchmark_running") and progress.get("progress_pct") is None:
        inferred.append(
            "Laufender Job ohne progress_pct — vermutlich Legacy oder noch in Prep "
            f"(elapsed={timing.get('benchmark_elapsed_s')}s)"
        )
    if timing.get("benchmark_over_eta"):
        inferred.append("Job über ETA — Status prüfen, Neustart nur nach Operator-Freigabe")
    if progress.get("phase") == "prep" and progress.get("prep_done") is not None:
        inferred.append(
            f"Prep-Phase sichtbar: {progress.get('prep_done')}/{progress.get('prep_total')} "
            f"({progress.get('progress_pct')}%)"
        )

    doc = {
        "ok": True,
        "schema_version": 1,
        "recorded_at_utc": _utc_now(),
        "trigger_de": trigger_de or "auto",
        "lessons_de": _KNOWN_LESSONS_DE,
        "inferred_de": inferred,
        "fixes_de": [
            "bash tools/king_ops.sh h1-seal — flock, GPU-Prep, Progress ab Sekunde 0",
            "AA_H1_GPU_RETURNS=1 · AA_H1_UNLOAD_OLLAMA=1 für maximale 3090-Nutzung",
            "bash tools/king_ops.sh status — phase, prep_done, benchmark_over_eta",
        ],
        "progress_snapshot": progress,
        "timing_snapshot": timing,
        "headline_de": (
            f"{len(inferred)} aktive Beobachtung(en) · {len(_KNOWN_LESSONS_DE)} dokumentierte Lessons"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
