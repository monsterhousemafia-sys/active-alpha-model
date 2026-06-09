"""Phase 0: fetch T212 instruments + positions samples and write quote-source decision."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_safe_io import atomic_write_json

from integrations.trading212.t212_quote_spike_analysis import (
    CHAMPION_T212_TICKERS,
    analyze_position_price_units,
    discover_price_fields,
    filter_instruments_by_tickers,
    filter_positions_list,
    recommend_quote_strategy,
    summarize_positions_for_pricing,
    _normalize_instruments_list,
)

EVIDENCE_DIR = ROOT / "evidence"
INSTRUMENTS_SAMPLE = EVIDENCE_DIR / "t212_instruments_sample.json"
CHAMPION_INSTRUMENTS_CACHE = EVIDENCE_DIR / "t212_champion_instruments_verified.json"
POSITIONS_SAMPLE = EVIDENCE_DIR / "t212_positions_sample.json"
SPIKE_SUMMARY = EVIDENCE_DIR / "t212_phase0_spike_summary.json"
DECISION_MD = ROOT / "docs" / "T212_QUOTE_SOURCE_DECISION.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_live_credentials(root: Path) -> Tuple[Optional[Any], str]:
    """Prefer execution profile (live invest), else monitoring readonly."""
    from integrations.trading212.t212_auth_profile_model import (
        PROFILE_CONFIRMED_EXECUTION,
        PROFILE_MONITORING_READONLY,
    )
    from integrations.trading212.t212_credentials_loader import T212Credentials
    from integrations.trading212.t212_dual_profile_credential_store import get_profile_credentials
    from integrations.trading212.t212_execution_dpapi_store import load_execution_credentials
    from integrations.trading212.t212_dual_profile_secure_store import load_profile_credentials

    for label, loader in (
        ("CONFIRMED_EXECUTION", lambda: load_execution_credentials(root) or get_profile_credentials(PROFILE_CONFIRMED_EXECUTION)),
        ("MONITORING_READONLY", lambda: get_profile_credentials(PROFILE_MONITORING_READONLY) or load_profile_credentials(PROFILE_MONITORING_READONLY)),
    ):
        creds = loader()
        if creds and creds.configured:
            return creds, label
    env_key = __import__("os").environ.get("T212_API_KEY", "").strip()
    env_sec = __import__("os").environ.get("T212_API_SECRET", "").strip()
    if env_key and env_sec:
        return T212Credentials(api_key=env_key, api_secret=env_sec), "ENV"
    return None, "NONE"


def _fetch_live_get(creds: Any, path: str) -> Dict[str, Any]:
    from integrations.trading212.t212_live_readonly_client import T212LiveReadOnlyClient

    client = T212LiveReadOnlyClient(creds)
    return client.get(path)


def _load_cached_positions(root: Path) -> Optional[List[Dict[str, Any]]]:
    path = root / "live_pilot/manual_execution/readonly_real_positions/positions_snapshot.json"
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return filter_positions_list(doc.get("positions") or doc)
    except (json.JSONDecodeError, OSError):
        return None


def _load_prior_champion_instruments() -> Tuple[List[Dict[str, Any]], str]:
    """Recover champion instrument rows from prior successful spike artifacts."""
    for path, label in (
        (CHAMPION_INSTRUMENTS_CACHE, "champion_cache"),
        (INSTRUMENTS_SAMPLE, "instruments_sample"),
    ):
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rows = doc.get("champion_instruments") if isinstance(doc, dict) else doc
        if isinstance(rows, list) and rows:
            return [x for x in rows if isinstance(x, dict)], label
    return [], ""


def _truncate_instruments_payload(
    all_rows: List[Dict[str, Any]],
    champion_rows: List[Dict[str, Any]],
    *,
    max_full: int = 200,
) -> Dict[str, Any]:
    return {
        "total_instruments_reported": len(all_rows),
        "stored_full_count": min(len(all_rows), max_full),
        "champion_ticker_count": len(champion_rows),
        "instruments_truncated": all_rows[:max_full],
        "champion_instruments": champion_rows,
        "note": (
            f"Full list capped at {max_full} rows in this artifact; "
            f"champion subset always included ({len(champion_rows)} tickers)."
        ),
    }


def _write_decision_md(summary: Dict[str, Any], strategy: Dict[str, Any]) -> None:
    rec = strategy
    lines = [
        "# T212 Quote Source Decision (Phase 0)",
        "",
        f"**Generated:** {summary.get('generated_at_utc', '')}  ",
        f"**Credential profile:** {summary.get('credential_profile', '—')}  ",
        "",
        "## Spike results",
        "",
        f"| Fetch | Status |",
        f"|-------|--------|",
        f"| `GET /equity/metadata/instruments` | {summary.get('instruments_fetch_status', '—')} |",
        f"| `GET /equity/positions` | {summary.get('positions_fetch_status', '—')} |",
        "",
        f"- Instruments total (parsed): **{summary.get('instruments_total', 0)}**",
        f"- Champion tickers matched: **{summary.get('champion_instruments_matched', 0)}** / "
        f"{len(CHAMPION_T212_TICKERS)}",
        f"- Open positions: **{summary.get('positions_count', 0)}**",
        "",
        "## Official API (v0)",
        "",
        "- Documented read paths: `/equity/metadata/instruments`, `/equity/positions`, `/equity/account/cash`.",
        "- **No** documented REST endpoint for live bid/ask quotes for arbitrary tickers.",
        "- Stop-order docs reference **Last Traded Price (LTP)** internally, not exposed as a standalone quote API.",
        "",
        "## Recommendation",
        "",
        f"**Held positions:** `{rec.get('primary_for_held_positions', '')}`  ",
        f"**Pre-buy champion wave:** `{rec.get('primary_for_pre_buy_champion', '')}`  ",
        "",
        f"- Instruments usable for live quote (spike): **{rec.get('instruments_usable_for_live_quote', False)}**",
        f"- Positions usable for live quote: **{rec.get('positions_usable_for_live_quote', False)}**",
        "",
        "### Notes",
        "",
    ]
    for note in rec.get("notes_de") or []:
        lines.append(f"- {note}")
    for warn in summary.get("positions_price_unit_warnings") or []:
        lines.append(f"- ⚠ {warn}")
    lines.extend(
        [
            "",
            "## Price-like fields in instruments payload",
            "",
        ]
    )
    for row in summary.get("instruments_price_fields") or []:
        lines.append(f"- `{row.get('path')}` → sample `{row.get('sample')}`")
    if not summary.get("instruments_price_fields"):
        lines.append("- *(none detected in champion subset / truncated sample)*")
    lines.extend(
        [
            "",
            "## Positions pricing summary",
            "",
            "```json",
            json.dumps(summary.get("positions_pricing_summary") or [], indent=2, ensure_ascii=False),
            "```",
            "",
            "## Artifacts",
            "",
            f"- `{INSTRUMENTS_SAMPLE.relative_to(ROOT).as_posix()}`",
            f"- `{POSITIONS_SAMPLE.relative_to(ROOT).as_posix()}`",
            f"- `{SPIKE_SUMMARY.relative_to(ROOT).as_posix()}`",
            "",
            "## Next (Phase 1)",
            "",
            "Implement `t212_instrument_quotes.py` per pre-buy recommendation above; cache instruments 50s+; "
            "never size orders from Yahoo caps when T212 or validated price exists.",
            "",
        ]
    )
    DECISION_MD.parent.mkdir(parents=True, exist_ok=True)
    DECISION_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    root = ROOT
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    creds, profile = _load_live_credentials(root)

    instruments_raw: Any = None
    positions_raw: Any = None
    inst_err = ""
    pos_err = ""
    inst_status = "SKIPPED_NO_CREDENTIALS"
    pos_status = "SKIPPED_NO_CREDENTIALS"

    prior_champion, prior_label = _load_prior_champion_instruments()

    if creds:
        try:
            instruments_raw = _fetch_live_get(creds, "/equity/metadata/instruments")
            inst_status = "OK"
        except Exception as exc:
            inst_err = str(exc)[:300]
            inst_status = f"ERROR:{inst_err[:80]}"
            if prior_champion:
                instruments_raw = {
                    "champion_instruments": prior_champion,
                    "total_instruments_reported": len(prior_champion),
                    "_restored_from": prior_label,
                }
                inst_status = "OK_CACHED_PRIOR"
                inst_err = f"{inst_err}; using prior champion cache ({prior_label})"
        try:
            positions_raw = _fetch_live_get(creds, "/equity/positions")
            pos_status = "OK"
        except Exception as exc:
            pos_err = str(exc)[:300]
            pos_status = f"ERROR:{pos_err[:80]}"

    all_inst = _normalize_instruments_list(instruments_raw) if instruments_raw is not None else []
    champion_inst = filter_instruments_by_tickers(all_inst, CHAMPION_T212_TICKERS)
    if not champion_inst and prior_champion:
        champion_inst = prior_champion
        if inst_status.startswith("ERROR"):
            inst_status = "OK_CACHED_PRIOR"

    positions_list: List[Dict[str, Any]] = []
    if positions_raw is not None:
        positions_list = filter_positions_list(positions_raw)
        pos_source = "LIVE_API"
    else:
        cached = _load_cached_positions(root)
        if cached:
            positions_list = cached
            pos_status = "OK_CACHED" if pos_status.startswith("ERROR") or pos_status.startswith("SKIPPED") else pos_status
            pos_source = "CACHE_READONLY_SNAPSHOT"
            positions_raw = {"positions": cached, "_source": pos_source}
        else:
            pos_source = "NONE"

    positions_summary = summarize_positions_for_pricing(positions_list)
    position_unit_warnings = analyze_position_price_units(positions_summary)
    inst_for_discovery = champion_inst or (all_inst[:20] if all_inst else [])
    price_fields = discover_price_fields(inst_for_discovery)

    strategy = recommend_quote_strategy(
        instruments_price_fields=price_fields,
        instruments_champion_rows=champion_inst,
        positions_summary=positions_summary,
        instruments_fetch_ok=inst_status in ("OK", "OK_CACHED_PRIOR"),
        positions_fetch_ok=pos_status in ("OK", "OK_CACHED"),
    )

    generated = _utc_now()
    instruments_doc = {
        "generated_at_utc": generated,
        "fetch_status": inst_status,
        "fetch_error": inst_err or None,
        "credential_profile": profile,
        "endpoint": "GET /api/v0/equity/metadata/instruments",
        "rate_limit_note": "1 req / 50s per T212 docs",
        **_truncate_instruments_payload(all_inst, champion_inst),
        "price_fields_discovered": price_fields,
    }
    positions_doc = {
        "generated_at_utc": generated,
        "fetch_status": pos_status,
        "fetch_error": pos_err or None,
        "credential_profile": profile,
        "endpoint": "GET /api/v0/equity/positions",
        "positions": positions_list,
        "pricing_summary": positions_summary,
        "source": pos_source if positions_raw else "NONE",
    }
    summary = {
        "generated_at_utc": generated,
        "credential_profile": profile,
        "instruments_fetch_status": inst_status,
        "positions_fetch_status": pos_status,
        "instruments_total": len(all_inst),
        "champion_instruments_matched": len(champion_inst),
        "positions_count": len(positions_list),
        "instruments_price_fields": price_fields,
        "positions_pricing_summary": positions_summary,
        "positions_price_unit_warnings": position_unit_warnings,
        "strategy": strategy,
        "champion_tickers_requested": list(CHAMPION_T212_TICKERS),
        "artifacts": {
            "instruments": str(INSTRUMENTS_SAMPLE),
            "positions": str(POSITIONS_SAMPLE),
            "decision_md": str(DECISION_MD),
        },
    }

    if champion_inst:
        atomic_write_json(
            CHAMPION_INSTRUMENTS_CACHE,
            {
                "generated_at_utc": generated,
                "champion_instruments": champion_inst,
                "champion_ticker_count": len(champion_inst),
                "source_status": inst_status,
            },
        )
    if inst_status in ("OK", "OK_CACHED_PRIOR") or champion_inst:
        atomic_write_json(INSTRUMENTS_SAMPLE, instruments_doc)
    atomic_write_json(POSITIONS_SAMPLE, positions_doc)
    atomic_write_json(SPIKE_SUMMARY, summary)
    _write_decision_md(summary, strategy)

    print(f"Phase 0 OK — instruments={inst_status} positions={pos_status}")
    print(f"  champion matched: {len(champion_inst)}/{len(CHAMPION_T212_TICKERS)}")
    print(f"  pre-buy recommendation: {strategy.get('primary_for_pre_buy_champion')}")
    print(f"  decision: {DECISION_MD}")
    ok_inst = inst_status in ("OK", "OK_CACHED_PRIOR") and len(champion_inst) > 0
    ok_pos = pos_status in ("OK", "OK_CACHED")
    return 0 if ok_inst and ok_pos else 1


if __name__ == "__main__":
    raise SystemExit(main())
