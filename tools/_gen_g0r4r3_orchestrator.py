#!/usr/bin/env python3
"""Generate complete_g0r4r3_submission.py from G0R4R2 orchestrator with gap-closing gates."""
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "tools/complete_g0r4r2_submission.py"
text = src.read_text(encoding="utf-8")

# Order matters: longer / more specific tokens first.
replacements = [
    ('"""G0R4R2 verbatim authoritative baseline resubmission orchestrator."""',
     '"""G0R4R3 final git-blob and ZIP-entry verbatim remediation orchestrator."""'),
    ("write_g0r4r2_review_snapshot", "write_g0r4r3_review_snapshot"),
    ("G0R4R2_VERBATIM_AUTHORITATIVE_BASELINE_RESUBMISSION",
     "G0R4R3_FINAL_BLOB_ZIP_VERBATIM_AND_AUDIT_INPUT_COMPLETENESS_REMEDIATION"),
    ("incoming_external_reviews/g0r4r2", "incoming_external_reviews/g0r4r3"),
    ("remediation/g0r4r2-verbatim-authoritative-baseline-resubmission",
     "remediation/g0r4r3-final-blob-zip-verbatim"),
    ("remediation/g0r4r2-verbatim-authoritative-baseline",
     "remediation/g0r4r3-final-blob-zip-verbatim"),
    ("codex_g0r4r2_verbatim_authoritative_baseline_resubmission",
     "codex_g0r4r3_final_blob_zip_verbatim_remediation_review"),
    ("CODEX_G0R4R2_", "CODEX_G0R4R3_"),
    ("G0R4R2-CHANGE_MANIFEST.json", "G0R4R3-CHANGE_MANIFEST.json"),
    ("docs/phases/G0R4R2/", "docs/phases/G0R4R3/"),
    ("docs/integrity/session_logs/G0R4R2/", "docs/integrity/session_logs/G0R4R3/"),
    ("docs/integrity/protected_hashes/G0R4R2/", "docs/integrity/protected_hashes/G0R4R3/"),
    ("EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY",
     "EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY"),
    ("G0R4R2_CODEX_INPUT_BUNDLE", "G0R4R3_CODEX_INPUT_BUNDLE"),
    ("G0R4R2_CODEX_INPUT_MANIFEST", "G0R4R3_CODEX_INPUT_MANIFEST"),
    ("tools/complete_g0r4r2_submission.py", "tools/complete_g0r4r3_submission.py"),
    ("tests/test_g0r4r2_submission_integrity.py", "tests/test_g0r4r3_submission_integrity.py"),
    ("EXTERNAL_REVIEW_APPROVAL_G0R4R2_TEMPLATE.md", "EXTERNAL_REVIEW_APPROVAL_G0R4R3_TEMPLATE.md"),
    ("g0r4r2_decision_cockpit_snapshot.json", "g0r4r3_decision_cockpit_snapshot.json"),
    ("deliver_g0r4r2_outgoing_submission", "deliver_g0r4r3_outgoing_submission"),
    ("G0R4R2_OUTGOING_REL", "G0R4R3_OUTGOING_REL"),
    ("outgoing_external_reviews/g0r4r2", "outgoing_external_reviews/g0r4r3"),
    ("296e20abd3d88ca9f6c7138b97ec2a19e9a51836406393067a8e6282b9d16af2",
     "f6c65b8afcc18f216fa64bed2a276d90ebb0cb135badacfa8d942632d5d54ad4"),
    ("fe2a76e49bf6e6d385e0cf5666f2d74317ab68bfed0f473f2b8f1bb6bf98908f",
     "b974af8cd9bbaa22a8f018ab8f67ecdcb00b3f2d4a18345aca7ddc8d43632d85"),
    ("fix: resubmit G0R4R2 with verbatim authoritative baseline",
     "fix: G0R4R3 final blob-zip verbatim and audit-input completeness remediation"),
    ("G0R4R2_", "G0R4R3_"),
    ("g0r4r2_", "g0r4r3_"),
    ("G0R4R3R3", "G0R4R3"),
    ("g0r4r3r3", "g0r4r3"),
]
for old, new in replacements:
    text = text.replace(old, new)

# Fix over-replaced audit path segments (g0r4r3_approval for G0R4R2 inputs)
text = text.replace(
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
)
text = text.replace(
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md.sha256",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
)

# Inject extract dir and gitattributes constants after BASELINE_ORIGINALS_DIR
inject_after = "BASELINE_ORIGINALS_DIR = INPUT_DIR / \"baseline_originals\""
inject_block = """
EXTRACT_DIR = INPUT_DIR / "extracted"
GIT_BYTE_PRESERVE_PATHS: Tuple[str, ...] = (
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md",
    "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md.sha256",
)
MANDATORY_AUDIT_ZIP_PATHS: Tuple[str, ...] = GIT_BYTE_PRESERVE_PATHS[3:]
EXPECTED_VERBATIM_INPUTS_NAME = "CODEX_G0R4R3_EXPECTED_VERBATIM_INPUTS.json"
"""
text = text.replace(inject_after, inject_after + inject_block)

# Replace REVIEW_INPUT_MAPPINGS block
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
        f"control/external_reviews/g0r4r2_approval/{APPROVAL_DOC_NAME}",
    ),
    (
        APPROVAL_SIDECAR_NAME,
        f"control/external_reviews/g0r4r2_approval/{APPROVAL_SIDECAR_NAME}",
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

# Fix EXTRACTED_REQUIRED_FILES - use extracted/ sources
old_extracted = """EXTRACTED_REQUIRED_FILES: Tuple[str, ...] = (
    "EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",
    "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",
    BASELINE_ZIP_NAME,
    BASELINE_SIDECAR_NAME,
    BASELINE_MANIFEST_NAME,
    APPROVAL_DOC_NAME,
    APPROVAL_SIDECAR_NAME,
    BUNDLE_MANIFEST_NAME,
)"""
new_extracted = """EXTRACTED_REQUIRED_FILES: Tuple[str, ...] = (
    BUNDLE_MANIFEST_NAME,
    APPROVAL_DOC_NAME,
    APPROVAL_SIDECAR_NAME,
    "EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    BASELINE_ZIP_NAME,
    BASELINE_SIDECAR_NAME,
    BASELINE_MANIFEST_NAME,
    "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
)"""
text = text.replace(old_extracted, new_extracted)

# Remove verbatim verification name - use expected verbatim
text = text.replace(
    'VERBATIM_VERIFICATION_NAME = "CODEX_G0R4R3_AUTHORITATIVE_BASELINE_VERBATIM_VERIFICATION.json"',
    "",
)

# Fix authorized commit paths tail
old_auth_tail = """    "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",
    f"control/external_reviews/g0r4r2_approval/{APPROVAL_DOC_NAME}",
    f"control/external_reviews/g0r4r2_approval/{APPROVAL_SIDECAR_NAME}",
)"""
new_auth_tail = """    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    f"control/external_reviews/g0r4r3_approval/{APPROVAL_DOC_NAME}",
    f"control/external_reviews/g0r4r3_approval/{APPROVAL_SIDECAR_NAME}",
    f"docs/phases/G0R4R3/{EXPECTED_VERBATIM_INPUTS_NAME}",
    "docs/phases/G0R4R3/CODEX_G0R4R3_GIT_ATTRIBUTE_BYTE_PRESERVATION_VERIFICATION.json",
)"""
text = text.replace(old_auth_tail, new_auth_tail)

# Remove wrong verbatim verification from authorized paths if present
text = text.replace(
    '    "docs/phases/G0R4R3/CODEX_G0R4R3_AUTHORITATIVE_BASELINE_VERBATIM_VERIFICATION.json",\n',
    "",
)

out = Path(__file__).resolve().parents[1] / "tools/complete_g0r4r3_submission.py"
out.write_text(text, encoding="utf-8")
print("wrote", out, "bytes", out.stat().st_size)
