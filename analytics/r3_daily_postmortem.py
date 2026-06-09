"""Read-only Tages-Postmortem — Plan-Picks vs. SPY-Tagesreturn (OHLCV, kein Backtest)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_daily_postmortem_policy.json")
_EVIDENCE_REL = Path("evidence/r3_daily_postmortem_latest.json")


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


def load_postmortem_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "enabled": True,
            "max_picks": 12,
            "bad_day_underperform_bps": 50,
            "bad_day_portfolio_pct": -0.01,
            "voice_on_bad_day": True,
            "voice_on_stale_sync": True,
            "benchmark_ticker": "SPY",
            "exclude_tickers": ["SPY"],
            "portfolio_csv_rel": "model_output_sp500_pit_t212/target_portfolio_explained.csv",
        }
    return doc


def _out_dir(root: Path) -> Path:
    return Path(root) / "model_output_sp500_pit_t212"


def _load_panel_closes(out_dir: Path) -> Dict[str, Any]:
    panel_path = out_dir / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return {"ok": False, "reason_de": "OHLCV-Panel fehlt — Prognose/Ingest zuerst"}
    try:
        import pandas as pd

        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
    except Exception:
        try:
            import pandas as pd

            panel = pd.read_parquet(panel_path)
        except Exception as exc:
            return {"ok": False, "reason_de": f"Panel nicht lesbar: {exc}"[:80]}
    if panel.empty or "ticker" not in panel.columns or "Close" not in panel.columns:
        return {"ok": False, "reason_de": "Panel ohne ticker/Close"}
    panel = panel.copy()
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    panel = panel.dropna(subset=["date"])
    panel["ticker"] = panel["ticker"].astype(str).str.upper()
    panel["Close"] = pd.to_numeric(panel["Close"], errors="coerce")
    latest = panel["date"].max()
    if pd.isna(latest):
        return {"ok": False, "reason_de": "Kein Datum im Panel"}
    prev_dates = sorted(panel.loc[panel["date"] < latest, "date"].unique())
    if not prev_dates:
        return {"ok": False, "reason_de": "Kein Vortag im Panel"}
    prev = prev_dates[-1]
    as_of = latest.date().isoformat()
    prev_iso = prev.date().isoformat() if hasattr(prev, "date") else str(prev)[:10]
    rows: Dict[str, Tuple[float, float, float]] = {}
    for ticker, grp in panel.groupby("ticker"):
        g = grp.sort_values("date")
        c_now = g.loc[g["date"] == latest, "Close"]
        c_prev = g.loc[g["date"] == prev, "Close"]
        if c_now.empty or c_prev.empty:
            continue
        p0 = float(c_prev.iloc[-1])
        p1 = float(c_now.iloc[-1])
        if p0 <= 0:
            continue
        rows[str(ticker).upper()] = (p0, p1, p1 / p0 - 1.0)
    return {
        "ok": True,
        "as_of_date": as_of,
        "prev_date": prev_iso,
        "returns": rows,
    }


def _load_plan_picks(root: Path, policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = Path(root)
    exclude = {str(t).upper() for t in (policy.get("exclude_tickers") or ["SPY"])}
    max_picks = int(policy.get("max_picks") or 12)

    plan_path = root / "evidence/pilot_investment_plan_latest.json"
    plan = _load_json(plan_path)
    picks: List[Dict[str, Any]] = []
    for row in plan.get("allocations") or []:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("symbol") or "").upper()
        if not sym or sym in exclude:
            continue
        tw = row.get("model_weight_pct")
        if tw is None:
            tw = row.get("target_weight_pct")
        try:
            weight = float(tw) / 100.0 if tw is not None and float(tw) > 1 else float(tw or 0)
        except (TypeError, ValueError):
            weight = 0.0
        if weight <= 0:
            weight = float(row.get("target_eur") or 0)
        picks.append(
            {
                "symbol": sym,
                "weight": weight,
                "target_eur": row.get("target_eur"),
                "pick_rationale_de": str(row.get("pick_rationale_de") or "")[:120],
            }
        )
    if picks:
        total = sum(float(p["weight"]) for p in picks if p["weight"] > 0)
        if total > 0:
            for p in picks:
                if p["weight"] > 0:
                    p["weight_norm"] = float(p["weight"]) / total
        return picks[:max_picks]

    csv_rel = str(policy.get("portfolio_csv_rel") or "model_output_sp500_pit_t212/target_portfolio_explained.csv")
    csv_path = root / csv_rel
    if not csv_path.is_file():
        return []
    try:
        import pandas as pd

        df = pd.read_csv(csv_path)
    except Exception:
        return []
    if df.empty or "ticker" not in df.columns:
        return []
    eligible = df.get("eligible")
    if eligible is not None:
        df = df[df["eligible"].astype(str).str.lower().isin(("true", "1", "yes"))]
    df = df[~df["ticker"].astype(str).str.upper().isin(exclude)]
    if "target_weight" in df.columns:
        df = df.sort_values("target_weight", ascending=False)
    for _, row in df.head(max_picks).iterrows():
        sym = str(row.get("ticker") or "").upper()
        try:
            w = float(row.get("target_weight") or 0)
        except (TypeError, ValueError):
            w = 0.0
        if not sym or w <= 0:
            continue
        picks.append({"symbol": sym, "weight": w, "weight_norm": w, "target_eur": None})
    total = sum(float(p["weight"]) for p in picks)
    if total > 0:
        for p in picks:
            p["weight_norm"] = float(p["weight"]) / total
    return picks


def _stale_sync_warning(root: Path, policy: Dict[str, Any]) -> Optional[str]:
    if not policy.get("voice_on_stale_sync", True):
        return None
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        trust = assess_t212_trust_from_root(root, persist=False)
        if trust.get("trusted"):
            return None
        return str(trust.get("message_de") or "Kontostand veraltet — «Aktualisieren» in R3")[:160]
    except Exception:
        bond = _load_json(root / "evidence/r3_t212_api_bond_latest.json")
        msg = str(bond.get("confirmation_de") or bond.get("message_de") or "")
        if "veraltet" in msg.lower() or "aktualisieren" in msg.lower():
            return msg[:160]
        return None


def run_daily_postmortem(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Tagesreturn der Plan-Picks vs. Benchmark — read-only, Evidence für R3."""
    root = Path(root)
    policy = load_postmortem_policy(root)
    if not policy.get("enabled", True):
        return {"ok": False, "skipped": True, "reason_de": "postmortem_disabled"}

    bench = str(policy.get("benchmark_ticker") or "SPY").upper()
    panel = _load_panel_closes(_out_dir(root))
    picks = _load_plan_picks(root, policy)
    predict = _load_json(root / "control/prediction_readiness.json")
    signal_date = str(predict.get("signal_date") or "")[:10]

    stale_warn = _stale_sync_warning(root, policy)

    if not panel.get("ok"):
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": False,
            "signal_date": signal_date,
            "message_de": panel.get("reason_de") or "Postmortem — keine Kurse",
            "stale_sync_warning_de": stale_warn,
            "voice_warning_de": stale_warn,
        }
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    returns: Dict[str, Tuple[float, float, float]] = panel.get("returns") or {}
    bench_row = returns.get(bench)
    bench_ret = bench_row[2] if bench_row else None

    lines: List[Dict[str, Any]] = []
    weighted_sum = 0.0
    weight_total = 0.0
    missing: List[str] = []

    for pick in picks:
        sym = str(pick.get("symbol") or "").upper()
        w = float(pick.get("weight_norm") or pick.get("weight") or 0)
        if w <= 0:
            continue
        row = returns.get(sym)
        if not row:
            missing.append(sym)
            continue
        ret = float(row[2])
        weighted_sum += w * ret
        weight_total += w
        lines.append(
            {
                "symbol": sym,
                "daily_return_pct": round(ret * 100, 2),
                "vs_spy_bps": round((ret - (bench_ret or 0)) * 10000, 1) if bench_ret is not None else None,
                "weight_pct": round(w * 100, 2),
            }
        )

    lines.sort(key=lambda x: float(x.get("daily_return_pct") or 0))
    port_ret = weighted_sum / weight_total if weight_total > 0 else None
    under_bps = float(policy.get("bad_day_underperform_bps") or 50) / 10000.0
    bad_abs = float(policy.get("bad_day_portfolio_pct") or -0.01)
    bad_day = False
    if port_ret is not None and bench_ret is not None:
        bad_day = port_ret < bad_abs or (port_ret - bench_ret) < -under_bps
    elif port_ret is not None:
        bad_day = port_ret < bad_abs

    worst = lines[0] if lines else None
    best = lines[-1] if lines else None

    summary_parts: List[str] = []
    if port_ret is not None:
        summary_parts.append(f"Plan-Portfolio {port_ret * 100:+.2f} %")
    if bench_ret is not None:
        summary_parts.append(f"{bench} {bench_ret * 100:+.2f} %")
    if port_ret is not None and bench_ret is not None:
        summary_parts.append(f"Delta {(port_ret - bench_ret) * 100:+.2f} %")
    summary_de = " · ".join(summary_parts) if summary_parts else "Keine auswertbaren Pick-Returns"

    voice_parts: List[str] = []
    if stale_warn:
        voice_parts.append(stale_warn)
    if bad_day and policy.get("voice_on_bad_day", True):
        voice_parts.append(
            f"Achtung — schwacher Handelstag. {summary_de}."
            + (f" Schwächste Position: {worst['symbol']} {worst['daily_return_pct']:+.1f} Prozent." if worst else "")
        )
    elif port_ret is not None and not bad_day:
        voice_parts.append(f"Tagesbilanz: {summary_de}.")

    voice_warning_de = " ".join(voice_parts)[:400] if voice_parts else None

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": bool(lines),
        "read_only": True,
        "signal_date": signal_date,
        "as_of_date": panel.get("as_of_date"),
        "prev_date": panel.get("prev_date"),
        "benchmark_ticker": bench,
        "benchmark_return_pct": round(bench_ret * 100, 2) if bench_ret is not None else None,
        "portfolio_return_pct": round(port_ret * 100, 2) if port_ret is not None else None,
        "delta_vs_benchmark_pct": (
            round((port_ret - bench_ret) * 100, 2) if port_ret is not None and bench_ret is not None else None
        ),
        "bad_day": bad_day,
        "pick_count": len(lines),
        "missing_symbols": missing[:8],
        "picks": lines,
        "worst": worst,
        "best": best,
        "summary_de": summary_de,
        "headline_de": (
            f"⚠ Schlechter Tag — {summary_de}" if bad_day else f"Tagesbilanz — {summary_de}"
        ),
        "stale_sync_warning_de": stale_warn,
        "voice_warning_de": voice_warning_de,
        "message_de": summary_de,
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def format_postmortem_reply_de(doc: Dict[str, Any]) -> str:
    if doc.get("skipped"):
        return str(doc.get("reason_de") or "Postmortem deaktiviert")
    if not doc.get("ok"):
        parts = [str(doc.get("message_de") or doc.get("headline_de") or "Postmortem nicht verfügbar")]
        if doc.get("stale_sync_warning_de"):
            parts.insert(0, str(doc["stale_sync_warning_de"]))
        return "\n".join(parts)

    lines = [
        str(doc.get("headline_de") or ""),
        f"Stand {doc.get('as_of_date') or '—'} (Signal {doc.get('signal_date') or '—'})",
        "",
    ]
    if doc.get("stale_sync_warning_de"):
        lines.insert(1, f"⚠ {doc['stale_sync_warning_de']}")
    for row in doc.get("picks") or []:
        sym = row.get("symbol")
        ret = row.get("daily_return_pct")
        vs = row.get("vs_spy_bps")
        vs_s = f" · vs SPY {vs:+.0f} bp" if vs is not None else ""
        lines.append(f"  {sym}: {ret:+.2f} %{vs_s}")
    if doc.get("missing_symbols"):
        lines.append(f"  (ohne Kurs: {', '.join(doc['missing_symbols'])})")
    lines.append("")
    lines.append(str(doc.get("summary_de") or ""))
    if doc.get("bad_day"):
        w = doc.get("worst") or {}
        if w.get("symbol"):
            lines.append(
                f"Erklärung: Halbleiter/Tech-Schwerpunkt im Plan — {w['symbol']} "
                f"{w.get('daily_return_pct', 0):+.2f} % am schwächsten vs. Modell-Signal."
            )
    return "\n".join(lines)


def load_postmortem_status(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)
