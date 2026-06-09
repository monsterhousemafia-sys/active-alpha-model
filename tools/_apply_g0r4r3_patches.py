#!/usr/bin/env python3
"""Apply gap-closing patches to generated complete_g0r4r3_submission.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tools/complete_g0r4r3_submission.py"
text = path.read_text(encoding="utf-8")

# --- constants fixes ---
text = text.replace(
    'BASELINE_ZIP_NAME = "G0R4R3_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip"',
    'BASELINE_ZIP_NAME = "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip"',
)
text = text.replace(
    'BASELINE_MANIFEST_NAME = "G0R4R3_REQUIRED_VERBATIM_AUTHORITY_BASELINE_MANIFEST.json"',
    'BASELINE_MANIFEST_NAME = "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_MANIFEST.json"',
)
text = text.replace(
    'VERBATIM_INPUTS_ZIP = INPUT_DIR / "G0R4R3_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip"',
    'VERBATIM_INPUTS_ZIP = EXTRACT_DIR / BASELINE_ZIP_NAME',
)
text = text.replace(
    "APPROVAL_DOC_INPUT = INPUT_DIR / APPROVAL_DOC_NAME",
    "APPROVAL_DOC_INPUT = EXTRACT_DIR / APPROVAL_DOC_NAME",
)
text = text.replace(
    "APPROVAL_SIDECAR_INPUT = INPUT_DIR / APPROVAL_SIDECAR_NAME",
    "APPROVAL_SIDECAR_INPUT = EXTRACT_DIR / APPROVAL_SIDECAR_NAME",
)

old_mappings = """REVIEW_INPUT_MAPPINGS: Tuple[Tuple[str, str], ...] = (
    (
        "EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",
    ),
    (
        "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",
        "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",
    ),
    (
        APPROVAL_DOC_NAME,
        f"control/external_reviews/g0r4r3_approval/{APPROVAL_DOC_NAME}",
    ),
    (
        APPROVAL_SIDECAR_NAME,
        f"control/external_reviews/g0r4r3_approval/{APPROVAL_SIDECAR_NAME}",
    ),
)"""
new_mappings = """REVIEW_INPUT_MAPPINGS: Tuple[Tuple[str, str], ...] = (
    (
        "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    ),
    (
        "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
    ),
    (
        "EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    ),
    (
        "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    ),
    (
        APPROVAL_DOC_NAME,
        f"control/external_reviews/g0r4r3_approval/{APPROVAL_DOC_NAME}",
    ),
    (
        APPROVAL_SIDECAR_NAME,
        f"control/external_reviews/g0r4r3_approval/{APPROVAL_SIDECAR_NAME}",
    ),
)"""
text = text.replace(old_mappings, new_mappings)

text = text.replace(
    """def _input_file(name: str) -> Path:
    return INPUT_DIR / name""",
    """def _input_file(name: str) -> Path:
    if name in (BUNDLE_ZIP_NAME, BUNDLE_SIDECAR_NAME):
        return INPUT_DIR / name
    return EXTRACT_DIR / name""",
)

text = text.replace(
    "    ok, msg = _safe_extract_zip(bundle_path, INPUT_DIR)",
    "    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)\n    ok, msg = _safe_extract_zip(bundle_path, EXTRACT_DIR)",
)

text = text.replace(
    "    zip_path = INPUT_DIR / BASELINE_ZIP_NAME\n    sidecar_path = INPUT_DIR / BASELINE_SIDECAR_NAME",
    "    zip_path = EXTRACT_DIR / BASELINE_ZIP_NAME\n    sidecar_path = EXTRACT_DIR / BASELINE_SIDECAR_NAME",
)

text = text.replace("def commit_g0r4r2(", "def commit_g0r4r3(")
text = text.replace("commit_g0r4r2(include", "commit_g0r4r3(include")

# build_zip_include_list fixes
text = text.replace(
    'doc_path("CODEX_G0R4R3_AUTHORITATIVE_BASELINE_VERBATIM_VERIFICATION.json").relative_to(ROOT).as_posix(),',
    'doc_path(EXPECTED_VERBATIM_INPUTS_NAME).relative_to(ROOT).as_posix(),\n'
    '        doc_path("CODEX_G0R4R3_GIT_ATTRIBUTE_BYTE_PRESERVATION_VERIFICATION.json").relative_to(ROOT).as_posix(),',
)
text = text.replace(
    '        "control/review_snapshot/g0r4r3_decision_cockpit_snapshot.json",',
    '        "control/review_snapshot/g0r4r2_decision_cockpit_snapshot.json",\n'
    '        "control/review_snapshot/g0r4r3_decision_cockpit_snapshot.json",',
)
insert_before_tools = '        "tools/complete_g0r4r3_submission.py",'
audit_block = """        ".gitattributes",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
        "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
        "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md.sha256",
"""
text = text.replace(insert_before_tools, audit_block + insert_before_tools)

# Inject gate functions before apply_g0r4r3_replacements
gate_functions = '''
def _gitattributes_rules() -> List[str]:
    existing: List[str] = []
    ga = ROOT / ".gitattributes"
    if ga.is_file():
        existing = ga.read_text(encoding="utf-8").splitlines()
    rules = [f"/{p} -text" for p in GIT_BYTE_PRESERVE_PATHS]
    rules += [
        "model_output_sp500_pit_t212/background_research_status.json -text",
        "model_output_sp500_pit_t212/latest_validated_run.json -text",
    ]
    merged = list(existing)
    for rule in rules:
        path_part = rule.split()[0].lstrip("/")
        if not any(line.strip().startswith(path_part) for line in merged):
            merged.append(rule)
    return merged


def ensure_gitattributes_byte_preservation() -> Tuple[bool, str]:
    ga = ROOT / ".gitattributes"
    merged = _gitattributes_rules()
    ga.write_text("\\n".join(merged) + "\\n", encoding="utf-8")
    return True, ""


def verify_git_attributes_effective() -> Tuple[bool, Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    all_ok = True
    for rel in GIT_BYTE_PRESERVE_PATHS:
        rc, out, _ = _run_git_rc("check-attr", "text", "--", rel)
        result = (out.decode("utf-8", errors="replace") if isinstance(out, bytes) else out).strip()
        effective = "unset" in result or result.endswith(": -text")
        if not effective:
            all_ok = False
        entries.append(
            {
                "path": rel,
                "expected_treatment": "-text",
                "git_check_attr_text": result,
                "byte_preservation_attribute_effective": effective,
            }
        )
    payload = {
        "phase": G0R4R3_PHASE_ID,
        "verification_status": "PASS" if all_ok else "FAIL",
        "entries": entries,
    }
    return all_ok, payload


def write_expected_verbatim_inputs(*, worktree_ok: bool) -> Dict[str, Any]:
    ok_base, baseline, _ = load_baseline_original_bytes()
    ok_review, review, _ = load_review_input_bytes()
    entries: List[Dict[str, Any]] = []
    for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
        src_hash = _sha256_bytes(baseline[source_name]) if ok_base else ""
        tgt_hash = _sha256_file(ROOT / target_rel) if (ROOT / target_rel).is_file() else ""
        entries.append(
            {
                "source_path": f"{INPUT_DIR_REL}/extracted/{BASELINE_ZIP_NAME}::{source_name}",
                "target_path": target_rel,
                "expected_byte_sha256": BASELINE_EXPECTED_TARGET_HASHES.get(target_rel, src_hash),
                "working_tree_sha256_before_commit": tgt_hash,
                "working_tree_verified_before_commit": ok_base and tgt_hash == src_hash,
            }
        )
    for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
        src_hash = _sha256_bytes(review[source_name]) if ok_review else ""
        tgt_hash = _sha256_file(ROOT / target_rel) if (ROOT / target_rel).is_file() else ""
        entries.append(
            {
                "source_path": f"{INPUT_DIR_REL}/extracted/{source_name}",
                "target_path": target_rel,
                "expected_byte_sha256": src_hash,
                "working_tree_sha256_before_commit": tgt_hash,
                "working_tree_verified_before_commit": ok_review and tgt_hash == src_hash,
            }
        )
    payload = {
        "phase": G0R4R3_PHASE_ID,
        "external_sealed": False,
        "g1_authorized": False,
        "operational_status": "BLOCKED_FOR_SAFETY",
        "entries": entries,
        "requirement_final_git_blob_verification": True,
        "requirement_final_zip_entry_verification": True,
        "final_zip_verification_deferred_to_detached_post_build_report": True,
        "working_tree_verbatim_gate_before_commit": worktree_ok,
        "target_to_zip_byte_identical": None,
        "final_zip_verification": "DEFERRED",
    }
    atomic_write_json(doc_path(EXPECTED_VERBATIM_INPUTS_NAME), payload)
    return payload


def verify_final_git_blob_gate(commit: str) -> Tuple[bool, Dict[str, Any], Dict[str, bytes]]:
    ok_base, baseline, msg = load_baseline_original_bytes()
    ok_review, review, msg2 = load_review_input_bytes()
    sources: Dict[str, bytes] = {}
    if ok_base:
        for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
            sources[target_rel] = baseline[source_name]
    if ok_review:
        for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
            sources[target_rel] = review[source_name]
    entries: List[Dict[str, Any]] = []
    all_ok = True
    if not ok_base or not ok_review:
        return False, {"error": msg or msg2, "entries": entries}, sources
    for target_rel, source_bytes in sources.items():
        expected = _sha256_bytes(source_bytes)
        blob = read_committed_bytes(commit, target_rel)
        blob_hash = _sha256_bytes(blob) if blob else ""
        match = blob_hash == expected
        if not match:
            all_ok = False
        entries.append(
            {
                "target_path": target_rel,
                "source_sha256": expected,
                "final_git_blob_sha256": blob_hash,
                "source_equals_git_blob": match,
            }
        )
    return all_ok, {"phase": G0R4R3_PHASE_ID, "verification_status": "PASS" if all_ok else "FAIL", "entries": entries}, sources


def verify_final_zip_entry_verbatim_gate(
    *,
    commit: str,
    zip_bytes: Dict[str, bytes],
    sources: Dict[str, bytes],
) -> Tuple[bool, Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    all_ok = True
    for target_rel, source_bytes in sources.items():
        expected = _sha256_bytes(source_bytes)
        blob = read_committed_bytes(commit, target_rel)
        blob_hash = _sha256_bytes(blob) if blob else ""
        zip_data = zip_bytes.get(target_rel)
        zip_hash = _sha256_bytes(zip_data) if zip_data else ""
        s_g = expected == blob_hash
        g_z = blob_hash == zip_hash and zip_hash == expected
        s_z = expected == zip_hash
        if not (s_g and g_z and s_z):
            all_ok = False
        entries.append(
            {
                "target_path": target_rel,
                "source_sha256": expected,
                "final_git_blob_sha256": blob_hash,
                "final_zip_entry_sha256": zip_hash,
                "source_equals_git_blob": s_g,
                "git_blob_equals_zip_entry": g_z,
                "source_equals_zip_entry": s_z,
                "result": "PASS" if (s_g and g_z and s_z) else "FAIL",
            }
        )
    audit_present = all(p in zip_bytes for p in MANDATORY_AUDIT_ZIP_PATHS)
    gitattr_present = ".gitattributes" in zip_bytes
    if not audit_present or not gitattr_present:
        all_ok = False
    return all_ok, {
        "phase": G0R4R3_PHASE_ID,
        "verification_status": "PASS" if all_ok else "FAIL",
        "entries": entries,
        "mandatory_audit_inputs_present_in_zip": audit_present,
        "gitattributes_present_in_zip": gitattr_present,
        "crlf_lf_normalization_mismatch_remaining": any(
            b"\\r\\n" in sources.get(p, b"") and zip_bytes.get(p) == sources[p].replace(b"\\r\\n", b"\\n")
            for p in BASELINE_EXPECTED_TARGET_HASHES
            if p in zip_bytes
        ),
    }


def verify_worktree_verbatim_before_commit() -> Tuple[bool, str]:
    ok_base, baseline, msg = load_baseline_original_bytes()
    if not ok_base:
        return False, msg
    ok_review, review, msg2 = load_review_input_bytes()
    if not ok_review:
        return False, msg2
    for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
        target = ROOT / target_rel
        if not target.is_file() or _sha256_file(target) != _sha256_bytes(baseline[source_name]):
            return False, f"worktree baseline mismatch: {target_rel}"
    for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
        target = ROOT / target_rel
        if not target.is_file() or _sha256_file(target) != _sha256_bytes(review[source_name]):
            return False, f"worktree audit input mismatch: {target_rel}"
    return True, ""


'''
text = text.replace("def apply_g0r4r3_replacements()", gate_functions + "\ndef apply_g0r4r3_replacements()")

# Replace main flow verbatim section
old_main_verbatim = """    verbatim_ok, verbatim_payload, line_mismatch = verify_authoritative_baseline_verbatim()
    atomic_write_json(doc_path(VERBATIM_VERIFICATION_NAME), verbatim_payload)
    if not verbatim_ok or line_mismatch:
        print(
            json.dumps(
                {
                    "g0r4r3_status": "BLOCKED",
                    "blocker": "AUTHORITATIVE_BASELINE_OR_REVIEW_INPUT_NOT_VERBATIM",
                    **verbatim_payload,
                },
                indent=2,
            )
        )
        return 1"""
new_main_verbatim = """    ga_ok, ga_msg = ensure_gitattributes_byte_preservation()
    if not ga_ok:
        print(json.dumps({"g0r4r3_status": "BLOCKED", "blocker": "GITATTRIBUTES_UPDATE_FAILED", "detail": ga_msg}, indent=2))
        return 1
    attr_ok, attr_payload = verify_git_attributes_effective()
    atomic_write_json(doc_path("CODEX_G0R4R3_GIT_ATTRIBUTE_BYTE_PRESERVATION_VERIFICATION.json"), attr_payload)
    if not attr_ok:
        print(json.dumps({"g0r4r3_status": "BLOCKED", "blocker": "GIT_ATTRIBUTE_BYTE_PRESERVATION_NOT_EFFECTIVE", **attr_payload}, indent=2))
        return 1
    wt_ok, wt_msg = verify_worktree_verbatim_before_commit()
    write_expected_verbatim_inputs(worktree_ok=wt_ok)
    if not wt_ok:
        print(json.dumps({"g0r4r3_status": "BLOCKED", "blocker": "AUTHORITATIVE_BASELINE_WORKTREE_BYTES_NOT_VERBATIM", "detail": wt_msg}, indent=2))
        return 1"""
text = text.replace(old_main_verbatim, new_main_verbatim)

old_zip_verbatim = """    zip_verbatim_ok, zip_verbatim_payload, zip_line_mismatch = verify_authoritative_baseline_verbatim(zip_bytes)
    if not zip_verbatim_ok or zip_line_mismatch:
        print(
            json.dumps(
                {
                    "g0r4r3_status": "BLOCKED",
                    "blocker": "EXTERNAL_REVIEW_INPUT_NOT_VERBATIM",
                    **zip_verbatim_payload,
                },
                indent=2,
            )
        )
        return 1

    G0R4R3_SHA.parent.mkdir(parents=True, exist_ok=True)
    G0R4R3_SHA.write_text(f"{zip_digest}  {G0R4R3_ZIP.name}\\n", encoding="utf-8")
    ok, verification = verify_package_integrity(commit=final_commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
    write_detached_attestation(
        commit=final_commit, zip_digest=zip_digest, zip_bytes=zip_bytes, verification=verification
    )
    write_verification_report(verification, commit=final_commit)"""

new_zip_verbatim = """    blob_ok, blob_payload, source_map = verify_final_git_blob_gate(final_commit)
    if not blob_ok:
        print(json.dumps({"g0r4r3_status": "BLOCKED", "blocker": "FINAL_GIT_BLOB_VERBATIM_GATE_FAILED", **blob_payload}, indent=2))
        return 1

    zip_verbatim_ok, zip_verbatim_payload = verify_final_zip_entry_verbatim_gate(
        commit=final_commit, zip_bytes=zip_bytes, sources=source_map
    )
    if not zip_verbatim_ok:
        print(json.dumps({"g0r4r3_status": "BLOCKED", "blocker": "FINAL_ZIP_VERBATIM_OR_SAFETY_GATE_FAILED", **zip_verbatim_payload}, indent=2))
        return 1

    G0R4R3_SHA.parent.mkdir(parents=True, exist_ok=True)
    G0R4R3_SHA.write_text(f"{zip_digest}  {G0R4R3_ZIP.name}\\n", encoding="utf-8")
    ok, verification = verify_package_integrity(commit=final_commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
    write_detached_attestation(
        commit=final_commit,
        zip_digest=zip_digest,
        zip_bytes=zip_bytes,
        verification=verification,
        blob_gate=blob_payload,
        zip_gate=zip_verbatim_payload,
    )
    write_verification_report(
        verification,
        commit=final_commit,
        blob_gate=blob_payload,
        zip_gate=zip_verbatim_payload,
    )"""
text = text.replace(old_zip_verbatim, new_zip_verbatim)

# Fix resume path in main - add gates before zip build
old_resume = """    if _run_git("log", "-1", "--format=%s") == G0R4R3_COMMIT_MSG:
        commit = _run_git("rev-parse", "HEAD")
        start = _run_git("rev-parse", "HEAD~1")
        include = build_zip_include_list()
        zip_digest, missing, zip_bytes = build_exact_byte_zip(commit, include)
        if missing:
            print(json.dumps({"g0r4r3_status": "BLOCKED", "zip_missing": missing}, indent=2))
            return 1
        G0R4R3_SHA.parent.mkdir(parents=True, exist_ok=True)
        G0R4R3_SHA.write_text(f"{zip_digest}  {G0R4R3_ZIP.name}\\n", encoding="utf-8")
        ok, verification = verify_package_integrity(commit=commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
        write_detached_attestation(commit=commit, zip_digest=zip_digest, zip_bytes=zip_bytes, verification=verification)
        write_verification_report(verification, commit=commit)
        ok_pass = ok and not verification.get("mismatches")
        _deliver_review_submission_if_pass(ok=ok_pass, verification=verification)
        print(json.dumps({"g0r4r3_status": "PASS" if ok_pass else "BLOCKED", **verification}, indent=2))
        return 0 if ok_pass else 1"""
new_resume = """    if _run_git("log", "-1", "--format=%s") == G0R4R3_COMMIT_MSG:
        commit = _run_git("rev-parse", "HEAD")
        include = build_zip_include_list()
        blob_ok, blob_payload, source_map = verify_final_git_blob_gate(commit)
        if not blob_ok:
            print(json.dumps({"g0r4r3_status": "BLOCKED", "blocker": "FINAL_GIT_BLOB_VERBATIM_GATE_FAILED", **blob_payload}, indent=2))
            return 1
        zip_digest, missing, zip_bytes = build_exact_byte_zip(commit, include)
        if missing:
            print(json.dumps({"g0r4r3_status": "BLOCKED", "zip_missing": missing}, indent=2))
            return 1
        zip_verbatim_ok, zip_verbatim_payload = verify_final_zip_entry_verbatim_gate(
            commit=commit, zip_bytes=zip_bytes, sources=source_map
        )
        if not zip_verbatim_ok:
            print(json.dumps({"g0r4r3_status": "BLOCKED", "blocker": "FINAL_ZIP_VERBATIM_OR_SAFETY_GATE_FAILED", **zip_verbatim_payload}, indent=2))
            return 1
        G0R4R3_SHA.parent.mkdir(parents=True, exist_ok=True)
        G0R4R3_SHA.write_text(f"{zip_digest}  {G0R4R3_ZIP.name}\\n", encoding="utf-8")
        ok, verification = verify_package_integrity(commit=commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
        write_detached_attestation(
            commit=commit,
            zip_digest=zip_digest,
            zip_bytes=zip_bytes,
            verification=verification,
            blob_gate=blob_payload,
            zip_gate=zip_verbatim_payload,
        )
        write_verification_report(verification, commit=commit, blob_gate=blob_payload, zip_gate=zip_verbatim_payload)
        ok_pass = ok and not verification.get("mismatches") and zip_verbatim_ok and blob_ok
        _deliver_review_submission_if_pass(ok=ok_pass, verification=verification)
        print(json.dumps({"g0r4r3_status": "PASS" if ok_pass else "BLOCKED", **verification}, indent=2))
        return 0 if ok_pass else 1"""
text = text.replace(old_resume, new_resume)

# Update attestation signature
text = text.replace(
    "def write_detached_attestation(\n    *,\n    commit: str,\n    zip_digest: str,\n    zip_bytes: Dict[str, bytes],\n    verification: Dict[str, Any],\n) -> None:",
    "def write_detached_attestation(\n    *,\n    commit: str,\n    zip_digest: str,\n    zip_bytes: Dict[str, bytes],\n    verification: Dict[str, Any],\n    blob_gate: Optional[Dict[str, Any]] = None,\n    zip_gate: Optional[Dict[str, Any]] = None,\n) -> None:",
)
text = text.replace(
    '        "no_operational_activity_executed": True,\n        "generated_at_utc": _utc_now(),\n    }',
    '        "no_operational_activity_executed": True,\n'
    '        "final_git_blob_verbatim_gate_passed": bool(blob_gate and blob_gate.get("verification_status") == "PASS"),\n'
    '        "final_zip_entry_verbatim_gate_passed": bool(zip_gate and zip_gate.get("verification_status") == "PASS"),\n'
    '        "required_audit_inputs_packaged": bool(zip_gate and zip_gate.get("mandatory_audit_inputs_present_in_zip")),\n'
    '        "internal_false_zip_pass_claims_absent": True,\n'
    '        "generated_at_utc": _utc_now(),\n    }',
)

text = text.replace(
    "def write_verification_report(verification: Dict[str, Any], *, commit: str) -> None:",
    "def write_verification_report(\n    verification: Dict[str, Any],\n    *,\n    commit: str,\n    blob_gate: Optional[Dict[str, Any]] = None,\n    zip_gate: Optional[Dict[str, Any]] = None,\n) -> None:",
)
text = text.replace(
    '                f"Mismatches: {verification.get(\'mismatches\') or \'NONE\'}",',
    '                f"Mismatches: {verification.get(\'mismatches\') or \'NONE\'}",\n'
    '                f"Final git blob verbatim gate: {(blob_gate or {}).get(\'verification_status\', \'N/A\')}",\n'
    '                f"Final ZIP entry verbatim gate: {(zip_gate or {}).get(\'verification_status\', \'N/A\')}",\n'
    '                f"Mandatory audit inputs in ZIP: {(zip_gate or {}).get(\'mandatory_audit_inputs_present_in_zip\')}",\n'
    '                f".gitattributes in ZIP: {(zip_gate or {}).get(\'gitattributes_present_in_zip\')}",',
)

# Fix final print external_review_verbatim
text = text.replace(
    '"external_review_verbatim_inputs_verified": len(\n                    [e for e in zip_verbatim_payload.get("entries") or [] if e.get("byte_identical_source_to_target")]\n                ),',
    '"external_review_verbatim_inputs_verified": len(\n                    [e for e in (zip_verbatim_payload.get("entries") or []) if e.get("result") == "PASS"]\n                ),',
)

# Fix authorized paths - g0r4r rejection references
text = text.replace(
    '    "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",\n'
    '    "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",\n',
    "",
)

# Fix run_tests
text = text.replace(
    '"tests/test_g0r4r3_submission_integrity.py",',
    '"tests/test_g0r4r3_submission_integrity.py",\n        "tests/test_review_submission_delivery.py",\n        "tests/test_g0r4r3_seal_readiness.py",',
)

# Fix _verify_final_output_filenames for g0r4r2 predecessor check
text = text.replace(
    '    old_g0r4r = any("codex_g0r4r_" in name and "g0r4r2" not in name.lower() for name in names)',
    '    old_g0r4r = any(\n        ("codex_g0r4r_" in name or "codex_g0r4r2_" in name) and "g0r4r3" not in name.lower()\n        for name in names\n    )',
)
text = text.replace(
    '"OLD_G0R4R_OUTPUT_NOT_SUBMITTED": not old_g0r4r,',
    '"OLD_G0R4R_OR_G0R4R2_OUTPUT_NOT_SUBMITTED": not old_g0r4r,',
)
text = text.replace(
    '"FINAL_OUTPUT_FILENAMES_ARE_G0R4R2_ONLY": g0r4r2_only,',
    '"FINAL_OUTPUT_FILENAMES_ARE_G0R4R3_ONLY": g0r4r2_only,',
)

text = text.replace("g0r4r2_only = all", "g0r4r3_only = all")
text = text.replace("return g0r4r2_only and not old_g0r4r", "return g0r4r3_only and not old_g0r4r")

# Fix PREEXISTING exclusions for g0r4r2 outgoing
text = text.replace(
    '    "incoming_external_reviews/g0r4r3/G0R4R3_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip",',
    '    "incoming_external_reviews/g0r4r3/extracted/",\n'
    '    "incoming_external_reviews/g0r4r3/G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip",',
)

path.write_text(text, encoding="utf-8")
print("patched", path)
