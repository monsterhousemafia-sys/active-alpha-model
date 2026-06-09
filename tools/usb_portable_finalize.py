"""USB-Portable: Pfade patchen, Manifest schreiben, Kopie verifizieren."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_KEY_FILES = (
    "USB_WEITERARBEITEN.sh",
    "tools/king_ops.sh",
    "tools/ai_kernel.py",
    "control/prediction_operations.json",
    "requirements_active_alpha.txt",
    "control/usb_pip_freeze.txt",
)

_CONTROL_GLOBS = ("control/*.json", "control/**/*.json")


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


def _atomic_json(path: Path, doc: Dict[str, Any]) -> None:
    from aa_safe_io import atomic_write_json

    atomic_write_json(path, doc)


def discover_old_roots(root: Path, source_root: Path | None) -> List[str]:
    roots: List[str] = []
    if source_root:
        roots.append(str(source_root.resolve()))
    cont = _load_json(root / "control/r3_continuity.json")
    pr = str(cont.get("project_root") or "").strip()
    if pr and pr not in roots:
        roots.append(pr)
    return roots


def patch_control_paths(root: Path, *, new_root: Path, old_roots: List[str]) -> List[str]:
    """Ersetzt bekannte absolute Projekt-Pfade in control/*.json."""
    root = Path(root).resolve()
    new_root = Path(new_root).resolve()
    new_s = str(new_root)
    changed: List[str] = []
    for pattern in _CONTROL_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.name in ("usb_deploy_manifest.json", "usb_portable.json"):
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            updated = raw
            for old in old_roots:
                if old and old in updated:
                    updated = updated.replace(old, new_s)
            if updated != raw:
                path.write_text(updated, encoding="utf-8")
                changed.append(str(path.relative_to(root)))
    return changed


def write_portable_manifest(
    root: Path,
    *,
    source_root: Path,
    deploy_target: str,
    excludes: Tuple[str, ...],
) -> Dict[str, Any]:
    root = Path(root)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "deployed_at_utc": _utc_now(),
        "source_project_root": str(source_root.resolve()),
        "deploy_target": deploy_target,
        "project_root": str(root.resolve()),
        "rsync_excludes": list(excludes),
        "recommended_first_run": "./USB_WEITERARBEITEN.sh --full-setup",
        "recommended_install_local": "~/active_alpha_model",
        "note_de": (
            "Nach USB-Start: --full-setup spiegelt nach ext4, patcht Pfade, "
            "installiert systemd-Timer neu, prüft venv und king_ops."
        ),
    }
    _atomic_json(root / "control/usb_deploy_manifest.json", doc)
    _atomic_json(
        root / "control/usb_portable.json",
        {
            "schema_version": 1,
            "portable": True,
            "project_root": str(root.resolve()),
            "source_project_root": str(source_root.resolve()),
            "updated_at_utc": _utc_now(),
        },
    )
    return doc


def verify_portable_copy(root: Path) -> Dict[str, Any]:
    root = Path(root).resolve()
    missing = [rel for rel in _KEY_FILES if not (root / rel).is_file()]
    py = root / ".venv/bin/python3"
    venv_ok = False
    venv_error = ""
    if py.is_file():
        try:
            subprocess.run(
                [str(py), "-c", "import pandas, numpy, yaml"],
                check=True,
                capture_output=True,
                timeout=60,
            )
            venv_ok = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            venv_error = str(exc)[:120]
    else:
        venv_error = "missing .venv/bin/python3"
    ok = not missing and venv_ok
    return {
        "ok": ok,
        "project_root": str(root),
        "missing_files": missing,
        "venv_ok": venv_ok,
        "venv_error": venv_error or None,
        "pip_freeze_lines": sum(
            1 for _ in (root / "control/usb_pip_freeze.txt").open(encoding="utf-8")
        )
        if (root / "control/usb_pip_freeze.txt").is_file()
        else 0,
    }


def finalize_usb_copy(
    dest: Path,
    *,
    source_root: Path,
    deploy_target: str,
    excludes: Tuple[str, ...],
) -> Dict[str, Any]:
    dest = Path(dest).resolve()
    old_roots = discover_old_roots(dest, source_root)
    patched = patch_control_paths(dest, new_root=dest, old_roots=old_roots)
    manifest = write_portable_manifest(
        dest, source_root=source_root, deploy_target=deploy_target, excludes=excludes
    )
    verify = verify_portable_copy(dest)
    return {"manifest": manifest, "patched_files": patched, "verify": verify}


def main(argv: List[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if args and args[0] == "--verify-only":
        if len(args) < 2:
            print("Usage: usb_portable_finalize.py --verify-only DEST", file=sys.stderr)
            return 2
        verify = verify_portable_copy(Path(args[1]))
        print(json.dumps(verify, ensure_ascii=False, indent=2))
        return 0 if verify.get("ok") else 1
    if len(args) < 2:
        print(
            "Usage: usb_portable_finalize.py DEST SOURCE_ROOT [label] | --verify-only DEST",
            file=sys.stderr,
        )
        return 2
    dest = Path(args[0])
    source = Path(args[1])
    label = args[2] if len(args) > 2 else str(dest.parent)
    excludes = (
        "__pycache__/",
        ".pytest_cache/",
        "robustness_results_trading212\\_shared_cache/",
        "*.sock",
    )
    out = finalize_usb_copy(dest, source_root=source, deploy_target=label, excludes=excludes)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["verify"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
