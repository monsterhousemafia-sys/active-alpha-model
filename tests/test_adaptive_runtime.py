from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from aa_adaptive_runtime import (
    AdaptiveContext,
    build_adaptive_plan,
    load_adaptive_config,
    resolve_adaptive_price_source,
)


def test_resolve_adaptive_price_source_auto_fictive_when_offline(monkeypatch):
    monkeypatch.setattr("aa_adaptive_runtime.probe_internet_prices", lambda **k: False)
    src, reason = resolve_adaptive_price_source({"AA_PRICE_DATA_SOURCE": "auto"}, internet_ok=False)
    assert src == "fictive"
    assert "fictive" in reason


def test_resolve_adaptive_price_source_auto_internet_when_online(monkeypatch):
    monkeypatch.setattr("aa_adaptive_runtime.probe_internet_prices", lambda **k: True)
    src, reason = resolve_adaptive_price_source({"AA_PRICE_DATA_SOURCE": "auto"}, internet_ok=True)
    assert src == "internet"


def test_build_adaptive_plan_aggressive_on_regime_drift():
    ctx = AdaptiveContext(r3_regime_match=False, price_current=True, internet_ok=False)
    cfg = load_adaptive_config(Path("."))
    plan = build_adaptive_plan(ctx, adaptive_cfg=cfg, env={"AA_PRICE_DATA_SOURCE": "auto"})
    assert plan.mode == "AGGRESSIVE"
    assert plan.refinement_overrides.get("force_prices") is True
    assert plan.loop_interval_s <= 120


def test_build_adaptive_plan_schedules_retrain_when_stale():
    ctx = AdaptiveContext(
        integrity_status="NOT_VALIDATED",
        batch_busy=False,
        training_log_age_hours=200.0,
    )
    cfg = dict(load_adaptive_config(Path(".")))
    cfg["auto_exemplar_retrain_when_stale"] = True
    plan = build_adaptive_plan(ctx, adaptive_cfg=cfg, env={})
    assert "exemplar_retrain" in plan.actions


def test_adapt_operational_context(tmp_path, monkeypatch):
    (tmp_path / "control").mkdir()
    save_cfg = tmp_path / "control" / "adaptive_runtime.json"
    save_cfg.write_text('{"enabled": true, "price_data_mode": "fictive"}', encoding="utf-8")

    monkeypatch.setattr("aa_adaptive_runtime.probe_internet_prices", lambda **k: False)
    monkeypatch.setattr(
        "aa_adaptive_runtime.assess_adaptive_context",
        lambda *_a, **_k: AdaptiveContext(internet_ok=False, price_current=False),
    )

    from aa_adaptive_runtime import adapt_operational_context

    env, ref, plan = adapt_operational_context(tmp_path, {"AA_PRICE_DATA_SOURCE": "auto"}, {})
    assert env["AA_PRICE_DATA_SOURCE"] == "fictive"
    assert (tmp_path / "control" / "adaptive_runtime_state.json").is_file()
