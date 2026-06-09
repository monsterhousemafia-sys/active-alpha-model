"""Repair latest_validated_run.json when runs/<id> was deleted but out_dir artifacts remain."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out-dir", type=str, default="")
    args = p.parse_args()
    root = Path(args.root)
    from aa_config_env import load_aa_env
    from aa_ops_validation import validate_analytical_integrity
    from aa_run_provenance import published_backtest_artifacts_ok
    from aa_safe_io import atomic_write_json

    env = load_aa_env(root)
    rel = args.out_dir or env.get("AA_BACKTEST_OUT_DIR") or "model_output_sp500_pit_t212"
    out_dir = Path(rel) if Path(rel).is_absolute() else root / rel
    pointer = out_dir / "latest_validated_run.json"
    if not pointer.is_file():
        print(f"[ERROR] Fehlt: {pointer}")
        return 1
    pub_ok, pub_reason = published_backtest_artifacts_ok(out_dir)
    if not pub_ok:
        print(f"[ERROR] Publizierte Artefakte unvollständig: {pub_reason}")
        return 1
    doc = json.loads(pointer.read_text(encoding="utf-8"))
    old_run = str(doc.get("run_dir", ""))
    doc["run_dir"] = str(out_dir.resolve())
    doc["repaired_from_run_dir"] = old_run
    doc["repair_note"] = "Run-Ordner fehlte; Pointer auf out_dir mit PASS-Artefakten gesetzt."
    ir = out_dir / "integrity_report.json"
    if ir.is_file():
        try:
            integrity = json.loads(ir.read_text(encoding="utf-8"))
            rid = str(integrity.get("run_id") or "").strip()
            if rid:
                doc["run_id"] = rid
        except Exception:
            pass
    atomic_write_json(pointer, doc)
    ok, reason, run_id = validate_analytical_integrity(out_dir)
    print(f"[OK] Pointer repariert -> {out_dir}")
    print(f"     validate_analytical_integrity: {ok} ({reason}) run_id={run_id}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
