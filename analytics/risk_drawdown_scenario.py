"""Read-only risk/drawdown stress scenarios — simulation only, no market manipulation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/risk_drawdown_scenario_latest.json")
_SHOCKS = (-0.05, -0.10, -0.20)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_returns_series(path: Path):
    import pandas as pd

    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        col = "strategy_return" if "strategy_return" in frame.columns else frame.columns[0]
        s = pd.to_numeric(frame[col], errors="coerce").dropna()
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception:
        return None


def _max_drawdown(cumulative) -> float:
    import pandas as pd

    if cumulative is None or len(cumulative) == 0:
        return 0.0
    peak = cumulative.cummax()
    dd = cumulative / peak - 1.0
    return float(dd.min())


def _resolve_champion_returns_path(root: Path) -> tuple[Optional[Path], str]:
    root = Path(root)
    try:
        from analytics.champion_runtime_guard import verify_champion_runtime

        champ = verify_champion_runtime(root).authoritative_champion
    except Exception:
        champ = "R0_LEGACY_ENSEMBLE"
    try:
        from aa_champion_evidence_phase_f import resolve_variant_returns_path

        ret_path, reason = resolve_variant_returns_path(root, champ)
        if ret_path and ret_path.is_file():
            return ret_path, reason
    except Exception:
        pass
    fallback = root / "model_output_sp500_pit_t212/strategy_daily_returns.csv"
    if fallback.is_file():
        return fallback, "pilot_output_fallback"
    return None, "returns_missing"


def run_risk_drawdown_scenario(root: Path) -> Dict[str, Any]:
    """Offline stress: historical MDD + hypothetical one-day shocks on champion returns."""
    root = Path(root)
    ret_path, resolve_note = _resolve_champion_returns_path(root)
    if not ret_path:
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": False,
            "mode": "read_only_simulation",
            "message_de": "Champion-Returns fehlen — kein Drawdown-Szenario",
            "resolve_note": resolve_note,
        }
        atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    returns = _load_returns_series(ret_path)
    if returns is None or len(returns) < 5:
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": False,
            "mode": "read_only_simulation",
            "returns_path": str(ret_path.relative_to(root)).replace("\\", "/"),
            "message_de": "Returns-CSV leer oder unlesbar",
        }
        atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    cumulative = (1.0 + returns).cumprod()
    hist_mdd = _max_drawdown(cumulative)
    shocks: List[Dict[str, Any]] = []
    for shock in _SHOCKS:
        shocked = cumulative.copy()
        shocked.iloc[-1] = shocked.iloc[-1] * (1.0 + shock)
        shocks.append(
            {
                "one_day_shock": shock,
                "terminal_drawdown_from_peak": _max_drawdown(shocked),
                "note_de": f"Hypothetischer {int(abs(shock)*100)}%-Tag am letzten Handelstag",
            }
        )

    rolling_worst = float(returns.rolling(20).sum().min()) if len(returns) >= 20 else None
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": True,
        "mode": "read_only_simulation",
        "disclaimer_de": "Nur historische/hypothetische Simulation — keine Marktmanipulation.",
        "returns_path": str(ret_path.relative_to(root)).replace("\\", "/"),
        "resolve_note": resolve_note,
        "n_days": int(len(returns)),
        "historical_max_drawdown": hist_mdd,
        "rolling_20d_worst_return": rolling_worst,
        "hypothetical_shocks": shocks,
        "headline_de": (
            f"Drawdown-Szenario — historisch MDD {hist_mdd:.1%}, "
            f"{len(shocks)} Schock-Pfade simuliert"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
