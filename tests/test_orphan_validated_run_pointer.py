from __future__ import annotations

import json
from pathlib import Path

from aa_ops_validation import assess_analytical_status, validate_analytical_integrity
from tests.test_integrity import _seed_validated_run


def test_orphan_pointer_uses_out_dir_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "model"
    _seed_validated_run(out)
    pointer = out / "latest_validated_run.json"
    doc = json.loads(pointer.read_text(encoding="utf-8"))
    doc["run_dir"] = str(tmp_path / "runs" / "missing_run")
    pointer.write_text(json.dumps(doc), encoding="utf-8")
    ok, reason, run_id = validate_analytical_integrity(out)
    assert ok, reason
    assert assess_analytical_status(out)[0] == "PASS"
