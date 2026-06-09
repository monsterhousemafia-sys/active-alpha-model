"""Copy external-review submission artefacts to a single folder and open it."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

if sys.platform == "win32":
    _OPEN = lambda folder: subprocess.run(["explorer", str(folder)], check=False)
else:
    _OPEN = lambda folder: subprocess.run(["xdg-open", str(folder)], check=False)

G0R4R2_OUTGOING_REL = "outgoing_external_reviews/g0r4r2"
G0R4R3_OUTGOING_REL = "outgoing_external_reviews/g0r4r3"


def submission_folder_rel(phase_label: str) -> str:
    return f"{phase_label}_SUBMISSION_FOR_REVIEWER"


def prepare_and_open_review_submission_folder(
    *,
    root: Path,
    phase_label: str,
    zip_path: Path,
    sidecar_path: Path,
    attestation_path: Optional[Path] = None,
    verify_report_path: Optional[Path] = None,
) -> Path:
    """Stage reviewer files under ``<PHASE>_SUBMISSION_FOR_REVIEWER`` and open it."""
    dest = root / submission_folder_rel(phase_label)
    dest.mkdir(parents=True, exist_ok=True)
    artefacts: Sequence[Path] = (
        zip_path,
        sidecar_path,
        *(p for p in (attestation_path, verify_report_path) if p is not None),
    )
    for src in artefacts:
        if not src.is_file():
            raise FileNotFoundError(f"review submission artefact missing: {src}")
        shutil.copy2(src, dest / src.name)
    _OPEN(dest.resolve())
    return dest


def deliver_g0r4r2_outgoing_submission(
    *,
    root: Path,
    zip_path: Path,
    sidecar_path: Path,
    attestation_path: Path,
    verify_report_path: Path,
) -> Path:
    """Stage the four G0R4R2 reviewer files under ``outgoing_external_reviews/g0r4r2``."""
    dest = root / G0R4R2_OUTGOING_REL
    dest.mkdir(parents=True, exist_ok=True)
    for existing in dest.iterdir():
        if existing.is_file():
            existing.unlink()
    artefacts = (zip_path, sidecar_path, attestation_path, verify_report_path)
    for src in artefacts:
        if not src.is_file():
            raise FileNotFoundError(f"G0R4R2 submission artefact missing: {src}")
        if "g0r4r2" not in src.name.lower():
            raise ValueError(f"wrong-phase output filename (expected g0r4r2): {src.name}")
        shutil.copy2(src, dest / src.name)
    _OPEN(dest.resolve())
    return dest


def deliver_g0r4r3_outgoing_submission(
    *,
    root: Path,
    zip_path: Path,
    sidecar_path: Path,
    attestation_path: Path,
    verify_report_path: Path,
) -> Path:
    """Stage the four G0R4R3 reviewer files under ``outgoing_external_reviews/g0r4r3``."""
    dest = root / G0R4R3_OUTGOING_REL
    dest.mkdir(parents=True, exist_ok=True)
    for existing in dest.iterdir():
        if existing.is_file():
            existing.unlink()
    artefacts = (zip_path, sidecar_path, attestation_path, verify_report_path)
    for src in artefacts:
        if not src.is_file():
            raise FileNotFoundError(f"G0R4R3 submission artefact missing: {src}")
        if "g0r4r3" not in src.name.lower():
            raise ValueError(f"wrong-phase output filename (expected g0r4r3): {src.name}")
        shutil.copy2(src, dest / src.name)
    _OPEN(dest.resolve())
    return dest
