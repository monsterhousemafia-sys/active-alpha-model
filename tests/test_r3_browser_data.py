"""R3 lokaler Browser — Internet-Ingest für Prognose-Daten."""
import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_browser_data import (
    apply_session_browser_env,
    ingest_prognosis_data_from_internet,
    load_browser_data_policy,
    maybe_fast_ingest_for_hub,
)


def test_browser_policy_internet_first() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_browser_data_policy(root)
    assert policy.get("internet_first") is True
    assert policy.get("price_source") == "internet"


def test_apply_session_browser_env_sets_internet(monkeypatch) -> None:
    monkeypatch.delenv("AA_PRICE_DATA_SOURCE", raising=False)
    patch = apply_session_browser_env({"internet_first": True, "price_source": "internet"})
    assert patch.get("AA_PRICE_DATA_SOURCE") == "internet"


def test_ingest_fails_closed_without_internet(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_browser_data_policy.json").write_text(
        '{"internet_first":true,"price_source":"internet","mode_de":"test"}',
        encoding="utf-8",
    )
    with patch("aa_adaptive_runtime.probe_internet_prices", return_value=False):
        doc = ingest_prognosis_data_from_internet(tmp_path, persist=True)
    assert doc.get("ok") is False
    assert doc.get("internet_ok") is False
    assert (tmp_path / "evidence/r3_browser_ingest_latest.json").is_file()


def test_maybe_fast_ingest_skips_when_ok(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "control/r3_browser_data_policy.json").write_text(
        '{"fast_ingest_on_hub_open":true}',
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_browser_ingest_latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "price_current": True,
                "internet_ok": True,
                "updated_at_utc": fresh,
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "analytics.r3_quote_keepalive.assess_quote_freshness",
        return_value={"needs_refresh": False},
    ):
        doc = maybe_fast_ingest_for_hub(tmp_path)
    assert doc.get("ok") is True
