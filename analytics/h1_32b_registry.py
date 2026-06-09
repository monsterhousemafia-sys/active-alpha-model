"""H1-Fehler inventarisieren — Mandat für König 32B (build-kernel)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_MANDATE_REL = Path("evidence/king_32b_h1_fix_mandate.txt")
_RUN_REL = Path("evidence/h1_32b_fix_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def collect_h1_errors(root: Path) -> Dict[str, Any]:
    """IST: H1-Evidenz-Inkonsistenzen und Blocker (ohne Benchmark zu starten)."""
    root = Path(root)
    errors: List[str] = []
    facts: List[str] = []

    try:
        from analytics.h1_seal_policy import is_h1_benchmark_required, is_h1_seal_required, seal_policy_banner_de

        seal_required = is_h1_seal_required(root)
        bench_required = is_h1_benchmark_required(root)
        facts.append(f"seal_required={seal_required} benchmark_required={bench_required}")
        if not seal_required:
            facts.append(seal_policy_banner_de(root))
    except Exception as exc:
        seal_required = True
        bench_required = True
        errors.append(f"Seal-Policy lesen: {exc}")

    try:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        h1 = h1_backtest_status(root)
        h1_st = str(h1.get("status") or "MISSING")
        sealed = is_h1_backtest_sealed(root)
        facts.append(f"h1_status={h1_st} sealed={sealed}")
        if h1_st == "COMPLETE" and not sealed and not bench_required:
            eval_doc = _load_json(root / "evidence/daily_alpha_h1_evaluation_latest.json")
            msg = str(eval_doc.get("message_de") or "")
            if "Benchmark returns fehlen" in msg:
                errors.append("Evaluation zeigt Benchmark-Fehler obwohl Seal optional")
            conn = _load_json(root / "evidence/h1_unified_connect_latest.json")
            if conn.get("generating_live"):
                errors.append("h1_unified_connect: generating_live=true ohne laufenden Prozess")
            if "Benchmark läuft" in str(conn.get("headline_de") or ""):
                errors.append("h1_unified_connect Headline behauptet Benchmark-Lauf")
    except Exception as exc:
        errors.append(f"H1-Status: {exc}")

    try:
        from analytics.h1_benchmark import benchmark_status

        bench = benchmark_status(root)
        if bench_required and not bench.get("exists"):
            errors.append(f"mom_1-Benchmark fehlt: {bench.get('benchmark_path')}")
        elif not bench_required and not bench.get("exists"):
            facts.append("mom_1-Benchmark fehlt — policy: optional")
    except Exception as exc:
        errors.append(f"benchmark_status: {exc}")

    try:
        status = _load_json(root / "evidence/king_status_latest.json")
        if status.get("benchmark_csv_ok") is False and bench_required:
            errors.append("king_status: benchmark_csv_ok=false")
        elif status.get("benchmark_csv_ok") is False and not bench_required:
            facts.append("benchmark_csv_ok=false — policy: nicht blockierend")
        gpu = str(status.get("gpu_reason_de") or "")
        if "Ollama" in gpu and bench_required:
            errors.append(f"GPU blockiert: {gpu[:100]}")
    except Exception:
        pass

    gov = _load_json(root / "control/h1_governance_status.json")
    if gov.get("gate_blockers"):
        errors.append(f"gate_blockers: {gov.get('gate_blockers')}")

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "errors_de": errors,
        "facts_de": facts,
        "error_count": len(errors),
        "ok": len(errors) == 0,
        "seal_required": seal_required,
        "benchmark_required": bench_required,
    }


def prep_h1_evidence_sync(root: Path) -> Dict[str, Any]:
    """Bash-Vorlauf: Governance + Pipeline ohne Benchmark (Seal optional)."""
    root = Path(root)
    out: Dict[str, Any] = {"steps": []}
    try:
        from analytics.h1_governance_status import sync_h1_governance_status

        out["governance"] = sync_h1_governance_status(root, write_readiness=True)
        out["steps"].append("sync_h1_governance_status")
    except Exception as exc:
        out["governance_error"] = str(exc)[:120]

    try:
        from analytics.h1_unified_connect import connect_h1_pipeline

        out["connect"] = connect_h1_pipeline(root, auto_execute=False)
        out["steps"].append("connect_h1_pipeline(auto_execute=False)")
    except Exception as exc:
        out["connect_error"] = str(exc)[:120]

    try:
        from analytics.h1_seal_policy import is_h1_benchmark_required
        from analytics.live_profile_governance import h1_backtest_status

        if not is_h1_benchmark_required(root) and str(h1_backtest_status(root).get("status")) == "COMPLETE":
            py = root / ".venv/bin/python3"
            if py.is_file():
                import subprocess
                import sys

                proc = subprocess.run(
                    [str(py), str(root / "tools/evaluate_daily_alpha_h1.py"), "--json"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                out["evaluate_rc"] = proc.returncode
                out["steps"].append("evaluate_daily_alpha_h1")
    except Exception as exc:
        out["evaluate_error"] = str(exc)[:120]

    doc = collect_h1_errors(root)
    doc["prep"] = out
    atomic_write_json(root / _RUN_REL, doc)
    return doc


def build_32b_h1_mandate(root: Path) -> str:
    doc = prep_h1_evidence_sync(root)
    errors = list(doc.get("errors_de") or [])
    facts = list(doc.get("facts_de") or [])
    lines = [
        "König-Mandat: H1-assoziierte Fehler beheben — NUR König 32B, NICHT Cursor.",
        f"Fehler ({len(errors)}): " + ("; ".join(errors) if errors else "keine nach Prep-Sync"),
        "Facts: " + "; ".join(facts[:6]),
        "Policy: control/h1_seal_policy.json — Seal optional, mom_1-Benchmark NICHT blockierend.",
        "Ziel: Evidenz konsistent — H1 COMPLETE ohne irreführende Benchmark-/generating_live-Fehler.",
        "Pflicht-Reads: evidence/king_status_latest.json, evidence/h1_unified_connect_latest.json,",
        "evidence/daily_alpha_h1_evaluation_latest.json, control/h1_governance_status.json.",
        "Code-Fixes (nur analytics/, tools/, tests/):",
        "1) analytics/h1_unified_connect.py — bei seal optional: kein Benchmark-Start, next=/ready",
        "2) tools/evaluate_daily_alpha_h1.py — message_de wenn Benchmark optional aber Strategie da",
        "3) analytics/h1_governance_status.py — banner COMPLETE+seal optional",
        "4) Stale evidence/h1_benchmark_latest.json generating → retired wenn kein Prozess",
        "Safety: fail-closed, dry_run, keine Orders, keine Champion-Änderung, auto_promote=false.",
        "Nach jedem write_file: .venv/bin/python -m pytest tests/test_h1_seal_policy.py tests/test_h1_governance_status.py -q",
        "Dann: bash tools/king_ops.sh status && bash tools/king_ops.sh pulse --force",
        "finish wenn collect_h1_errors ok=true oder nur optionale Benchmark-Hinweise.",
    ]
    text = " ".join(lines)
    Path(root / _MANDATE_REL).write_text(text, encoding="utf-8")
    return text
