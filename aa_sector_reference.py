"""Versioned sector reference (PIT CSV) with legacy SECTOR_MAP fallback."""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Union

import pandas as pd

from aa_constants import SECTOR_MAP
from aa_safe_io import atomic_write_text

SECTOR_REFERENCE_FILE = "sector_reference.csv"
SECTOR_YFINANCE_CACHE_FILE = "sector_yfinance_cache.json"
SECTOR_STATUS_FILE = "control/sector_reference_status.json"
GICS_TO_COARSE_FILE = "config/gics_to_coarse.json"

REFERENCE_COLUMNS = [
    "ticker",
    "sector_coarse",
    "sector_gics",
    "valid_from",
    "valid_to",
    "source",
    "as_of_utc",
]

_GICS_CONFIG: Optional[Dict[str, Any]] = None
_REFERENCE_CACHE: Dict[str, pd.DataFrame] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_ticker(ticker: str) -> str:
    return str(ticker or "").upper().strip()


def _coerce_as_of(as_of: Union[str, date, None]) -> str:
    if as_of is None:
        return date.today().isoformat()
    if isinstance(as_of, date):
        return as_of.isoformat()
    return str(as_of)[:10]


def resolve_root(root: Optional[Path] = None) -> Path:
    if root is not None:
        return Path(root).resolve()
    env_root = os.environ.get("AA_PROJECT_ROOT", "").strip()
    if env_root:
        return Path(env_root).resolve()
    return Path.cwd().resolve()


def resolve_reference_path(root: Optional[Path] = None) -> Path:
    root = resolve_root(root)
    rel = os.environ.get("AA_SECTOR_REFERENCE_FILE", SECTOR_REFERENCE_FILE).strip() or SECTOR_REFERENCE_FILE
    path = Path(rel)
    return path if path.is_absolute() else root / path


def resolve_gics_config_path(root: Optional[Path] = None) -> Path:
    root = resolve_root(root)
    rel = os.environ.get("AA_GICS_TO_COARSE_FILE", GICS_TO_COARSE_FILE).strip() or GICS_TO_COARSE_FILE
    path = Path(rel)
    candidate = path if path.is_absolute() else root / path
    if candidate.is_file():
        return candidate
    package_default = Path(__file__).resolve().parent / "config" / "gics_to_coarse.json"
    if package_default.is_file():
        return package_default
    return candidate


def _load_gics_config(root: Optional[Path] = None) -> Dict[str, Any]:
    global _GICS_CONFIG
    path = resolve_gics_config_path(root)
    path_key = str(path.resolve())
    cached_key = getattr(_load_gics_config, "_cached_path", None)
    if _GICS_CONFIG is not None and cached_key == path_key:
        return _GICS_CONFIG
    if not path.is_file():
        _GICS_CONFIG = {"exact": {}, "contains": [], "default": "Unknown"}
    else:
        _GICS_CONFIG = json.loads(path.read_text(encoding="utf-8"))
    _load_gics_config._cached_path = path_key  # type: ignore[attr-defined]
    return _GICS_CONFIG


def gics_to_coarse(sector_gics: str, *, root: Optional[Path] = None) -> str:
    raw = str(sector_gics or "").strip()
    if not raw or raw.lower() in {"nan", "none", "unknown", ""}:
        return "Unknown"
    cfg = _load_gics_config(root)
    exact = cfg.get("exact") or {}
    if raw in exact:
        return str(exact[raw])
    lower_key = {str(k).lower(): v for k, v in exact.items()}
    hit = lower_key.get(raw.lower())
    if hit:
        return str(hit)
    low = raw.lower()
    for rule in cfg.get("contains") or []:
        needle = str(rule.get("needle", "")).lower()
        if needle and needle in low:
            return str(rule.get("coarse", "Unknown"))
    return str(cfg.get("default", "Unknown"))


def parse_sector_gics_from_row(row: Mapping[str, Any], columns: Optional[Iterable[str]] = None) -> str:
    """Extract raw GICS/sector text from a universe or Wikipedia row."""
    cols = {str(c).strip().lower(): c for c in (columns or row.keys())}
    for key in (
        "sector_gics",
        "gics sector",
        "gics_sector",
        "sector",
        "gics sub-industry",
        "gics sub industry",
    ):
        if key in cols:
            val = row.get(cols[key], row.get(key, ""))
            text = str(val or "").strip()
            if text and text.lower() not in {"nan", "none"}:
                return text
    for key, val in row.items():
        if "sector" in str(key).lower():
            text = str(val or "").strip()
            if text and text.lower() not in {"nan", "none"}:
                return text
    return ""


def _read_reference_df(path: Path) -> pd.DataFrame:
    key = str(path.resolve())
    if key in _REFERENCE_CACHE and path.is_file():
        mtime = path.stat().st_mtime
        cached_mtime = _REFERENCE_CACHE.get(f"{key}__mtime")
        if cached_mtime == mtime:
            return _REFERENCE_CACHE[key].copy()
    if not path.is_file():
        empty = pd.DataFrame(columns=REFERENCE_COLUMNS)
        _REFERENCE_CACHE[key] = empty
        _REFERENCE_CACHE[f"{key}__mtime"] = None
        return empty.copy()
    df = pd.read_csv(path)
    for col in REFERENCE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["valid_from"] = df["valid_from"].astype(str).str[:10]
    df["valid_to"] = df["valid_to"].fillna("").astype(str).str[:10]
    _REFERENCE_CACHE[key] = df
    _REFERENCE_CACHE[f"{key}__mtime"] = path.stat().st_mtime
    return df.copy()


def _invalidate_reference_cache(path: Path) -> None:
    key = str(path.resolve())
    _REFERENCE_CACHE.pop(key, None)
    _REFERENCE_CACHE.pop(f"{key}__mtime", None)


def _day_before(iso_date: str) -> str:
    d = pd.Timestamp(iso_date) - pd.Timedelta(days=1)
    return d.date().isoformat()


def _rows_from_records(
    records: List[Dict[str, str]],
    *,
    valid_from: str,
    source_detail: str,
    as_of_utc: str,
    root: Optional[Path],
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    vf = _coerce_as_of(valid_from)
    for rec in records:
        tk = _normalize_ticker(rec.get("ticker", ""))
        if not tk:
            continue
        gics = str(rec.get("sector_gics") or rec.get("sector") or "").strip()
        if not gics:
            gics = parse_sector_gics_from_row(rec)
        coarse = str(rec.get("sector_coarse") or "").strip()
        if not coarse:
            coarse = gics_to_coarse(gics, root=root) if gics else "Unknown"
        out.append(
            {
                "ticker": tk,
                "sector_coarse": coarse,
                "sector_gics": gics,
                "valid_from": vf,
                "valid_to": "",
                "source": str(rec.get("source") or source_detail or "wikipedia_sp500")[:120],
                "as_of_utc": as_of_utc,
            }
        )
    return out


def update_sector_reference_from_records(
    records: List[Dict[str, str]],
    path: Path,
    *,
    valid_from: str,
    source_detail: str,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Merge universe records into sector_reference.csv (PIT: closes rows on sector change)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    as_of_utc = _utc_now_iso()
    incoming = _rows_from_records(
        records,
        valid_from=valid_from,
        source_detail=source_detail,
        as_of_utc=as_of_utc,
        root=root,
    )
    df = _read_reference_df(path)
    added = 0
    updated = 0
    vf = _coerce_as_of(valid_from)

    for row in incoming:
        tk = row["ticker"]
        new_coarse = row["sector_coarse"]
        mask_open = (df["ticker"] == tk) & (df["valid_to"].fillna("").astype(str).str.len() == 0)
        if mask_open.any():
            idx = df.index[mask_open]
            current = str(df.loc[idx[-1], "sector_coarse"])
            if current == new_coarse:
                df.loc[idx[-1], "as_of_utc"] = as_of_utc
                if row["sector_gics"]:
                    df.loc[idx[-1], "sector_gics"] = row["sector_gics"]
                updated += 1
                continue
            close_date = _day_before(vf)
            df.loc[idx, "valid_to"] = close_date
            added += 1
        else:
            added += 1
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

    df = df[REFERENCE_COLUMNS].drop_duplicates(
        subset=["ticker", "valid_from", "sector_coarse", "valid_to"],
        keep="last",
    )
    csv_text = df.to_csv(index=False)
    atomic_write_text(path, csv_text)
    _invalidate_reference_cache(path)
    return {
        "added": int(added),
        "updated": int(updated),
        "as_of_utc": as_of_utc,
        "path": str(path),
        "row_count": int(len(df)),
    }


def lookup_sector(
    ticker: str,
    as_of: Union[str, date, None] = None,
    root: Optional[Path] = None,
) -> str:
    """PIT sector lookup: CSV → legacy SECTOR_MAP → Unknown."""
    tk = _normalize_ticker(ticker)
    if not tk:
        return "Unknown"
    as_of_s = _coerce_as_of(as_of)
    ref_path = resolve_reference_path(root)
    if ref_path.is_file():
        df = _read_reference_df(ref_path)
        sub = df[df["ticker"] == tk].copy()
        if not sub.empty:
            vf = pd.to_datetime(sub["valid_from"], errors="coerce")
            vt_raw = sub["valid_to"].fillna("").astype(str).str.strip()
            vt = pd.to_datetime(vt_raw.replace("", pd.NA), errors="coerce")
            as_of_ts = pd.Timestamp(as_of_s)
            ok_from = vf <= as_of_ts
            ok_to = vt_raw.eq("") | (vt >= as_of_ts)
            pit = sub.loc[ok_from & ok_to]
            if not pit.empty:
                pit = pit.sort_values("valid_from")
                return str(pit.iloc[-1]["sector_coarse"]) or "Unknown"
    legacy = SECTOR_MAP.get(tk)
    if legacy:
        return str(legacy)
    return "Unknown"


def clear_reference_cache() -> None:
    """Test helper: drop in-memory reference CSV and GICS config cache."""
    global _GICS_CONFIG
    _REFERENCE_CACHE.clear()
    _GICS_CONFIG = None
    if hasattr(_load_gics_config, "_cached_path"):
        delattr(_load_gics_config, "_cached_path")


def write_sector_reference_status(root: Path, result: Mapping[str, Any]) -> Path:
    root = resolve_root(root)
    rel = os.environ.get("AA_SECTOR_STATUS_FILE", SECTOR_STATUS_FILE).strip() or SECTOR_STATUS_FILE
    path = Path(rel) if Path(rel).is_absolute() else root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at_utc": _utc_now_iso(), **dict(result)}
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def load_sector_reference_status(root: Optional[Path] = None) -> Dict[str, Any]:
    root = resolve_root(root)
    rel = os.environ.get("AA_SECTOR_STATUS_FILE", SECTOR_STATUS_FILE).strip() or SECTOR_STATUS_FILE
    path = Path(rel) if Path(rel).is_absolute() else root / rel
    if not path.is_file():
        return {"schema_version": 1, "status": "MISSING"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "status": "ERROR"}


def format_sector_dashboard_status(root: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only status for Live-Dashboard (traffic: GRUEN/GELB/ROT)."""
    root = resolve_root(root)
    st = load_sector_reference_status(root)
    try:
        from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

        cov = champion_sector_coverage(root, CHAMPION_SYMBOLS)
    except Exception:
        cov = {"ok": False, "mapped_count": 0, "symbol_count": 0, "unknown_tickers": []}
    ref_path = resolve_reference_path(root)
    as_of = ""
    if ref_path.is_file():
        try:
            df = _read_reference_df(ref_path)
            if not df.empty and "as_of_utc" in df.columns:
                as_of = str(df["as_of_utc"].max())[:10]
        except Exception:
            pass
    if not as_of:
        as_of = str(st.get("updated_at_utc") or "")[:10]
    traffic = "GRUEN"
    if str(st.get("status")) in {"ERROR", "MISSING"}:
        traffic = "ROT"
    elif not cov.get("ok"):
        traffic = "GELB"
    mapped = int(cov.get("mapped_count") or 0)
    total = int(cov.get("symbol_count") or 0)
    summary_de = (
        f"Sektoren: Stand {as_of or '—'} · Champion {mapped}/{total}"
        if cov.get("ok")
        else f"Sektoren: Champion {mapped}/{total} — unbekannt: {', '.join(cov.get('unknown_tickers') or [])}"
    )
    if str(st.get("status")) == "MISSING":
        summary_de = "Sektoren: noch kein Refresh — ① oder ③ starten"
        traffic = "GELB"
    return {
        "traffic": traffic,
        "summary_de": summary_de,
        "champion_coverage": cov,
        "status_file": st,
        "reference_path": str(ref_path),
    }


def champion_sector_coverage(root: Optional[Path], symbols: Iterable[str]) -> Dict[str, Any]:
    root = resolve_root(root)
    rows = []
    for sym in symbols:
        tk = _normalize_ticker(sym)
        sec = lookup_sector(tk, root=root)
        rows.append({"ticker": tk, "sector_coarse": sec, "is_unknown": sec == "Unknown"})
    unknown = [r["ticker"] for r in rows if r["is_unknown"]]
    return {
        "symbol_count": len(rows),
        "mapped_count": len(rows) - len(unknown),
        "unknown_count": len(unknown),
        "unknown_tickers": unknown,
        "symbols": rows,
        "ok": len(unknown) == 0,
    }


def sync_sector_reference_after_universe(
    records: List[Dict[str, str]],
    *,
    valid_from: str,
    source_detail: str,
    root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Update sector_reference.csv from universe records (S2 hook)."""
    root = resolve_root(root)
    path = resolve_reference_path(root)
    result = update_sector_reference_from_records(
        records,
        path,
        valid_from=valid_from,
        source_detail=source_detail,
        root=root,
    )
    status = {
        "schema_version": 1,
        "status": "OK",
        "source_detail": source_detail,
        "valid_from": _coerce_as_of(valid_from),
        "last_universe_sync": result,
        "summary_de": (
            f"Sektor-Referenz: {result.get('row_count', 0)} Zeilen "
            f"(+{result.get('added', 0)}, ~{result.get('updated', 0)} aktualisiert)."
        ),
    }
    write_sector_reference_status(root, status)
    return {**result, "status": status}


def records_from_constituents_df(df: pd.DataFrame, *, source: str = "wikipedia_sp500") -> List[Dict[str, str]]:
    """Build universe-style records from parse_current_constituents output."""
    rows: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        tk = _normalize_ticker(str(row.get("ticker", "")))
        if not tk:
            continue
        gics = str(row.get("sector", row.get("sector_gics", "")) or "").strip()
        if not gics:
            gics = parse_sector_gics_from_row(row, columns=row.index)
        rows.append(
            {
                "ticker": tk,
                "sector_gics": gics,
                "sector_coarse": gics_to_coarse(gics) if gics else "Unknown",
                "company": str(row.get("company", "") or "").strip(),
                "source": source,
            }
        )
    return rows


def resolve_yfinance_cache_path(root: Optional[Path] = None) -> Path:
    root = resolve_root(root)
    rel = os.environ.get("AA_SECTOR_YFINANCE_CACHE_FILE", SECTOR_YFINANCE_CACHE_FILE).strip() or SECTOR_YFINANCE_CACHE_FILE
    path = Path(rel)
    return path if path.is_absolute() else root / path


def _env_enabled(env: Mapping[str, str], key: str, *, default: str = "1") -> bool:
    return str(env.get(key, default)).strip().lower() not in {"0", "false", "no", "off", ""}


def _reference_max_age_days(env: Mapping[str, str]) -> int:
    raw = str(
        env.get("AA_SECTOR_REFERENCE_MAX_AGE_DAYS")
        or env.get("AA_TICKER_CACHE_MAX_AGE_DAYS", "7")
        or "7"
    ).strip()
    try:
        return max(int(raw), 0)
    except ValueError:
        return 7


def _load_yfinance_cache(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "entries": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("entries"), dict):
            return doc
    except (json.JSONDecodeError, OSError):
        pass
    return {"schema_version": 1, "entries": {}}


def _save_yfinance_cache(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at_utc"] = _utc_now_iso()
    atomic_write_text(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def _cache_entry_fresh(entry: Mapping[str, Any], ttl_days: int) -> bool:
    if ttl_days <= 0:
        return False
    raw = str(entry.get("fetched_at_utc") or "").strip()
    if not raw:
        return False
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0
    return age <= float(ttl_days)


def _fetch_yfinance_sector_raw(ticker: str) -> tuple[str, str]:
    """Return (sector_or_industry_label, industry_detail) from yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return "", ""
    try:
        t = yf.Ticker(ticker)
        sector = ""
        industry = ""
        fast = getattr(t, "fast_info", None)
        if fast is not None:
            sector = str(getattr(fast, "sector", "") or getattr(fast, "sectorKey", "") or "").strip()
            industry = str(getattr(fast, "industry", "") or getattr(fast, "industryKey", "") or "").strip()
        if not sector and not industry:
            info = getattr(t, "info", None) or {}
            if isinstance(info, dict):
                sector = str(info.get("sector") or "").strip()
                industry = str(info.get("industry") or "").strip()
        label = sector or industry
        if label.lower() in {"nan", "none", "unknown"}:
            label = ""
        return label, industry
    except Exception:
        return "", ""


def resolve_missing_sectors_yfinance(
    tickers: Iterable[str],
    cache_path: Path,
    *,
    ttl_days: int = 7,
    root: Optional[Path] = None,
    sleep_s: float = 0.15,
) -> tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Fetch sector labels for tickers; uses JSON cache with TTL."""
    cache_path = Path(cache_path)
    doc = _load_yfinance_cache(cache_path)
    entries: Dict[str, Any] = dict(doc.get("entries") or {})
    records: List[Dict[str, str]] = []
    fetched = 0
    cache_hits = 0
    failures: List[str] = []

    for raw in sorted({_normalize_ticker(t) for t in tickers if _normalize_ticker(t)}):
        entry = entries.get(raw) if isinstance(entries.get(raw), dict) else None
        label = ""
        industry = ""
        if entry and _cache_entry_fresh(entry, ttl_days):
            label = str(entry.get("sector_gics") or "").strip()
            industry = str(entry.get("industry") or "").strip()
            cache_hits += 1
        else:
            label, industry = _fetch_yfinance_sector_raw(raw)
            if label:
                fetched += 1
                time.sleep(max(float(sleep_s), 0.0))
            else:
                failures.append(raw)
            entries[raw] = {
                "sector_gics": label,
                "industry": industry,
                "fetched_at_utc": _utc_now_iso(),
            }
        if not label:
            continue
        coarse = gics_to_coarse(label, root=root)
        if coarse == "Unknown" and industry:
            coarse = gics_to_coarse(industry, root=root)
        records.append(
            {
                "ticker": raw,
                "sector_gics": label,
                "sector_coarse": coarse if coarse != "Unknown" else gics_to_coarse(industry, root=root),
                "source": "yfinance_fallback",
            }
        )

    doc["entries"] = entries
    _save_yfinance_cache(cache_path, doc)
    meta = {
        "requested": len(set(_normalize_ticker(t) for t in tickers if _normalize_ticker(t))),
        "resolved_records": len(records),
        "network_fetches": fetched,
        "cache_hits": cache_hits,
        "failures": failures,
        "cache_path": str(cache_path),
    }
    return records, meta


def collect_run_tickers(root: Path, env: Mapping[str, str]) -> List[str]:
    """Tickers that need sector coverage in the current run (S3.3)."""
    root = resolve_root(root)
    out: Set[str] = set()
    try:
        from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

        out.update(CHAMPION_SYMBOLS)
    except Exception:
        pass

    for rel in (
        "model_output_sp500_pit_t212/latest_target_portfolio.csv",
        "paper/latest_target_portfolio.csv",
    ):
        path = root / rel
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path)
            if "ticker" in df.columns:
                out.update(_normalize_ticker(t) for t in df["ticker"].astype(str) if _normalize_ticker(t))
        except Exception:
            pass

    try:
        from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

        st = load_cached_broker_status(root)
        if st and st.positions:
            for pos in st.positions:
                sym = _normalize_ticker(str(pos.get("symbol") or pos.get("ticker") or ""))
                if sym:
                    out.add(sym)
    except Exception:
        pass

    cache_rel = str(env.get("AA_TICKER_CACHE_DIR", "universe_snapshots") or "universe_snapshots")
    cache_dir = Path(cache_rel) if Path(cache_rel).is_absolute() else root / cache_rel
    latest = cache_dir / "sp500_latest.csv"
    if latest.is_file():
        try:
            df = pd.read_csv(latest, usecols=["ticker"])
            out.update(_normalize_ticker(t) for t in df["ticker"].astype(str) if _normalize_ticker(t))
        except Exception:
            pass

    return sorted(out)


def _tickers_still_unknown(tickers: Iterable[str], *, root: Path, as_of: str) -> List[str]:
    missing: List[str] = []
    for tk in tickers:
        if lookup_sector(tk, as_of=as_of, root=root) == "Unknown":
            missing.append(tk)
    return missing


def _universe_refresh_needed(root: Path, env: Mapping[str, str], max_age_days: int) -> bool:
    source = str(env.get("AA_PAPER_TICKER_SOURCE", "") or env.get("AA_BACKTEST_TICKER_SOURCE", "")).strip().lower()
    if source not in {"sp500_auto", "wikipedia_sp500", "slickcharts_sp500"}:
        return False
    from aa_universe import cached_snapshot_age_days, latest_cached_sp500_path

    cache_rel = str(env.get("AA_TICKER_CACHE_DIR", "universe_snapshots") or "universe_snapshots")
    cache_dir = Path(cache_rel) if Path(cache_rel).is_absolute() else root / cache_rel
    latest = latest_cached_sp500_path(cache_dir)
    if latest is None:
        return True
    age = cached_snapshot_age_days(latest)
    if age is None:
        return True
    if "sector_gics" not in pd.read_csv(latest, nrows=0).columns:
        return True
    return age > float(max_age_days)


def ensure_sector_reference_fresh(root: Path, env: Mapping[str, str]) -> Dict[str, Any]:
    """Orchestrate Wikipedia universe refresh (if stale) + yfinance for remaining unknown run tickers."""
    root = resolve_root(root)
    env = dict(env)
    if not _env_enabled(env, "AA_SECTOR_REFERENCE_MODE", default="auto"):
        return {
            "refreshed": False,
            "reason": "DISABLED",
            "message_de": "Sektor-Referenz: AA_SECTOR_REFERENCE_MODE=off",
        }

    max_age = _reference_max_age_days(env)
    as_of = date.today().isoformat()
    universe_refreshed = False
    universe_logs: List[str] = []
    yfinance_meta: Dict[str, Any] = {}
    yfinance_result: Dict[str, Any] = {}

    if _universe_refresh_needed(root, env, max_age):
        try:
            from aa_ops_refresh import refresh_universe_if_needed

            universe_refreshed = bool(refresh_universe_if_needed(root, env, log=universe_logs.append))
        except Exception as exc:
            universe_logs.append(f"[WARN] Universum/Sektor-Refresh: {exc}")

    run_tickers = collect_run_tickers(root, env)
    missing = _tickers_still_unknown(run_tickers, root=root, as_of=as_of)

    if missing and _env_enabled(env, "AA_SECTOR_YFINANCE_FALLBACK", default="1"):
        records, yfinance_meta = resolve_missing_sectors_yfinance(
            missing,
            resolve_yfinance_cache_path(root),
            ttl_days=max_age,
            root=root,
        )
        if records:
            yfinance_result = update_sector_reference_from_records(
                records,
                resolve_reference_path(root),
                valid_from=as_of,
                source_detail="yfinance_fallback",
                root=root,
            )

    try:
        from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

        champion_cov = champion_sector_coverage(root, CHAMPION_SYMBOLS)
    except Exception:
        champion_cov = champion_sector_coverage(root, run_tickers)

    refreshed = bool(universe_refreshed or yfinance_result.get("added") or yfinance_result.get("updated"))
    still_unknown = _tickers_still_unknown(run_tickers, root=root, as_of=as_of)
    summary_de = (
        f"Sektor-Refresh: Universum={'ja' if universe_refreshed else 'nein'}, "
        f"yfinance={yfinance_meta.get('resolved_records', 0)}, "
        f"Champion {champion_cov.get('mapped_count', 0)}/{champion_cov.get('symbol_count', 0)}"
    )
    status = {
        "schema_version": 1,
        "status": "OK" if champion_cov.get("ok") else "PARTIAL",
        "refreshed": refreshed,
        "universe_refreshed": universe_refreshed,
        "yfinance": {**yfinance_meta, **yfinance_result},
        "champion_coverage": champion_cov,
        "run_ticker_count": len(run_tickers),
        "still_unknown": still_unknown,
        "summary_de": summary_de,
        "message_de": summary_de,
    }
    write_sector_reference_status(root, status)
    return {
        "refreshed": refreshed,
        "universe_refreshed": universe_refreshed,
        "universe_logs": universe_logs,
        "yfinance": yfinance_meta,
        "yfinance_update": yfinance_result,
        "champion_coverage": champion_cov,
        "still_unknown": still_unknown,
        "message_de": summary_de,
        "status": status,
    }


def audit_sp500_snapshot_sector_columns(root: Optional[Path] = None) -> Dict[str, Any]:
    """Read-only check whether cached S&P snapshot exposes sector_gics (S6 evidence)."""
    root = resolve_root(root)
    cache_rel = os.environ.get("AA_TICKER_CACHE_DIR", "universe_snapshots").strip() or "universe_snapshots"
    cache_dir = Path(cache_rel) if Path(cache_rel).is_absolute() else root / cache_rel
    try:
        from aa_universe import latest_cached_sp500_path

        latest = latest_cached_sp500_path(cache_dir)
    except Exception as exc:
        return {"path": None, "exists": False, "error": str(exc)[:200]}
    if latest is None or not latest.is_file():
        return {"path": None, "exists": False, "has_sector_gics": False, "has_sector_coarse": False}
    try:
        cols = list(pd.read_csv(latest, nrows=0).columns)
    except Exception as exc:
        return {"path": str(latest), "exists": True, "error": str(exc)[:200]}
    return {
        "path": str(latest),
        "exists": True,
        "columns": cols,
        "has_sector_gics": "sector_gics" in cols,
        "has_sector_coarse": "sector_coarse" in cols,
        "row_count": int(len(pd.read_csv(latest, usecols=["ticker"]))) if "ticker" in cols else None,
    }


def build_sector_rollout_summary(root: Optional[Path] = None) -> Dict[str, Any]:
    """Evidence payload for S6/S7 rollout verification (read-only)."""
    root = resolve_root(root)
    try:
        from aa_evidence_schema import AUTHORITATIVE_CHAMPION

        champion_id = AUTHORITATIVE_CHAMPION
    except Exception:
        champion_id = "R3_w075_q065_noexit"
    try:
        from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

        symbols = CHAMPION_SYMBOLS
    except Exception:
        symbols = ()
    champion_cov = champion_sector_coverage(root, symbols)
    ref_path = resolve_reference_path(root)
    status = load_sector_reference_status(root)
    snapshot = audit_sp500_snapshot_sector_columns(root)
    return {
        "schema_version": 1,
        "phase": "S6",
        "generated_at_utc": _utc_now_iso(),
        "authoritative_champion": champion_id,
        "lookup_chain": [
            "sector_reference.csv",
            "sector_yfinance_cache.json",
            "SECTOR_MAP",
            "Unknown",
        ],
        "reference_file_exists": ref_path.is_file(),
        "reference_path": str(ref_path),
        "sector_reference_status": status,
        "champion_coverage": champion_cov,
        "sp500_latest_snapshot": snapshot,
        "acceptance": {
            "champion_all_mapped": bool(champion_cov.get("ok")),
            "snapshot_has_sector_gics": bool(snapshot.get("has_sector_gics")),
        },
        "rollout_status": (
            "PASS"
            if champion_cov.get("ok") and snapshot.get("has_sector_gics")
            else "PENDING_ROLLOUT"
        ),
    }
