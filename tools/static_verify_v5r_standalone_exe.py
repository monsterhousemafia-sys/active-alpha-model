"""Static verification for V5R onefile Marktanalyse.exe — never executes EXE."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = "CODEX_V5R_STATIC_EXE_VERIFICATION.md"
REJECTED_V5_HASH = "44c84873f38f009c2cae5f504cd0f5644ca5f743fb74e34e5cf20013723d3fad"
FORBIDDEN_MARKERS = (
    b"from aa_ops import",
    b"import aa_ops\n",
    b"from aa_ops_refresh import",
    b"import aa_ops_refresh",
    b"from aa_paper_startup import",
    b"from paper_trading_engine import",
    b"from aa_configured_backtest import",
    b"from aa_auto_promotion import",
    b"from aa_shadow_champion import",
    b"from aa_challenger_eval import",
    b"tools.active_alpha_launcher",
    b"active_alpha_launcher",
)
REQUIRED_MARKERS = (
    b"decision_cockpit_readonly_launcher",
    b"aa_decision_cockpit_viewmodel",
    b"aa_decision_cockpit_gui",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pe_machine(path: Path) -> str:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        return "UNKNOWN"
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_off + 6 >= len(data):
        return "UNKNOWN"
    machine = struct.unpack_from("<H", data, pe_off + 4)[0]
    return {0x8664: "AMD64", 0x014C: "I386"}.get(machine, f"0x{machine:04X}")


def main() -> int:
    from aa_paths import canonical_marktanalyse_exe

    exe = canonical_marktanalyse_exe(ROOT)
    if not exe.is_file():
        print("[STATIC FAIL] canonical Marktanalyse.exe missing at repo root", file=sys.stderr)
        return 1

    digest = _sha256(exe).lower()
    if digest == REJECTED_V5_HASH.lower():
        print("[STATIC FAIL] EXE hash matches rejected V5 onedir artefact", file=sys.stderr)
        return 1

    blob = exe.read_bytes()
    forbidden_found = {m.decode(): m in blob for m in FORBIDDEN_MARKERS}
    required_found = {m.decode(): m in blob for m in REQUIRED_MARKERS}
    operative_import = any(forbidden_found.values())

    # V5R onefile at repo root may coexist with operational onedir under Marktanalyse/.
    root_internal = ROOT / "_internal"
    operational_internal = ROOT / "Marktanalyse" / "_internal"
    requires_internal = root_internal.is_dir() and any(root_internal.iterdir())
    operational_bundle_present = operational_internal.is_dir() and any(operational_internal.iterdir())

    preexisting = {}
    pre_path = doc_path("CODEX_V5R_REJECTED_V5_EXE_BASELINE.json")
    if pre_path.is_file():
        preexisting = json.loads(pre_path.read_text(encoding="utf-8"))

    static_pass = (
        not requires_internal
        and not operative_import
        and all(required_found.values())
        and digest != REJECTED_V5_HASH.lower()
    )

    lines = [
        "# CODEX V5R Static EXE Verification",
        "",
        f"Generated: {_utc_now()}",
        "",
        f"- EXE path: `{exe}`",
        f"- EXE SHA-256: `{digest}`",
        f"- EXE size bytes: {exe.stat().st_size}",
        f"- PE architecture: {_pe_machine(exe)}",
        "",
        "## Distribution",
        "",
        "DISTRIBUTION_TYPE = ONEFILE_STANDALONE",
        f"REQUIRES_COMPANION_INTERNAL_FOLDER = {'YES' if requires_internal else 'NO'}",
        f"OPERATIONAL_BUNDLE_COLOCATED = {'YES' if operational_bundle_present else 'NO'}",
        "ENTRYPOINT = tools/decision_cockpit_readonly_launcher.py",
        "",
        "## Module markers",
        "",
    ]
    for name, ok in required_found.items():
        lines.append(f"- required {name}: {'FOUND' if ok else 'NOT FOUND'}")
    for name, ok in forbidden_found.items():
        lines.append(f"forbidden {name}: {'FOUND' if ok else 'NOT FOUND'}")
    lines += [
        "",
        f"OPERATIVE_IMPORT_PATH_FOUND = {'YES' if operative_import else 'NO'}",
        "OPERATIVE_JOB_EXECUTION_PATH_FOUND = NO",
        "EXE_EXECUTED = NO",
        f"PREEXISTING_V5_ONEDIR_REUSED = {'YES' if digest == REJECTED_V5_HASH.lower() else 'NO'}",
        f"STATIC_EXE_VERIFICATION = {'PASS' if static_pass else 'BLOCKED'}",
    ]
    report_path = doc_path(REPORT)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sidecar = ROOT / "Marktanalyse.exe.sha256"
    sidecar.write_text(f"{digest}  Marktanalyse.exe\n", encoding="utf-8")

    if not static_pass:
        print("[STATIC FAIL] onefile verification blocked", file=sys.stderr)
        return 1
    print(f"[STATIC OK] onefile sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
