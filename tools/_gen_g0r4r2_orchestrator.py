#!/usr/bin/env python3
"""One-off generator for complete_g0r4r2_submission.py from G0R4R template."""
from pathlib import Path

src = Path(__file__).resolve().parents[1] / "tools/complete_g0r4r_submission.py"
text = src.read_text(encoding="utf-8")
replacements = [
    ('"""G0R4R verbatim external review chain resubmission orchestrator."""', '"""G0R4R2 verbatim authoritative baseline resubmission orchestrator."""'),
    ("write_g0r4r_review_snapshot", "write_g0r4r2_review_snapshot"),
    ("G0R4R_VERBATIM_EXTERNAL_REVIEW_CHAIN_RESUBMISSION", "G0R4R2_VERBATIM_AUTHORITATIVE_BASELINE_RESUBMISSION"),
    ("incoming_external_reviews/g0r4r", "incoming_external_reviews/g0r4r2"),
    ("remediation/g0r4r-verbatim-external-review-chain", "remediation/g0r4r2-verbatim-authoritative-baseline-resubmission"),
    ("codex_g0r4r_verbatim_external_review_chain_resubmission", "codex_g0r4r2_verbatim_authoritative_baseline_resubmission"),
    ("CODEX_G0R4R_", "CODEX_G0R4R2_"),
    ("G0R4R-CHANGE_MANIFEST.json", "G0R4R2-CHANGE_MANIFEST.json"),
    ("docs/phases/G0R4R/", "docs/phases/G0R4R2/"),
    ("docs/integrity/session_logs/G0R4R/", "docs/integrity/session_logs/G0R4R2/"),
    ("docs/integrity/protected_hashes/G0R4R/", "docs/integrity/protected_hashes/G0R4R2/"),
    ("EXTERNAL_REVIEW_APPROVAL_G0R4R_REMEDIATION_RESUBMISSION_ONLY", "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY"),
    ("G0R4R_CODEX_INPUT_BUNDLE", "G0R4R2_CODEX_INPUT_BUNDLE"),
    ("G0R4R_CODEX_INPUT_MANIFEST", "G0R4R2_CODEX_INPUT_MANIFEST"),
    ("G0R4R_VERBATIM_EXTERNAL_REVIEW_INPUTS", "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS"),
    ("tools/complete_g0r4r_submission.py", "tools/complete_g0r4r2_submission.py"),
    ("tests/test_g0r4r_submission_integrity.py", "tests/test_g0r4r2_submission_integrity.py"),
    ("EXTERNAL_REVIEW_APPROVAL_G0R4R_TEMPLATE.md", "EXTERNAL_REVIEW_APPROVAL_G0R4R2_TEMPLATE.md"),
    ("g0r4r_decision_cockpit_snapshot.json", "g0r4r2_decision_cockpit_snapshot.json"),
    ("control/external_reviews/g0r4r_approval/", "control/external_reviews/g0r4r2_approval/"),
    ("498cc262f6dac2696fd9d93b4ba158ddee78791069d9f2a2a72c571407242ec6", "296e20abd3d88ca9f6c7138b97ec2a19e9a51836406393067a8e6282b9d16af2"),
    ("e38526ce71ef4cd8c893e59420d7b3918ded5166ba7d2aee6ade7d28bdd1fc35", "fe2a76e49bf6e6d385e0cf5666f2d74317ab68bfed0f473f2b8f1bb6bf98908f"),
    ("fix: resubmit G0R4R with verbatim external review chain", "fix: resubmit G0R4R2 with verbatim authoritative baseline"),
    ("G0R4R_", "G0R4R2_"),
    ("G0R4R2R2", "G0R4R2"),
    ("g0r4r2r2", "g0r4r2"),
]
for old, new in replacements:
    text = text.replace(old, new)

# G0R4R2-specific constants block insertion marker
baseline_block = '''
BASELINE_ZIP_NAME = "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip"
BASELINE_SIDECAR_NAME = f"{BASELINE_ZIP_NAME}.sha256"
BASELINE_MANIFEST_NAME = "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_MANIFEST.json"
BASELINE_ZIP = INPUT_DIR / BASELINE_ZIP_NAME
BASELINE_EXPECTED_TARGET_HASHES: Dict[str, str] = {
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md": "efaf57ec98345f5e571c6694d6b8aba64e40205a4ed85dfdbcdeba336ea90ec3",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md": "08a18385f8e6498b0c63437c372ec4d43980e70e8ad32e5ca6220e9a30b1c97f",
    "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json": (
        "291b1d75d0774dff20db4cd2efc113239254adfcd3a0193b7a5d1bb4180abd17"
    ),
}
BASELINE_VERBATIM_MAPPINGS: Tuple[Tuple[str, str], ...] = (
    ("EXTERNAL_REVIEW_APPROVAL_FINAL.md", "EXTERNAL_REVIEW_APPROVAL_FINAL.md"),
    ("V5R_EXTERNAL_ACCEPTANCE_REPORT.md", "V5R_EXTERNAL_ACCEPTANCE_REPORT.md"),
    (
        "CODEX_V5R_PROTECTED_HASHES_AFTER.json",
        "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json",
    ),
)
REVIEW_INPUT_MAPPINGS: Tuple[Tuple[str, str], ...] = (
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
)
VERBATIM_VERIFICATION_NAME = "CODEX_G0R4R2_AUTHORITATIVE_BASELINE_VERBATIM_VERIFICATION.json"
'''

text = text.replace(
    "G0R4R2_COMMIT_MSG = ",
    baseline_block + "\nG0R4R2_COMMIT_MSG = ",
)

# Fix required input files tuple
old_req = '''REQUIRED_INPUT_FILES: Tuple[str, ...] = (
    BUNDLE_ZIP_NAME,
    BUNDLE_SIDECAR_NAME,
    BUNDLE_MANIFEST_NAME,
    APPROVAL_DOC_NAME,
    APPROVAL_SIDECAR_NAME,
    "EXTERNAL_REVIEW_DECISION_G0R4_REMEDIATION_REQUIRED.md",
    "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4.sha256",
    "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip",
)'''
new_req = '''REQUIRED_INPUT_FILES: Tuple[str, ...] = (
    BUNDLE_ZIP_NAME,
    BUNDLE_SIDECAR_NAME,
    BUNDLE_MANIFEST_NAME,
    APPROVAL_DOC_NAME,
    APPROVAL_SIDECAR_NAME,
    "EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",
    "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",
    BASELINE_ZIP_NAME,
    BASELINE_SIDECAR_NAME,
    BASELINE_MANIFEST_NAME,
)'''
text = text.replace(old_req, new_req)

# Remove old verbatim external mappings section through VERBATIM_ZIP_ONLY_SOURCES
start = text.index("VERBATIM_EXTERNAL_MAPPINGS:")
end = text.index("PREVIOUSLY_DRIFTED_PATHS")
text = text[:start] + text[end:]

# Fix authorized commit paths - replace the external review section at end of tuple
old_paths = '''    "control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G0_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G1_NOT_APPROVED.md",
    "control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_SUMMARY_G0_G1.md",
    "control/external_reviews/g0r_rejection/EXTERNAL_REVIEW_DECISION_G0R_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r3_rejection/EXTERNAL_REVIEW_DECISION_G0R3_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4_rejection/EXTERNAL_REVIEW_DECISION_G0R4_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4.sha256",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
)'''
new_paths = '''    "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md",
    "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json",
    "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",
    f"control/external_reviews/g0r4r2_approval/{APPROVAL_DOC_NAME}",
    f"control/external_reviews/g0r4r2_approval/{APPROVAL_SIDECAR_NAME}",
    "docs/phases/G0R4R2/CODEX_G0R4R2_AUTHORITATIVE_BASELINE_VERBATIM_VERIFICATION.json",
)'''
text = text.replace(old_paths, new_paths)

# Rename verification artifact references
text = text.replace(
    "CODEX_G0R4R2_EXTERNAL_REVIEW_INPUT_VERBATIM_VERIFICATION.json",
    "CODEX_G0R4R2_AUTHORITATIVE_BASELINE_VERBATIM_VERIFICATION.json",
)

out = Path(__file__).resolve().parents[1] / "tools/complete_g0r4r2_submission.py"
out.write_text(text, encoding="utf-8")
print("wrote", out)
