"""Champion vs challenger comparison — read-only, no auto-promotion."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from aa_evidence_schema import (
    AUTHORITATIVE_CHAMPION,
    resolve_locked_champion,
    resolve_unsealed_operational_champion_claim,
)
from aa_reporting import calculate_metrics
from aa_safe_io import atomic_write_json, atomic_write_text

QUARANTINED_VARIANT_PREFIXES = ("R5_rank_only_train5",)

REPORT_JSON = "challenger_report.json"
REPORT_TXT = "challenger_report.txt"
REGISTRY_FILE = "challenger_registry.json"

REFERENCE_VARIANT_SUFFIXES = (
    "R0_LEGACY_ENSEMBLE",
    "R1_GATE_BASE_ONLY",
    "R2_MOM_BLEND_REPLACE",
    "R3_w070_q070_noexit",
    "R3_w075_q065_noexit",
    "R4_w070_q070_forceexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)

DEFAULT_REGISTRY: Dict[str, Any] = {
    "auto_promotion": "DISABLED",
    "challengers": [
        {"id": "B0_DAILY_REFERENCE", "status": "planned", "enabled": False},
        {"id": "B1_REALTIME_EXECUTION_ONLY", "status": "planned", "enabled": False},
        {"id": "B2_ATTENTION_CONTINUATION", "status": "planned", "enabled": False},
        {"id": "B3_LIQUIDITY_STRESS", "status": "planned", "enabled": False},
        {"id": "B4_CROWDING_OVERLAY", "status": "planned", "enabled": False},
    ],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def registry_path(root: Path) -> Path:
    return Path(root) / REGISTRY_FILE


def load_registry(root: Path) -> Dict[str, Any]:
    path = registry_path(root)
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(DEFAULT_REGISTRY)


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_champion_variant(out_dir: Path, *, root: Path | None = None) -> str:
    """Authoritative champion id — never an unsealed R5 claim or mismatched pointer."""
    base = root
    if base is None and out_dir.name == "model_output_sp500_pit_t212":
        base = out_dir.parent
    return resolve_locked_champion(base)


def is_quarantined_variant(variant_id: str, *, root: Path | None = None) -> bool:
    vid = str(variant_id or "").strip()
    if any(vid.startswith(p) for p in QUARANTINED_VARIANT_PREFIXES):
        return True
    if root is not None:
        claim = resolve_unsealed_operational_champion_claim(root)
        if claim and vid == str(claim).strip():
            return True
    return False


def embedded_metrics_for_variant(root: Path, variant_id: str) -> Dict[str, float]:
    row = load_embedded_variant_inventory(root).get(variant_id) or {}
    return dict(row.get("metrics_embedded") or {})


def load_embedded_variant_inventory(root: Path) -> Dict[str, Dict[str, Any]]:
    """Phase A/B inventory: metrics when validation_runs/ is absent locally."""
    path = Path(root) / "evidence" / "variant_run_inventory.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for row in doc.get("variants") or []:
        vid = str(row.get("variant_id") or "").strip()
        if not vid or is_quarantined_variant(vid, root=root):
            continue
        out[vid] = row
    return out


def _metrics_for_variant(
    root: Path,
    variant_id: str,
    run_dir: Optional[Path],
    embedded: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, float], bool, str]:
    """Return (metrics, integrity_pass, metrics_source)."""
    if run_dir is not None and (run_dir / "strategy_daily_returns.csv").is_file():
        m = _variant_metrics(run_dir)
        if m:
            return m, _integrity_pass(run_dir), "local_run_dir"
    row = embedded.get(variant_id) or {}
    m_emb = dict(row.get("metrics_embedded") or {})
    if m_emb:
        integ = row.get("integrity") or {}
        return m_emb, bool(integ.get("integrity_pass", True)), str(row.get("source") or "embedded_inventory")
    return {}, False, "missing"


def _integrity_pass(run_dir: Path) -> bool:
    if not (run_dir / "integrity_report.json").is_file():
        return False
    try:
        data = json.loads((run_dir / "integrity_report.json").read_text(encoding="utf-8"))
        return str(data.get("status", "")) == "PASS" and not data.get("errors")
    except Exception:
        return False


def discover_validation_variants(root: Path) -> Dict[str, Path]:
    """Map variant suffix -> latest PASS validation dir."""
    validation_root = Path(root) / "validation_runs"
    found: Dict[str, Path] = {}
    if not validation_root.is_dir():
        return found
    for child in sorted(validation_root.iterdir()):
        if not child.is_dir():
            continue
        for suffix in REFERENCE_VARIANT_SUFFIXES:
            if child.name.endswith(f"_{suffix}") and _integrity_pass(child):
                found[suffix] = child
    return found


def _load_strategy_returns(run_dir: Path) -> Optional[pd.Series]:
    path = run_dir / "strategy_daily_returns.csv"
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        col = "strategy_return" if "strategy_return" in frame.columns else frame.columns[0]
        return pd.to_numeric(frame[col], errors="coerce").dropna()
    except Exception:
        return None


def _load_benchmark_returns(run_dir: Path) -> Optional[pd.Series]:
    path = run_dir / "benchmark_daily_returns.csv"
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        col = "benchmark_return" if "benchmark_return" in frame.columns else frame.columns[0]
        return pd.to_numeric(frame[col], errors="coerce").dropna()
    except Exception:
        return None


def _variant_metrics(run_dir: Path) -> Dict[str, float]:
    strat = _load_strategy_returns(run_dir)
    if strat is None or strat.empty:
        return {}
    bench = _load_benchmark_returns(run_dir)
    return calculate_metrics(strat, bench)


def evaluate_promotion_gate(
    *,
    champion: Dict[str, Any],
    m1: Optional[Dict[str, Any]],
    challenger: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Always returns blocked — manual promotion only."""
    checks = {
        "integrity_pass": bool(champion.get("integrity_pass")),
        "data_quality_ok": True,
        "calendar_complete": bool(champion.get("n_days", 0) >= 200),
        "beats_m1_sharpe": False,
        "beats_champion_sharpe": False,
        "cost_stress_pass": None,
        "paper_forward_documented": False,
        "manual_approval": False,
    }
    c_sharpe = float(champion.get("metrics", {}).get("sharpe_0rf", float("nan")))
    if m1:
        m_sharpe = float(m1.get("metrics", {}).get("sharpe_0rf", float("nan")))
        checks["beats_m1_sharpe"] = bool(c_sharpe > m_sharpe) if pd.notna(c_sharpe) and pd.notna(m_sharpe) else False
    if challenger:
        ch_sharpe = float(challenger.get("metrics", {}).get("sharpe_0rf", float("nan")))
        checks["beats_champion_sharpe"] = bool(ch_sharpe > c_sharpe) if pd.notna(ch_sharpe) and pd.notna(c_sharpe) else False
    blocked_reasons = ["auto_promotion_disabled"]
    if not checks["manual_approval"]:
        blocked_reasons.append("manual_approval_required")
    return {
        "status": "BLOCKED",
        "checks": checks,
        "blocked_reasons": blocked_reasons,
    }


def build_challenger_report(root: Path, out_dir: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = Path(out_dir)
    champion_variant = resolve_locked_champion(root)
    registry = load_registry(root)
    variants = discover_validation_variants(root)
    embedded = load_embedded_variant_inventory(root)

    # Never attach model_output/ returns to champion (Phase B — may be wrong calendar / R5 spill).
    for suffix in REFERENCE_VARIANT_SUFFIXES:
        if suffix not in variants and suffix in embedded:
            run_dir_s = embedded[suffix].get("run_dir")
            if run_dir_s and Path(str(run_dir_s)).is_dir():
                variants[suffix] = Path(str(run_dir_s))

    variant_ids = sorted(
        vid for vid in (set(variants.keys()) | set(embedded.keys())) if not is_quarantined_variant(vid, root=root)
    )
    entries: List[Dict[str, Any]] = []
    for suffix in variant_ids:
        if is_quarantined_variant(suffix, root=root):
            continue
        run_dir = variants.get(suffix)
        metrics, integrity_pass, metrics_source = _metrics_for_variant(root, suffix, run_dir, embedded)
        if not metrics:
            continue
        run_dir_str = str(run_dir.resolve()) if run_dir is not None else str((embedded.get(suffix) or {}).get("run_dir") or "")
        entries.append(
            {
                "variant_id": suffix,
                "run_dir": run_dir_str,
                "integrity_pass": integrity_pass,
                "metrics": metrics,
                "metrics_source": metrics_source,
                "is_champion": suffix == champion_variant,
                "is_m1_reference": suffix == "M1_MOM_BLEND_MATCHED_CONTROLS",
            }
        )

    champion_entry = next((e for e in entries if e["is_champion"]), None)
    m1_entry = next((e for e in entries if e["is_m1_reference"]), None)
    if champion_entry:
        champion_entry["n_days"] = champion_entry.get("metrics", {}).get("n_days", 0)
    gate = evaluate_promotion_gate(
        champion=champion_entry or {"integrity_pass": False, "metrics": {}, "n_days": 0},
        m1=m1_entry,
    )

    ranked = sorted(entries, key=lambda e: float(e.get("metrics", {}).get("sharpe_0rf", float("-inf")) or float("-inf")), reverse=True)

    unsealed = resolve_unsealed_operational_champion_claim(root)
    return {
        "generated_at_utc": _utc_now(),
        "champion_variant_id": champion_variant,
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "quarantined_operational_claim": unsealed,
        "auto_promotion": registry.get("auto_promotion", "DISABLED"),
        "variants_compared": len(entries),
        "entries": entries,
        "ranked_by_sharpe": [e["variant_id"] for e in ranked],
        "promotion_gate": gate,
        "m1_available": m1_entry is not None,
    }


def format_challenger_report_text(report: Dict[str, Any]) -> str:
    lines = [
        "Champion / Challenger Evaluation Report",
        f"Generated: {report.get('generated_at_utc', '')}",
        f"Champion: {report.get('champion_variant_id', '—')}",
        f"Auto-promotion: {report.get('auto_promotion', 'DISABLED')}",
        f"Variants compared: {report.get('variants_compared', 0)}",
        "",
        "Ranked by Sharpe (0 rf):",
    ]
    for vid in report.get("ranked_by_sharpe") or []:
        entry = next((e for e in report.get("entries") or [] if e["variant_id"] == vid), None)
        if not entry:
            continue
        m = entry.get("metrics") or {}
        tag = []
        if entry.get("is_champion"):
            tag.append("CHAMPION")
        if entry.get("is_m1_reference"):
            tag.append("M1")
        label = f" [{', '.join(tag)}]" if tag else ""
        lines.append(
            f"  {vid}{label}: Sharpe={m.get('sharpe_0rf', float('nan')):.3f} "
            f"CAGR={m.get('cagr', float('nan')):.2%} MaxDD={m.get('max_drawdown', float('nan')):.2%}"
        )
    gate = report.get("promotion_gate") or {}
    lines.extend(["", f"Promotion gate: {gate.get('status', 'BLOCKED')}"])
    for reason in gate.get("blocked_reasons") or []:
        lines.append(f"  - {reason}")
    return "\n".join(lines) + "\n"


def write_challenger_report(root: Path, out_dir: Path) -> Tuple[Path, Path]:
    report = build_challenger_report(root, out_dir)
    text = format_challenger_report_text(report)
    json_path = atomic_write_json(Path(out_dir) / REPORT_JSON, report)
    txt_path = atomic_write_text(Path(out_dir) / REPORT_TXT, text)
    ctrl = Path(root) / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    atomic_write_json(ctrl / REPORT_JSON, report)
    atomic_write_text(ctrl / REPORT_TXT, text)
    return json_path, txt_path


def run_challenger_evaluation(root: Path, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(root)
    if out_dir is None:
        from aa_ops_refresh import resolve_out_dir
        import os

        out_dir = resolve_out_dir(root, os.environ)
    json_path, txt_path = write_challenger_report(root, Path(out_dir))
    report = json.loads(json_path.read_text(encoding="utf-8"))
    return {
        "json_path": str(json_path),
        "txt_path": str(txt_path),
        "variants_compared": report.get("variants_compared", 0),
        "promotion_status": report.get("promotion_gate", {}).get("status", "BLOCKED"),
    }
