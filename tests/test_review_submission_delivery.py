from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.review_submission_delivery import prepare_and_open_review_submission_folder, submission_folder_rel


def test_submission_folder_rel() -> None:
    assert submission_folder_rel("G0R4R") == "G0R4R_SUBMISSION_FOR_REVIEWER"


def test_prepare_and_open_copies_artefacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        "tools.review_submission_delivery._OPEN",
        lambda folder: opened.append(str(folder)),
    )
    zip_path = tmp_path / "review.zip"
    sidecar_path = tmp_path / "review.zip.sha256"
    attestation_path = tmp_path / "attestation.json"
    zip_path.write_bytes(b"zip")
    sidecar_path.write_text("abc  review.zip\n", encoding="utf-8")
    attestation_path.write_text("{}", encoding="utf-8")

    dest = prepare_and_open_review_submission_folder(
        root=tmp_path,
        phase_label="TEST",
        zip_path=zip_path,
        sidecar_path=sidecar_path,
        attestation_path=attestation_path,
    )

    assert dest == tmp_path / "TEST_SUBMISSION_FOR_REVIEWER"
    assert (dest / zip_path.name).read_bytes() == b"zip"
    assert (dest / sidecar_path.name).read_text(encoding="utf-8") == "abc  review.zip\n"
    assert json.loads((dest / attestation_path.name).read_text(encoding="utf-8")) == {}
    assert opened == [str(dest.resolve())]
