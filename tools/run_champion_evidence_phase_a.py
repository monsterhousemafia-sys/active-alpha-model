#!/usr/bin/env python3
"""Phase A — Champion / variant truth inventory (read-only evidence generation)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_challenger_eval import REFERENCE_VARIANT_SUFFIXES, discover_validation_variants
from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion
from aa_safe_io import atomic_write_json, atomic_write_text

EVIDENCE_DIR = ROOT / "evidence"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    "work_fail_closed_test",
    "work",
}

POINTER_JSON_KEYS = (
    "champion_variant_id",
    "active_champion",
    "authoritative_champion",
    "expected_champion",
    "validated_variant_id",
    "promoted_from_champion",
    "previous_champion_variant_id",
    "is_champion",
    "is_active_champion",
)

POINTER_TEXT_PATTERNS = (
    re.compile(r"AUTHORITATIVE_CHAMPION\s*=\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"LOCKED_CHAMPION\s*=\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"Champion:\s*([A-Za-z0-9_]+)", re.I),
    re.compile(r"active_champion['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_]+)"),
)

EXTRA_VARIANT_SUFFIXES = (
    "R5_rank_only_train5",
    "MOM_63_TOP12",
    "MOM_63_TOP12_STRICT",
    "MOM_63_TOP15_RECONSTRUCTED",
)

SCAN_ROOTS = (
    "control",
    "evidence",
    "model_output_sp500_pit_t212",
    "model_output",
    "validation_runs",
    "runs",
    "docs",
    "research_evidence",
    "live_pilot",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_scan_files(root: Path) -> Iterable[Path]:
    for rel in SCAN_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix.lower() in {".json", ".md", ".yaml", ".yml", ".txt", ".py"}:
                yield path


def _extract_json_pointers(path: Path, data: Any, *, rel: str) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []

    def walk(obj: Any, prefix: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k)
                jp = f"{prefix}.{key}" if prefix else key
                if key in POINTER_JSON_KEYS or key == "variant_id":
                    if isinstance(v, (str, int, float, bool)) and str(v).strip():
                        val = str(v).strip()
                        if "champion" in key.lower() or key == "variant_id" or "R3_" in val or "R5_" in val or "M1_" in val or "MOM_" in val:
                            hits.append(
                                {
                                    "file": rel,
                                    "json_path": jp,
                                    "key": key,
                                    "value": val,
                                    "kind": "json_field",
                                }
                            )
                walk(v, jp)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{prefix}[{i}]")

    walk(data, "")
    return hits


def _extract_text_pointers(path: Path, text: str, *, rel: str) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for key in POINTER_JSON_KEYS:
            if key in line and ":" in line:
                try:
                    frag = line.split(":", 1)[1].strip().strip(",").strip('"').strip("'")
                    if frag and len(frag) < 80:
                        hits.append(
                            {
                                "file": rel,
                                "line": i,
                                "key": key,
                                "value": frag,
                                "kind": "text_line",
                            }
                        )
                except Exception:
                    pass
        for pat in POINTER_TEXT_PATTERNS:
            m = pat.search(line)
            if m:
                hits.append(
                    {
                        "file": rel,
                        "line": i,
                        "key": pat.pattern[:40],
                        "value": m.group(1),
                        "kind": "text_pattern",
                    }
                )
    return hits


def build_champion_pointer_audit(root: Path) -> Dict[str, Any]:
    locked = resolve_locked_champion(root)
    hits: List[Dict[str, Any]] = []
    files_scanned = 0
    parse_errors: List[str] = []

    for path in sorted(_iter_scan_files(root)):
        rel = str(path.relative_to(root)).replace("\\", "/")
        files_scanned += 1
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                hits.extend(_extract_json_pointers(path, data, rel=rel))
            except Exception as exc:
                parse_errors.append(f"{rel}: {exc}")
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                hits.extend(_extract_text_pointers(path, text, rel=rel))
            except Exception as exc:
                parse_errors.append(f"{rel}: {exc}")

    # Critical control-plane files (always summarized)
    critical: Dict[str, Any] = {}
    for rel in (
        "model_output_sp500_pit_t212/latest_validated_run.json",
        "model_output_sp500_pit_t212/challenger_report.json",
        "control/background_research_status.json",
        "control/r5_challenger_registry.json",
        "control/authorization/current_authorization_status.json",
        "aa_evidence_schema.py",
    ):
        p = root / rel
        if not p.is_file():
            critical[rel] = {"present": False}
            continue
        if rel.endswith(".json"):
            try:
                critical[rel] = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                critical[rel] = {"present": True, "error": str(exc)}
        else:
            critical[rel] = {"present": True, "authoritative_champion_constant": AUTHORITATIVE_CHAMPION}

    by_value: Dict[str, List[Dict[str, Any]]] = {}
    for h in hits:
        v = str(h.get("value") or "").upper()
        if not v:
            continue
        by_value.setdefault(v, []).append(h)

    conflicts: List[str] = []
    champion_like = {k for k in by_value if "R3_" in k or "R5_" in k or k == locked.upper()}
    if len(champion_like) > 1:
        conflicts.append(f"Multiple champion-like variant ids in pointers: {sorted(champion_like)}")

    ptr_champion = str(critical.get("model_output_sp500_pit_t212/challenger_report.json", {}).get("champion_variant_id") or "")
    lvr = critical.get("model_output_sp500_pit_t212/latest_validated_run.json") or {}
    if isinstance(lvr, dict):
        if str(lvr.get("variant_id") or "") != locked and lvr.get("variant_id"):
            conflicts.append(f"latest_validated_run variant_id={lvr.get('variant_id')} != locked {locked}")
        if str(lvr.get("run_id") or "") and "R5" in str(lvr.get("run_id")) and locked in str(lvr.get("variant_id") or ""):
            conflicts.append("latest_validated_run: R5 run_id with R3 variant_id")
    if ptr_champion and ptr_champion != locked:
        conflicts.append(f"challenger_report champion_variant_id={ptr_champion} != locked {locked}")

    return {
        "schema_version": 1,
        "phase": "A1",
        "generated_at_utc": _utc_now(),
        "locked_champion_code": locked,
        "authoritative_champion_constant": AUTHORITATIVE_CHAMPION,
        "files_scanned": files_scanned,
        "pointer_hit_count": len(hits),
        "unique_values": sorted(by_value.keys()),
        "conflicts": conflicts,
        "parse_errors": parse_errors[:50],
        "critical_artifacts": critical,
        "hits_sample": hits[:200],
        "hits_by_value": {k: v[:15] for k, v in sorted(by_value.items())},
    }


def _returns_calendar_stats(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "strategy_daily_returns.csv"
    out: Dict[str, Any] = {
        "run_dir": str(run_dir.resolve()),
        "returns_path": str(path) if path.is_file() else None,
        "returns_sha256": _sha256_file(path) if path.is_file() else None,
        "n_days": None,
        "start_date": None,
        "end_date": None,
    }
    if not path.is_file():
        return out
    try:
        import pandas as pd

        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        col = "strategy_return" if "strategy_return" in frame.columns else frame.columns[0]
        s = pd.to_numeric(frame[col], errors="coerce").dropna()
        out["n_days"] = int(len(s))
        if len(s):
            out["start_date"] = str(s.index.min())[:10]
            out["end_date"] = str(s.index.max())[:10]
    except Exception as exc:
        out["error"] = str(exc)
    return out


def _integrity_status(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "integrity_report.json"
    if not path.is_file():
        return {"status": "MISSING", "integrity_pass": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        st = str(data.get("status", ""))
        return {
            "status": st,
            "integrity_pass": st == "PASS" and not data.get("errors"),
            "errors_count": len(data.get("errors") or []),
        }
    except Exception as exc:
        return {"status": "ERROR", "integrity_pass": False, "error": str(exc)}


def discover_all_variant_dirs(root: Path) -> Dict[str, Path]:
    found = dict(discover_validation_variants(root))
    validation_root = root / "validation_runs"
    all_suffixes = list(REFERENCE_VARIANT_SUFFIXES) + list(EXTRA_VARIANT_SUFFIXES)
    if validation_root.is_dir():
        for child in sorted(validation_root.iterdir()):
            if not child.is_dir():
                continue
            for suffix in all_suffixes:
                if child.name.endswith(f"_{suffix}") or suffix in child.name:
                    if (child / "strategy_daily_returns.csv").is_file():
                        prev = found.get(suffix)
                        if prev is None or child.name > prev.name:
                            found[suffix] = child
    out_dir = root / "model_output_sp500_pit_t212"
    if (out_dir / "strategy_daily_returns.csv").is_file():
        found.setdefault("model_output_sp500_pit_t212", out_dir)
    return found


def _role_for_variant(suffix: str, locked: str) -> str:
    if suffix == locked:
        return "CHAMPION"
    if suffix == "M1_MOM_BLEND_MATCHED_CONTROLS":
        return "M1_CONTROL"
    if suffix == "model_output_sp500_pit_t212":
        return "OUTPUT_DIR"
    if "R5" in suffix:
        return "QUARANTINED"
    return "RESEARCH"


def _embedded_entries_from_reports(root: Path) -> List[Dict[str, Any]]:
    """When validation_runs/ is absent (gitignored), reuse metrics embedded in control reports."""
    out: List[Dict[str, Any]] = []
    for rel in (
        "control/background_research_status.json",
        "model_output_sp500_pit_t212/challenger_report.json",
        "model_output/challenger_report.json",
    ):
        path = root / rel
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for entry in doc.get("entries") or []:
            vid = str(entry.get("variant_id") or "").strip()
            if not vid:
                continue
            metrics = dict(entry.get("metrics") or {})
            out.append(
                {
                    "variant_id": vid,
                    "source": rel,
                    "run_dir": entry.get("run_dir"),
                    "n_days": metrics.get("n_days") or entry.get("n_days"),
                    "returns_sha256": None,
                    "integrity": {
                        "status": entry.get("status") or ("PASS" if entry.get("integrity_pass") else "UNKNOWN"),
                        "integrity_pass": bool(entry.get("integrity_pass")),
                    },
                    "metrics_embedded": metrics,
                    "note": entry.get("note") or entry.get("reference_type"),
                }
            )
    return out


def build_variant_run_inventory(root: Path) -> Dict[str, Any]:
    locked = resolve_locked_champion(root)
    dirs = discover_all_variant_dirs(root)
    validation_root = root / "validation_runs"
    variants: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for suffix in sorted(dirs.keys()):
        run_dir = dirs[suffix]
        cal = _returns_calendar_stats(run_dir)
        integ = _integrity_status(run_dir)
        variants.append(
            {
                "variant_id": suffix,
                "role": _role_for_variant(suffix, locked),
                "source": "local_run_dir",
                **cal,
                "integrity": integ,
            }
        )
        seen.add(suffix)

    for emb in _embedded_entries_from_reports(root):
        vid = str(emb["variant_id"])
        if vid in seen:
            continue
        seen.add(vid)
        variants.append(
            {
                "variant_id": vid,
                "role": _role_for_variant(vid, locked),
                "source": emb.get("source"),
                "run_dir": emb.get("run_dir"),
                "returns_path": None,
                "returns_sha256": emb.get("returns_sha256"),
                "n_days": emb.get("n_days"),
                "start_date": None,
                "end_date": None,
                "integrity": emb.get("integrity"),
                "metrics_embedded": emb.get("metrics_embedded"),
                "note": emb.get("note"),
            }
        )

    expected = list(REFERENCE_VARIANT_SUFFIXES) + list(EXTRA_VARIANT_SUFFIXES)
    missing = [s for s in expected if s not in seen]
    return {
        "schema_version": 1,
        "phase": "A2",
        "generated_at_utc": _utc_now(),
        "locked_champion": locked,
        "validation_runs_present": validation_root.is_dir(),
        "validation_runs_gitignored": (root / ".gitignore").is_file()
        and "validation_runs/" in (root / ".gitignore").read_text(encoding="utf-8", errors="replace"),
        "variants_found": len(variants),
        "variants_missing_local_dir": missing,
        "variants": sorted(variants, key=lambda v: str(v.get("variant_id"))),
    }


def build_calendar_mismatch_report(root: Path, inventory: Dict[str, Any]) -> str:
    locked = resolve_locked_champion(root)
    by_id = {v["variant_id"]: v for v in inventory.get("variants") or []}

    def n_days(vid: str) -> Optional[int]:
        v = by_id.get(vid) or {}
        n = v.get("n_days")
        return int(n) if n is not None else None

    matrix_r3 = n_days("R3_w075_q065_noexit")
    if matrix_r3 is None:
        emb = by_id.get("R3_w075_q065_noexit") or {}
        if emb.get("n_days") is not None:
            matrix_r3 = int(emb["n_days"])
    out_dir = n_days("model_output_sp500_pit_t212")
    inv_meta = inventory.get("validation_runs_present")
    inv_git = inventory.get("validation_runs_gitignored")
    r5_dirs = [v for v in inventory.get("variants") or [] if "R5" in str(v.get("variant_id", ""))]

    lines = [
        "# Calendar mismatch root cause (Phase A3)",
        "",
        f"Generated: {_utc_now()}",
        "",
        "## Summary",
        "",
        f"- **Locked champion (code):** `{locked}`",
        f"- **Matrix R3 run (`validation_runs/..._R3_w075_q065_noexit`):** {matrix_r3 or 'MISSING (see embedded report metrics)'} trading days",
        f"- **`model_output_sp500_pit_t212` returns:** {out_dir or 'MISSING'} trading days",
        f"- **`validation_runs/` on disk:** {inv_meta} (gitignored={inv_git})",
        "",
    ]

    if out_dir and matrix_r3 and matrix_r3 != out_dir:
        lines.extend(
            [
                "## Primary finding",
                "",
                f"The production output directory has **{out_dir}** return rows while the matrix validation run has **{matrix_r3}**.",
                "Metrics that read `strategy_daily_returns.csv` from `model_output_sp500_pit_t212/` are **not** comparable",
                "to matrix siblings (R0, M1, R2, …) without re-aligning calendars.",
                "",
                "## Likely cause",
                "",
                "1. A later backtest (e.g. `R5_rank_only_train5` or extended sample) wrote into `model_output_sp500_pit_t212/`.",
                "2. `latest_validated_run.json` may still declare `variant_id=R3` while `run_id` references an R5 run (pointer split).",
                "3. `aa_challenger_eval.resolve_champion_variant()` reads `variant_id` from the pointer first, but",
                "   `build_challenger_report` can attach **metrics from `out_dir`** — mixing folder returns with matrix champion id.",
                "",
                "## Evidence pointers",
                "",
            ]
        )
        for vid in ("R3_w075_q065_noexit", "model_output_sp500_pit_t212"):
            v = by_id.get(vid) or {}
            sha = v.get("returns_sha256")
            sha_short = f"{sha[:16]}…" if isinstance(sha, str) and len(sha) >= 16 else "-"
            lines.append(f"- **{vid}:** `{v.get('run_dir', '-')}` · n_days={v.get('n_days')} · sha256={sha_short}")
        lines.append("")
        if r5_dirs:
            lines.append("## R5 validation dirs")
            lines.append("")
            for v in r5_dirs:
                lines.append(
                    f"- `{v.get('variant_id')}`: n_days={v.get('n_days')} · integrity={v.get('integrity', {}).get('status')}"
                )
            lines.append("")
    elif out_dir and matrix_r3 is None:
        lines.extend(
            [
                "## Primary finding",
                "",
                f"`model_output_sp500_pit_t212` has **{out_dir}** return days; matrix R3 run dir is **not present locally**",
                f"(validation_runs gitignored={inv_git}). Embedded reports cite R3 with **1860** days — treat output dir as **contaminated or extended** until Phase B pointer repair.",
                "",
            ]
        )
    else:
        lines.append("## Primary finding")
        lines.append("")
        lines.append("Insufficient local return files to compare calendars (see variant_run_inventory.json).")
        lines.append("")

    # P11 cost stress reference
    p11 = root / "docs/phases/P11_STATISTICAL_RESEARCH_VALIDATION/cost_stress_comparison.csv"
    if p11.is_file():
        lines.extend(
            [
                "## P11 cost_stress_comparison.csv (label check)",
                "",
                "Rows labeled `R3_w075_q065_noexit` in P11 show Sharpe ~0.883 and MaxDD ~−54% — consistent with",
                "**longer/different** return series (same order of magnitude as `model_output` ~2450 days), **not** matrix R3 (~1860 days, MaxDD ~−26%).",
                "",
                "| Source | Approx. n_days | Typical MaxDD (from reports) |",
                "|--------|----------------|----------------------------|",
                f"| Matrix R3 | {matrix_r3 or '?'} | ~−26% |",
                f"| model_output_sp500_pit_t212 | {out_dir or '?'} | varies |",
                "| P11 row R3 (cost stress) | ~2450 (implicit) | ~−54% |",
                "",
            ]
        )

    lines.extend(
        [
            "## Phase B remediation (forward reference)",
            "",
            "- Point `latest_validated_run.json` `run_dir` / `run_id` to the matrix PASS R3 folder only.",
            "- Stop writing non-R3 variant full backtests into `model_output_sp500_pit_t212/`.",
            "- Rebuild `challenger_report` from `validation_runs/` only for champion metrics.",
            "",
        ]
    )
    return "\n".join(lines)


def build_governance_baseline(root: Path) -> Dict[str, Any]:
    auth_path = root / "control/authorization/current_authorization_status.json"
    auth = {}
    if auth_path.is_file():
        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
        except Exception:
            auth = {"error": "parse_failed"}

    approvals: List[Dict[str, Any]] = []
    for path in sorted(root.glob("EXTERNAL_REVIEW_APPROVAL*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        champion_unchanged = "unchanged" in text.lower() and "champion" in text.lower()
        mentions_r3 = "R3_w075_q065_noexit" in text
        mentions_r5 = "R5_rank_only_train5" in text
        approvals.append(
            {
                "file": path.name,
                "sha256": _sha256_file(path),
                "champion_unchanged_wording": champion_unchanged,
                "mentions_R3_w075_q065_noexit": mentions_r3,
                "mentions_R5_rank_only_train5": mentions_r5,
            }
        )

    quarantine = root / "control/quarantine/g0r_r5_unauthorized/operational_champion_r5_claim.json"
    q = {}
    if quarantine.is_file():
        try:
            q = json.loads(quarantine.read_text(encoding="utf-8"))
        except Exception:
            q = {"error": "parse_failed"}

    locked = resolve_locked_champion(root)
    aligned = str(auth.get("authoritative_champion") or "") == locked

    return {
        "schema_version": 1,
        "phase": "A4",
        "generated_at_utc": _utc_now(),
        "locked_champion_code": locked,
        "authorization_status_path": str(auth_path.relative_to(root)).replace("\\", "/"),
        "authorization_snapshot": auth,
        "authoritative_champion_matches_locked": aligned,
        "external_review_approvals_root": approvals,
        "quarantined_r5_claim": q,
        "conflicts_from_authorization": list(auth.get("conflict_details") or []),
    }


def run_phase_a(root: Path) -> Dict[str, Any]:
    root = Path(root)
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    a1 = build_champion_pointer_audit(root)
    a1_path = evidence_dir / "champion_pointer_audit.json"
    atomic_write_json(a1_path, a1)

    a2 = build_variant_run_inventory(root)
    a2_path = evidence_dir / "variant_run_inventory.json"
    atomic_write_json(a2_path, a2)

    a3_md = build_calendar_mismatch_report(root, a2)
    a3_path = evidence_dir / "calendar_mismatch_root_cause.md"
    atomic_write_text(a3_path, a3_md)

    a4 = build_governance_baseline(root)
    a4_path = evidence_dir / "governance_baseline.json"
    atomic_write_json(a4_path, a4)

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(root)).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    summary = {
        "schema_version": 1,
        "phase": "A",
        "generated_at_utc": _utc_now(),
        "status": "COMPLETE",
        "outputs": {
            "A1_champion_pointer_audit": _rel(a1_path),
            "A2_variant_run_inventory": _rel(a2_path),
            "A3_calendar_mismatch_root_cause": _rel(a3_path),
            "A4_governance_baseline": _rel(a4_path),
        },
        "conflict_count": len(a1.get("conflicts") or []),
        "variants_inventoried": a2.get("variants_found"),
        "variants_missing_local_dir": a2.get("variants_missing_local_dir"),
        "validation_runs_present": a2.get("validation_runs_present"),
    }
    summary_path = evidence_dir / "phase_a_truth_inventory_summary.json"
    atomic_write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Champion evidence Phase A inventory")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    summary = run_phase_a(args.root)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("status") == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
