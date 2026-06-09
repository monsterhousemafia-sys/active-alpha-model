"""Intraday data quality gates for P5 replay/live feeds."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from aa_market_data import BarFrame, QuoteFrame, ReplayMarketDataProvider


@dataclass
class IntradayQualityResult:
    status: str  # PASS | FAIL
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duplicate_bars: int = 0
    non_monotonic_bars: int = 0
    invalid_price_rows: int = 0
    negative_spread_rows: int = 0
    stale_quote_rows: int = 0
    missing_spy: bool = False
    tickers_checked: int = 0

    @property
    def passed(self) -> bool:
        return self.status == "PASS" and not self.errors


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def validate_bars(bars: BarFrame, *, ticker: str) -> IntradayQualityResult:
    errors: List[str] = []
    warnings: List[str] = []
    if bars is None or bars.empty:
        return IntradayQualityResult(status="FAIL", errors=[f"{ticker}: empty bar series"], missing_spy=ticker == "SPY")

    dup = int(bars.index.duplicated(keep=False).sum())
    if dup:
        errors.append(f"{ticker}: duplicate bar timestamps ({dup})")
    if not bars.index.is_monotonic_increasing:
        errors.append(f"{ticker}: non-monotonic timestamps")
        non_mono = 1
    else:
        non_mono = 0

    invalid = 0
    for col in ("open", "high", "low", "close"):
        if col in bars.columns:
            invalid += int((pd.to_numeric(bars[col], errors="coerce") <= 0).sum())
    if "high" in bars.columns and "low" in bars.columns:
        invalid += int((bars["high"] < bars["low"]).sum())
    if invalid:
        errors.append(f"{ticker}: invalid price rows ({invalid})")

    # Expected 5m spacing within contiguous RTH blocks (warn only on internal gaps)
    if len(bars) > 1:
        deltas = bars.index.to_series().diff().dropna()
        gap_count = int((deltas > pd.Timedelta(minutes=6)).sum())
        if gap_count:
            warnings.append(f"{ticker}: possible missing bars ({gap_count} gaps >6min)")

    status = "PASS" if not errors else "FAIL"
    return IntradayQualityResult(
        status=status,
        errors=errors,
        warnings=warnings,
        duplicate_bars=dup,
        non_monotonic_bars=non_mono,
        invalid_price_rows=invalid,
        tickers_checked=1,
        missing_spy=False,
    )


def validate_quotes(quotes: QuoteFrame, *, stale_after_minutes: int = 60, reference: Optional[pd.Timestamp] = None) -> IntradayQualityResult:
    errors: List[str] = []
    warnings: List[str] = []
    if quotes is None or quotes.empty:
        return IntradayQualityResult(status="PASS", warnings=["no quotes to validate"])
    ref = pd.Timestamp(reference or pd.Timestamp.now(tz="UTC"))
    stale = 0
    neg_spread = 0
    for rec in quotes.to_dict(orient="records"):
        bid = float(rec.get("bid", float("nan")))
        ask = float(rec.get("ask", float("nan")))
        if pd.notna(bid) and pd.notna(ask) and ask < bid:
            neg_spread += 1
        ts = pd.Timestamp(rec.get("timestamp"))
        if pd.notna(ts) and (ref - ts) > pd.Timedelta(minutes=stale_after_minutes):
            stale += 1
    if neg_spread:
        errors.append(f"negative or inconsistent spreads ({neg_spread})")
    if stale:
        warnings.append(f"stale quotes ({stale})")
    status = "PASS" if not errors else "FAIL"
    return IntradayQualityResult(
        status=status,
        errors=errors,
        warnings=warnings,
        negative_spread_rows=neg_spread,
        stale_quote_rows=stale,
        tickers_checked=len(quotes),
    )


def validate_replay_dataset(
    provider: ReplayMarketDataProvider,
    *,
    tickers: Sequence[str],
    require_spy: bool = True,
    reference: Optional[pd.Timestamp] = None,
) -> IntradayQualityResult:
    errors: List[str] = []
    warnings: List[str] = []
    duplicate_bars = invalid_price_rows = non_monotonic_bars = 0
    stale_quote_rows = negative_spread_rows = 0
    tickers_checked = 0
    missing_spy = False

    if require_spy:
        spy_bars = provider.get_historical_bars("SPY")
        if spy_bars.empty:
            missing_spy = True
            errors.append("missing SPY bar data")
        else:
            spy_res = validate_bars(spy_bars, ticker="SPY")
            errors.extend(spy_res.errors)
            warnings.extend(spy_res.warnings)
            duplicate_bars += spy_res.duplicate_bars
            invalid_price_rows += spy_res.invalid_price_rows
            non_monotonic_bars += spy_res.non_monotonic_bars
            tickers_checked += 1

    for ticker in tickers:
        if ticker.upper() == "SPY":
            continue
        bars = provider.get_historical_bars(ticker)
        res = validate_bars(bars, ticker=ticker)
        errors.extend(res.errors)
        warnings.extend(res.warnings)
        duplicate_bars += res.duplicate_bars
        invalid_price_rows += res.invalid_price_rows
        non_monotonic_bars += res.non_monotonic_bars
        tickers_checked += 1

    quotes = provider.get_latest_quotes(list({*tickers, "SPY"}))
    q_res = validate_quotes(quotes, reference=reference)
    errors.extend(q_res.errors)
    warnings.extend(q_res.warnings)
    stale_quote_rows += q_res.stale_quote_rows
    negative_spread_rows += q_res.negative_spread_rows

    status = "PASS" if not errors else "FAIL"
    return IntradayQualityResult(
        status=status,
        errors=errors,
        warnings=warnings,
        duplicate_bars=duplicate_bars,
        non_monotonic_bars=non_monotonic_bars,
        invalid_price_rows=invalid_price_rows,
        negative_spread_rows=negative_spread_rows,
        stale_quote_rows=stale_quote_rows,
        missing_spy=missing_spy,
        tickers_checked=tickers_checked,
    )


def quality_result_to_dict(result: IntradayQualityResult) -> Dict[str, Any]:
    payload = asdict(result)
    payload["checked_at_utc"] = _utc_now()
    return payload
