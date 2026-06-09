#!/usr/bin/env python3
"""
Build a DIY point-in-time S&P 500 membership file from Wikipedia.

The script uses two public Wikipedia tables:
1) the current S&P 500 constituents table
2) the selected changes table with effective date, added ticker and removed ticker

It reconstructs membership intervals by walking the change table backwards from
current constituents to the requested start date, then walks forward to create
valid_from / valid_to intervals.

Output files:
- ticker_membership.csv          consumed by active_alpha_model.py
- sp500_change_events.csv        normalized audit trail of parsed changes
- sp500_reconstruction_report.txt diagnostics and limitations
- asset_master.csv               lightweight symbol audit table

Limitations:
This is a free DIY point-in-time proxy. It is not an institutional constituent
history and does not solve delisting returns, ticker-permanent-ID mapping, or
all corporate-action edge cases.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def normalize_ticker(symbol: object) -> str:
    tk = str(symbol).strip().upper()
    if not tk or tk in {"NAN", "NONE", "NULL", "-", "—"}:
        return ""
    tk = tk.replace(".", "-").replace(" ", "")
    return tk


def http_get_text(url: str, *, timeout: int = 45) -> str:
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


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        cols = []
        for tup in out.columns:
            parts = []
            for item in tup:
                s = str(item).strip()
                if not s or s.lower() == "nan" or s.lower().startswith("unnamed"):
                    continue
                if not parts or parts[-1] != s:
                    parts.append(s)
            cols.append(" ".join(parts).strip())
        out.columns = cols
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def clean_str(x: object) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    return "" if s.lower() in {"nan", "none"} else s


def find_col(cols: Iterable[str], predicates: List[str], *, any_of: bool = False) -> Optional[str]:
    for col in cols:
        low = str(col).strip().lower()
        if any_of:
            ok = any(p in low for p in predicates)
        else:
            ok = all(p in low for p in predicates)
        if ok:
            return col
    return None


def parse_current_constituents(tables: List[pd.DataFrame]) -> pd.DataFrame:
    candidates = []
    for table in tables:
        df = flatten_columns(table)
        cols_lower = {c.lower(): c for c in df.columns}
        if "symbol" in cols_lower and ("security" in cols_lower or "company" in cols_lower or "company name" in cols_lower):
            candidates.append(df)
    if not candidates:
        raise RuntimeError("Could not find the current S&P 500 constituents table on Wikipedia.")
    df = candidates[0].copy()
    cols_lower = {c.lower(): c for c in df.columns}
    symbol_col = cols_lower.get("symbol")
    company_col = cols_lower.get("security") or cols_lower.get("company") or cols_lower.get("company name")
    sector_col = cols_lower.get("gics sector") or find_col(df.columns, ["sector"])
    sub_col = cols_lower.get("gics sub-industry") or find_col(df.columns, ["sub"])
    date_added_col = cols_lower.get("date added") or find_col(df.columns, ["date", "added"])

    rows = []
    for _, row in df.iterrows():
        tk = normalize_ticker(row.get(symbol_col, ""))
        if not tk:
            continue
        rows.append({
            "ticker": tk,
            "company": clean_str(row.get(company_col, "")) if company_col else "",
            "sector": clean_str(row.get(sector_col, "")) if sector_col else "",
            "sub_industry": clean_str(row.get(sub_col, "")) if sub_col else "",
            "date_added_raw": clean_str(row.get(date_added_col, "")) if date_added_col else "",
            "source": "wikipedia_current_constituents",
        })
    out = pd.DataFrame(rows).drop_duplicates("ticker")
    if len(out) < 450:
        raise RuntimeError(f"Current constituents parse returned only {len(out)} tickers.")
    return out.sort_values("ticker").reset_index(drop=True)


def parse_change_events(tables: List[pd.DataFrame]) -> pd.DataFrame:
    parsed_tables: List[pd.DataFrame] = []
    for table in tables:
        df = flatten_columns(table)
        cols = list(df.columns)
        has_date = any(str(c).strip().lower() in {"date", "effective date"} or "date" in str(c).lower() for c in cols)
        has_added = any("added" in str(c).lower() for c in cols)
        has_removed = any("removed" in str(c).lower() for c in cols)
        if has_date and has_added and has_removed:
            parsed_tables.append(df)
    if not parsed_tables:
        raise RuntimeError("Could not find the Wikipedia S&P 500 changes table.")

    # Pick the table with the most rows because the current table may contain a Date added column.
    df = max(parsed_tables, key=len).copy()
    cols = list(df.columns)
    date_col = find_col(cols, ["date"], any_of=True)
    added_ticker_col = find_col(cols, ["added", "ticker"])
    added_security_col = find_col(cols, ["added", "security"]) or find_col(cols, ["added", "company"])
    removed_ticker_col = find_col(cols, ["removed", "ticker"])
    removed_security_col = find_col(cols, ["removed", "security"]) or find_col(cols, ["removed", "company"])
    reason_col = find_col(cols, ["reason"], any_of=True)

    if date_col is None or (added_ticker_col is None and removed_ticker_col is None):
        raise RuntimeError(f"Changes table columns were not recognized: {cols}")

    rows = []
    for _, row in df.iterrows():
        dt = pd.to_datetime(row.get(date_col, ""), errors="coerce")
        if pd.isna(dt):
            continue
        added = normalize_ticker(row.get(added_ticker_col, "")) if added_ticker_col else ""
        removed = normalize_ticker(row.get(removed_ticker_col, "")) if removed_ticker_col else ""
        if not added and not removed:
            continue
        rows.append({
            "effective_date": dt.date().isoformat(),
            "added_ticker": added,
            "added_security": clean_str(row.get(added_security_col, "")) if added_security_col else "",
            "removed_ticker": removed,
            "removed_security": clean_str(row.get(removed_security_col, "")) if removed_security_col else "",
            "reason": clean_str(row.get(reason_col, "")) if reason_col else "",
            "source": "wikipedia_sp500_changes",
        })
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("Changes table parse returned no usable events.")
    out["effective_date"] = pd.to_datetime(out["effective_date"], errors="coerce")
    out = out[out["effective_date"].notna()].copy()
    out.sort_values(["effective_date", "added_ticker", "removed_ticker"], inplace=True)
    out["effective_date"] = out["effective_date"].dt.date.astype(str)
    return out.reset_index(drop=True)


def reconstruct_membership(current: pd.DataFrame, events: pd.DataFrame, *, start_date: str, end_date: str) -> Tuple[pd.DataFrame, Dict[str, object]]:
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start >= end:
        raise ValueError("start_date must be earlier than end_date")

    events2 = events.copy()
    events2["effective_date"] = pd.to_datetime(events2["effective_date"], errors="coerce")
    events2 = events2[(events2["effective_date"].notna()) & (events2["effective_date"] <= end)].copy()

    company: Dict[str, str] = {}
    for _, row in current.iterrows():
        company[normalize_ticker(row["ticker"])] = clean_str(row.get("company", ""))
    for _, row in events2.iterrows():
        at = normalize_ticker(row.get("added_ticker", ""))
        rt = normalize_ticker(row.get("removed_ticker", ""))
        if at and clean_str(row.get("added_security", "")):
            company.setdefault(at, clean_str(row.get("added_security", "")))
        if rt and clean_str(row.get("removed_security", "")):
            company.setdefault(rt, clean_str(row.get("removed_security", "")))

    # Walk backwards from today's/current membership to membership at start_date.
    active = set(current["ticker"].map(normalize_ticker))
    reverse_events = events2[events2["effective_date"] > start].sort_values("effective_date", ascending=False)
    reverse_adds_removed = 0
    reverse_removed_added = 0
    for _, row in reverse_events.iterrows():
        added = normalize_ticker(row.get("added_ticker", ""))
        removed = normalize_ticker(row.get("removed_ticker", ""))
        if added and added in active:
            active.remove(added)
            reverse_adds_removed += 1
        if removed:
            active.add(removed)
            reverse_removed_added += 1

    open_from: Dict[str, pd.Timestamp] = {tk: start for tk in sorted(active)}
    interval_reason: Dict[str, str] = {tk: "present_at_start_reconstructed" for tk in open_from}
    intervals: List[Dict[str, object]] = []
    warnings: List[str] = []
    unmatched_removals = 0
    duplicate_additions = 0

    forward_events = events2[events2["effective_date"] > start].sort_values("effective_date")
    for _, row in forward_events.iterrows():
        dt = pd.Timestamp(row["effective_date"]).normalize()
        added = normalize_ticker(row.get("added_ticker", ""))
        removed = normalize_ticker(row.get("removed_ticker", ""))
        reason_text = clean_str(row.get("reason", ""))
        if removed:
            if removed in open_from:
                intervals.append({
                    "ticker": removed,
                    "valid_from": open_from.pop(removed).date().isoformat(),
                    "valid_to": dt.date().isoformat(),
                    "source": "wikipedia_sp500_reconstructed",
                    "reason": interval_reason.pop(removed, "removed_from_sp500"),
                    "company": company.get(removed, clean_str(row.get("removed_security", ""))),
                    "confidence": "medium" if dt <= pd.Timestamp.today().normalize() else "low",
                })
            else:
                unmatched_removals += 1
                warnings.append(f"Removed ticker was not open at {dt.date()}: {removed}")
        if added:
            if added in open_from:
                duplicate_additions += 1
                warnings.append(f"Added ticker was already open at {dt.date()}: {added}")
            else:
                open_from[added] = dt
                interval_reason[added] = "added_to_sp500"
                if clean_str(row.get("added_security", "")):
                    company.setdefault(added, clean_str(row.get("added_security", "")))

    for tk, vf in sorted(open_from.items()):
        intervals.append({
            "ticker": tk,
            "valid_from": vf.date().isoformat(),
            "valid_to": "",
            "source": "wikipedia_sp500_reconstructed",
            "reason": interval_reason.get(tk, "open_interval"),
            "company": company.get(tk, ""),
            "confidence": "medium" if vf == start else "high",
        })

    membership = pd.DataFrame(intervals)
    membership["ticker"] = membership["ticker"].map(normalize_ticker)
    membership = membership[membership["ticker"].astype(bool)].copy()
    membership.sort_values(["ticker", "valid_from", "valid_to"], inplace=True)
    membership = membership.drop_duplicates(["ticker", "valid_from", "valid_to"], keep="first").reset_index(drop=True)

    active_at_start = int(((pd.to_datetime(membership["valid_from"]) <= start) & (membership["valid_to"].replace("", pd.NA).isna() | (pd.to_datetime(membership["valid_to"], errors="coerce") > start))).sum())
    active_at_end = int(((pd.to_datetime(membership["valid_from"]) <= end) & (membership["valid_to"].replace("", pd.NA).isna() | (pd.to_datetime(membership["valid_to"], errors="coerce") > end))).sum())

    diagnostics: Dict[str, object] = {
        "start_date": start.date().isoformat(),
        "end_date": end.date().isoformat(),
        "current_constituents_count": int(len(current)),
        "change_events_count": int(len(events2)),
        "reverse_adds_removed": reverse_adds_removed,
        "reverse_removed_added": reverse_removed_added,
        "reconstructed_start_count": int(len(active)),
        "membership_rows": int(len(membership)),
        "membership_unique_tickers": int(membership["ticker"].nunique()),
        "active_at_start": active_at_start,
        "active_at_end": active_at_end,
        "unmatched_removals": unmatched_removals,
        "duplicate_additions": duplicate_additions,
        "warnings_count": len(warnings),
        "warnings": warnings[:50],
    }
    return membership, diagnostics


def build_asset_master(membership: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tk, g in membership.groupby("ticker", sort=True):
        first_seen = str(pd.to_datetime(g["valid_from"], errors="coerce").min().date())
        valid_to = pd.to_datetime(g["valid_to"].replace("", pd.NA), errors="coerce")
        active = bool(valid_to.isna().any())
        last_seen = "" if active else str(valid_to.max().date())
        company = ""
        if "company" in g.columns:
            vals = [clean_str(x) for x in g["company"].tolist() if clean_str(x)]
            company = vals[-1] if vals else ""
        rows.append({
            "ticker": tk,
            "company": company,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "active": active,
            "source_first_seen": "wikipedia_sp500_reconstructed",
            "source_last_seen": "wikipedia_sp500_reconstructed",
        })
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def write_report(path: Path, diagnostics: Dict[str, object]) -> None:
    lines = []
    lines.append("S&P 500 Wikipedia Membership Reconstruction Report")
    lines.append("==================================================")
    lines.append("")
    for key, value in diagnostics.items():
        if key == "warnings":
            continue
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("Warnings")
    lines.append("--------")
    warnings = diagnostics.get("warnings", []) or []
    if warnings:
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("None")
    lines.append("")
    lines.append("Interpretation")
    lines.append("--------------")
    lines.append("This file is a DIY point-in-time approximation based on Wikipedia's current S&P 500 constituents and selected change table.")
    lines.append("It reduces recency/survivorship bias versus a static current ticker list, but it is not institutional constituent history.")
    lines.append("Remaining limitations: missing delisted price histories, ticker changes, mergers, corporate actions and delisting returns.")
    path.write_text("\n".join(lines), encoding="utf-8")


def backup(path: Path) -> None:
    if path.exists():
        i = 1
        while True:
            b = path.with_suffix(path.suffix + f".bak{i}")
            if not b.exists():
                shutil.copy2(path, b)
                return
            i += 1


def run_self_test() -> None:
    current = pd.DataFrame([
        {"ticker": "AAA", "company": "AAA Co"},
        {"ticker": "BBB", "company": "BBB Co"},
        {"ticker": "CCC", "company": "CCC Co"},
    ])
    events = pd.DataFrame([
        {"effective_date": "2020-01-01", "added_ticker": "CCC", "added_security": "CCC Co", "removed_ticker": "XXX", "removed_security": "Old X", "reason": "test"},
        {"effective_date": "2021-01-01", "added_ticker": "BBB", "added_security": "BBB Co", "removed_ticker": "YYY", "removed_security": "Old Y", "reason": "test"},
    ])
    membership, diag = reconstruct_membership(current, events, start_date="2019-01-01", end_date="2022-01-01")
    assert "XXX" in set(membership["ticker"]), membership
    assert "YYY" in set(membership["ticker"]), membership
    assert membership.loc[(membership["ticker"] == "CCC") & (membership["valid_from"] == "2020-01-01")].shape[0] == 1
    assert diag["active_at_end"] == 3, diag
    print("Self-test passed: Wikipedia membership reconstruction logic is consistent.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build ticker_membership.csv from Wikipedia S&P 500 current constituents and change history.")
    p.add_argument("--start-date", default="2012-01-01", help="Historical reconstruction start date.")
    p.add_argument("--end-date", default=pd.Timestamp.today().date().isoformat(), help="End date. Defaults to today.")
    p.add_argument("--out", default="ticker_membership.csv", help="Output membership CSV.")
    p.add_argument("--events-out", default="sp500_change_events.csv", help="Output normalized change events CSV.")
    p.add_argument("--asset-master-out", default="asset_master.csv", help="Output lightweight asset master CSV.")
    p.add_argument("--report-out", default="sp500_reconstruction_report.txt", help="Output reconstruction report.")
    p.add_argument("--current-out", default="sp500_current_constituents.csv", help="Output parsed current constituents table.")
    p.add_argument(
        "--sector-reference-out",
        default="sector_reference.csv",
        help="Output sector reference CSV (PIT rows from current constituents GICS).",
    )
    p.add_argument(
        "--no-sector-reference",
        action="store_true",
        help="Skip writing sector_reference.csv.",
    )
    p.add_argument("--url", default=WIKI_URL, help="Wikipedia URL to fetch.")
    p.add_argument("--no-backup", action="store_true", help="Do not create .bakN copies before overwriting output files.")
    p.add_argument("--self-test", action="store_true", help="Run a local logic self-test without internet access.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_test()
        return 0

    print(f"Fetching Wikipedia S&P 500 tables: {args.url}")
    html = http_get_text(args.url)
    tables = pd.read_html(StringIO(html))
    current = parse_current_constituents(tables)
    events = parse_change_events(tables)
    membership, diagnostics = reconstruct_membership(current, events, start_date=args.start_date, end_date=args.end_date)
    asset_master = build_asset_master(membership)

    outputs = [Path(args.out), Path(args.events_out), Path(args.asset_master_out), Path(args.report_out), Path(args.current_out)]
    if not args.no_backup:
        for path in outputs:
            backup(path)

    current.to_csv(args.current_out, index=False)
    events.to_csv(args.events_out, index=False)
    membership.to_csv(args.out, index=False)
    asset_master.to_csv(args.asset_master_out, index=False)
    write_report(Path(args.report_out), diagnostics)

    if not args.no_sector_reference:
        from aa_sector_reference import (
            records_from_constituents_df,
            update_sector_reference_from_records,
            write_sector_reference_status,
        )

        sector_path = Path(args.sector_reference_out)
        if not args.no_backup and sector_path.exists():
            backup(sector_path)
        sector_records = records_from_constituents_df(current, source="wikipedia_current_constituents")
        sector_result = update_sector_reference_from_records(
            sector_records,
            sector_path,
            valid_from=str(args.end_date),
            source_detail="wikipedia_membership_build",
            root=Path.cwd(),
        )
        write_sector_reference_status(
            Path.cwd(),
            {
                "status": "OK",
                "source_detail": "wikipedia_membership_build",
                "last_membership_build_sync": sector_result,
            },
        )
        print(f"Sector reference: {sector_path} ({sector_result.get('row_count', 0)} rows)")

    print("Done.")
    print(f"Membership:       {args.out} ({len(membership)} rows, {membership['ticker'].nunique()} tickers)")
    print(f"Change events:    {args.events_out} ({len(events)} events)")
    print(f"Asset master:     {args.asset_master_out} ({len(asset_master)} tickers)")
    print(f"Report:           {args.report_out}")
    print(f"Active at start:  {diagnostics['active_at_start']}")
    print(f"Active at end:    {diagnostics['active_at_end']}")
    print("Note: this is a DIY point-in-time proxy, not institutional PIT data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
