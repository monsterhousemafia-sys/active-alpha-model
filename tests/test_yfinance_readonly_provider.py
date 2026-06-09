from research.p12a.providers.yfinance_readonly import ReadOnlyYFinanceProvider


def test_fetch_quotes_returns_dataframe_for_spy() -> None:
    provider = ReadOnlyYFinanceProvider()
    df = provider.fetch_quotes(["SPY"])
    if df.empty:
        return  # network/yfinance may be unavailable in CI
    assert "ticker" in df.columns
    assert float(df.iloc[0]["last"]) > 0
