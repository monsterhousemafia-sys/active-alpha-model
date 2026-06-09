from analytics.h1_benchmark import estimate_h1_benchmark_eta_de


def test_estimate_h1_benchmark_eta_daily_king_h1():
    eta = estimate_h1_benchmark_eta_de(rebalance_dates=1867)
    assert "45" in eta or "60" in eta
    assert "1867" in eta


def test_estimate_h1_benchmark_eta_short_run():
    eta = estimate_h1_benchmark_eta_de(rebalance_dates=120)
    assert "5" in eta
    assert "12" in eta
