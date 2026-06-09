"""P7 auto-promotion infrastructure — gated paper/signal promotion, rollback, EXE visibility."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from aa_challenger_eval import resolve_champion_variant
from aa_recovery import load_last_known_good, restore_last_known_good
from aa_safe_io import atomic_write_json

CONFIG_FILE = "promotion_gate_config.yaml"
STATUS_FILE = "auto_promotion_status.json"
SIGNAL_POINTER = "latest_validated_signal.json"
PROMOTION_HISTORY = "promotion_history.jsonl"
ACTIVE_STATE_FILE = "active_promotion_state.json"

CHALLENGER_STATUSES = (
    "QUEUED",
    "RUNNING",
    "VALIDATING",
    "SHADOW_TESTING",
    "PROMOTION_CANDIDATE",
    "AUTO_PROMOTED",
    "REJECTED",
    "ROLLED_BACK",
    "FAILED",
)

REQUIRED_PROMOTION_GATE_IDS = (
    "CONFIG_PRESENT",
    "INTEGRITY_GATE",
    "DATA_QUALITY_GATE",
    "FORECAST_QUALITY_GATE",
    "M1_COMPARISON_GATE",
    "CHAMPION_COMPARISON_GATE",
    "ECONOMIC_VALUE_GATE",
    "RISK_GATE",
    "COST_STRESS_GATE",
    "SHADOW_GATE",
    "ROLLBACK_READINESS_GATE",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def config_path(root: Path) -> Path:
    return Path(root) / CONFIG_FILE


def status_path(root: Path) -> Path:
    return Path(root) / "control" / STATUS_FILE


def out_status_path(out_dir: Path) -> Path:
    return Path(out_dir) / STATUS_FILE


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_promotion_gate_config(root: Path) -> Dict[str, Any]:
    path = config_path(root)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        data["auto_execute_real_money_enabled"] = False
        return data
    except Exception:
        return {}


def automation_modes(config: Dict[str, Any]) -> Dict[str, str]:
    """Return ENABLED/DISABLED labels for automation modes."""
    return {
        "AUTO_RESEARCH": "ENABLED" if config.get("auto_research_enabled") else "DISABLED",
        "AUTO_PROMOTE_PAPER": "ENABLED" if config.get("auto_promote_paper_enabled") else "DISABLED",
        "AUTO_PROMOTE_SIGNAL": "ENABLED" if config.get("auto_promote_signal_enabled") else "DISABLED",
        "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
    }


def _research_entry(out_dir: Path, variant_id: str) -> Dict[str, Any]:
    research = _read_json(out_dir / "background_research_status.json")
    for entry in research.get("entries") or []:
        if str(entry.get("variant_id")) == variant_id:
            return dict(entry)
    return {}


def _m1_available(out_dir: Path) -> bool:
    return bool(_research_entry(out_dir, "M1_MOM_BLEND_MATCHED_CONTROLS"))


def _evaluate_data_quality_gate(out_dir: Path, root: Path) -> Dict[str, Any]:
    """Fail-closed: missing or negative data-quality evidence never passes."""
    candidates: Tuple[Tuple[Path, str], ...] = (
        (out_dir / "intraday_data_quality.json", "status"),
        (root / "market_data" / "quality" / "intraday_data_quality.json", "status"),
        (out_dir / "realtime_replay_status.json", "data_quality_status"),
    )
    for path, key in candidates:
        data = _read_json(path)
        if not data:
            continue
        raw = str(data.get(key, "") or "").upper()
        if raw == "PASS":
            return {
                "pass": True,
                "detail": f"verified PASS evidence: {path.name}",
                "evidence_state": "pass",
            }
        return {
            "pass": False,
            "detail": f"negative evidence: {path.name} {key}={raw or 'EMPTY'}",
            "evidence_state": "fail",
        }
    return {
        "pass": False,
        "detail": "no acceptable data-quality artifact",
        "evidence_state": "missing",
    }


def evaluate_auto_promotion_gates(
    root: Path,
    out_dir: Path,
    *,
    challenger: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate all promotion gates for a challenger (default: shadow challenger)."""
    root = Path(root)
    out_dir = Path(out_dir)
    config = config if config is not None else load_promotion_gate_config(root)
    from aa_shadow_champion import evaluate_promotion_gates, load_shadow_outcomes, load_shadow_signals

    shadow_gates = evaluate_promotion_gates(root, out_dir)
    champion_variant = resolve_champion_variant(out_dir)
    challenger = challenger or {}
    if not challenger:
        reg = _read_json(out_dir / "challenger_registry.json") or _read_json(root / "challenger_registry.json")
        cid = str(reg.get("shadow_challenger_id", "") or "")
        if cid:
            challenger = _research_entry(out_dir, cid)
            challenger.setdefault("variant_id", cid)

    ch_integrity = bool(challenger.get("integrity_pass", False))
    ch_variant = str(challenger.get("variant_id", "") or "")
    ch_metrics = dict(challenger.get("metrics") or {})
    champion_entry = _research_entry(out_dir, champion_variant)
    m1_entry = _research_entry(out_dir, "M1_MOM_BLEND_MATCHED_CONTROLS")
    shadow_n = int(len(load_shadow_signals(out_dir)))
    mature_shadow = int(len(load_shadow_outcomes(out_dir)))
    min_shadow = int(config.get("minimum_mature_shadow_outcomes", 100) or 100)

    ch_sharpe = float(ch_metrics.get("sharpe_0rf", float("nan")))
    champ_sharpe = float((champion_entry.get("metrics") or {}).get("sharpe_0rf", float("nan")))
    m1_sharpe = float((m1_entry.get("metrics") or {}).get("sharpe_0rf", float("nan")))
    max_dd = float(ch_metrics.get("max_drawdown", float("nan")))
    dd_tol = float(config.get("drawdown_tolerance", 0.35) or 0.35)

    dq_gate = _evaluate_data_quality_gate(out_dir, root)
    gates = {
        "CONFIG_PRESENT": {"pass": bool(config.get("schema_version")), "detail": CONFIG_FILE},
        "INTEGRITY_GATE": {"pass": ch_integrity, "detail": ch_variant or "no challenger"},
        "DATA_QUALITY_GATE": {
            "pass": dq_gate["pass"] is True,
            "detail": dq_gate["detail"],
            "evidence_state": dq_gate["evidence_state"],
        },
        "FORECAST_QUALITY_GATE": {"pass": shadow_gates.get("gates", {}).get("FORECAST_QUALITY_GATE", {}).get("pass") is True, "detail": "mature outcomes"},
        "M1_COMPARISON_GATE": {"pass": bool(m1_entry), "detail": "M1_MOM_BLEND_MATCHED_CONTROLS"},
        "CHAMPION_COMPARISON_GATE": {
            "pass": bool(champion_entry) and ch_sharpe == ch_sharpe and champ_sharpe == champ_sharpe,
            "detail": f"challenger_sharpe={ch_sharpe} champion_sharpe={champ_sharpe}",
        },
        "ECONOMIC_VALUE_GATE": {
            "pass": ch_sharpe > m1_sharpe if ch_sharpe == ch_sharpe and m1_sharpe == m1_sharpe else False,
            "detail": "beats M1 sharpe",
        },
        "RISK_GATE": {"pass": max_dd == max_dd and abs(max_dd) <= dd_tol if max_dd == max_dd else False, "detail": f"max_dd={max_dd}"},
        "COST_STRESS_GATE": {"pass": None, "detail": "not evaluated in P7 v1"},
        "SHADOW_GATE": {"pass": mature_shadow >= min_shadow, "detail": f"mature_shadow={mature_shadow} min={min_shadow}"},
        "ROLLBACK_READINESS_GATE": shadow_gates.get("gates", {}).get("ROLLBACK_READINESS_GATE", {"pass": False}),
        "AUTO_PROMOTE_ENABLED": {
            "pass": bool(config.get("auto_promote_paper_enabled") or config.get("auto_promote_signal_enabled")),
            "detail": "promotion flags in config",
        },
    }
    blocked: List[str] = []
    if not config:
        blocked.append("promotion_gate_config_missing")
    if not config.get("auto_promote_paper_enabled") and not config.get("auto_promote_signal_enabled"):
        blocked.append("auto_promotion_disabled")
    if not ch_integrity:
        blocked.append("challenger_integrity_fail")
    dq_state = str(gates["DATA_QUALITY_GATE"].get("evidence_state", "") or "")
    if dq_state == "missing":
        blocked.append("data_quality_evidence_missing")
    elif gates["DATA_QUALITY_GATE"].get("pass") is not True:
        blocked.append("data_quality_fail")
    if not gates["M1_COMPARISON_GATE"]["pass"]:
        blocked.append("m1_comparison_missing")
    if not gates["SHADOW_GATE"]["pass"]:
        blocked.append("shadow_gate_not_passed")
    if gates["ROLLBACK_READINESS_GATE"].get("pass") is not True:
        blocked.append("rollback_not_ready")
    if gates["COST_STRESS_GATE"].get("pass") is not True:
        blocked.append("cost_stress_not_passed")
    if gates["ECONOMIC_VALUE_GATE"].get("pass") is not True:
        blocked.append("economic_value_not_passed")
    if gates["RISK_GATE"].get("pass") is not True:
        blocked.append("risk_gate_not_passed")

    required_pass = all(gates[g].get("pass") is True for g in REQUIRED_PROMOTION_GATE_IDS)
    promotion_flag_on = bool(config.get("auto_promote_paper_enabled") or config.get("auto_promote_signal_enabled"))
    promotion_allowed = required_pass and promotion_flag_on
    return {
        "updated_at_utc": _utc_now(),
        "challenger_variant_id": ch_variant,
        "champion_variant_id": champion_variant,
        "gates": gates,
        "all_required_gates_pass": required_pass,
        "promotion_allowed": promotion_allowed,
        "blocked_reasons": blocked,
        "shadow_signal_count": shadow_n,
        "mature_shadow_comparisons": mature_shadow,
        "auto_execute_real_money": False,
    }


def _append_promotion_event(root: Path, event: Dict[str, Any]) -> None:
    ctrl = Path(root) / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"at_utc": _utc_now(), **event}, ensure_ascii=False, sort_keys=True)
    with (ctrl / PROMOTION_HISTORY).open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def attempt_auto_promotion(
    root: Path,
    out_dir: Path,
    *,
    mode: str = "paper",
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Promote challenger to paper/signal pointer only after gates pass. Never touches champion model pointer."""
    root = Path(root)
    out_dir = Path(out_dir)
    config = config if config is not None else load_promotion_gate_config(root)
    champion_before = resolve_champion_variant(out_dir)
    pointer_before = _read_json(out_dir / "latest_validated_run.json")
    mode = str(mode).lower().strip()
    if mode not in {"paper", "signal"}:
        gate_eval = evaluate_auto_promotion_gates(root, out_dir, config=config)
        return {"status": "BLOCKED", "reason": "invalid_promotion_mode", "gate_eval": gate_eval}

    gate_eval = evaluate_auto_promotion_gates(root, out_dir, config=config)

    if mode == "paper" and not config.get("auto_promote_paper_enabled"):
        return {"status": "BLOCKED", "reason": "auto_promote_paper_disabled", "gate_eval": gate_eval}
    if mode == "signal" and not config.get("auto_promote_signal_enabled"):
        return {"status": "BLOCKED", "reason": "auto_promote_signal_disabled", "gate_eval": gate_eval}
    if not gate_eval.get("promotion_allowed"):
        return {"status": "BLOCKED", "reason": "gates_not_passed", "gate_eval": gate_eval}

    challenger_id = str(gate_eval.get("challenger_variant_id", "") or "")
    entry = _research_entry(out_dir, challenger_id)
    signal_payload = {
        "updated_at_utc": _utc_now(),
        "promotion_mode": mode.upper(),
        "variant_id": challenger_id,
        "run_dir": str(entry.get("run_dir", "") or ""),
        "integrity_status": "PASS" if entry.get("integrity_pass") else "FAIL",
        "promoted_from_champion": champion_before,
        "auto_promoted": True,
        "metrics_status": "SHADOW_FORWARD",
    }
    atomic_write_json(out_dir / SIGNAL_POINTER, signal_payload)
    state = {
        "updated_at_utc": _utc_now(),
        "active_signal_variant": challenger_id,
        "previous_champion_variant": champion_before,
        "promotion_mode": mode.upper(),
        "status": "AUTO_PROMOTED",
        "rollback_available": True,
    }
    atomic_write_json(out_dir / ACTIVE_STATE_FILE, state)
    atomic_write_json(root / "control" / ACTIVE_STATE_FILE, state)
    _append_promotion_event(
        root,
        {"event": "auto_promote", "mode": mode, "challenger": challenger_id, "champion": champion_before},
    )

    champion_after = resolve_champion_variant(out_dir)
    pointer_after = _read_json(out_dir / "latest_validated_run.json")
    return {
        "status": "OK",
        "mode": mode,
        "challenger_variant_id": challenger_id,
        "champion_unchanged": champion_before == champion_after and pointer_before == pointer_after,
        "gate_eval": gate_eval,
    }


def execute_auto_rollback(root: Path, out_dir: Path, *, reason: str = "manual") -> Dict[str, Any]:
    """Restore LKG champion/signal pointers without mutating historical shadow signals."""
    root = Path(root)
    out_dir = Path(out_dir)
    shadow_before = 0
    try:
        from aa_shadow_champion import load_shadow_signals

        shadow_before = int(len(load_shadow_signals(out_dir)))
    except Exception:
        pass

    champion_before = resolve_champion_variant(out_dir)
    state = _read_json(out_dir / ACTIVE_STATE_FILE)
    rolled_back_variant = str(state.get("active_signal_variant", "") or "")

    ok, msg = restore_last_known_good(root, out_dir)
    lkg = load_last_known_good(root / "control")
    signal_payload = {
        "updated_at_utc": _utc_now(),
        "variant_id": str(lkg.get("validated_variant_id", champion_before) or champion_before),
        "run_id": str(lkg.get("validated_run_id", "") or ""),
        "integrity_status": str(lkg.get("integrity_status", "PASS") or "PASS"),
        "promotion_mode": "ROLLBACK",
        "rolled_back_from": rolled_back_variant,
        "metrics_status": "VALIDATED_BACKTEST",
    }
    atomic_write_json(out_dir / SIGNAL_POINTER, signal_payload)
    new_state = {
        "updated_at_utc": _utc_now(),
        "active_signal_variant": signal_payload["variant_id"],
        "previous_challenger_variant": rolled_back_variant,
        "status": "ROLLED_BACK",
        "rollback_reason": reason,
        "rollback_available": bool(lkg.get("validated_run_id")),
    }
    atomic_write_json(out_dir / ACTIVE_STATE_FILE, new_state)
    atomic_write_json(root / "control" / ACTIVE_STATE_FILE, new_state)
    _append_promotion_event(
        root,
        {
            "event": "rollback",
            "reason": reason,
            "rolled_back_variant": rolled_back_variant,
            "restored_variant": signal_payload["variant_id"],
            "restore_msg": msg,
        },
    )

    shadow_after = shadow_before
    try:
        from aa_shadow_champion import load_shadow_signals

        shadow_after = int(len(load_shadow_signals(out_dir)))
    except Exception:
        pass

    return {
        "status": "OK" if ok else "PARTIAL",
        "restore_message": msg,
        "shadow_signals_unchanged": shadow_before == shadow_after,
        "champion_variant": resolve_champion_variant(out_dir),
    }


def build_challenger_experiment_view(root: Path, out_dir: Path) -> List[Dict[str, Any]]:
    root = Path(root)
    out_dir = Path(out_dir)
    reg = _read_json(out_dir / "challenger_registry.json") or _read_json(root / "challenger_registry.json")
    state = _read_json(out_dir / ACTIVE_STATE_FILE)
    active_signal = str(_read_json(out_dir / SIGNAL_POINTER).get("variant_id", "") or "")
    experiments: List[Dict[str, Any]] = []
    for entry in reg.get("challengers") or []:
        vid = str(entry.get("id", "") or "")
        if not vid:
            continue
        status = str(entry.get("status", "QUEUED")).upper()
        if vid == active_signal and state.get("status") == "AUTO_PROMOTED":
            status = "AUTO_PROMOTED"
        elif state.get("status") == "ROLLED_BACK" and vid == state.get("previous_challenger_variant"):
            status = "ROLLED_BACK"
        elif entry.get("role") == "shadow" and entry.get("enabled"):
            status = "SHADOW_TESTING"
        elif entry.get("role") == "behavioral_research":
            status = "VALIDATING" if entry.get("status") == "research_ready" else "QUEUED"
        experiments.append(
            {
                "variant_id": vid,
                "status": status if status in CHALLENGER_STATUSES else "QUEUED",
                "enabled": bool(entry.get("enabled")),
                "last_gate_result": "BLOCKED" if status not in {"AUTO_PROMOTED"} else "PASS",
                "rejection_reason": "" if status != "REJECTED" else "gates_not_passed",
            }
        )
    return experiments


def format_ai_development_block(status: Dict[str, Any]) -> str:
    lines = [
        "AI-Entwicklung",
        f"  Aktiver Champion: {status.get('active_variant_label', '—')}",
        f"  Validierung: {status.get('integrity_status', '—')}",
        f"  Promotionmodus: {status.get('promotion_mode', 'MANUAL')}",
        f"  Vorheriger Champion: {status.get('previous_champion_variant', '—')}",
        f"  Rollback verfügbar: {'ja' if status.get('rollback_available') else 'nein'}",
        f"  Pipeline-Phase: {status.get('current_pipeline_phase', '—')}",
        f"  Auto-Research: {status.get('auto_research_status', 'DISABLED')}",
        f"  Auto-Promotion: {status.get('auto_promotion_status', 'DISABLED')}",
        f"  Realtime/Behavioral: {status.get('realtime_behavioral_status', '—')}",
        f"  Fail-Safe: {status.get('failsafe_status', 'INACTIVE')}",
        f"  Echtgeld-Ausführung: DISABLED",
    ]
    experiments = status.get("challenger_experiments") or []
    if experiments:
        lines.append("  Challenger/Experimente:")
        for exp in experiments[:8]:
            lines.append(f"    {exp.get('variant_id')}: {exp.get('status')}")
    safety = status.get("safety_status") or {}
    if safety:
        lines.extend(
            [
                f"  Operational Health: {safety.get('operational_health', '—')}",
                f"  Analytical Validity: {safety.get('analytical_validity', '—')}",
                f"  Data Quality: {safety.get('data_quality', '—')}",
                f"  Signal Validity: {safety.get('signal_validity', '—')}",
            ]
        )
    return "\n".join(lines)


def auto_promotion_status_summary(out_dir: Path, root: Optional[Path] = None) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    root = root or out_dir.parent
    config = load_promotion_gate_config(root)
    modes = automation_modes(config)
    state = _read_json(out_dir / ACTIVE_STATE_FILE)
    signal = _read_json(out_dir / SIGNAL_POINTER)
    for candidate in (out_status_path(out_dir), status_path(root)):
        data = _read_json(candidate)
        if data:
            return {
                "auto_research_status": modes["AUTO_RESEARCH"],
                "auto_promotion_status": (
                    "ENABLED" if modes["AUTO_PROMOTE_PAPER"] == "ENABLED" or modes["AUTO_PROMOTE_SIGNAL"] == "ENABLED" else "DISABLED"
                ),
                "auto_execute_real_money_status": "DISABLED",
                "promotion_mode": str(config.get("promotion_mode", "MANUAL")),
                "active_signal_variant": str(signal.get("variant_id", "") or state.get("active_signal_variant", "")),
                "previous_champion_variant": str(state.get("previous_champion_variant", signal.get("promoted_from_champion", "")) or ""),
                "promotion_state": str(state.get("status", "IDLE")),
                "rollback_available": bool(state.get("rollback_available") or load_last_known_good(root / "control")),
                "auto_promotion_updated_at_utc": str(data.get("updated_at_utc", "") or ""),
            }
    return {
        "auto_research_status": modes["AUTO_RESEARCH"],
        "auto_promotion_status": "DISABLED",
        "auto_execute_real_money_status": "DISABLED",
        "promotion_mode": str(config.get("promotion_mode", "MANUAL")),
        "active_signal_variant": str(signal.get("variant_id", "") or ""),
        "previous_champion_variant": "",
        "promotion_state": "IDLE",
        "rollback_available": bool(load_last_known_good(root / "control")),
        "auto_promotion_updated_at_utc": "",
    }


def run_auto_promotion_sync(root: Path, out_dir: Path) -> Dict[str, Any]:
    """P7 sync: evaluate gates, write status, keep champion unless explicit gated promotion."""
    root = Path(root)
    out_dir = Path(out_dir)
    config = load_promotion_gate_config(root)
    if not config:
        return {"status": "FAIL", "reason": "promotion_gate_config_missing"}

    champion_before = resolve_champion_variant(out_dir)
    gate_eval = evaluate_auto_promotion_gates(root, out_dir, config=config)
    modes = automation_modes(config)
    experiments = build_challenger_experiment_view(root, out_dir)

    status = {
        "updated_at_utc": _utc_now(),
        "schema_version": int(config.get("schema_version", 1) or 1),
        "automation_modes": modes,
        "auto_execute_real_money_enabled": False,
        "promotion_mode": str(config.get("promotion_mode", "MANUAL")),
        "gate_evaluation": gate_eval,
        "promotion_allowed": gate_eval.get("promotion_allowed"),
        "challenger_experiments": experiments,
        "champion_variant_id": champion_before,
        "champion_unchanged": True,
        "config_path": str(config_path(root)),
    }

    promo_result: Dict[str, Any] = {"status": "SKIPPED"}
    if config.get("auto_promote_paper_enabled"):
        promo_result = attempt_auto_promotion(root, out_dir, mode="paper", config=config)
    elif config.get("auto_promote_signal_enabled"):
        promo_result = attempt_auto_promotion(root, out_dir, mode="signal", config=config)

    status["last_promotion_attempt"] = promo_result
    champion_after = resolve_champion_variant(out_dir)
    status["champion_unchanged"] = champion_before == champion_after

    atomic_write_json(out_status_path(out_dir), status)
    atomic_write_json(status_path(root), status)

    from aa_shadow_champion import evaluate_promotion_gates as shadow_promo

    promo = shadow_promo(root, out_dir)
    promo["auto_promotion_enabled"] = modes["AUTO_PROMOTE_PAPER"] == "ENABLED" or modes["AUTO_PROMOTE_SIGNAL"] == "ENABLED"
    promo["auto_execute_real_money"] = False
    promo["automation_modes"] = modes
    promo["updated_at_utc"] = _utc_now()
    atomic_write_json(out_dir / "promotion_status.json", promo)
    atomic_write_json(root / "control" / "promotion_status.json", promo)

    reg_path = root / "challenger_registry.json"
    reg = _read_json(reg_path)
    if reg:
        reg["auto_promotion"] = status["automation_modes"]["AUTO_PROMOTE_PAPER"]
        if reg["auto_promotion"] == "DISABLED" and modes["AUTO_PROMOTE_SIGNAL"] == "ENABLED":
            reg["auto_promotion"] = "SIGNAL_ONLY"
        atomic_write_json(reg_path, reg)
        atomic_write_json(out_dir / "challenger_registry.json", reg)

    return {
        "status": "OK",
        "auto_research_status": modes["AUTO_RESEARCH"],
        "auto_promotion_status": status["automation_modes"]["AUTO_PROMOTE_PAPER"],
        "auto_execute_real_money": "DISABLED",
        "promotion_allowed": gate_eval.get("promotion_allowed"),
        "champion_unchanged": status["champion_unchanged"],
        "gate_blocked_reasons": gate_eval.get("blocked_reasons"),
    }
