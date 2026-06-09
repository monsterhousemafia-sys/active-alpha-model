"""Build codex_sector_reference_automation_review.zip for external handoff (S8)."""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ZIP_NAME = "codex_sector_reference_automation_review.zip"

INCLUDE = [
    "docs/SECTOR_REFERENCE_AUTOMATION_PLAN.md",
    "SECTOR_REFERENCE_AUTOMATION_STATUS.md",
    "AGENTS.md",
    "aa_sector_reference.py",
    "aa_constants.py",
    "aa_universe.py",
    "aa_ops_refresh.py",
    "aa_config_env.py",
    "config/gics_to_coarse.json",
    "sector_reference.csv.example",
    "active_alpha_marktanalyse_os.bat",
    "active_alpha_settings.bat",
    "1_live_daily_sync.bat",
    "analytics/live_trading_operations.py",
    "ui/live_trading_dashboard/service.py",
    "ui/live_trading_dashboard/window.py",
    "ui/interactive_cockpit/services/cockpit_state_service.py",
    "build/decision_cockpit/Marktanalyse.spec",
    "tools/run_sector_reference_phase_s0.py",
    "tools/run_ensure_sector_reference.py",
    "tools/verify_sector_reference_coverage.py",
    "tools/check_sector_matrix_smoke.py",
    "tools/run_sector_reference_rollout_s7.py",
    "tools/run_sector_reference_acceptance_s8.py",
    "tools/seed_sector_reference_from_constants.py",
    "tools/build_sector_reference_review_zip.py",
    "evidence/sector_map_gap_analysis.json",
    "evidence/sector_reference_governance_note.json",
    "evidence/sector_wikipedia_parser_alignment.json",
    "evidence/sector_reference_rollout_summary.json",
    "evidence/sector_reference_matrix_smoke_s7.json",
    "evidence/sector_reference_acceptance_s8.json",
    "evidence/sector_reference_acceptance_s8.md",
    "evidence/sector_reference_refresh_latest.json",
    "tests/test_sector_reference.py",
    "tests/test_sector_reference_phase_s0.py",
    "tests/test_sector_reference_s2.py",
    "tests/test_sector_reference_s3.py",
    "tests/test_sector_reference_s4.py",
    "tests/test_sector_reference_s5.py",
    "tests/test_sector_reference_s6.py",
    "tests/test_sector_reference_s7.py",
    "tests/test_sector_reference_s8.py",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    out_zip = ROOT / ZIP_NAME
    manifest: dict = {"zip": ZIP_NAME, "files": []}
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = ROOT / rel
            if not path.is_file():
                print(f"[SKIP] missing: {rel}")
                continue
            zf.write(path, rel.replace("\\", "/"))
            manifest["files"].append({"path": rel, "sha256": _sha256(path)})
    manifest_path = ROOT / f"{ZIP_NAME}.sha256"
    digest = _sha256(out_zip)
    manifest_path.write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    (ROOT / "evidence" / "sector_reference_review_zip_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"ZIP: {out_zip} ({len(manifest['files'])} files)")
    print(f"SHA256: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
