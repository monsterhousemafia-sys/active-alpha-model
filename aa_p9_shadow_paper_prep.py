"""P9 controlled shadow/paper validation preparation — read-only gate, no promotion."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_auto_promotion import evaluate_auto_promotion_gates, load_promotion_gate_config
from aa_challenger_eval import resolve_champion_variant
from aa_recovery import load_last_known_good
from aa_safe_io import atomic_write_json

STATUS_FILE = "p9_shadow_paper_prep_status.json"
M1_CONTROL_VARIANT = "M1_MOM_BLEND_MATCHED_CONTROLS"
PAPER_ENGINE = "paper_trading_engine.py"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _research_entry(out_dir: Path, variant_id: str) -> Dict[str, Any]:
    research = _read_json(out_dir / "background_research_status.json")
    for entry in research.get("entries") or []:
        if str(entry.get("variant_id", "")) == variant_id:
            return dict(entry)
    return {}


def evaluate_p9_preparation_gates(root: Path, out_dir: Path) -> Dict[str, Any]:
    """Evaluate P9 preparation gates without running shadow/paper jobs or promotion."""
    root = Path(root)
    out_dir = Path(out_dir)
    config = load_promotion_gate_config(root)
    lkg = load_last_known_good(root / "control")
    champion = resolve_champion_variant(out_dir)
    pointer = _read_json(out_dir / "latest_validated_run.json")
    reg = _read_json(out_dir / "challenger_registry.json") or _read_json(root / "challenger_registry.json")
    shadow_id = str(reg.get("shadow_challenger_id", "") or "")
    m1_entry = _research_entry(out_dir, M1_CONTROL_VARIANT)
    promo_eval = evaluate_auto_promotion_gates(root, out_dir, config=config)
    signal = _read_json(out_dir / "latest_validated_signal.json")

    try:
        from aa_shadow_champion import load_shadow_outcomes, load_shadow_signals

        shadow_n = int(len(load_shadow_signals(out_dir)))
        mature_n = int(len(load_shadow_outcomes(out_dir)))
    except Exception:
        shadow_n = 0
        mature_n = 0

    min_shadow = int(config.get("minimum_mature_shadow_outcomes", 100) or 100)
    lkg_variant = str(lkg.get("validated_variant_id", "") or "")
    champion_matches_lkg = bool(lkg_variant) and champion == lkg_variant
    champion_matches_pointer = str(pointer.get("variant_id", "") or "") == champion
    integrity_ok = str(pointer.get("integrity_status", pointer.get("status", ""))).upper() == "PASS"

    paper_dir = ""
    try:
        from aa_config_env import parse_aa_env_files

        paper_dir = str(parse_aa_env_files(root).get("AA_PAPER_DIR", "") or "").strip()
    except Exception:
        pass

    gates: Dict[str, Dict[str, Any]] = {
        "CHAMPION_REFERENCE_GATE": {
            "pass": champion_matches_lkg and champion_matches_pointer and integrity_ok,
            "detail": f"champion={champion} lkg={lkg_variant} integrity={integrity_ok}",
        },
        "M1_CONTROL_GATE": {
            "pass": bool(m1_entry),
            "detail": M1_CONTROL_VARIANT if m1_entry else "missing",
        },
        "SHADOW_CHALLENGER_GATE": {
            "pass": bool(shadow_id) and shadow_n > 0 and mature_n >= min_shadow,
            "detail": f"shadow_challenger={shadow_id} signals={shadow_n} mature={mature_n} min={min_shadow}",
        },
        "PROMOTION_BLOCKED_GATE": {
            "pass": promo_eval.get("promotion_allowed") is False
            and not config.get("auto_promote_paper_enabled")
            and not config.get("auto_promote_signal_enabled"),
            "detail": f"promotion_allowed={promo_eval.get('promotion_allowed')}",
        },
        "REAL_MONEY_DISABLED_GATE": {
            "pass": config.get("auto_execute_real_money_enabled") is False,
            "detail": "AUTO_EXECUTE_REAL_MONEY=DISABLED",
        },
        "PAPER_SCAFFOLD_GATE": {
            "pass": (root / PAPER_ENGINE).is_file(),
            "detail": PAPER_ENGINE if (root / PAPER_ENGINE).is_file() else "missing",
        },
        "NO_SIGNAL_PROMOTION_GATE": {
            "pass": not signal or str(signal.get("variant_id", "") or "") == champion,
            "detail": "no promoted signal pointer" if not signal else f"signal={signal.get('variant_id')}",
        },
    }

    blocked: List[str] = []
    for gate_id, gate in gates.items():
        if gate.get("pass") is not True:
            blocked.append(gate_id.lower())

    all_pass = not blocked
    return {
        "updated_at_utc": _utc_now(),
        "phase_id": "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION",
        "champion_variant_id": champion,
        "shadow_challenger_id": shadow_id,
        "m1_control_variant": M1_CONTROL_VARIANT,
        "gates": gates,
        "all_gates_pass": all_pass,
        "preparation_ready": all_pass,
        "blocked_reasons": blocked,
        "promotion_allowed": False,
        "auto_execute_real_money": False,
        "paper_dir_configured": bool(paper_dir),
        "paper_dir": paper_dir or None,
        "shadow_signal_count": shadow_n,
        "mature_shadow_comparisons": mature_n,
        "note": "Preparation gate only — no shadow/paper execution or promotion in P9.",
    }


def run_p9_shadow_paper_prep_sync(root: Path, out_dir: Path) -> Dict[str, Any]:
    """Write P9 preparation status; never mutates champion, signals, or promotion pointers."""
    root = Path(root)
    out_dir = Path(out_dir)
    champion_before = resolve_champion_variant(out_dir)
    pointer_before = _read_json(out_dir / "latest_validated_run.json")
    gate_eval = evaluate_p9_preparation_gates(root, out_dir)

    status = {
        "schema_version": 1,
        "sync_status": "OK" if gate_eval.get("all_gates_pass") else "BLOCKED",
        **gate_eval,
    }
    atomic_write_json(out_dir / STATUS_FILE, status)
    atomic_write_json(root / "control" / STATUS_FILE, status)

    champion_after = resolve_champion_variant(out_dir)
    pointer_after = _read_json(out_dir / "latest_validated_run.json")
    return {
        "status": status["sync_status"],
        "preparation_ready": gate_eval.get("preparation_ready"),
        "champion_unchanged": champion_before == champion_after and pointer_before == pointer_after,
        "blocked_reasons": gate_eval.get("blocked_reasons"),
        "gate_evaluation": gate_eval,
    }


def p9_status_summary(out_dir: Path, root: Optional[Path] = None) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    root = root or out_dir.parent
    for candidate in (out_dir / STATUS_FILE, root / "control" / STATUS_FILE):
        data = _read_json(candidate)
        if data:
            return {
                "p9_preparation_status": str(data.get("sync_status", "UNKNOWN")),
                "p9_preparation_ready": bool(data.get("preparation_ready")),
                "p9_champion_variant_id": str(data.get("champion_variant_id", "") or ""),
                "p9_updated_at_utc": str(data.get("updated_at_utc", "") or ""),
            }
    return {
        "p9_preparation_status": "NOT_RUN",
        "p9_preparation_ready": False,
        "p9_champion_variant_id": "",
        "p9_updated_at_utc": "",
    }
