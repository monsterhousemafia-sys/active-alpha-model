"""Operator-Segnung (Abnahme) der verbesserten USB-Portable-Kopie — fail-closed."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/usb_portable_seal_policy.json")
_EVIDENCE_REL = Path("evidence/usb_portable_seal_latest.json")
_MANIFEST = Path("control/usb_deploy_manifest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_safety_flags(root: Path) -> Dict[str, Any]:
    try:
        from analytics.spread_secure_ops import _check_safety_flags

        doc = _check_safety_flags(root)
        return {
            "check": "safety_flags",
            "pass": bool(doc.get("ok")),
            "detail": doc.get("headline_de") or doc.get("detail_de") or "—",
        }
    except Exception as exc:
        return {"check": "safety_flags", "pass": False, "detail": str(exc)[:120]}


def _run_portable_tests(root: Path) -> Dict[str, Any]:
    py = root / ".venv/bin/python3"
    if not py.is_file():
        return {"check": "portable_tests", "pass": False, "detail": "venv fehlt"}
    try:
        proc = subprocess.run(
            [
                str(py),
                "-m",
                "pytest",
                "tests/test_usb_portable.py",
                "-q",
                "--tb=no",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return {
            "check": "portable_tests",
            "pass": proc.returncode == 0,
            "detail": (proc.stdout or proc.stderr or "").strip()[-120:],
        }
    except Exception as exc:
        return {"check": "portable_tests", "pass": False, "detail": str(exc)[:120]}


def verify_usb_portable_seal(root: Path) -> Dict[str, Any]:
    """Fail-closed Checks vor Operator-Segnung."""
    root = Path(root).resolve()
    checks: List[Dict[str, Any]] = []
    blockers: List[str] = []

    from tools.usb_portable_finalize import verify_portable_copy

    v = verify_portable_copy(root)
    checks.append(
        {
            "check": "verify_portable_copy",
            "pass": bool(v.get("ok")),
            "detail": f"venv={v.get('venv_ok')} missing={v.get('missing_files')}",
        }
    )

    manifest = _load_json(root / _MANIFEST)
    checks.append(
        {
            "check": "usb_deploy_manifest",
            "pass": bool(manifest.get("deployed_at_utc")),
            "detail": manifest.get("deploy_target") or manifest.get("project_root") or "—",
        }
    )

    freeze_lines = 0
    freeze_path = root / "control/usb_pip_freeze.txt"
    if freeze_path.is_file():
        freeze_lines = sum(1 for _ in freeze_path.open(encoding="utf-8"))
    checks.append(
        {
            "check": "usb_pip_freeze",
            "pass": freeze_lines >= 20,
            "detail": f"{freeze_lines} Pakete",
        }
    )

    autostart = _load_json(root / "control/usb_portable_autostart.json")
    checks.append(
        {
            "check": "usb_autostart_policy",
            "pass": bool(autostart.get("enabled")) and bool(autostart.get("auto_install_local")),
            "detail": f"install_dest={autostart.get('install_dest')}",
        }
    )

    checks.append(_check_safety_flags(root))
    checks.append(_run_portable_tests(root))

    for c in checks:
        if not c.get("pass"):
            blockers.append(str(c.get("check")))

    ok = not blockers
    return {
        "pass": ok,
        "checks": checks,
        "blockers": blockers,
        "project_root": str(root),
        "verified_at_utc": _utc_now(),
    }


def bless_usb_portable_copy(
    root: Path,
    *,
    blessed_by_de: str = "Operator",
    note_de: str = "",
    persist: bool = True,
) -> Dict[str, Any]:
    """Segnet die Portable-Kopie ab — schreibt evidence/usb_portable_seal_latest.json."""
    root = Path(root).resolve()
    policy = _load_json(root / _POLICY_REL)
    verification = verify_usb_portable_seal(root)
    manifest = _load_json(root / _MANIFEST)

    status = "BLESSED" if verification.get("pass") else "BLOCKED"
    headline = (
        "USB-Kopie gesegnet — portable Abnahme PASS"
        if status == "BLESSED"
        else "USB-Segnung BLOCKIERT — Checks fehlgeschlagen"
    )

    artifact_hashes: Dict[str, str] = {}
    for rel in (
        "control/usb_deploy_manifest.json",
        "control/usb_portable.json",
        "control/usb_portable_autostart.json",
        "USB_WEITERARBEITEN.sh",
        "tools/usb_full_project_deploy.sh",
        "tools/usb_portable_finalize.py",
        "tools/usb_auto_install_local.sh",
        "tools/setup_usb_autostart.sh",
    ):
        h = _sha256_file(root / rel)
        if h:
            artifact_hashes[rel] = h

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "blessed": status == "BLESSED",
        "sealed": status == "BLESSED",
        "headline_de": headline,
        "blessed_at_utc": _utc_now(),
        "blessed_by_de": blessed_by_de,
        "note_de": note_de
        or (
            "Verbesserte USB-Kopie: auto install-local, Spread-Sustain, Manifest, Verify. "
            "Erster Start: ./USB_WEITERARBEITEN.sh --full-setup"
        ),
        "project_root": str(root),
        "source_project_root": manifest.get("source_project_root"),
        "deployed_at_utc": manifest.get("deployed_at_utc"),
        "deploy_target": manifest.get("deploy_target"),
        "governance_invariants_de": policy.get("governance_invariants_de") or [],
        "verification": verification,
        "artifact_hashes": artifact_hashes,
        "first_run_de": "./USB_WEITERARBEITEN.sh --full-setup",
        "autostart_de": "bash tools/king_ops.sh usb-autostart setup",
    }

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
        # Spiegel im Manifest der Kopie
        if manifest:
            manifest["blessed"] = doc["blessed"]
            manifest["blessed_at_utc"] = doc["blessed_at_utc"]
            manifest["blessing_headline_de"] = headline
            atomic_write_json(root / _MANIFEST, manifest)

    return doc
