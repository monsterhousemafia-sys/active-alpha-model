"""Startup checks: verify market/signal data is current for today."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

LogFn = Callable[[str], None]


@dataclass
class DailyDataReport:
    reference_date: date
    price_latest: Optional[date] = None
    price_cache_fresh: bool = False
    price_current: bool = False
    signal_date: Optional[date] = None
    signal_current: bool = False
    paper_mark_today: Optional[bool] = None
    ok: bool = False
    log_lines: List[str] = field(default_factory=list)


def last_expected_market_date(*, today: Optional[date] = None) -> date:
    """Last US equity session expected on disk (Fri if weekend)."""
    ref = today or date.today()
    while ref.weekday() >= 5:
        ref -= timedelta(days=1)
    return ref


def _parse_iso_date(raw: str) -> Optional[date]:
    if not raw or raw in {"n/a", "NaT", "nan"}:
        return None
    try:
        return pd_timestamp_to_date(raw)
    except Exception:
        return None


def pd_timestamp_to_date(raw: str) -> date:
    import pandas as pd

    return pd.Timestamp(str(raw).split(" ")[0]).date()


def read_price_cache_latest_date(out_dir: Path, *, benchmark: Optional[str] = None) -> Optional[date]:
    """Latest session date in price cache — benchmark-first (SPY), else global max."""
    panel_path = Path(out_dir) / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return None
    try:
        import pandas as pd

        panel = pd.read_parquet(panel_path)
        if panel.empty or "date" not in panel.columns:
            return None
        panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
        if benchmark and "ticker" in panel.columns:
            sym = str(benchmark).upper().strip()
            sub = panel[panel["ticker"].astype(str).str.upper() == sym]
            if not sub.empty:
                latest = sub["date"].max()
                if pd.notna(latest):
                    return latest.date()
        latest = panel["date"].max()
        if pd.isna(latest):
            return None
        return latest.date()
    except Exception:
        return None


def _parquet_has_column(path: Path, col: str) -> bool:
    try:
        import pyarrow.parquet as pq

        return col in pq.ParquetFile(path).schema.names
    except Exception:
        return True


def read_price_cache_meta_fresh(out_dir: Path, *, ttl_hours: int = 24) -> bool:
    meta_path = Path(out_dir) / "price_cache" / "price_cache_meta.json"
    if not meta_path.is_file():
        return False
    try:
        from aa_features import _price_cache_is_fresh

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return bool(_price_cache_is_fresh(meta, ttl_hours))
    except Exception:
        return False


def read_signal_date(out_dir: Path, *, paper_model_dir: Optional[Path] = None) -> Optional[date]:
    candidates = [Path(out_dir) / "latest_target_portfolio.csv"]
    if paper_model_dir is not None:
        candidates.insert(0, Path(paper_model_dir) / "latest_target_portfolio.csv")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            import pandas as pd

            df = pd.read_csv(path, usecols=lambda c: c in {"signal_date", "ticker"})
            if df.empty or "signal_date" not in df.columns:
                continue
            val = str(df["signal_date"].iloc[0])
            parsed = _parse_iso_date(val)
            if parsed is not None:
                return parsed
        except Exception:
            continue
    return None


def is_market_data_current(latest: Optional[date], *, reference: Optional[date] = None) -> bool:
    if latest is None:
        return False
    ref = reference or last_expected_market_date()
    # Allow one session lag (e.g. early run before close) and long weekends.
    return (ref - latest).days <= 3 and latest <= ref


def is_signal_current(signal: Optional[date], *, reference: Optional[date] = None) -> bool:
    if signal is None:
        return False
    ref = reference or last_expected_market_date()
    return (ref - signal).days <= 7 and signal <= ref


def assess_daily_data(root: Path, env: Mapping[str, str]) -> DailyDataReport:
    from aa_paper_startup import mark_recorded_today, paper_dir_from_env

    ref = last_expected_market_date()
    out_rel = str(env.get("AA_BACKTEST_OUT_DIR", "model_output") or "model_output")
    out_dir = Path(out_rel) if Path(out_rel).is_absolute() else root / out_rel
    paper_model = str(env.get("AA_PAPER_MODEL_OUT_DIR", "") or "").strip()
    paper_model_dir = Path(paper_model) if paper_model and Path(paper_model).is_absolute() else (root / paper_model if paper_model else None)
    ttl = int(str(env.get("AA_PRICE_CACHE_TTL_HOURS", "24") or "24"))
    benchmark = str(env.get("AA_BENCHMARK", "SPY") or "SPY").upper().strip()

    price_latest = read_price_cache_latest_date(out_dir, benchmark=benchmark)
    price_meta_fresh = read_price_cache_meta_fresh(out_dir, ttl_hours=ttl)
    from aa_cache_coherence import price_cache_operational

    price_current = price_cache_operational(price_latest, meta_fresh=price_meta_fresh, reference=ref)

    signal = read_signal_date(out_dir, paper_model_dir=paper_model_dir)
    signal_current = is_signal_current(signal, reference=ref)

    paper_dir = paper_dir_from_env(env, root=root)
    paper_mark: Optional[bool] = None
    if (paper_dir / "paper_state.json").is_file():
        paper_mark = mark_recorded_today(paper_dir)

    lines: List[str] = []
    lines.append(f"[INFO] Tagesdaten-Check (Referenz: {ref.isoformat()})")

    if price_latest is None:
        lines.append("[WARN] Preis-Cache: keine Kursdaten gefunden")
    elif price_current:
        lines.append(f"[OK] Preis-Cache: Stand {price_latest.isoformat()} (tagesaktuell)")
    else:
        stale = f"Stand {price_latest.isoformat()}" if price_latest else "unbekannt"
        if not price_meta_fresh:
            lines.append(f"[WARN] Preis-Cache: {stale}, TTL abgelaufen — Update beim Lauf")
        else:
            lines.append(f"[WARN] Preis-Cache: {stale}, nicht tagesaktuell — Update beim Lauf")

    if signal is None:
        lines.append("[WARN] Modell-Signal: keine latest_target_portfolio.csv")
    elif signal_current:
        lines.append(f"[OK] Modell-Signal: {signal.isoformat()} (aktuell)")
    else:
        lines.append(f"[WARN] Modell-Signal: {signal.isoformat()} (veraltet)")

    if paper_mark is True:
        lines.append(f"[OK] Paper Mark-to-Market: für {ref.isoformat()} erfasst")
    elif paper_mark is False:
        lines.append(f"[INFO] Paper Mark-to-Market: für heute noch nicht erfasst (wird gestartet)")

    ok = price_current and signal_current
    if price_latest is None and signal is None:
        ok = False
    elif price_current and signal is None:
        ok = False

    if ok:
        lines.append("[OK] Tagesdaten gelesen und aktuell")
    else:
        lines.append("[INFO] Beim Lauf werden fehlende/veraltete Daten nachgeladen")

    return DailyDataReport(
        reference_date=ref,
        price_latest=price_latest,
        price_cache_fresh=price_meta_fresh,
        price_current=price_current,
        signal_date=signal,
        signal_current=signal_current,
        paper_mark_today=paper_mark,
        ok=ok,
        log_lines=lines,
    )


def apply_stale_data_env(env: Dict[str, str], report: DailyDataReport) -> Dict[str, str]:
    """Force price refresh on this run when cache is stale."""
    from aa_cache_coherence import apply_stale_price_env

    return apply_stale_price_env(env, price_current=report.price_current)


def verify_and_log_daily_data(
    root: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    apply_env: Optional[Dict[str, str]] = None,
) -> DailyDataReport:
    report = assess_daily_data(root, env)
    for line in report.log_lines:
        log(line)
    if apply_env is not None and not report.price_current:
        apply_env.update(apply_stale_data_env(dict(env), report))
    return report
