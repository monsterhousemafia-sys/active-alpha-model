"""Stufe A — Wachstum, RAG, Teacher-Student, H1-Live-KPIs (König 32B)."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

from analytics.king_evidence_rag import build_evidence_rag, load_stufe_a_policy

_POLICY_REL = Path("control/king_stufe_a_policy.json")
_EVIDENCE_REL = Path("evidence/king_stufe_a_latest.json")
_STATE_REL = Path("control/king_stufe_a_state.json")
_TEACHER_REL = Path("evidence/king_teacher_student_latest.json")


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


def _parse_utc(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _prognosis_age_s(root: Path) -> Optional[float]:
    doc = _load_json(root / "evidence/r3_t212_prognosis_latest.json")
    ts = _parse_utc(str(doc.get("updated_at_utc") or ""))
    if not ts:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds()


def evaluate_stufe_a_kpis(root: Path) -> Dict[str, Any]:
    root = Path(root)
    policy = load_stufe_a_policy(root)
    thr = dict(policy.get("kpi_thresholds") or {})
    checks: List[Dict[str, Any]] = []

    readiness = _load_json(root / "control/prediction_readiness.json")
    pred_ok = bool(readiness.get("ok"))
    if thr.get("require_prediction_ready", True):
        checks.append(
            {
                "id": "prediction_ready",
                "pass": pred_ok,
                "detail_de": f"signal={readiness.get('signal_date')} ok={pred_ok}",
            }
        )

    h1_eval = _load_json(root / "evidence/daily_alpha_h1_evaluation_latest.json")
    h1_gov = _load_json(root / "control/h1_governance_status.json")
    h1_status = str(h1_gov.get("status") or readiness.get("h1_backtest_status") or "")
    sharpe = None
    metrics = h1_eval.get("metrics_strategy") or h1_gov.get("metrics_strategy") or {}
    if isinstance(metrics, dict):
        sharpe = metrics.get("sharpe_0rf") or metrics.get("sharpe")
    try:
        sharpe_f = float(sharpe) if sharpe is not None else None
    except (TypeError, ValueError):
        sharpe_f = None
    checks.append(
        {
            "id": "h1_complete",
            "pass": h1_status.upper() in ("COMPLETE", "SEALED", "PASS"),
            "detail_de": f"status={h1_status}",
        }
    )
    min_sharpe = float(thr.get("h1_sharpe_min") or 0.5)
    checks.append(
        {
            "id": "h1_sharpe",
            "pass": sharpe_f is not None and sharpe_f >= min_sharpe,
            "detail_de": f"sharpe={sharpe_f} min={min_sharpe}",
            "value": sharpe_f,
        }
    )

    age = _prognosis_age_s(root)
    max_stale = float(thr.get("prognosis_max_stale_s") or 900)
    checks.append(
        {
            "id": "prognosis_fresh",
            "pass": age is not None and age <= max_stale,
            "detail_de": f"age_s={round(age or -1, 1)} max={max_stale}",
            "age_s": age,
        }
    )

    learn = _load_json(root / "evidence/public_learning_report_latest.json")
    learn_score = learn.get("score")
    if learn_score is None:
        q = learn.get("quality_score") or {}
        learn_score = q.get("total") if isinstance(q, dict) else None
    try:
        learn_score_f = float(learn_score) if learn_score is not None else None
    except (TypeError, ValueError):
        learn_score_f = None
    min_learn = float(thr.get("learn_min_score") or 40)
    checks.append(
        {
            "id": "learn_score",
            "pass": learn_score_f is not None and learn_score_f >= min_learn,
            "detail_de": f"score={learn_score_f} min={min_learn}",
        }
    )

    king = _load_json(root / "evidence/king_trading_assist_latest.json")
    if thr.get("require_king_trading_tick"):
        checks.append(
            {
                "id": "king_trading",
                "pass": bool(king.get("updated_at_utc")),
                "detail_de": king.get("headline_de") or "—",
            }
        )

    blockers = [c["id"] for c in checks if not c.get("pass")]
    wachstum_pass = pred_ok and (sharpe_f is not None and sharpe_f >= min_sharpe)
    forschung_reif_pass = wachstum_pass and not blockers

    return {
        "ok": forschung_reif_pass,
        "wachstum_ok": wachstum_pass,
        "forschung_reif_ok": forschung_reif_pass,
        "checks": checks,
        "blockers": blockers,
        "evaluated_at_utc": _utc_now(),
    }


def resolve_growth_phase_from_kpis(kpis: Dict[str, Any], *, ollama_ok: bool) -> str:
    if not ollama_ok:
        return "keim"
    if kpis.get("forschung_reif_ok"):
        return "forschung_reif"
    if kpis.get("wachstum_ok"):
        return "wachstum"
    return "spross"


def build_teacher_student_snapshot(root: Path) -> Dict[str, Any]:
    root = Path(root)
    policy = load_stufe_a_policy(root)
    ts_pol = dict(policy.get("teacher_student_de") or {})
    advisor_ok = False
    advisor_msg = ""
    teacher_provider = "none"
    try:
        from analytics.gemini_advisor_bridge import bridge_status as gemini_bridge_status
        from analytics.gemini_advisor_bridge import is_gemini_configured

        if is_gemini_configured(root):
            gst = gemini_bridge_status(root)
            advisor_ok = bool(gst.get("configured"))
            teacher_provider = "gemini"
            advisor_msg = str(gst.get("headline_de") or "")[:120]
        else:
            from analytics.r3_external_advisor import advisor_status

            st = advisor_status(root)
            advisor_ok = bool(st.get("configured"))
            teacher_provider = str(st.get("primary_provider") or "keyless")
            advisor_msg = str(st.get("headline_de") or "")[:120]
    except Exception as exc:
        advisor_msg = str(exc)[:80]

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "teacher_available": advisor_ok,
        "teacher_provider": teacher_provider,
        "teacher_de": (
            "Gemini Cloud /kombi /tipp — Parallel-Compute"
            if teacher_provider == "gemini"
            else (ts_pol.get("teacher_role_de") or "Cloud /kombi /tipp — Berater, keine Orders")
        ),
        "student_de": ts_pol.get("student_executes_de") or "König 32B lokal",
        "advisor_status_de": advisor_msg,
        "operator_de": "Teacher berät — Student (32B) führt nur king_ops/R3 aus, keine Auto-Orders.",
        "commands_de": [
            "/kombi <frage>",
            "/tipp <frage>",
            "bash tools/king_ops.sh stufe-a",
            "control/secrets/gemini_api_key (optional, Stealth)",
        ],
        "cloud_teacher_ref": "evidence/king_cloud_teacher_latest.json",
    }
    atomic_write_json(root / _TEACHER_REL, doc)
    return doc


def _cooldown_ok(root: Path, minutes: int) -> bool:
    state = _load_json(root / _STATE_REL)
    stamp = _parse_utc(str(state.get("last_tick_utc") or ""))
    if not stamp:
        return True
    age = (datetime.now(timezone.utc) - stamp).total_seconds() / 60.0
    return age >= float(minutes)


def run_stufe_a_tick(root: Path, *, force: bool = False, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = load_stufe_a_policy(root)
    if not policy.get("enabled", True):
        return {"ok": True, "skipped": True, "headline_de": "Stufe A deaktiviert"}

    cd = int(policy.get("tick_cooldown_min") or 45)
    if not force and not _cooldown_ok(root, cd):
        cached = _load_json(root / _EVIDENCE_REL)
        return {
            **cached,
            "ok": True,
            "skipped": True,
            "reason_de": f"cooldown_{cd}m",
        }

    steps: List[Dict[str, Any]] = []

    kpis = evaluate_stufe_a_kpis(root)
    steps.append({"step": "kpis", "ok": True, "kpis": kpis})

    rag = build_evidence_rag(root, persist=True)
    steps.append({"step": "evidence_rag", "ok": bool(rag.get("chunk_count")), "chunks": rag.get("chunk_count")})

    try:
        from analytics.king_trading_assist import run_king_trading_assist

        kt = run_king_trading_assist(root, force=force)
        steps.append({"step": "king_trading", "ok": bool(kt.get("ok")), "detail": kt.get("reason_de") or kt.get("detail_de")})
    except Exception as exc:
        steps.append({"step": "king_trading", "ok": False, "error": str(exc)[:80]})

    learn_ok = False
    py = root / ".venv/bin/python3"
    learn_script = root / "tools/run_public_learning_daily.py"
    if py.is_file() and learn_script.is_file():
        try:
            proc = subprocess.run(
                [str(py), str(learn_script)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            learn_ok = proc.returncode == 0
            steps.append({"step": "learn", "ok": learn_ok, "detail_de": (proc.stdout or "")[-120:]})
        except Exception as exc:
            steps.append({"step": "learn", "ok": False, "error": str(exc)[:80]})
    else:
        steps.append({"step": "learn", "ok": False, "skipped": True})

    kpis = evaluate_stufe_a_kpis(root)
    phase = resolve_growth_phase_from_kpis(kpis, ollama_ok=True)
    try:
        from analytics.local_llm_bridge import load_llm_config, ollama_available

        cfg = load_llm_config(root)
        base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
        phase = resolve_growth_phase_from_kpis(kpis, ollama_ok=ollama_available(base, timeout_s=3.0))
    except Exception:
        pass

    if phase == "forschung_reif":
        try:
            from analytics.evolution_stage_runner import run_evolution_cycle

            evo = run_evolution_cycle(root, apply_improvements=False)
            steps.append({"step": "evolve", "ok": bool(evo.get("ok")), "stage": evo.get("current_stage")})
        except Exception as exc:
            steps.append({"step": "evolve", "ok": False, "error": str(exc)[:80]})

    teacher = build_teacher_student_snapshot(root)
    steps.append({"step": "teacher_student", "ok": True, "teacher_available": teacher.get("teacher_available")})

    ts_pol = dict(policy.get("teacher_student_de") or {})
    if ts_pol.get("enabled", True) and bool(policy.get("teacher_consult_on_tick", True)):
        try:
            from analytics.cloud_teacher_orchestrator import (
                build_teacher_question_from_kpis,
                run_cloud_teacher_consult,
            )

            tq = build_teacher_question_from_kpis(kpis)
            consult = run_cloud_teacher_consult(root, tq, mode="kombi", source="stufe_a", persist=True)
            steps.append(
                {
                    "step": "teacher_consult",
                    "ok": bool(consult.get("ok")),
                    "provider": consult.get("provider"),
                    "compute_boost": consult.get("compute_boost"),
                    "headline_de": consult.get("headline_de"),
                }
            )
        except Exception as exc:
            steps.append({"step": "teacher_consult", "ok": False, "error": str(exc)[:80]})

    from analytics.king_32b_forschung import build_king_32b_forschung_status

    forschung = build_king_32b_forschung_status(root, persist=True)
    growth = dict(forschung.get("growth") or {})
    growth["phase"] = phase
    growth["phase_kpi_de"] = f"Stufe-A KPI — wachstum={kpis.get('wachstum_ok')} reif={kpis.get('forschung_reif_ok')}"
    forschung["growth"] = growth
    forschung["stufe_a_kpis"] = kpis
    atomic_write_json(root / "evidence/king_32b_forschung_latest.json", forschung)

    ok = kpis.get("wachstum_ok", False)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok,
        "headline_de": (
            f"Stufe A — Phase {phase} · {len(kpis.get('blockers') or [])} KPI-Blocker"
            if not kpis.get("forschung_reif_ok")
            else f"Stufe A — Phase {phase} · FORSCHUNG_REIF"
        ),
        "growth_phase": phase,
        "kpis": kpis,
        "steps": steps,
        "rag_ref": "evidence/king_evidence_rag_latest.json",
        "teacher_ref": str(_TEACHER_REL).replace("\\", "/"),
        "next_de": growth.get("next_growth_de") or forschung.get("growth", {}).get("next_growth_de"),
    }
    if persist:
        atomic_write_json(root / _STATE_REL, {"last_tick_utc": _utc_now(), "phase": phase})
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
