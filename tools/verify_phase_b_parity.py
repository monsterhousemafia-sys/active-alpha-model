#!/usr/bin/env python3
"""Compare walk-forward strategy returns against a saved reference snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _load_returns(path: Path) -> pd.Series:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
        if "strategy_return" in df.columns and "date" in df.columns:
            return pd.Series(df["strategy_return"].values, index=pd.to_datetime(df["date"])).sort_index()
        if len(df.columns) == 2:
            return pd.Series(df.iloc[:, 1].values, index=pd.to_datetime(df.iloc[:, 0])).sort_index()
    df = pd.read_csv(path)
    date_col = "date" if "date" in df.columns else df.columns[0]
    val_col = "strategy_return" if "strategy_return" in df.columns else df.columns[-1]
    return pd.Series(df[val_col].values, index=pd.to_datetime(df[date_col])).sort_index()


def compare(current: Path, reference: Path, *, tol_corr: float = 0.9999, tol_return: float = 0.002) -> dict:
    a = _load_returns(current).astype(float)
    b = _load_returns(reference).astype(float)
    joined = pd.concat([a, b], axis=1, join="inner").dropna()
    if joined.empty:
        raise RuntimeError("No overlapping dates between current and reference returns.")
    ra, rb = joined.iloc[:, 0], joined.iloc[:, 1]
    corr = float(ra.corr(rb))
    total_a = float((1.0 + ra).prod() - 1.0)
    total_b = float((1.0 + rb).prod() - 1.0)
    ok = corr >= tol_corr and abs(total_a - total_b) <= tol_return
    return {
        "ok": ok,
        "overlap_days": int(len(joined)),
        "corr": corr,
        "total_return_current": total_a,
        "total_return_reference": total_b,
        "total_return_delta": total_a - total_b,
        "current": str(current),
        "reference": str(reference),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verify Phase B / strategy return parity.")
    p.add_argument("--current", required=True, help="Current strategy returns CSV/parquet")
    p.add_argument("--reference", required=True, help="Reference strategy returns CSV/parquet")
    p.add_argument("--out", default="", help="Optional JSON report path")
    args = p.parse_args(argv)
    report = compare(Path(args.current), Path(args.reference))
    print(json.dumps(report, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
