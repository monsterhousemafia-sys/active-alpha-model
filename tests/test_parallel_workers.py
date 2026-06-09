from __future__ import annotations

import numpy as np
import pandas as pd

import aa_features as aaf
import aa_parallel as aap
import active_alpha_model as aam


def test_resolve_n_jobs_serial_values():
    cfg = aam.BacktestConfig(cpu_cores=16, system_ram_gb=64, n_jobs="1")
    assert aam.resolve_n_jobs("1", cfg) == 1
    assert aam.resolve_n_jobs("serial", cfg) == 1
    assert aam.resolve_parallel_workers(cfg) == 1


def test_resolve_n_jobs_explicit_integer():
    cfg = aam.BacktestConfig(cpu_cores=16, system_ram_gb=64, n_jobs="4")
    assert aam.resolve_n_jobs("4", cfg) == 4
    assert aam.resolve_parallel_workers(cfg) == 4


def test_resolve_n_jobs_auto_respects_physical_core_cap():
    cfg = aam.BacktestConfig(cpu_cores=16, system_ram_gb=64, parallel_profile="high", n_jobs="auto")
    workers = aam.resolve_n_jobs("auto", cfg, backend="process")
    assert 1 <= workers <= 16


def test_resolve_n_jobs_auto_scales_down_with_large_feature_table():
    cfg = aam.BacktestConfig(cpu_cores=16, system_ram_gb=64, parallel_profile="high", n_jobs="auto")
    workers_small = aam.resolve_n_jobs("auto", cfg, feature_table_gb=0.1, backend="process")
    workers_large = aam.resolve_n_jobs("auto", cfg, feature_table_gb=12.0, backend="process")
    assert workers_large <= workers_small
    assert workers_large >= 1


def _synthetic_ohlcv(n_days: int = 280, start: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    close = start + np.linspace(0, 20, n_days) + np.sin(np.linspace(0, 8, n_days))
    volume = np.full(n_days, 1_000_000.0)
    return pd.DataFrame({"Close": close, "Volume": volume}, index=dates)


def test_build_feature_table_reuses_active_pool(monkeypatch):
    pool_create_count = {"n": 0}
    real_mp_pool = aam._mp_pool

    def counting_mp_pool(*args, **kwargs):
        pool_create_count["n"] += 1
        return real_mp_pool(*args, **kwargs)

    monkeypatch.setattr(aap, "_mp_pool", counting_mp_pool)
    monkeypatch.setattr(aaf, "_mp_pool", counting_mp_pool)

    class FakePool:
        def imap_unordered(self, func, tasks, chunksize=1):
            for item in tasks:
                yield func(item)

    monkeypatch.setattr(aap, "_ACTIVE_POOL", FakePool())
    monkeypatch.setattr(aaf, "_ACTIVE_POOL", FakePool())

    loaded = {"n": 0}

    class FakeSession:
        workers = 2
        _pool = FakePool()

        def __init__(self, cfg: aam.BacktestConfig) -> None:
            self.cfg = cfg

        def load_feature_engineering_state(self, bench_close, bench_features, sector_index) -> None:
            loaded["n"] += 1
            aaf._feature_engineering_initializer(bench_close, bench_features, sector_index, self.cfg)

    cfg = aam.BacktestConfig(
        n_jobs="2",
        cpu_cores=2,
        system_ram_gb=64,
        horizon=5,
        membership_mode="off",
        universe_mode="static",
    )
    data = {
        "SPY": _synthetic_ohlcv(),
        "AAPL": _synthetic_ohlcv(start=150.0),
        "MSFT": _synthetic_ohlcv(start=200.0),
    }

    features, _bench, returns = aam.build_feature_table(
        data, "SPY", cfg, pool_session=FakeSession(cfg)
    )
    assert not features.empty
    assert "SPY" in returns.columns
    assert loaded["n"] == 1
    assert pool_create_count["n"] == 0


def test_process_pool_session_rebinds_worker_state():
    cfg = aam.BacktestConfig(n_jobs="1", cpu_cores=1, horizon=5, membership_mode="off")
    bench_close = pd.Series([100.0, 101.0], index=pd.to_datetime(["2020-06-01", "2020-06-02"]))
    bench_features = pd.DataFrame(index=bench_close.index)
    features = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-06-01", "2020-06-02"]),
            "ticker": ["AAPL", "AAPL"],
            "close": [100.0, 101.0],
        }
    )
    returns = pd.DataFrame({"AAPL": [0.01, 0.02]}, index=pd.to_datetime(["2020-06-01", "2020-06-02"]))

    with aam.ProcessPoolSession(cfg) as session:
        session.load_feature_engineering_state(bench_close, bench_features, {})
        assert aam._CTX.feat_cfg is cfg
        session.load_backtest_state(features, returns)
        assert aam._CTX.features is not None
        assert len(aam._CTX.features) == 2
