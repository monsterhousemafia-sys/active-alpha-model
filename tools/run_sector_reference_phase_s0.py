"""Phase S0 — sector reference gap analysis and governance baseline (no code changes to champion)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_constants import DEFAULT_TICKERS, SECTOR_MAP, ticker_to_sector
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS


def _active_membership_tickers(path: Path, as_of: str) -> List[str]:
    import pandas as pd

    if not path.is_file():
        return []
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        return []
    as_of_ts = pd.Timestamp(as_of)
    vf = pd.to_datetime(df.get("valid_from"), errors="coerce")
    vt = pd.to_datetime(df.get("valid_to"), errors="coerce")
    active = (vf <= as_of_ts) & (vt.isna() | (vt >= as_of_ts))
    return sorted(df.loc[active, "ticker"].astype(str).str.upper().str.strip().unique())


def _snapshot_tickers(path: Path) -> List[str]:
    import pandas as pd

    if not path.is_file():
        return []
    df = pd.read_csv(path)
    col = "ticker" if "ticker" in df.columns else "Symbol"
    if col not in df.columns:
        return []
    from aa_config import normalize_yfinance_ticker

    out: List[str] = []
    for raw in df[col].astype(str):
        tk = normalize_yfinance_ticker(raw)
        if tk:
            out.append(tk)
    return sorted(set(out))


def _portfolio_tickers(root: Path) -> List[str]:
    import pandas as pd

    for rel in (
        "model_output_sp500_pit_t212/latest_target_portfolio.csv",
        "paper/latest_target_portfolio.csv",
    ):
        path = root / rel
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        if "ticker" not in df.columns:
            continue
        return sorted(df["ticker"].astype(str).str.upper().str.strip().unique())
    return []


def _classify_ticker(tk: str) -> Dict[str, Any]:
    sec = ticker_to_sector(tk)
    in_map = tk in SECTOR_MAP
    return {
        "ticker": tk,
        "sector_map_sector": sec,
        "in_sector_map": in_map,
        "is_unknown": sec == "Unknown",
    }


def _summarize_group(name: str, tickers: List[str]) -> Dict[str, Any]:
    rows = [_classify_ticker(tk) for tk in tickers]
    unknown = [r for r in rows if r["is_unknown"]]
    missing_map = [r["ticker"] for r in rows if not r["in_sector_map"]]
    return {
        "group": name,
        "ticker_count": len(tickers),
        "mapped_count": len(tickers) - len(unknown),
        "unknown_count": len(unknown),
        "unknown_tickers": [r["ticker"] for r in unknown],
        "missing_from_sector_map": missing_map,
        "coverage_pct": round(100.0 * (len(tickers) - len(unknown)) / len(tickers), 2) if tickers else 100.0,
        "tickers": rows,
    }


def _wikipedia_parser_alignment() -> Dict[str, Any]:
    """S0.2 — compare live aa_universe vs membership build parser."""
    return {
        "live_aa_universe": {
            "module": "aa_universe._component_records_from_tables",
            "fields_emitted": ["ticker", "source_symbol", "company", "source"],
            "sector_gics_emitted": False,
            "symbol_column_candidates": ["symbol", "ticker", "ticker symbol"],
            "company_column_candidates": ["company name", "name", "security", "company"],
            "sector_column_candidates": [],
        },
        "build_sp500_membership_wikipedia": {
            "module": "build_sp500_membership_wikipedia.parse_current_constituents",
            "fields_emitted": ["ticker", "company", "sector", "sub_industry", "date_added_raw", "source"],
            "sector_gics_emitted": True,
            "sector_column_candidates": ["gics sector", "sector (fallback find_col)"],
            "sub_industry_column_candidates": ["gics sub-industry"],
        },
        "alignment_gap": {
            "summary_de": (
                "Live-Universe-Fetch verwirft GICS; Build-Skript liest GICS Sector. "
                "Phase S2 muss _component_records_from_tables um sector_gics erweitern "
                "und save_universe_snapshot persistieren."
            ),
            "required_s2_fields": ["sector_gics"],
            "column_names_to_support": [
                "GICS Sector",
                "gics sector",
                "Sector",
                "GICS Sub-Industry",
                "gics sub-industry",
            ],
        },
        "universe_snapshot_current": {
            "path": "universe_snapshots/sp500_latest.csv",
            "columns_observed": ["ticker", "source_symbol", "company", "source", "source_detail", "fetched_at_utc"],
            "has_sector_column": False,
        },
    }


def _governance_note(root: Path) -> Dict[str, Any]:
    """S0.3 — confirm phase is infrastructure-only."""
    frozen_champion_params = {
        "AUTHORITATIVE_CHAMPION": AUTHORITATIVE_CHAMPION,
        "AA_ALPHA_MODEL_MODE": "rank_only",
        "AA_RISK_OFF_SELECTION_MODE": "mom_blend_blend",
        "AA_RISK_OFF_MOMENTUM_WEIGHT": "0.75",
        "AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE": "0.65",
        "AA_RISK_OFF_FORCE_EXIT_ENABLED": "0",
        "AA_MAX_SECTOR": "0.55",
        "AA_UNIVERSE_MODE": "diy_pit_liquidity",
        "AA_UNIVERSE_TOP_N": "100",
    }
    in_scope = [
        "sector_reference.csv automated refresh",
        "ticker_to_sector lookup chain",
        "dashboard status display",
        "wikipedia_gics in universe snapshots",
        "yfinance fallback cache",
    ]
    out_of_scope_without_approval = [
        "change max_sector or gics_to_coarse buckets",
        "champion variant change",
        "signal weight or risk-off parameter change",
        "auto_promotion",
    ]
    return {
        "phase": "S0",
        "classification": "INFRASTRUCTURE_ONLY",
        "champion_unchanged": AUTHORITATIVE_CHAMPION,
        "frozen_parameter_reference": frozen_champion_params,
        "in_scope": in_scope,
        "out_of_scope_without_external_approval": out_of_scope_without_approval,
        "s4_acceptance_criterion": {
            "champion_symbols_all_mapped": list(CHAMPION_SYMBOLS),
            "rule": "After rollout, champion_sector_coverage unknown_count must be 0 when yfinance/wikipedia succeed",
        },
        "note_de": (
            "Automatische Sektor-Referenz ändert keine Champion-Hyperparameter. "
            "Weniger Unknown-Ticker kann Portfolio-Caps und sector_rel_strength leicht beeinflussen — "
            "das ist dokumentierte Infrastruktur-Stabilisierung, kein neues Alpha."
        ),
    }


def build_gap_analysis(root: Path, *, as_of: str) -> Dict[str, Any]:
    membership_path = root / "ticker_membership.csv"
    snapshot_path = root / "universe_snapshots" / "sp500_latest.csv"

    champion = list(CHAMPION_SYMBOLS)
    membership_active = _active_membership_tickers(membership_path, as_of)
    snapshot = _snapshot_tickers(snapshot_path)
    portfolio = _portfolio_tickers(root)
    default_tickers = sorted(set(DEFAULT_TICKERS))

    # Proxy for "liquid top-N universe": active membership is S&P pool; production filters to top 100 by ADV at runtime.
    top_n_proxy = membership_active[:100] if len(membership_active) >= 100 else membership_active

    groups = [
        _summarize_group("champion_symbols_14", champion),
        _summarize_group("portfolio_latest_target", portfolio),
        _summarize_group("membership_active_all", membership_active),
        _summarize_group("membership_active_top100_proxy", top_n_proxy),
        _summarize_group("universe_snapshot_sp500_latest", snapshot),
        _summarize_group("default_tickers_legacy_list", default_tickers),
    ]

    sector_map_keys: Set[str] = set(SECTOR_MAP.keys())
    all_checked: Set[str] = set()
    for g in groups:
        for r in g.get("tickers") or []:
            all_checked.add(r["ticker"])

    return {
        "schema_version": 1,
        "phase": "S0",
        "generated_on": as_of,
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "sector_map_entry_count": len(sector_map_keys),
        "wikipedia_parser_alignment": _wikipedia_parser_alignment(),
        "groups": groups,
        "champion_exit_criteria_s4": {
            "required_symbols": champion,
            "current_unknown": [r["ticker"] for r in groups[0]["tickers"] if r["is_unknown"]],
            "passes_s0": groups[0]["unknown_count"] == 0,
        },
        "aggregate": {
            "unique_tickers_checked": len(all_checked),
            "unique_unknown_via_sector_map": sorted(
                tk for tk in all_checked if ticker_to_sector(tk) == "Unknown"
            ),
            "unique_missing_from_sector_map": sorted(tk for tk in all_checked if tk not in sector_map_keys),
        },
        "recommendations": [
            "Phase S2: emit sector_gics in aa_universe records and snapshots.",
            "Phase S3: yfinance fallback for champion-only symbols not in S&P snapshot (e.g. CIEN).",
            "Phase S4 acceptance: champion_symbols_14 unknown_count == 0 after refresh.",
            "Do not commit generated sector_reference.csv; use universe_snapshots pattern.",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Run sector reference Phase S0 evidence generation.")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--as-of", default=date.today().isoformat())
    p.add_argument("--evidence-dir", type=Path, default=None)
    args = p.parse_args()
    root = args.root.resolve()
    evidence = (args.evidence_dir or root / "evidence").resolve()
    evidence.mkdir(parents=True, exist_ok=True)

    gap = build_gap_analysis(root, as_of=args.as_of)
    gov = _governance_note(root)

    gap_path = evidence / "sector_map_gap_analysis.json"
    gov_path = evidence / "sector_reference_governance_note.json"
    align_path = evidence / "sector_wikipedia_parser_alignment.json"

    gap_path.write_text(json.dumps(gap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    gov_path.write_text(json.dumps(gov, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    align_path.write_text(
        json.dumps(gap["wikipedia_parser_alignment"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"[OK] {gap_path}")
    print(f"[OK] {gov_path}")
    print(f"[OK] {align_path}")
    ch = gap["champion_exit_criteria_s4"]
    print(
        f"Champion 14/14 SECTOR_MAP coverage: "
        f"{gap['groups'][0]['mapped_count']}/14 "
        f"(unknown: {ch['current_unknown']})"
    )
    if not ch["passes_s0"]:
        print("[WARN] S4 acceptance: champion_symbols_14 must reach 14/14 after automated refresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
