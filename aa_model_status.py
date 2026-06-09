"""Model validation status for Marktanalyse.exe (P1 integrity foundation)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json
from aa_variant_id import normalize_variant_label
from aa_version import MODEL_PROFILE

STATUS_FILE = "model_status.json"


def _resolve_next_development_step(out_dir: Path) -> str:
    root = _resolve_repo_root(out_dir)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml"):
        path = root / name
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            phase = str(data.get("current_phase", "") or "")
            for item in data.get("phases") or []:
                if str(item.get("id", "")) == phase:
                    nxt = item.get("next_phase")
                    return str(nxt) if nxt else "COMPLETE"
            return phase or "UNKNOWN"
        except Exception:
            pass
    return "P3_BACKGROUND_RESEARCH_EXISTING_MODELS"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_repo_root(out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    if (out_dir.parent / "DEVELOPMENT_PIPELINE.json").is_file():
        return out_dir.parent
    if (out_dir.parent.parent / "DEVELOPMENT_PIPELINE.json").is_file():
        return out_dir.parent.parent
    return out_dir.parent


def resolve_current_pipeline_phase(out_dir: Path) -> str:
    root = _resolve_repo_root(out_dir)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml"):
        path = root / name
        if not path.is_file():
            continue
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return str(data.get("current_phase", "") or "")
            except Exception:
                pass
    return ""


def resolve_failsafe_status(out_dir: Path) -> str:
    root = _resolve_repo_root(out_dir)
    try:
        from aa_failsafe import is_failsafe_active

        return "ACTIVE" if is_failsafe_active(root) else "INACTIVE"
    except Exception:
        return "INACTIVE"


def resolve_integrity_label(out_dir: Path) -> str:
    """Return PASS, FAIL, or NOT_VALIDATED for the active output directory."""
    out_dir = Path(out_dir)
    try:
        from aa_integrity import backfill_integrity_status_json

        backfill_integrity_status_json(out_dir)
    except Exception:
        pass
    for name in ("integrity_status.json", "integrity_report.json"):
        payload = _read_json(out_dir / name)
        if not payload:
            continue
        raw = str(payload.get("status", "") or "").upper()
        if raw in {"PASS"}:
            return "PASS"
        if raw in {"FAIL", "INVALID"}:
            return "FAIL"
    pointer = _read_json(out_dir / "latest_validated_run.json")
    if pointer:
        raw = str(pointer.get("integrity_status", pointer.get("status", "")) or "").upper()
        if raw == "PASS":
            return "PASS"
        if raw in {"FAIL", "INVALID"}:
            return "FAIL"
    return "NOT_VALIDATED"


def build_model_status(out_dir: Path, *, variant_id: str = "", root: Optional[Path] = None) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    integrity = resolve_integrity_label(out_dir)
    pointer = _read_json(out_dir / "latest_validated_run.json")
    variant = str(variant_id or pointer.get("variant_id") or "").strip()
    if not variant:
        variant = normalize_variant_label(MODEL_PROFILE)
    validated_at = str(pointer.get("published_at_utc", "") or "")
    if not validated_at:
        integrity_path = out_dir / "integrity_status.json"
        if integrity_path.is_file():
            validated_at = str(_read_json(integrity_path).get("checked_at_utc", "") or "")
    phase = resolve_current_pipeline_phase(out_dir)
    failsafe = resolve_failsafe_status(out_dir)
    next_step = _resolve_next_development_step(out_dir)
    ledger_counts: Dict[str, Any] = {}
    try:
        from aa_prediction_outcomes import ledger_status_counts

        ledger_counts = ledger_status_counts(out_dir)
    except Exception:
        ledger_counts = {}
    research: Dict[str, Any] = {}
    try:
        from aa_background_research import research_status_summary

        research = research_status_summary(out_dir)
    except Exception:
        research = {}
    shadow: Dict[str, Any] = {}
    try:
        from aa_shadow_champion import shadow_status_summary

        shadow = shadow_status_summary(out_dir)
    except Exception:
        shadow = {}
    replay: Dict[str, Any] = {}
    try:
        from aa_realtime_replay import replay_status_summary

        replay = replay_status_summary(out_dir)
    except Exception:
        replay = {}
    behavioral: Dict[str, Any] = {}
    try:
        from aa_behavioral_research import behavioral_status_summary

        behavioral = behavioral_status_summary(out_dir)
    except Exception:
        behavioral = {}
    auto_promo: Dict[str, Any] = {}
    try:
        from aa_auto_promotion import auto_promotion_status_summary, build_challenger_experiment_view

        root = _resolve_repo_root(out_dir)
        auto_promo = auto_promotion_status_summary(out_dir, root)
        challenger_experiments = build_challenger_experiment_view(root, out_dir)
    except Exception:
        auto_promo = {}
        challenger_experiments = []
    p9_prep: Dict[str, Any] = {}
    try:
        from aa_p9_shadow_paper_prep import p9_status_summary

        p9_prep = p9_status_summary(out_dir, _resolve_repo_root(out_dir))
    except Exception:
        p9_prep = {}
    r3_diagnosis: Dict[str, Any] = {}
    try:
        from aa_r3_daily_diagnosis import read_r3_diagnosis_manifest

        r3_diagnosis = read_r3_diagnosis_manifest(out_dir)
    except Exception:
        r3_diagnosis = {}
    adaptive_runtime: Dict[str, Any] = {}
    try:
        state_path = _resolve_repo_root(out_dir) / "control" / "adaptive_runtime_state.json"
        if state_path.is_file():
            adaptive_runtime = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        adaptive_runtime = {}
    auto_research = str(auto_promo.get("auto_research_status", "DISABLED"))
    auto_promotion = str(auto_promo.get("auto_promotion_status", "DISABLED"))
    payload = {
        "active_model_label": MODEL_PROFILE,
        "active_variant_label": variant,
        "integrity_status": integrity,
        "last_validated_at_utc": validated_at,
        "auto_research_status": auto_research,
        "auto_promotion_status": auto_promotion,
        "auto_execute_real_money_status": "DISABLED",
        "promotion_mode": str(auto_promo.get("promotion_mode", "MANUAL")),
        "active_signal_variant": str(auto_promo.get("active_signal_variant", "") or ""),
        "previous_champion_variant": str(auto_promo.get("previous_champion_variant", "") or ""),
        "promotion_state": str(auto_promo.get("promotion_state", "IDLE")),
        "challenger_experiments": challenger_experiments,
        "safety_status": {
            "operational_health": "OK" if failsafe == "INACTIVE" else "DEGRADED",
            "analytical_validity": integrity,
            "data_quality": str(replay.get("intraday_data_quality_status", "NOT_VALIDATED")),
            "signal_validity": integrity if integrity == "PASS" else "INVALID",
        },
        "realtime_behavioral_status": (
            "RESEARCH_ONLY"
            if str(behavioral.get("behavioral_research_status", "")).upper() == "PASS"
            else "NOT_IMPLEMENTED"
        ),
        "behavioral_research_status": str(behavioral.get("behavioral_research_status", "NOT_STARTED")),
        "behavioral_production_active": bool(behavioral.get("behavioral_production_active", False)),
        "behavioral_feature_groups": list(behavioral.get("behavioral_feature_groups") or []),
        "behavioral_challengers": list(behavioral.get("behavioral_challengers") or []),
        "behavioral_data_quality_status": str(
            behavioral.get("behavioral_data_quality_status", replay.get("intraday_data_quality_status", "NOT_VALIDATED"))
        ),
        "behavioral_updated_at_utc": str(behavioral.get("behavioral_updated_at_utc", "") or ""),
        "realtime_provider_status": str(replay.get("realtime_provider_status", "NOT_CONFIGURED")),
        "intraday_data_quality_status": str(replay.get("intraday_data_quality_status", "NOT_VALIDATED")),
        "last_intraday_processed_at_utc": str(replay.get("last_processed_at_utc", "") or ""),
        "last_bar_timestamp_utc": str(replay.get("last_bar_timestamp_utc", "") or ""),
        "current_pipeline_phase": phase or "P2_PREDICTION_OUTCOME_LEDGER",
        "failsafe_status": failsafe,
        "next_development_step": next_step,
        "stored_predictions": int(ledger_counts.get("stored_predictions", 0)),
        "mature_outcomes": int(ledger_counts.get("mature_outcomes", 0)),
        "pending_predictions": int(ledger_counts.get("pending_predictions", 0)),
        "last_feedback_update_utc": str(ledger_counts.get("last_feedback_update_utc", "") or ""),
        "background_research_status": str(research.get("background_research_status", "NOT_STARTED")),
        "background_research_variants_checked": int(research.get("background_research_variants_checked", 0)),
        "best_research_candidate_id": str(research.get("best_research_candidate_id", "") or ""),
        "last_comparison_run_dir": str(research.get("last_comparison_run_dir", "") or ""),
        "last_background_research_at_utc": str(research.get("background_research_updated_at_utc", "") or ""),
        "active_champion_variant": str(shadow.get("active_champion_variant", variant) or variant),
        "shadow_challenger_variant": str(shadow.get("shadow_challenger_variant", "") or ""),
        "shadow_signal_count": int(shadow.get("shadow_signal_count", 0) or 0),
        "mature_shadow_comparisons": int(shadow.get("mature_shadow_comparisons", 0) or 0),
        "promotion_status": str(shadow.get("promotion_status", "BLOCKED") or "BLOCKED"),
        "rollback_available": bool(auto_promo.get("rollback_available", shadow.get("rollback_available", False))),
        "p9_preparation_status": str(p9_prep.get("p9_preparation_status", "NOT_RUN")),
        "p9_preparation_ready": bool(p9_prep.get("p9_preparation_ready", False)),
        "r3_diagnosis_ok": bool(r3_diagnosis.get("ok", False)),
        "r3_regime_match": r3_diagnosis.get("regime_match"),
        "r3_live_regime": str((r3_diagnosis.get("live_regime") or {}).get("regime_label", "") or ""),
        "r3_refinement_hints": list(r3_diagnosis.get("refinement_hints") or []),
        "r3_diagnosis": r3_diagnosis,
        "adaptive_runtime": adaptive_runtime,
    }
    return payload


def write_model_status(out_dir: Path, *, variant_id: str = "") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_model_status(out_dir, variant_id=variant_id)
    return atomic_write_json(out_dir / STATUS_FILE, payload)


def read_model_status(out_dir: Path) -> Dict[str, Any]:
    path = Path(out_dir) / STATUS_FILE
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return build_model_status(out_dir)


def format_model_status_block(status: Optional[Dict[str, Any]] = None) -> str:
    s = status or {}
    integrity = str(s.get("integrity_status", "NOT_VALIDATED") or "NOT_VALIDATED").upper()
    variant = str(s.get("active_variant_label", "—") or "—")
    validated = str(s.get("last_validated_at_utc", "—") or "—")
    if validated and "T" in validated:
        validated = validated.replace("T", " ").replace("+00:00", " UTC")
    phase = str(s.get("current_pipeline_phase", "—") or "—")
    failsafe = str(s.get("failsafe_status", "INACTIVE") or "INACTIVE")
    lines = [
        "Modellstatus",
        f"  Aktive Variante: {variant}",
        f"  Validierung: {integrity}",
        f"  Letzter validierter Lauf: {validated}",
        f"  Pipeline-Phase: {phase}",
        f"  Fail-Safe: {failsafe}",
        "  Automatische Verbesserung: deaktiviert",
        f"  Nächster Schritt: {s.get('next_development_step', '—')}",
    ]
    stored = int(s.get("stored_predictions", 0) or 0)
    if stored > 0 or s.get("last_feedback_update_utc"):
        mature = int(s.get("mature_outcomes", 0) or 0)
        pending_n = int(s.get("pending_predictions", 0) or 0)
        fb = str(s.get("last_feedback_update_utc", "") or "—")
        if fb and "T" in fb:
            fb = fb.replace("T", " ").replace("+00:00", " UTC")
        lines.extend(
            [
                f"  Gespeicherte Prognosen: {stored}",
                f"  Reife ausgewertete Prognosen: {mature}",
                f"  Noch nicht reife Prognosen: {pending_n}",
                f"  Letztes Feedback-Update: {fb}",
            ]
        )
    br_status = str(s.get("background_research_status", "") or "")
    if br_status and br_status != "NOT_STARTED":
        br_at = str(s.get("last_background_research_at_utc", "—") or "—")
        if br_at and "T" in br_at:
            br_at = br_at.replace("T", " ").replace("+00:00", " UTC")
        checked = int(s.get("background_research_variants_checked", 0) or 0)
        best = str(s.get("best_research_candidate_id", "") or "—")
        lines.extend(
            [
                f"  Hintergrund-Research: {br_status}",
                f"  Geprüfte Varianten: {checked}",
                f"  Bester Kandidat (nicht aktiv): {best or '—'}",
                f"  Letzter Research-Lauf: {br_at}",
            ]
        )
    if int(s.get("shadow_signal_count", 0) or 0) > 0 or s.get("shadow_challenger_variant"):
        lines.extend(
            [
                f"  Shadow-Challenger: {s.get('shadow_challenger_variant', '—')}",
                f"  Shadow-Prognosen: {int(s.get('shadow_signal_count', 0) or 0)}",
                f"  Reife Shadow-Vergleiche: {int(s.get('mature_shadow_comparisons', 0) or 0)}",
                f"  Promotion: {s.get('promotion_status', 'BLOCKED')}",
                f"  Rollback verfügbar: {'ja' if s.get('rollback_available') else 'nein'}",
            ]
        )
    rq = str(s.get("intraday_data_quality_status", "") or "")
    rp = str(s.get("realtime_provider_status", "") or "")
    if rq not in {"", "NOT_VALIDATED"} or rp not in {"", "NOT_CONFIGURED"}:
        lp = str(s.get("last_intraday_processed_at_utc", "—") or "—")
        lb = str(s.get("last_bar_timestamp_utc", "—") or "—")
        if lp and "T" in lp:
            lp = lp.replace("T", " ").replace("+00:00", " UTC")
        if lb and "T" in lb:
            lb = lb.replace("T", " ").replace("+00:00", " UTC")
        lines.extend(
            [
                f"  Realtime/Replay: {rp or '—'}",
                f"  Intraday Data Quality: {rq or '—'}",
                f"  Letzter Bar-Zeitpunkt: {lb}",
                f"  Letzte Verarbeitung: {lp}",
            ]
        )
    br = str(s.get("behavioral_research_status", "") or "")
    if br not in {"", "NOT_STARTED"}:
        groups = ", ".join(s.get("behavioral_feature_groups") or []) or "—"
        chall = ", ".join(s.get("behavioral_challengers") or []) or "—"
        prod = "ja" if s.get("behavioral_production_active") else "nein"
        bq = str(s.get("behavioral_data_quality_status", "—") or "—")
        lines.extend(
            [
                f"  Behavioral Research: {br}",
                f"  Featuregruppen: {groups}",
                f"  Behavioral Challenger: {chall}",
                f"  Behavioral Data Quality: {bq}",
                f"  Produktiv aktiv: {prod}",
            ]
        )
    if integrity != "PASS":
        lines.append("  Analyse nicht validiert – Performancewerte nicht freigegeben.")
    if failsafe == "ACTIVE":
        lines.append("  Fail-Safe aktiv – keine Signalveröffentlichung.")
    try:
        from aa_auto_promotion import format_ai_development_block

        ai_block = format_ai_development_block(s)
        if ai_block:
            lines.extend(["", ai_block])
    except Exception:
        pass
    try:
        from aa_r3_daily_diagnosis import format_r3_diagnosis_block

        r3_block = format_r3_diagnosis_block(s.get("r3_diagnosis") or {})
        if r3_block:
            lines.extend(["", r3_block])
    except Exception:
        pass
    try:
        from aa_adaptive_runtime import format_adaptive_status_block

        ar = s.get("adaptive_runtime") or {}
        if ar:
            ctx = ar.get("context") or {}
            lines.extend(
                [
                    "",
                    "Adaptive Runtime",
                    f"  Modus: {ar.get('mode', '—')}",
                    f"  Preisquelle: {ar.get('price_source', '—')}",
                    f"  Internet: {'OK' if ctx.get('internet_ok') else 'offline'}",
                    f"  R3-Match: {ctx.get('r3_regime_match')}",
                ]
            )
            for note in (ar.get("notes") or [])[:3]:
                lines.append(f"  -> {note}")
    except Exception:
        pass
    return "\n".join(lines)
