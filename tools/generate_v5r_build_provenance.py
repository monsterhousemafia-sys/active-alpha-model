"""Generate static V5R build provenance baked into release EXE at build time."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATED_SOURCE_BASE = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"
BUILD_SCOPE = "V5R_NEUTRAL_READ_ONLY_RELEASE"
RELEASE_SNAPSHOT_SCOPE = "V5R_READ_ONLY_NEUTRAL"
MODULE_PATH = ROOT / "aa_v5r_build_provenance.py"
JSON_PATH = ROOT / "build" / "decision_cockpit" / "v5r_build_provenance.json"
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_build_source_commit(root: Path | None = None) -> str:
    root = root or ROOT
    if GIT.is_file():
        proc = subprocess.run(
            [str(GIT), "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        commit = (proc.stdout or "").strip()
        if proc.returncode == 0 and commit:
            return commit
    return "UNKNOWN"


def build_provenance_dict(*, root: Path | None = None) -> dict:
    commit = resolve_build_source_commit(root)
    return {
        "build_source_commit": commit,
        "validated_source_base": VALIDATED_SOURCE_BASE,
        "build_scope": BUILD_SCOPE,
        "release_snapshot_scope": RELEASE_SNAPSHOT_SCOPE,
        "generated_at_utc": _utc_now(),
    }


def write_build_provenance(*, root: Path | None = None) -> dict:
    root = root or ROOT
    payload = build_provenance_dict(root=root)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    module_src = f'''"""Auto-generated at V5R release build — do not edit manually."""
from __future__ import annotations

BUILD_SOURCE_COMMIT = {payload["build_source_commit"]!r}
VALIDATED_SOURCE_BASE = {payload["validated_source_base"]!r}
BUILD_SCOPE = {payload["build_scope"]!r}
RELEASE_SNAPSHOT_SCOPE = {payload["release_snapshot_scope"]!r}
GENERATED_AT_UTC = {payload["generated_at_utc"]!r}
'''
    MODULE_PATH.write_text(module_src, encoding="utf-8")
    return payload


def main() -> int:
    payload = write_build_provenance()
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
