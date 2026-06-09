"""Verify V4R3 git checkpoint matches codex_v4r3_final_build_gate_review.zip."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
GIT = r"C:\Program Files\Git\cmd\git.exe"
ZIP_NAME = "codex_v4r3_final_build_gate_review.zip"
EXPECTED_ZIP_HASH = "ea345927f370bd8cf0807b77addd7a2413025af8cf89ebb32e3b3b828b070999"
V4R3_CHECKPOINT = "50d6cfbced22032012db499c0756427b121597d4"
OUT = doc_rel("CODEX_V5_V4R3_BASELINE_VERIFICATION.json")

COMPARE_PATHS = [
    "aa_decision_cockpit_viewmodel.py",
    "aa_decision_cockpit_gui.py",
    "aa_decision_cockpit_export.py",
    "aa_dashboard_qt_window.py",
    "aa_vision_controller.py",
    "aa_vision_phase_catalog.py",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/phase_catalog.json",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    ".cursor/hooks.json",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def git_show(commit: str, rel: str) -> bytes | None:
    proc = subprocess.run(
        [GIT, "show", f"{commit}:{rel.replace(chr(92), '/')}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def main() -> Dict[str, object]:
    zip_path = ROOT / ZIP_NAME
    if not zip_path.is_file():
        raise SystemExit(f"Missing review zip: {ZIP_NAME}")
    zip_hash = sha256_file(zip_path)
    if zip_hash != EXPECTED_ZIP_HASH:
        raise SystemExit(f"V4R3 zip hash mismatch: {zip_hash} != {EXPECTED_ZIP_HASH}")

    mismatches: List[Dict[str, str]] = []
    compared: List[str] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        for rel in COMPARE_PATHS:
            norm = rel.replace("\\", "/")
            if norm not in names:
                mismatches.append({"path": norm, "reason": "missing_in_zip"})
                continue
            commit_blob = git_show(V4R3_CHECKPOINT, norm)
            if commit_blob is None:
                mismatches.append({"path": norm, "reason": "missing_in_checkpoint_commit"})
                continue
            z_hash = sha256_bytes(normalize_text_bytes(zf.read(norm)))
            c_hash = sha256_bytes(normalize_text_bytes(commit_blob))
            compared.append(norm)
            if z_hash != c_hash:
                mismatches.append({"path": norm, "reason": "hash_mismatch", "zip": z_hash, "commit": c_hash})

    result = {
        "zip": ZIP_NAME,
        "zip_sha256": zip_hash,
        "expected_zip_sha256": EXPECTED_ZIP_HASH,
        "checkpoint_commit": V4R3_CHECKPOINT,
        "paths_compared": compared,
        "ok": len(mismatches) == 0,
        "mismatches": mismatches,
    }
    (ROOT / OUT).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if mismatches:
        raise SystemExit(f"V4R3 baseline verification failed: {mismatches}")
    print(f"V4R3 baseline OK commit={V4R3_CHECKPOINT[:8]} paths={len(compared)}")
    return result


if __name__ == "__main__":
    main()
