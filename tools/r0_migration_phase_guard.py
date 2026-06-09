#!/usr/bin/env python3
"""Fail-closed phase gates and seals for R0 migration (M0–M12)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from aa_evidence_schema import AUTHORITATIVE_CHAMPION  # noqa: E402
from aa_safe_io import atomic_write_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONTROL_DIR = ROOT / "control" / "r0_migration"
EVIDENCE_DIR = ROOT / "evidence" / "r0_migration"
GATES_PATH = CONTROL_DIR / "phase_gates.json"
PHASE_STATUS_PATH = CONTROL_DIR / "phase_status.json"
PROGRAM_PATH = ROOT / "control" / "r0_migration_program.json"

M1_VARIANTS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_phase_gates(root: Path = ROOT) -> Dict[str, Any]:
    path = root / GATES_PATH.relative_to(ROOT)
    if not path.is_file():
        raise FileNotFoundError(f"Missing phase gates: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _seal_path(root: Path, phase: str) -> Path:
    return root / EVIDENCE_DIR.relative_to(ROOT) / f"{phase.lower()}_phase_seal.json"


def _prev_phase(phase: str, gates: Dict[str, Any]) -> Optional[str]:
    order: List[str] = list(gates.get("phase_order") or [])
    if phase not in order:
        return None
    idx = order.index(phase)
    if idx <= 0:
        return None
    return order[idx - 1]


def _check_record(name: str, *, pass_: bool, detail: str, path: Optional[str] = None) -> Dict[str, Any]:
    return {"check": name, "pass": pass_, "detail": detail, "path": path}


def _auto_promotion_disabled(root: Path) -> Dict[str, Any]:
    flags: List[Tuple[str, Path]] = [
        ("promotion_gate_config.yaml", root / "promotion_gate_config.yaml"),
        ("aa_config defaults", root / "aa_config.py"),
    ]
    for label, path in flags:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"auto_promote_\w+\s*=\s*True", text, re.I):
            return _check_record(
                "auto_promotion_disabled",
                pass_=False,
                detail=f"auto_promote enabled in {label}",
                path=str(path.relative_to(root)),
            )
    return _check_record("auto_promotion_disabled", pass_=True, detail="no auto_promote True in scanned files")


def _champion_unchanged(root: Path) -> Dict[str, Any]:
    for rel in (
        "control/r0_migration/mandate.json",
        "evidence/r0_migration/m1_completion_summary.json",
    ):
        p = root / rel
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        champ = data.get("authoritative_champion_unchanged") or data.get("authoritative_champion_until_m9")
        if champ and champ != AUTHORITATIVE_CHAMPION:
            return _check_record(
                "authoritative_champion_unchanged",
                pass_=False,
                detail=f"{rel} declares {champ}",
                path=rel,
            )
    return _check_record(
        "authoritative_champion_unchanged",
        pass_=True,
        detail=f"unchanged vs {AUTHORITATIVE_CHAMPION}",
    )


def _check_required_files(root: Path, rel_paths: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel in rel_paths:
        p = root / rel
        out.append(
            _check_record(
                f"file_exists:{rel}",
                pass_=p.is_file(),
                detail="present" if p.is_file() else "missing",
                path=rel,
            )
        )
    return out


def _check_json_equals(root: Path, spec: Dict[str, Any]) -> Dict[str, Any]:
    rel = str(spec.get("path") or "")
    p = root / rel
    if not p.is_file():
        return _check_record(f"json_equals:{rel}", pass_=False, detail="missing", path=rel)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return _check_record(f"json_equals:{rel}", pass_=False, detail=str(exc), path=rel)
    expected = spec.get("equals") or {}
    fails = [k for k, v in expected.items() if data.get(k) != v]
    return _check_record(
        f"json_equals:{rel}",
        pass_=not fails,
        detail="ok" if not fails else f"mismatch keys: {fails}",
        path=rel,
    )


CUSTOM: Dict[str, Callable[[Path], Dict[str, Any]]] = {}


def _custom(name: str) -> Callable[[Callable[[Path], Dict[str, Any]]], Callable[[Path], Dict[str, Any]]]:
    def deco(fn: Callable[[Path], Dict[str, Any]]) -> Callable[[Path], Dict[str, Any]]:
        CUSTOM[name] = fn
        return fn

    return deco


@_custom("m1_returns_integrity")
def _m1_returns(root: Path) -> Dict[str, Any]:
    p = root / "evidence/r0_migration/returns_manifest.json"
    if not p.is_file():
        return _check_record("m1_returns_integrity", pass_=False, detail="returns_manifest missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = bool(data.get("all_m1_variants_integrity_pass"))
    missing = [v for v in M1_VARIANTS if not ((data.get("variants") or {}).get(v) or {}).get("integrity_pass")]
    return _check_record(
        "m1_returns_integrity",
        pass_=ok,
        detail="all pass" if ok else f"failed variants: {missing}",
        path=str(p.relative_to(root)),
    )


@_custom("m1_env_audit_pass")
def _m1_env(root: Path) -> Dict[str, Any]:
    p = root / "evidence/r0_migration/env_alpha_model_mode_audit.json"
    if not p.is_file():
        return _check_record("m1_env_audit_pass", pass_=False, detail="missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    return _check_record(
        "m1_env_audit_pass",
        pass_=bool(data.get("pass")),
        detail="pass" if data.get("pass") else f"issues={data.get('issues')}",
        path=str(p.relative_to(root)),
    )


@_custom("m2_go_criteria_documented")
def _m2_go(root: Path) -> Dict[str, Any]:
    p = root / "evidence/r0_migration/aligned_comparison.json"
    if not p.is_file():
        return _check_record("m2_go_criteria_documented", pass_=False, detail="aligned_comparison missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    go = data.get("go_no_go") or data.get("decision")
    if isinstance(go, dict):
        go = go.get("decision") or go.get("go_no_go")
    return _check_record(
        "m2_go_criteria_documented",
        pass_=go in ("GO", "NO_GO", "CONDITIONAL"),
        detail=f"decision={go}",
        path=str(p.relative_to(root)),
    )


@_custom("m3_candidate_selected")
def _m3_candidate(root: Path) -> Dict[str, Any]:
    p = root / "evidence/r0_migration/m3_candidate_decision.json"
    if not p.is_file():
        return _check_record("m3_candidate_selected", pass_=False, detail="m3_candidate_decision.json missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    return _check_record(
        "m3_candidate_selected",
        pass_=bool(data.get("selected_variant_id")),
        detail=str(data.get("selected_variant_id") or "none"),
        path=str(p.relative_to(root)),
    )


@_custom("m5_all_gates_pass")
def _m5_gates(root: Path) -> Dict[str, Any]:
    p = root / "evidence/r0_migration/gate_matrix.json"
    if not p.is_file():
        return _check_record("m5_all_gates_pass", pass_=False, detail="gate_matrix missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = str(data.get("status", "")).upper() == "PASS" and not (data.get("failures") or [])
    return _check_record("m5_all_gates_pass", pass_=ok, detail=str(data.get("status")), path=str(p.relative_to(root)))


@_custom("m9_external_approval_file")
def _m9_approval(root: Path) -> Dict[str, Any]:
    hits = sorted(root.glob("EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md"))
    hits = [h for h in hits if not h.name.startswith("TEMPLATE_")]
    return _check_record(
        "m9_external_approval_file",
        pass_=bool(hits),
        detail=hits[0].name if hits else "no EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md",
        path=str(hits[0].relative_to(root)) if hits else None,
    )


@_custom("m9_champion_change_executed")
def _m9_executed(root: Path) -> Dict[str, Any]:
    p = root / "control/champion_strategic_decision.json"
    if not p.is_file():
        return _check_record("m9_champion_change_executed", pass_=False, detail="missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = bool(data.get("champion_change_executed"))
    return _check_record(
        "m9_champion_change_executed",
        pass_=ok,
        detail=str(data.get("active_champion") or "not executed"),
        path=str(p.relative_to(root)),
    )


@_custom("m10_stabilization_window")
def _m10_stab(root: Path) -> Dict[str, Any]:
    p = root / "evidence/r0_migration/m10_stabilization_summary.json"
    if not p.is_file():
        return _check_record("m10_stabilization_window", pass_=False, detail="summary missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = str(data.get("status", "")).upper() == "COMPLETE"
    return _check_record("m10_stabilization_window", pass_=ok, detail=str(data.get("status")), path=str(p.relative_to(root)))


@_custom("m11_runtime_verify_pass")
def _m11_runtime(root: Path) -> Dict[str, Any]:
    p = root / "evidence/v5r_final_validation_summary.json"
    if not p.is_file():
        p = root / "evidence/v5r_runtime_readonly_verification.json"
    if not p.is_file():
        return _check_record("m11_runtime_verify_pass", pass_=False, detail="no v5r validation evidence", path=None)
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = str(data.get("status", data.get("overall_status", ""))).upper() in ("PASS", "OK", "COMPLETE")
    return _check_record("m11_runtime_verify_pass", pass_=ok, detail=str(data.get("status")), path=str(p.relative_to(root)))


@_custom("m12_rollout_documented")
def _m12_rollout(root: Path) -> Dict[str, Any]:
    p = root / "evidence/r0_migration/m12_os_rollout_summary.json"
    if not p.is_file():
        return _check_record("m12_rollout_documented", pass_=False, detail="m12 summary missing", path=str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    ok = str(data.get("status", "")).upper() == "COMPLETE"
    return _check_record("m12_rollout_documented", pass_=ok, detail=str(data.get("notes") or data.get("status")), path=str(p.relative_to(root)))


def verify_prerequisite_seal(root: Path, phase: str, gates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    gates = gates or load_phase_gates(root)
    prev = _prev_phase(phase, gates)
    if prev is None:
        return _check_record("prerequisite_seal", pass_=True, detail="first phase")
    seal = _seal_path(root, prev)
    if not seal.is_file():
        return _check_record(
            "prerequisite_seal",
            pass_=False,
            detail=f"{prev} not sealed — run seal_r0_migration_phase.py --phase {prev}",
            path=str(seal.relative_to(root)),
        )
    data = json.loads(seal.read_text(encoding="utf-8"))
    ok = str(data.get("status", "")).upper() == "SEALED"
    return _check_record(
        "prerequisite_seal",
        pass_=ok,
        detail=f"{prev} status={data.get('status')}",
        path=str(seal.relative_to(root)),
    )


def verify_phase(root: Path, phase: str, *, skip_optional: bool = False) -> Dict[str, Any]:
    gates = load_phase_gates(root)
    phase = phase.upper()
    if phase not in (gates.get("phase_order") or []):
        raise ValueError(f"Unknown phase: {phase}")

    spec = (gates.get("phases") or {}).get(phase) or {}
    if spec.get("optional") and skip_optional:
        return {
            "phase": phase,
            "pass": True,
            "skipped_optional": True,
            "checks": [_check_record("optional_phase", pass_=True, detail="skipped by flag")],
            "blockers": [],
        }

    checks: List[Dict[str, Any]] = [
        _champion_unchanged(root),
        _auto_promotion_disabled(root),
        verify_prerequisite_seal(root, phase, gates),
    ]
    checks.extend(_check_required_files(root, list(spec.get("required_files") or [])))
    for js in spec.get("json_checks") or []:
        checks.append(_check_json_equals(root, js))
    for name in spec.get("custom_checks") or []:
        fn = CUSTOM.get(name)
        if fn:
            checks.append(fn(root))
        else:
            checks.append(_check_record(name, pass_=False, detail="unknown custom check"))

    blockers = [c["check"] for c in checks if not c.get("pass")]
    return {
        "phase": phase,
        "title": spec.get("title"),
        "pass": not blockers,
        "verified_at_utc": _utc_now(),
        "checks": checks,
        "blockers": blockers,
    }


def _artifact_hashes(root: Path, phase: str, gates: Dict[str, Any]) -> Dict[str, str]:
    spec = (gates.get("phases") or {}).get(phase) or {}
    rels = list(spec.get("required_files") or [])
    seal_prev = _seal_path(root, phase)
    if seal_prev.is_file():
        rels.append(str(seal_prev.relative_to(root).as_posix()))
    out: Dict[str, str] = {}
    for rel in rels:
        h = _sha256_file(root / rel)
        if h:
            out[rel] = h
    return out


def _update_phase_status(root: Path, phase: str, *, sealed: bool, blockers: List[str]) -> None:
    status_path = root / PHASE_STATUS_PATH.relative_to(ROOT)
    data: Dict[str, Any] = {}
    if status_path.is_file():
        data = json.loads(status_path.read_text(encoding="utf-8"))
    phases = data.get("phases") or {}
    now = _utc_now()
    if sealed:
        phases[phase] = {"status": "SEALED", "sealed_at_utc": now, "blockers": []}
        order: List[str] = list(load_phase_gates(root).get("phase_order") or [])
        if phase in order:
            idx = order.index(phase)
            if idx + 1 < len(order):
                nxt = order[idx + 1]
                if nxt == "M1" and not is_phase_sealed(root, "M1"):
                    from tools.r0_migration_crash_guard import reconcile_m1_phase_status

                    data["phases"] = phases
                    data["last_completed_phase"] = phase
                    atomic_write_json(status_path, data)
                    reconcile_m1_phase_status(root)
                    prog = {
                        "schema_version": 1,
                        "program": "R0_LONG_TERM_MIGRATION",
                        "current_phase": "M1",
                        "last_completed_phase": phase,
                        "last_sealed_phase": phase,
                        "updated_at_utc": now,
                        "phase_blockers": [],
                    }
                    atomic_write_json(root / PROGRAM_PATH.relative_to(ROOT), prog)
                    return
                phases[nxt] = {"status": "READY", "blocked_by": None}
        data["current_phase"] = order[order.index(phase) + 1] if phase in order and order.index(phase) + 1 < len(order) else phase
        data["last_completed_phase"] = phase
    else:
        phases[phase] = {"status": "BLOCKED", "updated_at_utc": now, "blockers": blockers}
    data["phases"] = phases
    data["updated_at_utc"] = now
    data.setdefault("schema_version", 2)
    data.setdefault("program", "R0_LONG_TERM_MIGRATION")
    atomic_write_json(status_path, data)

    prog = {
        "schema_version": 1,
        "program": "R0_LONG_TERM_MIGRATION",
        "current_phase": data.get("current_phase"),
        "last_completed_phase": data.get("last_completed_phase"),
        "last_sealed_phase": phase if sealed else data.get("last_sealed_phase"),
        "updated_at_utc": now,
        "phase_blockers": blockers if not sealed else [],
    }
    atomic_write_json(root / PROGRAM_PATH.relative_to(ROOT), prog)


def seal_phase(
    root: Path,
    phase: str,
    *,
    skip_optional: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    phase = phase.upper()
    verification = verify_phase(root, phase, skip_optional=skip_optional)
    if not verification.get("pass"):
        if not dry_run:
            _update_phase_status(root, phase, sealed=False, blockers=list(verification.get("blockers") or []))
        return {
            "phase": phase,
            "status": "SEAL_FAILED",
            "dry_run": dry_run,
            "verification": verification,
        }

    gates = load_phase_gates(root)
    order: List[str] = list(gates.get("phase_order") or [])
    nxt = order[order.index(phase) + 1] if phase in order and order.index(phase) + 1 < len(order) else None

    payload = {
        "schema_version": 1,
        "phase": phase,
        "status": "SEALED",
        "sealed_at_utc": _utc_now(),
        "authoritative_champion_until_m9": AUTHORITATIVE_CHAMPION,
        "verification": verification,
        "artifact_hashes": _artifact_hashes(root, phase, gates),
        "next_phase": nxt,
        "sealed_by": "tools/r0_migration_phase_guard.py",
    }

    if dry_run:
        return {"phase": phase, "status": "SEAL_DRY_RUN", "dry_run": True, "would_write": payload}

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(_seal_path(root, phase), payload)
    atomic_write_json(
        EVIDENCE_DIR / f"{phase.lower()}_completion_summary.json",
        {
            "phase": phase,
            "status": "SEALED",
            "completed_at_utc": payload["sealed_at_utc"],
            "blockers": [],
            "seal_path": str(_seal_path(root, phase).relative_to(root)),
            "authoritative_champion_unchanged": AUTHORITATIVE_CHAMPION,
        },
    )
    _update_phase_status(root, phase, sealed=True, blockers=[])
    return {"phase": phase, "status": "SEALED", "seal_path": str(_seal_path(root, phase)), "next_phase": nxt}


def try_seal_phase(root: Path, phase: str) -> Dict[str, Any]:
    """Best-effort seal after phase work; never raises."""
    try:
        return seal_phase(root, phase)
    except Exception as exc:
        return {"phase": phase, "status": "SEAL_ERROR", "error": str(exc)}


def is_phase_sealed(root: Path, phase: str) -> bool:
    p = _seal_path(root, phase.upper())
    if not p.is_file():
        return False
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("status", "")).upper() == "SEALED"
    except Exception:
        return False
