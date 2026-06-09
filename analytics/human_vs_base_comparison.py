"""Human portfolio vs suggested base portfolio — read-only comparison (R1 growth)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from market.learning_pipeline import BROKER_DAILY_LEDGER, learning_root

DEFAULT_BASE_CONFIG = Path("paper/config/p16c_cost_adjusted_initial_allocation_500eur.json")
CHAMPION_REF = "R3_w075_q065_noexit"
ACCOUNT_HISTORY_REL = Path("live_pilot/comparison/account_value_history.jsonl")
TRADE_HISTORY_REL = Path("live_pilot/manual_execution/readonly_real_trade_history/latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_base_portfolio(root: Path) -> Dict[str, Any]:
    path = Path(root) / DEFAULT_BASE_CONFIG
    if not path.is_file():
        return {"positions": [], "initial_capital_eur": 500.0, "status": "BASE_CONFIG_MISSING"}
    doc = json.loads(path.read_text(encoding="utf-8"))
    positions = []
    for row in doc.get("positions") or []:
        sym = str(row.get("symbol_reference") or "").strip().upper()
        if not sym:
            continue
        w = float(row.get("normalized_weight_pct") or row.get("displayed_weight_pct") or 0)
        positions.append(
            {
                "symbol": sym,
                "name": row.get("display_name") or sym,
                "weight_pct": w,
                "target_notional_eur": float(row.get("cost_adjusted_target_eur") or 0),
            }
        )
    return {
        "source": str(path),
        "champion_ref": CHAMPION_REF,
        "initial_capital_eur": float(doc.get("initial_capital_eur") or 500),
        "positions": positions,
        "status": "OK",
    }


def _position_symbol(pos: Dict[str, Any]) -> str:
    inst = pos.get("instrument") if isinstance(pos.get("instrument"), dict) else {}
    ticker = str(inst.get("ticker") or pos.get("ticker") or pos.get("symbol") or "").strip()
    if ticker.endswith("_EQ"):
        ticker = ticker[:-3]
    if ticker.endswith("l"):
        ticker = ticker[:-1]
    return ticker.upper()


def _position_value_eur(pos: Dict[str, Any]) -> float:
    wi = pos.get("walletImpact")
    if isinstance(wi, dict) and wi.get("currentValue") is not None:
        try:
            return float(wi["currentValue"])
        except (TypeError, ValueError):
            pass
    try:
        return float(pos.get("value_eur") or pos.get("currentValue") or 0)
    except (TypeError, ValueError):
        return 0.0


def human_portfolio_from_broker(broker: Dict[str, Any]) -> Dict[str, Any]:
    cash = broker.get("cash_eur")
    try:
        cash_f = float(cash) if cash is not None else 0.0
    except (TypeError, ValueError):
        cash_f = 0.0
    positions_raw = broker.get("positions") or []
    holdings: List[Dict[str, Any]] = []
    invested = 0.0
    for pos in positions_raw:
        if not isinstance(pos, dict):
            continue
        val = _position_value_eur(pos)
        invested += val
        sym = _position_symbol(pos)
        inst = pos.get("instrument") if isinstance(pos.get("instrument"), dict) else {}
        holdings.append(
            {
                "symbol": sym,
                "name": inst.get("name") or sym,
                "value_eur": val,
                "quantity": pos.get("quantity"),
            }
        )
    total = cash_f + invested
    for h in holdings:
        h["weight_pct"] = round(100.0 * h["value_eur"] / total, 2) if total > 0 else 0.0
    cash_pct = round(100.0 * cash_f / total, 2) if total > 0 else 100.0
    return {
        "cash_eur": cash_f,
        "cash_weight_pct": cash_pct,
        "invested_eur": round(invested, 2),
        "total_value_eur": round(total, 2),
        "holdings": holdings,
        "positions_count": len(holdings),
    }


def compare_human_vs_base(
    root: Path,
    broker: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    base = load_base_portfolio(root)
    if not broker or not broker.get("credentials_configured"):
        return {
            "status": "NOT_EVALUABLE",
            "reason": "T212 nicht verbunden — Vergleich benötigt Live-Portfolio.",
            "generated_at_utc": _utc_now(),
            "base": base,
            "human": None,
        }

    human = human_portfolio_from_broker(broker)
    base_by_sym = {p["symbol"]: p for p in base.get("positions") or []}
    human_by_sym = {h["symbol"]: h for h in human.get("holdings") or []}

    rows: List[Dict[str, Any]] = []
    all_syms = sorted(set(base_by_sym) | set(human_by_sym))
    drift_sum = 0.0
    for sym in all_syms:
        b = base_by_sym.get(sym)
        h = human_by_sym.get(sym)
        bw = float(b["weight_pct"]) if b else 0.0
        hw = float(h["weight_pct"]) if h else 0.0
        drift = round(hw - bw, 2)
        drift_sum += abs(drift)
        rows.append(
            {
                "symbol": sym,
                "name": (h or b or {}).get("name") or sym,
                "base_weight_pct": bw,
                "human_weight_pct": hw,
                "drift_pct": drift,
                "in_base_only": b is not None and h is None,
                "in_human_only": h is not None and b is None,
            }
        )

    cash_drift = round(float(human.get("cash_weight_pct") or 0) - 0.0, 2)

    report: Dict[str, Any] = {
        "status": "OK",
        "generated_at_utc": _utc_now(),
        "champion_ref": CHAMPION_REF,
        "base": base,
        "human": human,
        "rows": rows,
        "metrics": {
            "allocation_drift_l1_pct": round(drift_sum + abs(cash_drift), 2),
            "cash_weight_human_pct": human.get("cash_weight_pct"),
            "max_single_position_human_pct": max((h["weight_pct"] for h in human.get("holdings") or []), default=0.0),
            "max_single_position_base_pct": max((p["weight_pct"] for p in base.get("positions") or []), default=0.0),
            "symbols_in_base_not_held": [r["symbol"] for r in rows if r.get("in_base_only")],
            "symbols_held_not_in_base": [r["symbol"] for r in rows if r.get("in_human_only")],
            "interpretation_de": _interpretation(rows, human),
        },
    }
    append_account_value_point(root, human)
    return enrich_comparison_report(root, broker, report)


def _interpretation(rows: List[Dict[str, Any]], human: Dict[str, Any]) -> str:
    not_held = [r["symbol"] for r in rows if r.get("in_base_only")]
    extra = [r["symbol"] for r in rows if r.get("in_human_only")]
    cash = float(human.get("cash_weight_pct") or 0)
    parts = []
    if cash > 50:
        parts.append(f"Hoher Cash-Anteil ({cash:.1f} %) vs. diversifiziertem Basisportfolio.")
    if not_held:
        parts.append(f"Basis-Positionen nicht gehalten: {', '.join(not_held[:6])}.")
    if extra:
        parts.append(f"Zusätzlich gehalten (nicht im Basisvorschlag): {', '.join(extra[:6])}.")
    if not parts:
        parts.append("Portfolio näher am Basisvorschlag — Details in Tabelle und Grafik.")
    return " ".join(parts)


def _read_jsonl(path: Path, *, limit: int = 500) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(doc, dict):
            rows.append(doc)
    return rows[-limit:] if limit else rows


def _parse_iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.date().isoformat()
    except ValueError:
        return text[:10] if len(text) >= 10 else None


def append_account_value_point(root: Path, human: Dict[str, Any]) -> None:
    """Append NAV point on each comparison refresh (equity curve in EXE)."""
    path = Path(root) / ACCOUNT_HISTORY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    total = float(human.get("total_value_eur") or 0)
    record = {
        "recorded_at_utc": _utc_now(),
        "total_value_eur": round(total, 2),
        "cash_eur": human.get("cash_eur"),
        "positions_count": human.get("positions_count"),
        "source": "comparison_refresh",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _total_from_broker_daily_row(row: Dict[str, Any]) -> float:
    cash = float(row.get("cash_eur") or 0)
    invested = 0.0
    for pos in row.get("positions_summary") or []:
        if isinstance(pos, dict):
            try:
                invested += float(pos.get("currentValue") or 0)
            except (TypeError, ValueError):
                pass
    return round(cash + invested, 2)


def build_equity_series(root: Path, human: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    points: List[Dict[str, Any]] = []
    seen_dates: set[str] = set()

    for row in _read_jsonl(learning_root(Path(root)) / BROKER_DAILY_LEDGER):
        day = str(row.get("snapshot_date") or row.get("recorded_at_utc") or "")[:10]
        if not day or day in seen_dates:
            continue
        val = _total_from_broker_daily_row(row)
        if val <= 0:
            continue
        seen_dates.add(day)
        points.append({"date": day, "value_eur": val, "source": "broker_daily"})

    for row in _read_jsonl(Path(root) / ACCOUNT_HISTORY_REL):
        day = str(row.get("recorded_at_utc") or "")[:10]
        if not day:
            continue
        try:
            val = float(row.get("total_value_eur") or 0)
        except (TypeError, ValueError):
            continue
        if val <= 0:
            continue
        if day in seen_dates:
            for p in points:
                if p["date"] == day:
                    p["value_eur"] = val
                    p["source"] = "comparison_refresh"
                    break
        else:
            seen_dates.add(day)
            points.append({"date": day, "value_eur": round(val, 2), "source": "comparison_refresh"})

    today = datetime.now(timezone.utc).date().isoformat()
    current = float(human.get("total_value_eur") or 0)
    if current > 0:
        if today in seen_dates:
            for p in points:
                if p["date"] == today:
                    p["value_eur"] = round(current, 2)
                    break
        else:
            points.append({"date": today, "value_eur": round(current, 2), "source": "live_now"})

    points.sort(key=lambda p: p["date"])
    ref_cap = float(base.get("initial_capital_eur") or 500)
    return {
        "human_points": points,
        "base_reference_capital_eur": ref_cap,
        "point_count": len(points),
        "note_de": (
            "Kurve aus Tages-Snapshots und Aktualisierungen in dieser Ansicht. "
            "Basislinie = Startkapital des Vorschlags (kein Backtest)."
        ),
    }


def _parse_history_trade(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    inst = raw.get("instrument") if isinstance(raw.get("instrument"), dict) else {}
    sym = _position_symbol({"instrument": inst, "ticker": raw.get("ticker")})
    if not sym:
        sym = str(raw.get("symbol") or raw.get("ticker") or "").strip().upper()
    if not sym:
        return None
    day = _parse_iso_date(
        raw.get("filledAt")
        or raw.get("createdAt")
        or raw.get("date")
        or raw.get("timestamp")
        or raw.get("time")
    )
    if not day:
        return None
    side = str(raw.get("side") or raw.get("type") or raw.get("orderType") or "TRADE").upper()[:24]
    return {
        "date": day,
        "symbol": sym,
        "side": side,
        "source": "t212_history",
        "note_de": "API-Historie",
    }


def build_trade_timeline(root: Path, broker: Dict[str, Any]) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    history_path = Path(root) / TRADE_HISTORY_REL
    history_status = "MISSING"
    if history_path.is_file():
        try:
            doc = json.loads(history_path.read_text(encoding="utf-8"))
            history_status = str(doc.get("status") or "UNKNOWN")
            for raw in doc.get("trades") or []:
                ev = _parse_history_trade(raw if isinstance(raw, dict) else {})
                if ev:
                    events.append(ev)
        except (json.JSONDecodeError, OSError):
            history_status = "READ_ERROR"

    for pos in broker.get("positions") or []:
        if not isinstance(pos, dict):
            continue
        sym = _position_symbol(pos)
        day = _parse_iso_date(pos.get("createdAt") or pos.get("creationDate") or pos.get("openedAt"))
        if not sym or not day:
            continue
        events.append(
            {
                "date": day,
                "symbol": sym,
                "side": "POSITION",
                "source": "position_entry",
                "note_de": "Position laut T212 (createdAt)",
            }
        )

    dedup: Dict[tuple, Dict[str, Any]] = {}
    for ev in events:
        key = (ev["date"], ev["symbol"], ev.get("side"), ev.get("source"))
        dedup[key] = ev
    ordered = sorted(dedup.values(), key=lambda e: (e["date"], e["symbol"]))
    return {
        "events": ordered,
        "event_count": len(ordered),
        "history_status": history_status,
        "note_de": (
            "Leere API-Historie ist normal bei Read-only-Keys — Eintritte aus offenen Positionen ergänzt."
            if history_status in ("EMPTY", "MISSING", "AWAITING_CREDENTIALS")
            else "Ereignisse aus T212-Historie und Positionen."
        ),
    }


def enrich_comparison_report(
    root: Path,
    broker: Dict[str, Any],
    report: Dict[str, Any],
) -> Dict[str, Any]:
    if report.get("status") != "OK":
        return report
    base = report.get("base") or {}
    human = report.get("human") or {}
    report["trade_timeline"] = build_trade_timeline(root, broker)
    report["equity_series"] = build_equity_series(root, human, base)
    report["drift_waterfall"] = [
        {"symbol": r["symbol"], "drift_pct": r.get("drift_pct", 0)}
        for r in (report.get("rows") or [])
        if abs(float(r.get("drift_pct") or 0)) >= 0.01
    ]
    metrics = report.setdefault("metrics", {})
    metrics["trade_event_count"] = report["trade_timeline"].get("event_count", 0)
    metrics["equity_point_count"] = report["equity_series"].get("point_count", 0)
    return report


def write_comparison_evidence(root: Path, report: Dict[str, Any]) -> Path:
    out_dir = Path(root) / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "portfolio_comparison_latest.json"
    latest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return latest


def render_allocation_chart_png(report: Dict[str, Any], out_path: Path) -> Tuple[bool, str]:
    if report.get("status") != "OK":
        return False, "NOT_EVALUABLE"
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False, "matplotlib_missing"

    rows = list(report.get("rows") or [])[:8]
    human = report.get("human") or {}
    labels = [r["symbol"] for r in rows] + ["CASH"]
    base_vals = [r["base_weight_pct"] for r in rows] + [0.0]
    human_vals = [r["human_weight_pct"] for r in rows] + [float(human.get("cash_weight_pct") or 0)]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = range(len(labels))
    w = 0.35
    ax.bar([i - w / 2 for i in x], base_vals, width=w, label="Basisvorschlag (R3/500€)", color="#0078D4")
    ax.bar([i + w / 2 for i in x], human_vals, width=w, label="Ihr T212-Portfolio", color="#34C759")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("Gewicht %")
    ax.set_title("Allokation: Basisportfolio vs. Ihr Trading")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, facecolor="#1a2332")
    plt.close(fig)
    return True, str(out_path)


def _mpl_setup():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def render_comparison_dashboard_png(report: Dict[str, Any], out_path: Path) -> Tuple[bool, str]:
    """R1 dashboard: allocation, drift, equity curve, trade timeline."""
    if report.get("status") != "OK":
        return False, "NOT_EVALUABLE"
    try:
        plt = _mpl_setup()
    except ImportError:
        return False, "matplotlib_missing"

    rows = list(report.get("rows") or [])[:8]
    human = report.get("human") or {}
    equity = report.get("equity_series") or {}
    timeline = report.get("trade_timeline") or {}
    base_cap = float(equity.get("base_reference_capital_eur") or 500)

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.patch.set_facecolor("#1a2332")
    for ax in axes.flat:
        ax.set_facecolor("#243044")
        ax.tick_params(colors="#e8ecf0")
        ax.xaxis.label.set_color("#e8ecf0")
        ax.yaxis.label.set_color("#e8ecf0")
        ax.title.set_color("#e8ecf0")
        for spine in ax.spines.values():
            spine.set_color("#4a5568")

    # 1 — allocation
    ax0 = axes[0, 0]
    labels = [r["symbol"] for r in rows] + ["CASH"]
    base_vals = [r["base_weight_pct"] for r in rows] + [0.0]
    human_vals = [r["human_weight_pct"] for r in rows] + [float(human.get("cash_weight_pct") or 0)]
    x = range(len(labels))
    w = 0.35
    ax0.bar([i - w / 2 for i in x], base_vals, width=w, label="Basis", color="#0078D4")
    ax0.bar([i + w / 2 for i in x], human_vals, width=w, label="Ihr Portfolio", color="#34C759")
    ax0.set_xticks(list(x))
    ax0.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax0.set_ylabel("Gewicht %")
    ax0.set_title("Allokation")
    ax0.legend(fontsize=7)
    ax0.grid(axis="y", alpha=0.25)

    # 2 — drift waterfall
    ax1 = axes[0, 1]
    drift_rows = sorted(report.get("drift_waterfall") or [], key=lambda r: abs(float(r.get("drift_pct") or 0)), reverse=True)[:10]
    if drift_rows:
        syms = [r["symbol"] for r in drift_rows]
        drifts = [float(r["drift_pct"]) for r in drift_rows]
        colors = ["#34C759" if d >= 0 else "#FF6B6B" for d in drifts]
        y = range(len(syms))
        ax1.barh(list(y), drifts, color=colors)
        ax1.set_yticks(list(y))
        ax1.set_yticklabels(syms, fontsize=8)
        ax1.axvline(0, color="#888", linewidth=0.8)
        ax1.set_xlabel("Drift vs. Basis (Prozentpunkte)")
        ax1.set_title("Abweichung je Symbol")
    else:
        ax1.text(0.5, 0.5, "Keine relevante Drift", ha="center", va="center", color="#ccc", transform=ax1.transAxes)
        ax1.set_title("Abweichung")

    # 3 — equity
    ax2 = axes[1, 0]
    pts = equity.get("human_points") or []
    if len(pts) >= 1:
        dates = [p["date"] for p in pts]
        vals = [float(p["value_eur"]) for p in pts]
        ax2.plot(dates, vals, marker="o", color="#34C759", label="Ihr Depotwert")
        ax2.axhline(base_cap, color="#0078D4", linestyle="--", linewidth=1.2, label=f"Basis-Start {base_cap:.0f} €")
        ax2.set_ylabel("EUR")
        ax2.set_title("Wertentwicklung (Snapshots)")
        ax2.legend(fontsize=7)
        ax2.tick_params(axis="x", rotation=30, labelsize=7)
        ax2.grid(alpha=0.25)
    else:
        ax2.text(0.5, 0.5, "Noch keine Verlaufsdaten\n(Aktualisieren Sie mehrfach)", ha="center", va="center", color="#ccc", transform=ax2.transAxes)
        ax2.set_title("Wertentwicklung")

    # 4 — timeline
    ax3 = axes[1, 1]
    events = timeline.get("events") or []
    if events:
        color_map = {"t212_history": "#FFD60A", "position_entry": "#64D2FF"}
        for ev in events:
            c = color_map.get(ev.get("source"), "#aaa")
            ax3.scatter(ev["date"], ev["symbol"], c=c, s=80, edgecolors="white", linewidths=0.5)
        ax3.tick_params(axis="x", rotation=35, labelsize=7)
        ax3.set_title("Ereignisse (Historie + Positionen)")
        ax3.set_xlabel("Datum")
    else:
        ax3.text(0.5, 0.5, "Keine Ereignisse erfasst", ha="center", va="center", color="#ccc", transform=ax3.transAxes)
        ax3.set_title("Trade-Timeline")

    fig.suptitle("Portfolio-Vergleich R1", color="#e8ecf0", fontsize=12, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, facecolor=fig.get_facecolor())
    plt.close(fig)
    return True, str(out_path)


def export_comparison_pdf(report: Dict[str, Any], pdf_path: Path) -> Tuple[bool, str]:
    if report.get("status") != "OK":
        return False, "NOT_EVALUABLE"
    try:
        plt = _mpl_setup()
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError:
        return False, "matplotlib_missing"

    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    metrics = report.get("metrics") or {}
    human = report.get("human") or {}

    with PdfPages(str(pdf_path)) as pdf:
        ok, _ = render_comparison_dashboard_png(report, pdf_path.parent / "_comparison_dashboard_tmp.png")
        if ok:
            img_path = pdf_path.parent / "_comparison_dashboard_tmp.png"
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_axes([0, 0, 1, 1])
            import matplotlib.image as mpimg

            ax.imshow(mpimg.imread(str(img_path)))
            ax.axis("off")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)
            try:
                img_path.unlink()
            except OSError:
                pass

        fig = plt.figure(figsize=(8.5, 11))
        fig.text(0.08, 0.92, "Portfolio-Vergleich — Zusammenfassung", fontsize=14, weight="bold")
        lines = [
            f"Erstellt: {report.get('generated_at_utc', '')}",
            f"Champion-Referenz: {report.get('champion_ref', CHAMPION_REF)}",
            f"Depotwert: {human.get('total_value_eur')} EUR | Cash: {human.get('cash_weight_pct')} %",
            f"Drift L1: {metrics.get('allocation_drift_l1_pct')} %",
            f"Ereignisse: {metrics.get('trade_event_count')} | Kurvenpunkte: {metrics.get('equity_point_count')}",
            "",
            str(metrics.get("interpretation_de") or ""),
            "",
            str((report.get("equity_series") or {}).get("note_de") or ""),
            str((report.get("trade_timeline") or {}).get("note_de") or ""),
        ]
        y = 0.82
        for line in lines:
            fig.text(0.08, y, line, fontsize=10, wrap=True)
            y -= 0.04
        pdf.savefig(fig)
        plt.close(fig)

    return True, str(pdf_path)
