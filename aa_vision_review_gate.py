"""External review approval validation — templates never authorize execution."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from aa_vision_phase_catalog import get_phase, is_transition_allowed

TEMPLATE_PREFIX = "TEMPLATE_"
APPROVAL_PATTERN = re.compile(r"EXTERNAL_REVIEW_APPROVAL_(?P<key>[A-Z0-9]+)\.md$", re.I)
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
from aa_evidence_schema import LOCKED_CHAMPION


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_template_path(path: Path) -> bool:
    return path.name.startswith(TEMPLATE_PREFIX)


def parse_predecessor_zip_hash(approval_text: str) -> Optional[str]:
    for line in approval_text.splitlines():
        lower = line.lower()
        if "sha-256" in lower or "sha256" in lower:
            match = SHA256_PATTERN.search(line)
            if match:
                return match.group(0).lower()
    match = SHA256_PATTERN.search(approval_text)
    return match.group(0).lower() if match else None


def parse_sidecar_hash(sidecar_text: str) -> Optional[str]:
    match = SHA256_PATTERN.search(sidecar_text)
    return match.group(0).lower() if match else None


def verify_sidecar_hash(zip_path: Path, sidecar_path: Path) -> Tuple[bool, str]:
    if not zip_path.is_file():
        return False, "review_zip_missing"
    if not sidecar_path.is_file():
        return False, "sidecar_missing"
    expected = parse_sidecar_hash(sidecar_path.read_text(encoding="utf-8"))
    if not expected:
        return False, "sidecar_hash_unparseable"
    actual = file_sha256(zip_path).lower()
    if actual != expected:
        return False, "sidecar_hash_mismatch"
    return True, actual


def read_hooks_status(root: Path) -> Tuple[bool, str]:
    hooks_path = Path(root) / ".cursor" / "hooks.json"
    if not hooks_path.is_file():
        return True, "missing hooks.json treated as disabled"
    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        hooks = data.get("hooks") or {}
        if hooks:
            return False, "active hooks present"
        text = hooks_path.read_text(encoding="utf-8").lower()
        if "sessionstart" in text or "allow_all" in text:
            return False, "sessionStart or allow_all detected"
        return True, "hooks empty"
    except Exception as exc:
        return False, f"hooks parse error: {exc}"


def git_available() -> Tuple[bool, str]:
    for cmd in (["git", "--version"], [r"C:\Program Files\Git\cmd\git.exe", "--version"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            if out.returncode == 0:
                return True, (out.stdout or out.stderr).strip()
        except Exception:
            continue
    return False, "git not available"


def read_automation_flags(root: Path) -> Dict[str, bool]:
    cfg_path = Path(root) / "promotion_gate_config.yaml"
    if not cfg_path.is_file():
        return {k: True for k in (
            "auto_research_enabled", "auto_promote_paper_enabled",
            "auto_promote_signal_enabled", "auto_execute_real_money_enabled",
        )}
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return {
        "auto_research_enabled": bool(data.get("auto_research_enabled", True)),
        "auto_promote_paper_enabled": bool(data.get("auto_promote_paper_enabled", True)),
        "auto_promote_signal_enabled": bool(data.get("auto_promote_signal_enabled", True)),
        "auto_execute_real_money_enabled": bool(data.get("auto_execute_real_money_enabled", True)),
    }


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def verify_champion_evidence(root: Path) -> Dict[str, Any]:
    root = Path(root)
    auto = _read_json(root / "control" / "auto_promotion_status.json")
    lkg = _read_json(root / "control" / "last_known_good_state.json")

    auto_champ = auto.get("champion_variant_id") or (
        (auto.get("gate_evaluation") or {}).get("champion_variant_id")
    )
    lkg_champ = (
        lkg.get("validated_variant_id")
        or lkg.get("variant_id")
        or (lkg.get("pointer") or {}).get("variant_id")
    )

    if not auto_champ or not lkg_champ:
        return {"ok": False, "error": "champion_evidence_missing", "champion": None}
    if str(auto_champ) != str(lkg_champ):
        return {"ok": False, "error": "champion_evidence_conflict", "champion": None}
    if str(auto_champ) != LOCKED_CHAMPION:
        return {"ok": False, "error": "champion_mismatch", "champion": str(auto_champ)}
    return {"ok": True, "error": None, "champion": str(auto_champ)}


def _load_status_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not path.is_file():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None, "not_object"
        return data, None
    except Exception:
        return None, "parse_error"


def verify_safety_status_artifacts(root: Path) -> Dict[str, Any]:
    root = Path(root)
    errors: List[str] = []
    auto_path = root / "control" / "auto_promotion_status.json"
    promo_path = root / "control" / "promotion_status.json"

    auto, auto_err = _load_status_json(auto_path)
    if auto_err == "missing":
        errors.append("auto_promotion_status_missing_or_invalid")
    elif auto_err:
        errors.append("auto_promotion_status_missing_or_invalid")
    elif auto is not None:
        required_auto = {
            "champion_variant_id": None,
            "promotion_allowed": False,
            "auto_execute_real_money_enabled": False,
        }
        for field, expected in required_auto.items():
            if field not in auto:
                errors.append("auto_promotion_required_field_missing")
            elif expected is not None and auto.get(field) != expected:
                if field == "promotion_allowed" and auto.get(field) is True:
                    errors.append("promotion_allowed_true_in_auto_status")
                elif field == "auto_execute_real_money_enabled" and auto.get(field) is True:
                    errors.append("auto_execute_real_money_enabled_true")

        modes = auto.get("automation_modes")
        if not isinstance(modes, dict):
            errors.append("auto_promotion_required_field_missing")
        else:
            for key in (
                "AUTO_RESEARCH",
                "AUTO_PROMOTE_PAPER",
                "AUTO_PROMOTE_SIGNAL",
                "AUTO_EXECUTE_REAL_MONEY",
            ):
                if key not in modes:
                    errors.append("auto_promotion_required_field_missing")
                elif str(modes.get(key, "")).upper() != "DISABLED":
                    errors.append(f"{key}_enabled_in_auto_status")

        gate_eval = auto.get("gate_evaluation")
        if not isinstance(gate_eval, dict):
            errors.append("auto_promotion_required_field_missing")
        elif gate_eval.get("promotion_allowed") is not False:
            errors.append("gate_evaluation_promotion_allowed_true")

    promo, promo_err = _load_status_json(promo_path)
    if promo_err == "missing":
        errors.append("promotion_status_missing_or_invalid")
    elif promo_err:
        errors.append("promotion_status_missing_or_invalid")
    elif promo is not None:
        if "all_gates_pass" not in promo:
            errors.append("promotion_status_required_field_missing")
        elif promo.get("all_gates_pass") is not False:
            errors.append("all_gates_pass_true_in_promotion_status")
        if "auto_execute_real_money" not in promo:
            errors.append("promotion_status_required_field_missing")
        elif promo.get("auto_execute_real_money") is not True and promo.get("auto_execute_real_money") is not False:
            errors.append("promotion_status_required_field_missing")
        elif promo.get("auto_execute_real_money") is True:
            errors.append("auto_execute_real_money_true_in_promotion_status")
        if "auto_promotion_enabled" in promo and promo.get("auto_promotion_enabled") is True:
            errors.append("auto_promotion_enabled_true_in_promotion_status")

    flags = read_automation_flags(root)
    cfg_path = root / "promotion_gate_config.yaml"
    if not cfg_path.is_file():
        errors.append("promotion_gate_config_missing")
    for flag, val in flags.items():
        if val:
            errors.append(f"{flag}_not_false_in_config")

    return {"ok": len(errors) == 0, "errors": errors}


def validate_approval_content(text: str, phase_id: str) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if "TEMPLATE ONLY" in text.upper() and "NOT AN EXECUTION APPROVAL" in text.upper():
        errors.append("template marker in approval file")
    if phase_id not in text:
        errors.append(f"phase_id {phase_id} not named in approval file")
    return len(errors) == 0, errors


def _common_prechecks(root: Path, phase_id: str) -> List[str]:
    errors: List[str] = []
    phase = get_phase(root, phase_id)
    if not phase:
        return ["unknown phase"]

    hooks_ok, hooks_detail = read_hooks_status(root)
    if not hooks_ok:
        errors.append(f"hooks blocked: {hooks_detail}")

    git_ok, git_detail = git_available()
    if not git_ok:
        errors.append(f"git blocked: {git_detail}")

    champ = verify_champion_evidence(root)
    if not champ["ok"]:
        errors.append(str(champ["error"]))

    safety = verify_safety_status_artifacts(root)
    if not safety["ok"]:
        errors.extend(safety["errors"])

    if phase.get("exe_execution_allowed"):
        errors.append("phase requests exe_execution_allowed")

    return errors


def check_phase_authorization(
    root: Path,
    *,
    phase_id: str,
    predecessor_phase: Optional[str] = None,
) -> Dict[str, Any]:
    """Legacy content check only — does not authorize phase start without automation_state."""
    root = Path(root)
    result: Dict[str, Any] = {
        "authorized": False,
        "phase_id": phase_id,
        "errors": ["approval_file_alone_insufficient_use_state_machine"],
        "approval_file": None,
        "approval_sha256": None,
    }

    phase = get_phase(root, phase_id)
    if not phase:
        result["errors"].append("unknown phase")
        return result

    approval_name = phase.get("approval_file")
    if not approval_name:
        if phase_id.startswith("V1_"):
            approval_name = "EXTERNAL_REVIEW_APPROVAL_V1.md"
        else:
            result["errors"].append("no approval_file in catalog")
            return result

    approval_path = root / str(approval_name)
    if is_template_path(approval_path):
        result["errors"].append("approval path is template")
        return result
    if not approval_path.is_file():
        result["errors"].append(f"missing approval file: {approval_name}")
        return result

    text = approval_path.read_text(encoding="utf-8")
    ok_content, content_errors = validate_approval_content(text, phase_id)
    if not ok_content:
        result["errors"].extend(content_errors)

    if predecessor_phase and not is_transition_allowed(root, predecessor_phase, phase_id):
        result["errors"].append(f"transition {predecessor_phase} -> {phase_id} not allowed")

    result["errors"].extend(_common_prechecks(root, phase_id))
    result["approval_file"] = str(approval_name)
    result["approval_sha256"] = file_sha256(approval_path)
    return result
