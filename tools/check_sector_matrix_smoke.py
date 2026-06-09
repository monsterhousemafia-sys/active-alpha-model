"""S7.4 read-only: max_unknown_sector_weight <= max_sector on R3 run artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_REL = "evidence/sector_reference_matrix_smoke_s7.json"


def _resolve_r3_run_dir(root: Path) -> Path | None:
    pointer = root / "model_output_sp500_pit_t212" / "latest_validated_run.json"
    if pointer.is_file():
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
            run_dir = Path(str(data.get("run_dir") or ""))
            if run_dir.is_dir():
                return run_dir
        except (json.JSONDecodeError, OSError):
            pass
    runs = root / "runs"
    if not runs.is_dir():
        return None
    candidates = sorted(
        (p for p in runs.iterdir() if p.is_dir() and "R3_w075" in p.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def check_matrix_smoke(root: Path, *, max_sector: float = 0.55) -> dict:
    import pandas as pd

    from aa_sector_reference import lookup_sector

    root = root.resolve()
    run_dir = _resolve_r3_run_dir(root)
    result: dict = {
        "schema_version": 1,
        "phase": "S7.4",
        "max_sector_cap": max_sector,
        "run_dir": str(run_dir) if run_dir else None,
        "source": None,
        "max_unknown_sector_weight": None,
        "pass": False,
    }
    if run_dir and (run_dir / "constraint_binding_history.csv").is_file():
        cb = pd.read_csv(run_dir / "constraint_binding_history.csv")
        max_u = float(cb["unknown_sector_weight"].max())
        result.update(
            {
                "source": "constraint_binding_history.csv",
                "max_unknown_sector_weight": max_u,
                "rebalances": int(len(cb)),
                "pass": max_u <= max_sector,
            }
        )
        return result

    port = root / "model_output_sp500_pit_t212" / "latest_target_portfolio.csv"
    if port.is_file():
        df = pd.read_csv(port)
        wcol = "target_weight" if "target_weight" in df.columns else "weight"
        if wcol in df.columns and "ticker" in df.columns:
            unknown_w = 0.0
            rows = []
            for _, row in df.iterrows():
                tk = str(row["ticker"]).upper().strip()
                w = float(row[wcol] or 0.0)
                sec = lookup_sector(tk, root=root)
                if sec == "Unknown":
                    unknown_w += w
                rows.append({"ticker": tk, "weight": w, "sector": sec})
            result.update(
                {
                    "source": "latest_target_portfolio.csv",
                    "max_unknown_sector_weight": unknown_w,
                    "portfolio_rows": rows,
                    "pass": unknown_w <= max_sector,
                }
            )
            return result

    result["error"] = "no_run_artifacts_or_portfolio"
    return result


def main() -> int:
    from aa_safe_io import atomic_write_json

    p = argparse.ArgumentParser(description="S7.4 matrix smoke (read-only).")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--max-sector", type=float, default=0.55)
    p.add_argument("--write-evidence", action="store_true")
    args = p.parse_args()
    root = args.root.resolve()
    report = check_matrix_smoke(root, max_sector=args.max_sector)
    if args.write_evidence:
        atomic_write_json(root / EVIDENCE_REL, report)
        print(f"Evidence: {root / EVIDENCE_REL}")
    src = report.get("source") or report.get("error", "—")
    max_u = report.get("max_unknown_sector_weight")
    print(f"source: {src}")
    print(f"max_unknown_sector_weight: {max_u}")
    print(f"pass: {report.get('pass')}")
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
