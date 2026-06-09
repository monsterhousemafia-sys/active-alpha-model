from pathlib import Path
from unittest.mock import patch

from analytics.r3_daytrading_data_care import run_daytrading_data_care


def test_daytrading_data_care_delegates_kernel(tmp_path: Path) -> None:
    kernel_doc = {
        "steps": [
            {"id": "quotes", "ok": True},
            {"id": "daytrading_snapshot", "ok": True},
            {"id": "cycle", "ok": True},
            {"id": "learning_capture", "ok": True},
        ],
        "steps_ok": 4,
        "headline_de": "kernel ok",
    }
    with patch(
        "analytics.r3_ops_kernel.run_ops_pipeline",
        return_value=kernel_doc,
    ), patch(
        "integrations.trading212.t212_trust_gate.assess_t212_trust_from_root",
        return_value={"trusted": True, "orders_allowed": True},
    ):
        doc = run_daytrading_data_care(tmp_path, persist=True)
    assert doc.get("ok") is True
    assert doc.get("kernel_phase") == "data_care"
    assert (tmp_path / "evidence/r3_daytrading_data_care_latest.json").is_file()
