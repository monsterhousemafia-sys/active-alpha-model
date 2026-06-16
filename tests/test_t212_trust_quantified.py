"""T212 Trust quantified evidence."""
from __future__ import annotations

from analytics.t212_trust_quantified import build_t212_trust_quantified


def test_quantified_untrusted_has_blockers(tmp_path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    import json

    (tmp_path / "control/t212_trust_policy.json").write_text(
        json.dumps({"max_stale_sync_s": 900, "max_stale_display_s": 1800, "fail_closed": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "credentials_configured": True,
                "broker_status": "CONNECTION_FAILED_RETRY_AVAILABLE",
                "last_sync_utc": None,
                "cash_eur": None,
                "connected": False,
                "bonded": True,
                "message_de": "⏱ Bitte 60 Sekunden warten.",
            }
        ),
        encoding="utf-8",
    )
    doc = build_t212_trust_quantified(tmp_path, persist=True)
    assert doc["trusted"] is False
    assert len(doc["blockers_de"]) >= 3
    assert doc["measurements"]["rate_limit_wait_s"] == 60
    assert (tmp_path / "evidence/t212_trust_quantified_latest.json").is_file()
