"""Stufe B — operational price cross-check (yfinance cache vs Stooq reference)."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from aa_safe_io import atomic_write_json
from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
from research.p12a.providers.stooq_readonly import ReadOnlyStooqProvider
from research.p12a.providers.yahoo_chart_readonly import ReadOnlyYahooChartProvider

_POLICY_REL = Path("control/price_data_sources_policy.json")
_EVIDENCE_REL = Path("evidence/price_crosscheck_latest.json")
_PANEL_REL = Path("model_output_sp500_pit_t212/price_cache/ohlcv_panel.parquet")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_price_data_sources_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "schema_version": 1,
            "enabled": True,
            "thresholds": {
                "warn_divergence_pct": 1.0,
                "fail_divergence_pct": 3.0,
                "min_reference_coverage_ratio": 0.6,
                "require_spy_match": True,
            },
            "fail_closed": {
                "block_signal_refresh_on_fail": True,
                "block_signal_refresh_on_warn": False,
                "block_signal_refresh_on_missing_spy": True,
            },
            "network": {"reference_fetch_timeout_s": 12, "max_reference_symbols_per_run": 20},
        }
    return doc


def resolve_crosscheck_symbols(root: Path, policy: Mapping[str, Any]) -> List[str]:
    mode = str(policy.get("symbols_mode") or "spy_plus_champion").lower()
    extra = [str(s).upper().strip() for s in (policy.get("extra_symbols") or ["SPY"]) if str(s).strip()]
    seen: set[str] = set()
    ordered: List[str] = []
    for sym in ["SPY"] + list(extra) + list(CHAMPION_SYMBOLS):
        if mode == "champion_only" and sym not in CHAMPION_SYMBOLS:
            continue
        tk = str(sym).upper().strip()
        if not tk or tk in seen:
            continue
        seen.add(tk)
        ordered.append(tk)
    max_n = int((policy.get("network") or {}).get("max_reference_symbols_per_run") or 20)
    max_n = max(max_n, 1)
    if "SPY" in seen:
        rest = [s for s in ordered if s != "SPY"]
        cap = max(max_n - 1, 0)
        return ["SPY"] + sorted(rest)[:cap]
    return sorted(ordered)[:max_n]


def _resolve_panel_path(root: Path) -> Path:
    root = Path(root)
    primary = root / _PANEL_REL
    if primary.is_file():
        return primary
    alt = root / "model_output" / "price_cache" / "ohlcv_panel.parquet"
    return alt if alt.is_file() else primary


def load_primary_closes(root: Path, symbols: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Latest yfinance-cache close per symbol from ohlcv_panel.parquet."""
    panel_path = _resolve_panel_path(root)
    want = {str(s).upper().strip() for s in symbols if str(s).strip()}
    if not panel_path.is_file() or not want:
        return {}
    try:
        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
    except Exception:
        return {}
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    panel["ticker"] = panel["ticker"].astype(str).str.upper()
    panel = panel.dropna(subset=["Close"])
    out: Dict[str, Dict[str, Any]] = {}
    for sym, grp in panel.groupby("ticker"):
        if sym not in want:
            continue
        row = grp.sort_values("date").iloc[-1]
        dt = row["date"]
        out[sym] = {
            "close": float(row["Close"]),
            "as_of": str(dt.date()) if hasattr(dt, "date") else str(dt),
            "source": "YFINANCE_PRICE_CACHE",
        }
    return out


def _divergence_pct(a: float, b: float) -> Optional[float]:
    if a <= 0 or b <= 0:
        return None
    mid = (a + b) / 2.0
    if mid <= 0:
        return None
    return abs(a - b) / mid * 100.0


def _parse_as_of(raw: Optional[str]) -> Optional[date]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _symbol_status(
    divergence_pct: Optional[float],
    *,
    warn_pct: float,
    fail_pct: float,
    has_primary: bool,
    has_reference: bool,
    primary_as_of: Optional[date],
    reference_as_of: Optional[date],
) -> str:
    if not has_primary:
        return "missing_primary"
    if not has_reference:
        return "missing_reference"
    if primary_as_of and reference_as_of and primary_as_of < reference_as_of:
        return "stale_primary"
    if primary_as_of and reference_as_of and primary_as_of > reference_as_of:
        return "stale_reference"
    if divergence_pct is None:
        return "fail"
    if divergence_pct >= fail_pct:
        return "fail"
    if divergence_pct >= warn_pct:
        return "warn"
    return "pass"


def _load_t212_live_usd(root: Path, symbols: Sequence[str]) -> Dict[str, float]:
    """Optional live T212/Yahoo merge — observation only, not gating."""
    try:
        from market.live_quote_engine import load_live_quote_snapshot

        snap = load_live_quote_snapshot(root) or {}
    except Exception:
        return {}
    prices_eur = snap.get("executable_prices_eur") or {}
    fx = snap.get("fx_usd_to_eur") or snap.get("usd_to_eur") or 0
    try:
        fx_f = float(fx)
    except (TypeError, ValueError):
        fx_f = 0.0
    if fx_f <= 0:
        fx_f = 0.866
    out: Dict[str, float] = {}
    for sym in symbols:
        tk = str(sym).upper()
        eur = prices_eur.get(tk)
        if eur is None:
            continue
        try:
            out[tk] = round(float(eur) / fx_f, 4)
        except (TypeError, ValueError):
            continue
    return out


def evaluate_price_crosscheck(
    root: Path,
    *,
    policy: Optional[Mapping[str, Any]] = None,
    fetch_reference: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    pol = dict(policy or load_price_data_sources_policy(root))
    if not pol.get("enabled", True):
        return {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "tier": "stufe_b",
            "ok": True,
            "skipped": True,
            "verdict": "skipped",
            "headline_de": "Stufe B deaktiviert",
            "block_signal_refresh": False,
            "policy_ref": str(_POLICY_REL),
            "checks": [],
            "blocks": [],
        }

    symbols = resolve_crosscheck_symbols(root, pol)
    thr = dict(pol.get("thresholds") or {})
    warn_pct = float(thr.get("warn_divergence_pct") or 1.0)
    fail_pct = float(thr.get("fail_divergence_pct") or 3.0)
    min_cov = float(thr.get("min_reference_coverage_ratio") or 0.6)
    require_spy = bool(thr.get("require_spy_match", True))
    fail_closed = dict(pol.get("fail_closed") or {})
    net = dict(pol.get("network") or {})
    timeout_s = float(net.get("reference_fetch_timeout_s") or 12)

    primary = load_primary_closes(root, symbols)
    stooq = ReadOnlyStooqProvider()
    yahoo_chart = ReadOnlyYahooChartProvider()
    reference: Dict[str, Dict[str, Any]] = {}
    if fetch_reference:
        for sym in symbols:
            row = stooq.fetch_last_close(sym, timeout_s=timeout_s)
            if not row:
                row = yahoo_chart.fetch_last_close(sym, timeout_s=timeout_s)
            if row:
                reference[sym] = row

    live_usd = _load_t212_live_usd(root, symbols) if pol.get("live_reference_source") else {}

    checks: List[Dict[str, Any]] = []
    counts = {
        "pass": 0,
        "warn": 0,
        "fail": 0,
        "stale_primary": 0,
        "stale_reference": 0,
        "missing_reference": 0,
        "missing_primary": 0,
    }
    for sym in symbols:
        prim = primary.get(sym)
        ref = reference.get(sym)
        live = live_usd.get(sym)
        prim_date = _parse_as_of(prim.get("as_of") if prim else None)
        ref_date = _parse_as_of(ref.get("as_of") if ref else None)
        same_date = bool(prim_date and ref_date and prim_date == ref_date)
        div = (
            _divergence_pct(float(prim["close"]), float(ref["close"]))
            if prim and ref and same_date
            else None
        )
        status = _symbol_status(
            div,
            warn_pct=warn_pct,
            fail_pct=fail_pct,
            has_primary=prim is not None,
            has_reference=ref is not None,
            primary_as_of=prim_date,
            reference_as_of=ref_date,
        )
        counts[status] = counts.get(status, 0) + 1
        live_div = None
        if prim and live and same_date:
            live_div = _divergence_pct(float(prim["close"]), float(live))
        checks.append(
            {
                "symbol": sym,
                "status": status,
                "same_date_compare": same_date,
                "primary_source": prim.get("source") if prim else None,
                "primary_close": prim.get("close") if prim else None,
                "primary_as_of": prim.get("as_of") if prim else None,
                "reference_source": ref.get("source") if ref else ReadOnlyStooqProvider().provider_name(),
                "reference_close": ref.get("close") if ref else None,
                "reference_as_of": ref.get("as_of") if ref else None,
                "divergence_pct": round(div, 4) if div is not None else None,
                "live_close_usd": live,
                "live_divergence_pct": round(live_div, 4) if live_div is not None else None,
            }
        )

    ref_cov = 0.0
    if symbols:
        ref_cov = sum(1 for c in checks if c.get("reference_close") is not None) / len(symbols)

    spy_check = next((c for c in checks if c.get("symbol") == "SPY"), None)
    spy_status = str(spy_check.get("status") if spy_check else "missing_primary")

    blocks: List[Dict[str, str]] = []
    verdict = "pass"
    divergence_fail = int(counts.get("fail", 0))
    if divergence_fail > 0:
        verdict = "fail"
        blocks.append({"code": "PRICE_DIVERGENCE_FAIL", "message_de": "Preis-Abweichung über Fail-Schwelle (gleicher Handelstag)"})
    elif int(counts.get("warn", 0)) > 0 or int(counts.get("stale_primary", 0)) > 0:
        verdict = "warn"
    if ref_cov < min_cov:
        verdict = "fail"
        blocks.append(
            {
                "code": "REFERENCE_COVERAGE_LOW",
                "message_de": f"Referenz-Abdeckung {ref_cov:.0%} < {min_cov:.0%}",
            }
        )
    if require_spy and spy_status in ("fail", "missing_primary"):
        verdict = "fail"
        if spy_status == "fail":
            blocks.append({"code": "SPY_DIVERGENCE", "message_de": "SPY-Abweichung am gleichen Handelstag"})
        elif spy_status == "missing_primary":
            blocks.append({"code": "SPY_PRIMARY_MISSING", "message_de": "SPY fehlt in price_cache"})
    elif require_spy and spy_status == "missing_reference" and bool(
        fail_closed.get("block_signal_refresh_on_missing_spy", True)
    ):
        verdict = "fail"
        blocks.append({"code": "SPY_REFERENCE_MISSING", "message_de": "SPY-Referenz fehlt"})

    block_refresh = False
    if verdict == "fail" and bool(fail_closed.get("block_signal_refresh_on_fail", True)):
        block_refresh = True
    if verdict == "warn" and bool(fail_closed.get("block_signal_refresh_on_warn", False)):
        block_refresh = True

    ok = verdict == "pass" or (verdict == "warn" and not block_refresh)
    messages_de: List[str] = []
    if ok:
        messages_de.append(
            f"[OK] Stufe B — {counts.get('pass', 0)}/{len(symbols)} Symbole im Toleranzband "
            f"(yfinance vs Stooq)."
        )
    elif verdict == "warn":
        stale_n = int(counts.get("stale_primary", 0))
        warn_n = int(counts.get("warn", 0))
        parts = []
        if warn_n:
            parts.append(f"{warn_n} mit leichter Abweichung (>{warn_pct}%)")
        if stale_n:
            parts.append(f"{stale_n} mit veraltetem price_cache")
        messages_de.append(f"[WARN] Stufe B — {', '.join(parts)}.")
    else:
        messages_de.append(
            f"[FAIL] Stufe B — Preis-Cross-Check blockiert Signal-Refresh "
            f"({counts.get('fail', 0)} fail, Referenz {ref_cov:.0%})."
        )

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "tier": "stufe_b",
        "headline_de": "Stufe B — operativer Preis-Cross-Check (price_cache vs Stooq/Yahoo)",
        "ok": ok,
        "verdict": verdict,
        "block_signal_refresh": block_refresh,
        "policy_ref": str(_POLICY_REL),
        "primary_daily_source": pol.get("primary_daily_source") or "yfinance_price_cache",
        "reference_daily_source": pol.get("reference_daily_source") or "stooq",
        "symbols_checked": len(symbols),
        "counts": counts,
        "reference_coverage_ratio": round(ref_cov, 4),
        "spy_status": spy_status,
        "thresholds": {"warn_divergence_pct": warn_pct, "fail_divergence_pct": fail_pct},
        "checks": checks,
        "blocks": blocks,
        "messages_de": messages_de,
    }


def crosscheck_blocks_signal_refresh(doc: Mapping[str, Any]) -> bool:
    return bool(doc.get("block_signal_refresh"))


def run_price_crosscheck(
    root: Path,
    *,
    persist: bool = True,
    fetch_reference: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    doc = evaluate_price_crosscheck(root, fetch_reference=fetch_reference)
    if persist and not doc.get("skipped"):
        path = root / _EVIDENCE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, doc)
    return doc


def load_price_crosscheck_evidence(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)
