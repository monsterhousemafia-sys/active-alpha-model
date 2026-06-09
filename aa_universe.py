from __future__ import annotations

import argparse
import urllib.request
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, normalize_yfinance_ticker, parse_extra_benchmark_tickers
from aa_constants import DEFAULT_TICKERS
from aa_dashboard import RunDashboard

def _http_get_text(url: str, *, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _component_records_from_tables(tables: List[pd.DataFrame], *, source: str) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for table in tables:
        if table is None or table.empty:
            continue
        df = table.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [" ".join([str(x) for x in tup if str(x) != "nan"]).strip() for tup in df.columns]
        else:
            df.columns = [str(c).strip() for c in df.columns]
        lower_cols = {str(c).strip().lower(): c for c in df.columns}
        symbol_col = None
        for candidate in ["symbol", "ticker", "ticker symbol"]:
            if candidate in lower_cols:
                symbol_col = lower_cols[candidate]
                break
        if symbol_col is None:
            continue
        company_col = None
        for candidate in ["company name", "name", "security", "company"]:
            if candidate in lower_cols:
                company_col = lower_cols[candidate]
                break
        sector_col = None
        for candidate in ["gics sector", "sector", "gics_sector"]:
            if candidate in lower_cols:
                sector_col = lower_cols[candidate]
                break
        from aa_sector_reference import gics_to_coarse, parse_sector_gics_from_row

        for _, row in df.iterrows():
            source_symbol = str(row.get(symbol_col, "")).strip()
            ticker = normalize_yfinance_ticker(source_symbol)
            if not ticker or ticker.startswith("^") or ticker in {"SYMBOL", "TICKER"}:
                continue
            company = ""
            if company_col is not None:
                company = str(row.get(company_col, "")).strip()
                if company.lower() == "nan":
                    company = ""
            sector_gics = ""
            if sector_col is not None:
                sector_gics = str(row.get(sector_col, "")).strip()
                if sector_gics.lower() in {"nan", "none"}:
                    sector_gics = ""
            if not sector_gics:
                sector_gics = parse_sector_gics_from_row(row, columns=df.columns)
            sector_coarse = gics_to_coarse(sector_gics) if sector_gics else ""
            records.append({
                "ticker": ticker,
                "source_symbol": source_symbol,
                "company": company,
                "sector_gics": sector_gics,
                "sector_coarse": sector_coarse,
                "source": source,
            })
    # de-duplicate while preserving order
    seen = set()
    unique: List[Dict[str, str]] = []
    for rec in records:
        tk = rec["ticker"]
        if tk not in seen:
            seen.add(tk)
            unique.append(rec)
    return unique


def fetch_wikipedia_sp500_components() -> List[Dict[str, str]]:
    """Fetch current S&P 500 components from Wikipedia.

    This is the primary online source for paper-trading universes. It is not an
    institutional point-in-time database, therefore every successful fetch is
    saved as an auditable snapshot.
    """
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    html = _http_get_text(url)
    tables = pd.read_html(StringIO(html))
    records = _component_records_from_tables(tables, source="wikipedia_sp500")
    if len(records) < 100:
        raise RuntimeError(f"Wikipedia S&P 500 fetch returned only {len(records)} symbols.")
    return records


def fetch_slickcharts_sp500_components() -> List[Dict[str, str]]:
    """Fetch current S&P 500 components from Slickcharts as secondary source."""
    url = "https://www.slickcharts.com/sp500"
    html = _http_get_text(url)
    tables = pd.read_html(StringIO(html))
    records = _component_records_from_tables(tables, source="slickcharts_sp500")
    if len(records) < 100:
        raise RuntimeError(f"Slickcharts S&P 500 fetch returned only {len(records)} symbols.")
    return records


def _parse_snapshot_timestamp(path: Path) -> Optional[datetime]:
    """Return the UTC timestamp stored in a snapshot, or None if unavailable."""
    try:
        df = pd.read_csv(path, nrows=5)
    except Exception:
        return None
    if "fetched_at_utc" in df.columns and len(df):
        raw = str(df["fetched_at_utc"].iloc[0]).strip()
        if raw and raw.lower() != "nan":
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                pass
    # Fallback for older snapshots without timestamp: infer date from filename.
    try:
        stem = path.stem
        if stem.startswith("sp500_") and stem != "sp500_latest":
            return datetime.fromisoformat(stem.replace("sp500_", "") + "T00:00:00+00:00")
    except Exception:
        return None
    return None


def latest_cached_sp500_path(cache_dir: Path) -> Optional[Path]:
    candidates: List[Path] = []
    latest = cache_dir / "sp500_latest.csv"
    if latest.exists() and latest.is_file():
        candidates.append(latest)
    candidates.extend([p for p in sorted(cache_dir.glob("sp500_*.csv"), reverse=True) if p.name != "sp500_latest.csv"])
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def cached_snapshot_age_days(path: Path) -> Optional[float]:
    ts = _parse_snapshot_timestamp(path)
    if ts is None:
        return None
    return max((datetime.now(timezone.utc) - ts).total_seconds() / 86400.0, 0.0)


def save_universe_snapshot(records: List[Dict[str, str]], cache_dir: Path, *, source_detail: str, dashboard: Optional[RunDashboard] = None) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    date_str = fetched_at[:10]
    df = pd.DataFrame(records).copy()
    if "ticker" not in df.columns:
        raise ValueError("Universe snapshot records must contain a ticker column.")
    df["fetched_at_utc"] = fetched_at
    df["source_detail"] = source_detail
    df = df[
        [
            c
            for c in [
                "ticker",
                "source_symbol",
                "company",
                "sector_gics",
                "sector_coarse",
                "source",
                "source_detail",
                "fetched_at_utc",
            ]
            if c in df.columns
        ]
    ]
    path = cache_dir / f"sp500_{date_str}.csv"
    latest = cache_dir / "sp500_latest.csv"
    df.to_csv(path, index=False)
    df.to_csv(latest, index=False)
    if dashboard is not None:
        dashboard.ok(f"Universe snapshot saved: {path} ({len(df)} tickers)")
    return path


def load_cached_sp500_components(cache_dir: Path, snapshot_date: str = "") -> Tuple[List[Dict[str, str]], Path]:
    if snapshot_date.strip():
        candidates = [cache_dir / f"sp500_{snapshot_date.strip()}.csv", cache_dir / snapshot_date.strip()]
    else:
        candidates = [cache_dir / "sp500_latest.csv"]
        candidates.extend(sorted(cache_dir.glob("sp500_*.csv"), reverse=True))
    for path in candidates:
        if path.exists() and path.is_file():
            df = pd.read_csv(path)
            if "ticker" not in df.columns:
                if "Symbol" in df.columns:
                    df["ticker"] = df["Symbol"].map(normalize_yfinance_ticker)
                else:
                    raise ValueError(f"Cached universe snapshot has no ticker column: {path}")
            records = []
            for _, row in df.iterrows():
                tk = normalize_yfinance_ticker(str(row.get("ticker", "")))
                if tk:
                    records.append({
                        "ticker": tk,
                        "source_symbol": str(row.get("source_symbol", tk)),
                        "company": str(row.get("company", "")),
                        "sector_gics": str(row.get("sector_gics", "") or ""),
                        "sector_coarse": str(row.get("sector_coarse", "") or ""),
                        "source": str(row.get("source", "cached_sp500")),
                    })
            # de-duplicate
            out: List[Dict[str, str]] = []
            seen = set()
            for rec in records:
                if rec["ticker"] not in seen:
                    seen.add(rec["ticker"])
                    out.append(rec)
            if not out:
                raise RuntimeError(f"Cached universe snapshot is empty: {path}")
            return out, path
    raise FileNotFoundError(f"No cached S&P 500 snapshot found in {cache_dir}.")


def load_file_tickers(args: argparse.Namespace) -> List[str]:
    if args.tickers.strip():
        return [normalize_yfinance_ticker(x) for x in args.tickers.split(",") if normalize_yfinance_ticker(x)]
    if args.tickers_file.strip():
        path = Path(args.tickers_file)
        return [normalize_yfinance_ticker(line) for line in path.read_text().splitlines() if line.strip() and not line.strip().startswith("#") and normalize_yfinance_ticker(line)]
    return DEFAULT_TICKERS.copy()


def load_membership_tickers(args: argparse.Namespace) -> List[str]:
    """Load the seed symbol set from ticker_membership.csv.

    This is the recommended ticker source for historical backtests. The returned
    list is only the download seed. Actual historical eligibility is enforced
    later by apply_membership_filter_to_features() using valid_from/valid_to.
    """
    path = Path(getattr(args, "membership_file", "ticker_membership.csv"))
    if not path.exists():
        raise FileNotFoundError(f"Membership ticker source requires a membership file: {path}")
    membership = normalize_membership_table(pd.read_csv(path))
    if membership.empty:
        raise RuntimeError(f"Membership ticker source is empty or invalid: {path}")
    tickers = sorted({normalize_yfinance_ticker(tk) for tk in membership["ticker"].astype(str) if normalize_yfinance_ticker(tk)})
    if not tickers:
        raise RuntimeError(f"Membership ticker source produced no tickers: {path}")
    return tickers


def _snapshot_valid_from(path: Optional[Path], records: Optional[List[Dict[str, str]]] = None) -> str:
    """Return a defensible forward valid_from date for a universe snapshot."""
    if records:
        for rec in records:
            for key in ("fetched_at_utc", "asof_date", "snapshot_date"):
                raw = str(rec.get(key, "")).strip()
                if raw and raw.lower() not in {"nan", "none"}:
                    return raw[:10]
    if path is not None:
        try:
            ts = _parse_snapshot_timestamp(path)
            if ts is not None:
                return ts.date().isoformat()
        except Exception:
            pass
        try:
            stem = path.stem
            if stem.startswith("sp500_") and stem != "sp500_latest":
                return stem.replace("sp500_", "")[:10]
        except Exception:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if path.exists() and path.is_file():
        return pd.read_csv(path)
    return pd.DataFrame()


def normalize_membership_table(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a ticker membership table for point-in-time universe filtering."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["ticker", "valid_from", "valid_to", "source", "reason"])
    out = df.copy()
    lower = {str(c).strip().lower(): c for c in out.columns}
    if "ticker" not in lower:
        if "symbol" in lower:
            out["ticker"] = out[lower["symbol"]]
        else:
            raise ValueError("Membership file must contain a ticker column.")
    else:
        out["ticker"] = out[lower["ticker"]]
    if "valid_from" not in lower:
        raise ValueError("Membership file must contain valid_from.")
    out["valid_from"] = out[lower["valid_from"]]
    if "valid_to" in lower:
        out["valid_to"] = out[lower["valid_to"]]
    else:
        out["valid_to"] = ""
    if "source" in lower:
        out["source"] = out[lower["source"]]
    else:
        out["source"] = "unknown"
    if "reason" in lower:
        out["reason"] = out[lower["reason"]]
    else:
        out["reason"] = ""
    out["ticker"] = out["ticker"].map(normalize_yfinance_ticker)
    out = out[out["ticker"].astype(bool)].copy()
    out["valid_from"] = pd.to_datetime(out["valid_from"], errors="coerce")
    out["valid_to"] = pd.to_datetime(out["valid_to"].replace({"": np.nan, "nan": np.nan, "None": np.nan}), errors="coerce")
    out = out[out["valid_from"].notna()].copy()
    out["source"] = out["source"].fillna("unknown").astype(str)
    out["reason"] = out["reason"].fillna("").astype(str)
    return out[["ticker", "valid_from", "valid_to", "source", "reason"]]


def update_membership_from_records(records: List[Dict[str, str]], membership_file: Path, *, valid_from: str, source_detail: str, reason: str = "forward_snapshot_added") -> Tuple[int, Path]:
    """Append new snapshot tickers to a forward-only membership file.

    Existing tickers are not backfilled. New tickers receive valid_from equal to
    the snapshot date, which prevents current constituents from being used in
    historical backtests before they were first observed by this workflow.
    """
    membership_file.parent.mkdir(parents=True, exist_ok=True)
    existing_raw = _read_csv_if_exists(membership_file)
    if existing_raw.empty:
        existing = pd.DataFrame(columns=["ticker", "valid_from", "valid_to", "source", "reason"])
    else:
        existing = normalize_membership_table(existing_raw)
    existing_tickers = set(existing["ticker"].astype(str)) if not existing.empty else set()
    valid_from_str = str(pd.to_datetime(valid_from).date())
    rows = []
    seen = set()
    for rec in records:
        tk = normalize_yfinance_ticker(str(rec.get("ticker", "")))
        if not tk or tk in existing_tickers or tk in seen:
            continue
        seen.add(tk)
        rows.append({
            "ticker": tk,
            "valid_from": valid_from_str,
            "valid_to": "",
            "source": str(rec.get("source", source_detail) or source_detail),
            "reason": reason,
        })
    if rows:
        export_existing = existing.copy()
        if not export_existing.empty:
            export_existing["valid_from"] = export_existing["valid_from"].dt.date.astype(str)
            export_existing["valid_to"] = export_existing["valid_to"].dt.date.astype(str).replace("NaT", "")
        out = pd.concat([export_existing, pd.DataFrame(rows)], ignore_index=True)
    else:
        out = existing.copy()
        if not out.empty:
            out["valid_from"] = out["valid_from"].dt.date.astype(str)
            out["valid_to"] = out["valid_to"].dt.date.astype(str).replace("NaT", "")
    out = out[["ticker", "valid_from", "valid_to", "source", "reason"]].drop_duplicates()
    out.sort_values(["ticker", "valid_from"], inplace=True)
    out.to_csv(membership_file, index=False)
    return len(rows), membership_file


def update_asset_master_from_records(records: List[Dict[str, str]], asset_master_file: Path, *, seen_date: str, source_detail: str) -> Tuple[int, int, Path]:
    """Maintain a lightweight asset master for auditability.

    This is not a permanent-ID security master, but it records when a symbol was
    first and last seen by this workflow and which snapshot source produced it.
    """
    asset_master_file.parent.mkdir(parents=True, exist_ok=True)
    seen_date_str = str(pd.to_datetime(seen_date).date())
    existing = _read_csv_if_exists(asset_master_file)
    if existing.empty:
        master = pd.DataFrame(columns=["ticker", "company", "first_seen", "last_seen", "active", "source_first_seen", "source_last_seen"])
    else:
        master = existing.copy()
        if "ticker" not in master.columns:
            raise ValueError("Asset master must contain ticker column.")
        master["ticker"] = master["ticker"].map(normalize_yfinance_ticker)
    master = master.dropna(subset=["ticker"]).copy()
    master = master[master["ticker"].astype(bool)].copy()
    for col in ["company", "first_seen", "last_seen", "active", "source_first_seen", "source_last_seen"]:
        if col not in master.columns:
            master[col] = ""
    master.set_index("ticker", inplace=True, drop=False)
    added = 0
    updated = 0
    for rec in records:
        tk = normalize_yfinance_ticker(str(rec.get("ticker", "")))
        if not tk:
            continue
        company = str(rec.get("company", "")).strip()
        if tk not in master.index:
            master.loc[tk, "ticker"] = tk
            master.loc[tk, "company"] = company
            master.loc[tk, "first_seen"] = seen_date_str
            master.loc[tk, "last_seen"] = seen_date_str
            master.loc[tk, "active"] = True
            master.loc[tk, "source_first_seen"] = source_detail
            master.loc[tk, "source_last_seen"] = source_detail
            added += 1
        else:
            if company and (str(master.loc[tk, "company"]).strip() == "" or str(master.loc[tk, "company"]).lower() == "nan"):
                master.loc[tk, "company"] = company
            master.loc[tk, "last_seen"] = seen_date_str
            master.loc[tk, "active"] = True
            master.loc[tk, "source_last_seen"] = source_detail
            updated += 1
    out = master.reset_index(drop=True)[["ticker", "company", "first_seen", "last_seen", "active", "source_first_seen", "source_last_seen"]]
    out.sort_values("ticker", inplace=True)
    out.to_csv(asset_master_file, index=False)
    return added, updated, asset_master_file


def apply_membership_filter_to_features(features: pd.DataFrame, cfg: BacktestConfig, dashboard: Optional[RunDashboard] = None) -> pd.DataFrame:
    """Apply valid_from/valid_to membership gating to feature rows.

    This is the DIY point-in-time safety layer. It does not make the universe
    delisting-complete, but it prevents tickers discovered today from being used
    retroactively in historical backtests.
    """
    mode = str(getattr(cfg, "membership_mode", "auto")).lower()
    if mode == "off":
        return features
    runtime_mode = str(getattr(cfg, "runtime_mode", "")).lower()
    if runtime_mode == "signal" and not bool(getattr(cfg, "membership_filter_signal", False)):
        return features

    path = Path(getattr(cfg, "membership_file", "ticker_membership.csv"))
    if not path.exists():
        if mode == "strict":
            raise FileNotFoundError(f"Membership file required but not found: {path}")
        if dashboard is not None:
            dashboard.warn(f"Membership file not found; membership filter skipped: {path}")
        return features

    membership = normalize_membership_table(pd.read_csv(path))
    if membership.empty:
        if mode == "strict":
            raise RuntimeError(f"Membership file is empty or invalid: {path}")
        if dashboard is not None:
            dashboard.warn(f"Membership file empty; membership filter skipped: {path}")
        return features

    out = features.copy()
    if dashboard is not None:
        dashboard.set_status(step=f"Membership-Filter: {len(out):,} Feature-Zeilen")
    row_dates = pd.to_datetime(out["date"], errors="coerce")
    allowed = pd.Series(False, index=out.index)
    source_col = pd.Series("", index=out.index, dtype="object")
    reason_col = pd.Series("", index=out.index, dtype="object")
    first_valid_col = pd.Series("", index=out.index, dtype="object")
    for tk, group in membership.groupby("ticker", sort=False):
        idx = out.index[out["ticker"].astype(str).str.upper() == tk]
        if len(idx) == 0:
            continue
        dates = row_dates.loc[idx]
        tk_allowed = pd.Series(False, index=idx)
        tk_source = ""
        tk_reason = ""
        tk_first = ""
        for _, m in group.iterrows():
            vf = pd.Timestamp(m["valid_from"])
            vt = pd.Timestamp(m["valid_to"]) if pd.notna(m["valid_to"]) else pd.NaT
            mask = dates >= vf
            if pd.notna(vt):
                mask &= dates < vt
            if mask.any():
                tk_allowed.loc[mask.index[mask]] = True
                tk_source = str(m.get("source", ""))
                tk_reason = str(m.get("reason", ""))
                tk_first = str(vf.date())
        allowed.loc[idx] = tk_allowed
        source_col.loc[idx] = tk_source
        reason_col.loc[idx] = tk_reason
        first_valid_col.loc[idx] = tk_first

    out["membership_allowed"] = allowed.astype(bool)
    out["membership_source"] = source_col
    out["membership_reason"] = reason_col
    out["membership_valid_from"] = first_valid_col
    if "in_universe" not in out.columns:
        out["in_universe"] = True
    before = int(out["in_universe"].fillna(False).astype(bool).sum())
    out["in_universe"] = out["in_universe"].fillna(False).astype(bool) & out["membership_allowed"]
    after = int(out["in_universe"].fillna(False).astype(bool).sum())
    out.loc[~out["membership_allowed"], "universe_reason"] = "membership_excluded"
    if dashboard is not None:
        dashboard.ok(f"Membership filter applied: {after:,}/{before:,} previously eligible rows remain ({path})")
    return out


def load_tickers(args: argparse.Namespace, dashboard: Optional[RunDashboard] = None) -> List[str]:
    source = str(getattr(args, "ticker_source", "file")).lower()
    cache_dir = Path(getattr(args, "ticker_cache_dir", "universe_snapshots"))
    allow_fallback = not bool(getattr(args, "no_ticker_fallback", False))
    save_snapshot = not bool(getattr(args, "no_save_universe_snapshot", False))
    cache_max_age_days = int(max(getattr(args, "ticker_cache_max_age_days", 7), 0))

    if dashboard is not None:
        dashboard.start_phase("Tickeruniversum laden", total=1, step=f"Quelle: {source}")

    source_detail = source
    records: List[Dict[str, str]] = []
    tickers: List[str]
    snapshot_valid_from = datetime.now(timezone.utc).date().isoformat()
    snapshot_path: Optional[Path] = None

    def records_to_tickers(recs: List[Dict[str, str]]) -> List[str]:
        return [normalize_yfinance_ticker(rec.get("ticker", "")) for rec in recs if normalize_yfinance_ticker(rec.get("ticker", ""))]

    def fallback_to_file(reason: str) -> Tuple[List[str], str, List[Dict[str, str]]]:
        # No static legacy ticker-list fallback in this package. Historical
        # backtests use sp500_pit; current signals must use an online or cached
        # S&P 500 source. Failing loudly is safer than silently reverting to a
        # biased static list.
        raise RuntimeError(reason + " No static ticker-list fallback is available in the no-legacy package.")

    try:
        if source == "sp500_pit":
            tickers = load_membership_tickers(args)
            source_detail = f"sp500_pit:{getattr(args, 'membership_file', 'ticker_membership.csv')}"
            records = [{"ticker": tk, "source_symbol": tk, "company": "", "source": "sp500_pit"} for tk in tickers]

        elif source == "file":
            tickers = load_file_tickers(args)
            source_detail = "file" if args.tickers_file.strip() else "default_tickers"

        elif source == "cached_sp500":
            records, cached_path = load_cached_sp500_components(cache_dir, getattr(args, "ticker_snapshot_date", ""))
            tickers = records_to_tickers(records)
            source_detail = f"cached_sp500:{cached_path}"
            snapshot_path = cached_path
            snapshot_valid_from = _snapshot_valid_from(cached_path, records)

        elif source == "wikipedia_sp500":
            try:
                records = fetch_wikipedia_sp500_components()
                tickers = records_to_tickers(records)
                source_detail = "wikipedia_sp500"
                if save_snapshot:
                    snapshot_path = save_universe_snapshot(records, cache_dir, source_detail=source_detail, dashboard=dashboard)
                    snapshot_valid_from = _snapshot_valid_from(snapshot_path, records)
            except Exception as exc:
                if not allow_fallback:
                    raise
                try:
                    records, cached_path = load_cached_sp500_components(cache_dir)
                    tickers = records_to_tickers(records)
                    source_detail = f"cached_sp500_fallback:{cached_path}"
                    snapshot_path = cached_path
                    snapshot_valid_from = _snapshot_valid_from(cached_path, records)
                    if dashboard is not None:
                        dashboard.warn(f"Wikipedia S&P 500 universe failed: {exc}")
                        dashboard.warn(f"Using cached S&P 500 universe: {cached_path}")
                except Exception:
                    tickers, source_detail, records = fallback_to_file(f"Wikipedia S&P 500 universe failed: {exc}")

        elif source == "slickcharts_sp500":
            try:
                records = fetch_slickcharts_sp500_components()
                tickers = records_to_tickers(records)
                source_detail = "slickcharts_sp500"
                if save_snapshot:
                    snapshot_path = save_universe_snapshot(records, cache_dir, source_detail=source_detail, dashboard=dashboard)
                    snapshot_valid_from = _snapshot_valid_from(snapshot_path, records)
            except Exception as exc:
                if not allow_fallback:
                    raise
                try:
                    records, cached_path = load_cached_sp500_components(cache_dir)
                    tickers = records_to_tickers(records)
                    source_detail = f"cached_sp500_fallback:{cached_path}"
                    snapshot_path = cached_path
                    snapshot_valid_from = _snapshot_valid_from(cached_path, records)
                    if dashboard is not None:
                        dashboard.warn(f"Slickcharts S&P 500 universe failed: {exc}")
                        dashboard.warn(f"Using cached S&P 500 universe: {cached_path}")
                except Exception:
                    tickers, source_detail, records = fallback_to_file(f"Slickcharts S&P 500 universe failed: {exc}")

        elif source == "sp500_auto":
            # 1) Fresh cache first: stable, reproducible and avoids unnecessary web fragility.
            latest_path = latest_cached_sp500_path(cache_dir)
            if latest_path is not None:
                age = cached_snapshot_age_days(latest_path)
                if age is not None and age <= cache_max_age_days:
                    records, cached_path = load_cached_sp500_components(cache_dir)
                    tickers = records_to_tickers(records)
                    source_detail = f"cached_sp500_fresh:{cached_path}"
                    snapshot_path = cached_path
                    snapshot_valid_from = _snapshot_valid_from(cached_path, records)
                    if dashboard is not None:
                        dashboard.ok(f"Using fresh cached S&P 500 universe: {cached_path} ({age:.1f} days old)")
                else:
                    tickers = []
            else:
                tickers = []

            # 2) Online refresh if cache is missing or stale. Wikipedia first, Slickcharts second.
            if not tickers:
                online_errors: List[str] = []
                try:
                    records = fetch_wikipedia_sp500_components()
                    tickers = records_to_tickers(records)
                    source_detail = "wikipedia_sp500"
                    if dashboard is not None:
                        dashboard.ok("S&P 500 universe loaded from Wikipedia.")
                    if save_snapshot:
                        snapshot_path = save_universe_snapshot(records, cache_dir, source_detail=source_detail, dashboard=dashboard)
                    snapshot_valid_from = _snapshot_valid_from(snapshot_path, records)
                except Exception as exc:
                    online_errors.append(f"Wikipedia: {exc}")
                    if dashboard is not None:
                        dashboard.warn(f"Wikipedia S&P 500 universe failed: {exc}")
                    try:
                        records = fetch_slickcharts_sp500_components()
                        tickers = records_to_tickers(records)
                        source_detail = "slickcharts_sp500"
                        if dashboard is not None:
                            dashboard.ok("S&P 500 universe loaded from Slickcharts.")
                        if save_snapshot:
                            snapshot_path = save_universe_snapshot(records, cache_dir, source_detail=source_detail, dashboard=dashboard)
                        snapshot_valid_from = _snapshot_valid_from(snapshot_path, records)
                    except Exception as exc2:
                        online_errors.append(f"Slickcharts: {exc2}")
                        if dashboard is not None:
                            dashboard.warn(f"Slickcharts S&P 500 universe failed: {exc2}")
                        if not allow_fallback:
                            raise RuntimeError("; ".join(online_errors))
                        # 3) Stale cache is still better than aborting a paper run when online pages fail.
                        try:
                            records, cached_path = load_cached_sp500_components(cache_dir)
                            tickers = records_to_tickers(records)
                            source_detail = f"cached_sp500_stale_fallback:{cached_path}"
                            snapshot_path = cached_path
                            snapshot_valid_from = _snapshot_valid_from(cached_path, records)
                            if dashboard is not None:
                                dashboard.warn(f"Using stale cached S&P 500 universe: {cached_path}")
                        except Exception:
                            tickers, source_detail, records = fallback_to_file("; ".join(online_errors))
        else:
            raise ValueError(f"Unsupported ticker_source: {source}")
    except Exception:
        if dashboard is not None:
            dashboard.finish_phase()
        raise

    tickers = [tk for tk in dict.fromkeys([normalize_yfinance_ticker(x) for x in tickers]) if tk]

    # Forward-only audit trail: non-file universes can update membership and
    # asset-master files. This does not retroactively add tickers to history.
    non_file_source = not (source_detail == "file" or source_detail == "default_tickers" or source_detail == "file_fallback" or str(source_detail).startswith("sp500_pit:"))
    if records and non_file_source:
        if not bool(getattr(args, "no_update_membership", False)):
            try:
                added, membership_path = update_membership_from_records(
                    records,
                    Path(getattr(args, "membership_file", "ticker_membership.csv")),
                    valid_from=snapshot_valid_from,
                    source_detail=source_detail,
                    reason="forward_snapshot_added",
                )
                setattr(args, "_membership_source_detail", f"{membership_path}: added {added} new symbols, valid_from={snapshot_valid_from}")
                if dashboard is not None:
                    dashboard.ok(f"Membership updated: {membership_path} (+{added}, valid_from={snapshot_valid_from})")
            except Exception as exc:
                if dashboard is not None:
                    dashboard.warn(f"Membership update failed: {exc}")
        if not bool(getattr(args, "no_update_asset_master", False)):
            try:
                added, updated, master_path = update_asset_master_from_records(
                    records,
                    Path(getattr(args, "asset_master_file", "asset_master.csv")),
                    seen_date=snapshot_valid_from,
                    source_detail=source_detail,
                )
                if dashboard is not None:
                    dashboard.ok(f"Asset master updated: {master_path} (+{added}, updated {updated})")
            except Exception as exc:
                if dashboard is not None:
                    dashboard.warn(f"Asset master update failed: {exc}")
        if not bool(getattr(args, "no_update_sector_reference", False)):
            try:
                from aa_sector_reference import sync_sector_reference_after_universe

                membership_path = Path(getattr(args, "membership_file", "ticker_membership.csv"))
                proj_root = membership_path.parent.resolve() if membership_path.is_absolute() else Path.cwd().resolve()
                sector_result = sync_sector_reference_after_universe(
                    records,
                    valid_from=snapshot_valid_from,
                    source_detail=source_detail,
                    root=proj_root,
                )
                setattr(args, "_sector_reference_detail", str(sector_result.get("path", "")))
                if dashboard is not None:
                    dashboard.ok(
                        f"Sector reference updated: {sector_result.get('path')} "
                        f"(+{sector_result.get('added', 0)}, rows={sector_result.get('row_count', 0)})"
                    )
            except Exception as exc:
                if dashboard is not None:
                    dashboard.warn(f"Sector reference update failed: {exc}")

    benchmark = normalize_yfinance_ticker(args.benchmark.upper())
    if benchmark not in tickers:
        tickers.append(benchmark)
    for extra_benchmark in parse_extra_benchmark_tickers(getattr(args, "extra_benchmarks", "")):
        if extra_benchmark not in tickers:
            tickers.append(extra_benchmark)

    # Store details on args so main can transfer them into cfg/report.
    setattr(args, "_ticker_source_detail", source_detail)
    setattr(args, "_ticker_count", len(tickers))

    if dashboard is not None:
        dashboard.advance_phase(1, step=f"{len(tickers)} Ticker geladen", ticker=f"{len(tickers)} Symbole")
        dashboard.ok(f"Ticker source: {source_detail}; symbols including benchmark: {len(tickers)}")
        dashboard.finish_phase()
    else:
        print(f"Ticker source: {source_detail}; symbols including benchmark: {len(tickers)}")
    return tickers

