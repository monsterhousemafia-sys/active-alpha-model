from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.federation_dependency import assess_federation_dependency, classify_compute_workers


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def test_classify_remote_vs_local() -> None:
    workers = [
        {"role": "king", "hostname": "king-host"},
        {"role": "compute", "hostname": "king-host"},
        {"role": "compute", "hostname": "friend-pc", "remote_join": True},
    ]
    cls = classify_compute_workers(workers)
    assert cls["compute_total"] == 2
    assert cls["remote_compute"] == 1
    assert cls["local_only_compute"] == 1


def test_assess_high_risk_local_only(tmp_path: Path) -> None:
    now = _now()
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"enabled": True, "join_token": "x" * 32}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/preview_federation.json").write_text(
        json.dumps(
            {
                "workers": {
                    "k": {"role": "king", "hostname": "same", "last_seen_utc": now},
                    "c": {"role": "compute", "hostname": "same", "last_seen_utc": now},
                }
            }
        ),
        encoding="utf-8",
    )
    doc = assess_federation_dependency(tmp_path)
    assert doc.get("risk_level") == "high"
    assert doc.get("adoption_done") is False
    assert int(doc.get("adoption_pct_honest") or 0) == 25
