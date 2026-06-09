"""P3 background research — evaluate existing variants without auto-promotion."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_challenger_eval import (
    build_challenger_report,
    discover_validation_variants,
    embedded_metrics_for_variant,
    load_embedded_variant_inventory,
    resolve_champion_variant,
    run_challenger_evaluation,
)
from aa_evidence_schema import resolve_locked_champion
from aa_job_lock import JobLock
from aa_reporting import calculate_metrics
from aa_safe_io import atomic_write_json, atomic_write_text

STATUS_FILE = "background_research_status.json"
REPORT_TXT = "background_research_report.txt"
LOCK_JOB = "background_research"

P3_VARIANT_TARGETS = (
    "R5_rank_only_train5",
    "R3_w075_q065_noexit",
    "R0_LEGACY_ENSEMBLE",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
    "MOM_63_TOP12",
)

MOM63_ALIASES = ("MOM_63_TOP12", "NAIVE_MOMENTUM_MOM_63_TOP12", "NAIVE_MOM_63_TOP12")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def status_path(root: Path) -> Path:
    return Path(root) / "control" / STATUS_FILE


def out_status_path(out_dir: Path) -> Path:
    return Path(out_dir) / STATUS_FILE


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _integrity_pass(run_dir: Path) -> bool:
    report = run_dir / "integrity_report.json"
    if not report.is_file():
        return False
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
        return str(data.get("status", "")).upper() == "PASS" and not data.get("errors")
    except Exception:
        return False


def _load_strategy_returns(run_dir: Path):
    import pandas as pd

    path = run_dir / "strategy_daily_returns.csv"
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        col = "strategy_return" if "strategy_return" in frame.columns else frame.columns[0]
        return pd.to_numeric(frame[col], errors="coerce").dropna()
    except Exception:
        return None


def _parse_mom63_bootstrap_median(m1_dir: Path) -> Dict[str, float]:
    """Read NAIVE_MOM_63 reference medians from M1 backtest_report (embedded control)."""
    report = m1_dir / "backtest_report.txt"
    if not report.is_file():
        return {}
    text = report.read_text(encoding="utf-8", errors="ignore")
    if "NAIVE_MOMENTUM_MOM_63_TOP12" not in text and "MOM_63" not in text:
        return {}
    metrics: Dict[str, float] = {}
    for key in ("cagr", "sharpe_0rf", "max_drawdown", "information_ratio"):
        m = re.search(rf"vs_NAIVE_MOMENTUM_MOM_63_TOP12\.{key}: p05=[^,]+, p50=([^,]+),", text)
        if m:
            try:
                metrics[key] = float(m.group(1))
            except ValueError:
                pass
    return metrics


def _mom63_entry(m1_dir: Optional[Path]) -> Dict[str, Any]:
    if m1_dir is None or not _integrity_pass(m1_dir):
        return {
            "variant_id": "MOM_63_TOP12",
            "status": "NOT_AVAILABLE",
            "integrity_pass": False,
            "is_active_champion": False,
            "is_research_candidate": False,
            "reference_source": "",
            "note": "Requires PASS M1 matched-controls run with embedded NAIVE_MOM_63 reference.",
        }
    metrics = _parse_mom63_bootstrap_median(m1_dir)
    if not metrics:
        return {
            "variant_id": "MOM_63_TOP12",
            "status": "NOT_AVAILABLE",
            "integrity_pass": True,
            "is_active_champion": False,
            "is_research_candidate": False,
            "reference_source": str(m1_dir),
            "note": "M1 PASS but NAIVE_MOM_63 metrics not found in backtest_report.",
        }
    return {
        "variant_id": "MOM_63_TOP12",
        "status": "PASS",
        "integrity_pass": True,
        "is_active_champion": False,
        "is_research_candidate": True,
        "reference_source": str(m1_dir.resolve()),
        "reference_type": "M1_EMBEDDED_CONTROL",
        "metrics": metrics,
        "note": "Embedded matched-control reference from M1 backtest_report (not a separate walk-forward run).",
    }


def _variant_entry(
    variant_id: str,
    run_dir: Optional[Path],
    *,
    champion_variant: str,
) -> Dict[str, Any]:
    if run_dir is None:
        return {
            "variant_id": variant_id,
            "status": "NOT_AVAILABLE",
            "integrity_pass": False,
            "is_active_champion": variant_id == champion_variant,
            "is_research_candidate": False,
            "run_dir": "",
        }
    integrity = _integrity_pass(run_dir)
    strat = _load_strategy_returns(run_dir)
    metrics = calculate_metrics(strat, None) if strat is not None and not strat.empty else {}
    if not integrity:
        status = "FAIL"
        candidate = False
    elif metrics:
        status = "PASS"
        candidate = variant_id != champion_variant
    else:
        status = "FAIL"
        candidate = False
    return {
        "variant_id": variant_id,
        "status": status,
        "integrity_pass": integrity,
        "is_active_champion": variant_id == champion_variant,
        "is_research_candidate": candidate and status == "PASS",
        "run_dir": str(run_dir.resolve()),
        "metrics": metrics,
    }


def discover_p3_variant_dirs(root: Path) -> Dict[str, Path]:
    """Latest validation dir per P3 target suffix (includes FAIL integrity for reporting)."""
    validation_root = Path(root) / "validation_runs"
    found: Dict[str, Path] = {}
    if not validation_root.is_dir():
        return found
    suffixes = set(P3_VARIANT_TARGETS) | {"R3_w070_q070_noexit", "R3_w075_q065_noexit"}
    for child in sorted(validation_root.iterdir()):
        if not child.is_dir():
            continue
        for suffix in suffixes:
            if child.name.endswith(f"_{suffix}"):
                found[suffix] = child
    return found


def build_background_research_status(root: Path, out_dir: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = Path(out_dir)
    champion_variant = resolve_locked_champion(root)
    discovered_pass = discover_validation_variants(root)
    discovered_all = discover_p3_variant_dirs(root)

    r0_dir = discovered_all.get("R0_LEGACY_ENSEMBLE")
    r3_dir = discovered_pass.get(champion_variant) or discovered_all.get(champion_variant)
    if r3_dir is None:
        for key, path in discovered_all.items():
            if key.startswith("R3_"):
                r3_dir = path
                break
    m1_dir = discovered_all.get("M1_MOM_BLEND_MATCHED_CONTROLS")

    entries: List[Dict[str, Any]] = [
        _variant_entry("R0_LEGACY_ENSEMBLE", r0_dir, champion_variant=champion_variant),
        _variant_entry(champion_variant, r3_dir, champion_variant=champion_variant),
        _variant_entry("M1_MOM_BLEND_MATCHED_CONTROLS", m1_dir, champion_variant=champion_variant),
        _mom63_entry(m1_dir if m1_dir and _integrity_pass(m1_dir) else None),
    ]
    champ_row = next((e for e in entries if e.get("variant_id") == champion_variant), None)
    if champ_row and champ_row.get("status") == "NOT_AVAILABLE":
        emb = embedded_metrics_for_variant(root, champion_variant)
        if emb:
            inv_row = load_embedded_variant_inventory(root).get(champion_variant) or {}
            champ_row.update(
                {
                    "status": "PASS",
                    "integrity_pass": True,
                    "metrics": emb,
                    "run_dir": inv_row.get("run_dir") or champ_row.get("run_dir"),
                    "metrics_source": "embedded_inventory",
                    "note": "Matrix run dir absent locally; metrics from Phase A embedded inventory.",
                }
            )
    checked = [e for e in entries if e.get("status") in {"PASS", "FAIL"}]
    pass_n = sum(1 for e in checked if e.get("status") == "PASS")
    fail_n = sum(1 for e in checked if e.get("status") == "FAIL")
    required = {"R0_LEGACY_ENSEMBLE", champion_variant, "M1_MOM_BLEND_MATCHED_CONTROLS"}
    required_pass = all(
        any(e.get("variant_id") == vid and e.get("status") == "PASS" for e in entries)
        for vid in required
    )

    candidates = [
        e for e in entries if e.get("is_research_candidate") and e.get("integrity_pass") and e.get("status") == "PASS"
    ]
    best = None
    if candidates:
        best = max(
            candidates,
            key=lambda e: float((e.get("metrics") or {}).get("sharpe_0rf", float("-inf")) or float("-inf")),
        )

    m1_entry = next((e for e in entries if e.get("variant_id") == "M1_MOM_BLEND_MATCHED_CONTROLS"), None)
    champ_entry = next((e for e in entries if e.get("is_active_champion")), None)
    m1_compare = None
    if m1_entry and champ_entry and m1_entry.get("metrics") and champ_entry.get("metrics"):
        c_sh = float(champ_entry["metrics"].get("sharpe_0rf", float("nan")))
        m_sh = float(m1_entry["metrics"].get("sharpe_0rf", float("nan")))
        m1_compare = {
            "champion_sharpe": c_sh,
            "m1_sharpe": m_sh,
            "champion_vs_m1_sharpe_delta": c_sh - m_sh if c_sh == c_sh and m_sh == m_sh else None,
        }

    if fail_n > 0 and not required_pass:
        research_status = "FAIL"
    elif required_pass:
        research_status = "PASS"
    elif not checked:
        research_status = "NOT_STARTED"
    else:
        research_status = "FAIL"

    last_run = ""
    for e in entries:
        rd = str(e.get("run_dir") or e.get("reference_source") or "")
        if rd:
            last_run = rd
            break

    return {
        "updated_at_utc": _utc_now(),
        "research_status": research_status,
        "auto_promotion": "DISABLED",
        "champion_variant_id": champion_variant,
        "variants_checked": len(checked),
        "variants_pass": pass_n,
        "variants_fail": fail_n,
        "last_comparison_run_dir": last_run,
        "best_research_candidate": {
            "variant_id": best.get("variant_id"),
            "sharpe_0rf": (best.get("metrics") or {}).get("sharpe_0rf"),
            "active": False,
            "note": "Research candidate only — not promoted in P3.",
        }
        if best
        else None,
        "m1_comparison": m1_compare,
        "entries": entries,
        "checked_variant_ids": [e.get("variant_id") for e in entries if e.get("status") != "NOT_AVAILABLE"],
    }


def format_background_research_report(status: Dict[str, Any]) -> str:
    lines = [
        "Background Research Status (P3)",
        f"Updated: {status.get('updated_at_utc', '')}",
        f"Research status: {status.get('research_status', 'NOT_STARTED')}",
        f"Champion: {status.get('champion_variant_id', '—')} (unchanged)",
        f"Auto-promotion: {status.get('auto_promotion', 'DISABLED')}",
        "",
        "Checked variants:",
    ]
    for entry in status.get("entries") or []:
        tag = []
        if entry.get("is_active_champion"):
            tag.append("CHAMPION")
        if entry.get("is_research_candidate"):
            tag.append("CANDIDATE")
        label = f" [{', '.join(tag)}]" if tag else ""
        m = entry.get("metrics") or {}
        sh = m.get("sharpe_0rf", float("nan"))
        sh_txt = f"{sh:.3f}" if isinstance(sh, (int, float)) and sh == sh else "n/a"
        lines.append(f"  {entry.get('variant_id')}{label}: {entry.get('status')} integrity={entry.get('integrity_pass')} Sharpe={sh_txt}")
    best = status.get("best_research_candidate")
    if best and best.get("variant_id"):
        lines.extend(
            [
                "",
                f"Best research candidate (not active): {best.get('variant_id')} Sharpe={best.get('sharpe_0rf', 'n/a')}",
            ]
        )
    m1c = status.get("m1_comparison") or {}
    if m1c:
        lines.extend(
            [
                "",
                f"M1 comparison Sharpe: champion={m1c.get('champion_sharpe', 'n/a')} m1={m1c.get('m1_sharpe', 'n/a')}",
            ]
        )
    return "\n".join(lines) + "\n"


def write_background_research_status(root: Path, out_dir: Path, status: Dict[str, Any]) -> Tuple[Path, Path]:
    root = Path(root)
    out_dir = Path(out_dir)
    ctrl = root / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    json_ctrl = atomic_write_json(status_path(root), status)
    json_out = atomic_write_json(out_status_path(out_dir), status)
    text = format_background_research_report(status)
    atomic_write_text(ctrl / REPORT_TXT, text)
    atomic_write_text(out_dir / REPORT_TXT, text)
    return json_out, json_ctrl


def research_status_summary(out_dir: Path) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    root = out_dir.parent
    for candidate in (out_status_path(out_dir), status_path(root)):
        data = _read_json(candidate)
        if data:
            return {
                "background_research_status": str(data.get("research_status", "NOT_STARTED")),
                "background_research_updated_at_utc": str(data.get("updated_at_utc", "") or ""),
                "background_research_variants_checked": int(data.get("variants_checked", 0) or 0),
                "best_research_candidate_id": str((data.get("best_research_candidate") or {}).get("variant_id", "") or ""),
                "last_comparison_run_dir": str(data.get("last_comparison_run_dir", "") or ""),
            }
    return {
        "background_research_status": "NOT_STARTED",
        "background_research_updated_at_utc": "",
        "background_research_variants_checked": 0,
        "best_research_candidate_id": "",
        "last_comparison_run_dir": "",
    }


def run_background_research(
    root: Path,
    out_dir: Optional[Path] = None,
    *,
    use_lock: bool = True,
) -> Dict[str, Any]:
    """Evaluate existing validation artifacts — no new full backtests, no promotion."""
    root = Path(root)
    if out_dir is None:
        from aa_ops_refresh import resolve_out_dir
        import os

        out_dir = resolve_out_dir(root, os.environ)
    out_dir = Path(out_dir)

    lock = JobLock(root, LOCK_JOB) if use_lock else None
    if lock is not None and not lock.acquire():
        existing = _read_json(status_path(root))
        return {
            "status": "LOCKED",
            "research_status": existing.get("research_status", "NOT_STARTED"),
            "message": "Background research already running.",
        }

    try:
        status = build_background_research_status(root, out_dir)
        status["research_status"] = "RUNNING"
        write_background_research_status(root, out_dir, status)

        challenger = run_challenger_evaluation(root, out_dir)
        status = build_background_research_status(root, out_dir)
        status["challenger_variants_compared"] = challenger.get("variants_compared", 0)
        status["promotion_status"] = challenger.get("promotion_status", "BLOCKED")
        write_background_research_status(root, out_dir, status)

        return {
            "status": "OK",
            "research_status": status.get("research_status"),
            "variants_checked": status.get("variants_checked"),
            "variants_pass": status.get("variants_pass"),
            "promotion_status": status.get("promotion_status"),
            "json_path": str(out_status_path(out_dir)),
        }
    finally:
        if lock is not None:
            lock.release()
