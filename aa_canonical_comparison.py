"""Canonical multi-variant model comparison (Phase C — aligned calendar framework)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from aa_challenger_eval import (
    discover_validation_variants,
    embedded_metrics_for_variant,
    is_quarantined_variant,
    load_embedded_variant_inventory,
)
from aa_cost_stress import (
    SCENARIOS,
    evaluate_cost_stress_gate,
    evaluate_variant_scenario,
    file_sha256,
    resolve_variant_sources,
)
from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion
from aa_reporting import calculate_metrics
from research.p11.robustness import _subperiod_metrics

CONTAMINATED_RETURNS_SHA256 = "3f8a1a3aea140bcb32dc46bff216ccda87b718727555109a2b8e394b4b7a2653"
MATRIX_EXPECTED_N_DAYS = 1860
MIN_ALIGNED_OVERLAP = 200
CALENDAR_WARN_DELTA_DAYS = 5

CANONICAL_VARIANT_ROLES: Tuple[Tuple[str, str], ...] = (
    (AUTHORITATIVE_CHAMPION, "CHAMPION"),
    ("M1_MOM_BLEND_MATCHED_CONTROLS", "M1_CONTROL"),
    ("R0_LEGACY_ENSEMBLE", "SIBLING_MATRIX"),
    ("R1_GATE_BASE_ONLY", "SIBLING_MATRIX"),
    ("R2_MOM_BLEND_REPLACE", "SIBLING_MATRIX"),
    ("R3_w070_q070_noexit", "SIBLING_MATRIX"),
    ("R4_w070_q070_forceexit", "SIBLING_MATRIX"),
    ("MOM_63_TOP12", "RESEARCH_CANDIDATE"),
    ("MOM_63_TOP12_STRICT", "RESEARCH_CANDIDATE"),
    ("MOM_63_TOP15_RECONSTRUCTED", "RESEARCH_CANDIDATE"),
    ("R5_rank_only_train5", "QUARANTINED"),
)

RETURN_ALIASES: Dict[str, List[str]] = {
    "MOM_63_TOP12": [
        "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/daily_returns.csv",
    ],
    "MOM_63_TOP12_STRICT": [
        "evidence/autonomous_research/MOM_63_TOP12_STRICT/daily_returns.csv",
    ],
    "MOM_63_TOP15_RECONSTRUCTED": [
        "evidence/autonomous_research/MOM_63_TOP15_RECONSTRUCTED/daily_returns.csv",
    ],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_returns_series(path: Path, *, column: Optional[str] = None) -> Optional[pd.Series]:
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        if column and column in frame.columns:
            col = column
        elif "strategy_return" in frame.columns:
            col = "strategy_return"
        else:
            col = frame.columns[0]
        series = pd.to_numeric(frame[col], errors="coerce").dropna()
        series.index = pd.to_datetime(series.index)
        return series.sort_index()
    except Exception:
        return None


def _returns_usable(path: Path) -> Tuple[bool, str]:
    sha = _sha256_file(path)
    if sha == CONTAMINATED_RETURNS_SHA256:
        return False, "contaminated_returns_archived_phase_b"
    series = _load_returns_series(path)
    n = int(len(series)) if series is not None and not series.empty else 0
    if n > MATRIX_EXPECTED_N_DAYS + 40:
        return False, f"calendar_too_long_n_days={n}"
    return True, ""


def resolve_variant_returns_path(root: Path, variant_id: str) -> Tuple[Optional[Path], str]:
    """Resolve daily returns CSV; empty reason if missing."""
    root = Path(root)
    discovered = discover_validation_variants(root)
    if variant_id in discovered:
        p = discovered[variant_id] / "strategy_daily_returns.csv"
        if p.is_file():
            ok, reason = _returns_usable(p)
            return (p if ok else None), ("" if ok else reason or "validation_run_rejected")

    inv = load_embedded_variant_inventory(root).get(variant_id) or {}
    run_dir = str(inv.get("run_dir") or "").strip()
    if run_dir:
        p = Path(run_dir) / "strategy_daily_returns.csv"
        if p.is_file():
            ok, reason = _returns_usable(p)
            return (p if ok else None), ("" if ok else reason)

    for rel in RETURN_ALIASES.get(variant_id, []):
        p = root / rel
        if p.is_file():
            return p, "alias_path"

    cost_src = resolve_variant_sources(root).get(variant_id, {})
    rel = str(cost_src.get("returns_path") or "")
    if rel:
        p = root / rel
        if p.is_file():
            ok, reason = _returns_usable(p)
            return (p if ok else None), ("" if ok else reason or "cost_source_rejected")

    m1_alt = root / "validation_runs" / "20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS"
    if variant_id == "M1_MOM_BLEND_MATCHED_CONTROLS":
        for name in ("mom_blend_matched_controls_daily_returns.csv", "strategy_daily_returns.csv"):
            p = m1_alt / name
            if p.is_file():
                ok, reason = _returns_usable(p)
                return (p if ok else None), ("" if ok else reason)

    return None, "returns_file_missing"


def align_return_series(
    series_by_variant: Dict[str, pd.Series],
    *,
    min_overlap: int = MIN_ALIGNED_OVERLAP,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if len(series_by_variant) < 2:
        return pd.DataFrame(), {"status": "INSUFFICIENT_SERIES", "n_aligned": 0}
    frame = pd.concat(series_by_variant, axis=1, join="inner").dropna()
    n = int(len(frame))
    meta: Dict[str, Any] = {
        "status": "OK" if n >= min_overlap else "INSUFFICIENT_OVERLAP",
        "n_aligned": n,
        "start_date": str(frame.index.min()) if n else None,
        "end_date": str(frame.index.max()) if n else None,
        "variants_included": list(series_by_variant.keys()),
    }
    if n:
        raw_days = {vid: int(len(s)) for vid, s in series_by_variant.items()}
        meta["raw_n_days"] = raw_days
        deltas = {vid: abs(raw_days[vid] - n) for vid in raw_days}
        meta["calendar_delta_days"] = deltas
        meta["calendar_warning"] = any(d > CALENDAR_WARN_DELTA_DAYS for d in deltas.values())
    return frame, meta


def _rank_table(rows: List[Dict[str, Any]], key: str, *, higher_better: bool = True) -> List[Dict[str, Any]]:
    scored = [r for r in rows if r.get(key) is not None and pd.notna(r.get(key))]
    scored.sort(key=lambda r: float(r[key]), reverse=higher_better)
    out = []
    for i, row in enumerate(scored, start=1):
        out.append({"rank": i, "variant_id": row["variant_id"], key: row[key], "role": row.get("role")})
    return out


def _metrics_from_challenger_report(root: Path, variant_id: str) -> Dict[str, float]:
    path = root / "model_output_sp500_pit_t212" / "challenger_report.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    for entry in doc.get("entries") or []:
        if str(entry.get("variant_id") or "").strip() == variant_id:
            return dict(entry.get("metrics") or {})
    return {}


def _variant_row_from_embedded(root: Path, variant_id: str, role: str) -> Dict[str, Any]:
    emb = embedded_metrics_for_variant(root, variant_id) or _metrics_from_challenger_report(root, variant_id)
    inv = load_embedded_variant_inventory(root).get(variant_id) or {}
    return {
        "variant_id": variant_id,
        "role": role,
        "metrics_mode": "matrix_embedded",
        "returns_path": None,
        "metrics": emb,
        "n_days": emb.get("n_days") or inv.get("n_days"),
        "integrity_pass": bool((inv.get("integrity") or {}).get("integrity_pass", bool(emb))),
    }


def _safe_cost_sources(root: Path) -> Dict[str, Dict[str, Any]]:
    """Cost-stress sources with contaminated champion returns rejected."""
    sources = dict(resolve_variant_sources(root))
    champion_id = resolve_locked_champion(root)
    path, _ = resolve_variant_returns_path(root, champion_id)
    if champion_id in sources:
        if path and path.is_file():
            sources[champion_id] = {
                **sources[champion_id],
                "returns_path": str(path.relative_to(root)).replace("\\", "/"),
            }
        else:
            sources[champion_id] = {
                **sources[champion_id],
                "returns_path": "",
            }
    return sources


def _cost_stress_block(root: Path, variant_ids: List[str]) -> Dict[str, Any]:
    sources = _safe_cost_sources(root)
    blockers: List[str] = []
    scenario_rows: Dict[str, List[Dict[str, Any]]] = {name: [] for name in SCENARIOS}

    for vid in variant_ids:
        if is_quarantined_variant(vid, root=root):
            continue
        src = sources.get(vid)
        if not src:
            continue
        for scenario_name, scenario in SCENARIOS.items():
            row = evaluate_variant_scenario(
                root,
                vid,
                src,
                scenario_name,
                scenario,
                allow_turnover_proxy=False,
            )
            scenario_rows[scenario_name].append(row)
            if vid == "MOM_63_TOP12" and row.get("turnover_is_proxy"):
                blockers.append("CHALLENGER_TURNOVER_PROXY_DETECTED")
            if vid == "MOM_63_TOP12" and row.get("reason") == "turnover_missing":
                if "CHALLENGER_TURNOVER_NOT_VERIFIED" not in blockers:
                    blockers.append("CHALLENGER_TURNOVER_NOT_VERIFIED")

    gate = evaluate_cost_stress_gate(
        scenario_rows,
        blockers=sorted(set(blockers)),
        champion_id=resolve_locked_champion(root),
    )
    return {
        "scenarios": scenario_rows,
        "gate": gate,
        "blockers": sorted(set(blockers)),
    }


def build_canonical_model_comparison(root: Path) -> Dict[str, Any]:
    root = Path(root)
    locked = resolve_locked_champion(root)
    variant_rows: List[Dict[str, Any]] = []
    series_loadable: Dict[str, pd.Series] = {}
    quarantined_rows: List[Dict[str, Any]] = []

    for variant_id, role in CANONICAL_VARIANT_ROLES:
        if role == "QUARANTINED":
            path, reason = resolve_variant_returns_path(root, variant_id)
            qrow: Dict[str, Any] = {
                "variant_id": variant_id,
                "role": role,
                "note": "Excluded from main rankings; unauthorized operational champion claim.",
            }
            if path and path.is_file():
                s = _load_returns_series(path)
                if s is not None and not s.empty:
                    qrow["metrics"] = calculate_metrics(s)
                    qrow["n_days"] = len(s)
                    qrow["returns_path"] = str(path.relative_to(root)).replace("\\", "/")
            else:
                qrow["skip_reason"] = reason or "quarantined_no_local_returns"
            quarantined_rows.append(qrow)
            continue

        path, miss_reason = resolve_variant_returns_path(root, variant_id)
        row: Dict[str, Any] = {
            "variant_id": variant_id,
            "role": role,
            "is_champion": variant_id == locked,
            "is_m1_control": variant_id == "M1_MOM_BLEND_MATCHED_CONTROLS",
        }
        if path and path.is_file():
            series = _load_returns_series(path)
            if series is not None and not series.empty:
                row["metrics_mode"] = "local_returns"
                row["returns_path"] = str(path.relative_to(root)).replace("\\", "/")
                row["returns_sha256"] = _sha256_file(path)
                row["raw_n_days"] = int(len(series))
                series_loadable[variant_id] = series
                variant_rows.append(row)
                continue
        emb_row = _variant_row_from_embedded(root, variant_id, role)
        emb_row["skip_reason"] = miss_reason or "embedded_fallback"
        variant_rows.append(emb_row)

    alignment_mode = "NONE"
    calendar_meta: Dict[str, Any] = {}
    aligned_frame = pd.DataFrame()

    if len(series_loadable) >= 2:
        aligned_frame, calendar_meta = align_return_series(series_loadable)
        if calendar_meta.get("status") == "OK":
            alignment_mode = "INTERSECTION_RECOMPUTED"
            for vid in aligned_frame.columns:
                seg_metrics = calculate_metrics(aligned_frame[vid])
                for row in variant_rows:
                    if row["variant_id"] == vid:
                        row["metrics_mode"] = "aligned_recomputed"
                        row["metrics"] = seg_metrics
                        row["n_aligned"] = calendar_meta.get("n_aligned")
                        row["subperiods"] = _subperiod_metrics(aligned_frame[vid])
                        break
    else:
        embedded_ndays = [
            int(r["n_days"])
            for r in variant_rows
            if r.get("metrics_mode") == "matrix_embedded" and r.get("n_days")
        ]
        if len(embedded_ndays) >= 3:
            spread = max(embedded_ndays) - min(embedded_ndays)
            if spread <= CALENDAR_WARN_DELTA_DAYS:
                alignment_mode = "MATRIX_EMBEDDED_SAME_WINDOW"
                calendar_meta = {
                    "status": "EMBEDDED_CONSENSUS",
                    "n_days_consensus": int(sum(embedded_ndays) / len(embedded_ndays)),
                    "embedded_n_days_spread": spread,
                    "note": "validation_runs/ absent; matrix metrics share documented window (typically 1860d).",
                }

    def _to_rank_row(row: Dict[str, Any]) -> Dict[str, Any]:
        m = row.get("metrics") or {}
        return {
            "variant_id": row["variant_id"],
            "role": row["role"],
            "metrics_mode": row.get("metrics_mode"),
            "sharpe_0rf": m.get("sharpe_0rf"),
            "max_drawdown": m.get("max_drawdown"),
            "cagr": m.get("cagr"),
            "n_days": m.get("n_days") or row.get("n_aligned") or row.get("n_days"),
            "segment_3_sharpe": (row.get("subperiods") or [{}])[-1].get("sharpe_0rf")
            if row.get("subperiods")
            else None,
        }

    rank_candidates = [r for r in variant_rows if r.get("role") != "QUARANTINED"]
    aligned_source = [_to_rank_row(r) for r in rank_candidates if r.get("metrics_mode") == "aligned_recomputed"]
    embedded_source = [_to_rank_row(r) for r in rank_candidates if r.get("metrics_mode") == "matrix_embedded"]

    cost_ids = [
        locked,
        "M1_MOM_BLEND_MATCHED_CONTROLS",
        "MOM_63_TOP12",
        "MOM_63_TOP12_STRICT",
        "MOM_63_TOP15_RECONSTRUCTED",
    ]
    cost_block = _cost_stress_block(root, cost_ids)
    plus_25 = cost_block["scenarios"].get("PLUS_25_BPS", [])
    for bucket in (aligned_source, embedded_source):
        for r in bucket:
            vid = r["variant_id"]
            stressed = next((x for x in plus_25 if x.get("variant_id") == vid), None)
            if stressed and stressed.get("evaluation_status") == "EVALUABLE":
                r["sharpe_plus_25_bps"] = (stressed.get("metrics") or {}).get("sharpe_0rf")

    rankings = {
        "sharpe_aligned_intersection": _rank_table(aligned_source, "sharpe_0rf"),
        "sharpe_matrix_embedded": _rank_table(embedded_source, "sharpe_0rf"),
        "max_drawdown_matrix_embedded": _rank_table(embedded_source, "max_drawdown", higher_better=False),
        "max_drawdown_aligned_intersection": _rank_table(aligned_source, "max_drawdown", higher_better=False),
        "cost_plus_25_bps_sharpe": _rank_table(
            [r for r in aligned_source + embedded_source if r.get("sharpe_plus_25_bps") is not None],
            "sharpe_plus_25_bps",
        ),
        "segment_3_sharpe": _rank_table(
            [r for r in aligned_source if r.get("segment_3_sharpe") is not None],
            "segment_3_sharpe",
        ),
    }

    matrix_rank = rankings["sharpe_matrix_embedded"]
    aligned_rank = rankings["sharpe_aligned_intersection"]
    primary_rank = matrix_rank if matrix_rank else aligned_rank
    leader = primary_rank[0]["variant_id"] if primary_rank else None
    champion_rank = next(
        (x["rank"] for x in primary_rank if x["variant_id"] == locked),
        None,
    )

    report = {
        "schema_version": 1,
        "phase": "C",
        "generated_at_utc": _utc_now(),
        "authoritative_champion": locked,
        "alignment_mode": alignment_mode,
        "calendar": calendar_meta,
        "validation_runs_present": (root / "validation_runs").is_dir()
        and any((root / "validation_runs").iterdir())
        if (root / "validation_runs").exists()
        else False,
        "variants": variant_rows,
        "quarantined": quarantined_rows,
        "rankings": rankings,
        "headline": {
            "matrix_embedded_sharpe_leader": matrix_rank[0]["variant_id"] if matrix_rank else None,
            "aligned_intersection_sharpe_leader": aligned_rank[0]["variant_id"] if aligned_rank else None,
            "primary_sharpe_leader": leader,
            "primary_ranking_frame": "matrix_embedded" if matrix_rank else "aligned_intersection",
            "champion_sharpe_rank_matrix": next(
                (x["rank"] for x in matrix_rank if x["variant_id"] == locked),
                None,
            ),
            "champion_sharpe_rank": champion_rank,
            "champion_is_sharpe_leader": leader == locked if leader else False,
            "do_not_cross_compare_frames": bool(matrix_rank and aligned_rank),
        },
        "cost_stress": cost_block,
        "governance_blockers": cost_block.get("blockers") or [],
    }
    return report


def format_canonical_comparison_md(doc: Dict[str, Any]) -> str:
    locked = doc.get("authoritative_champion")
    h = doc.get("headline") or {}
    lines = [
        "# Canonical Model Comparison (Phase C)",
        "",
        f"Generated: {doc.get('generated_at_utc')}",
        f"Authoritative champion: `{locked}`",
        f"Alignment mode: **{doc.get('alignment_mode')}**",
        "",
        "## Headline",
        "",
    ]
    if h.get("matrix_embedded_sharpe_leader"):
        lines.append(
            f"- Matrix embedded Sharpe leader: **{h['matrix_embedded_sharpe_leader']}** "
            f"(champion rank: {h.get('champion_sharpe_rank_matrix')})"
        )
    if h.get("aligned_intersection_sharpe_leader"):
        lines.append(
            f"- Aligned intersection Sharpe leader (MOM/research CSVs): **{h['aligned_intersection_sharpe_leader']}**"
        )
    if h.get("do_not_cross_compare_frames"):
        lines.append("- **Warning:** Do not compare matrix-embedded Sharpe to intersection-aligned MOM Sharpe directly.")
    cal = doc.get("calendar") or {}
    if cal:
        lines.append(f"- Aligned calendar: {json.dumps(cal, ensure_ascii=False)}")

    def _section(title: str, key: str) -> None:
        rows = (doc.get("rankings") or {}).get(key) or []
        if not rows:
            return
        lines.extend(["", f"## {title}", ""])
        for row in rows:
            tag = " [CHAMPION]" if row.get("variant_id") == locked else ""
            lines.append(
                f"{row.get('rank')}. `{row.get('variant_id')}` ({row.get('role')}) — "
                f"Sharpe {float(row.get('sharpe_0rf', 0)):.4f}{tag}"
            )

    _section("Rankings — matrix embedded (1860d governance frame)", "sharpe_matrix_embedded")
    _section("Rankings — aligned intersection (return CSV overlap)", "sharpe_aligned_intersection")
    lines.extend(["", "## Cost stress gate", ""])
    gate = (doc.get("cost_stress") or {}).get("gate") or {}
    lines.append(f"- Status: {gate.get('evaluation_status')} pass={gate.get('pass')}")
    for b in doc.get("governance_blockers") or []:
        lines.append(f"- Blocker: `{b}`")
    if doc.get("quarantined"):
        lines.extend(["", "## Quarantined (excluded from main rankings)", ""])
        for q in doc["quarantined"]:
            lines.append(f"- `{q.get('variant_id')}`: {q.get('note') or q.get('skip_reason')}")
    return "\n".join(lines) + "\n"
