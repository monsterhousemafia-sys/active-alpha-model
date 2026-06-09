"""Build ZIP packages with manifest derived from actual archive entry names."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_arcname(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel.startswith("/") or ":" in rel.split("/")[0]:
        raise ValueError(f"ABSOLUTE_OR_DRIVE_PATH_NOT_ALLOWED:{path}")
    return rel


def collect_files(root: Path, include_dirs: Iterable[Path], include_files: Iterable[Path]) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for base in include_dirs:
        bp = root / base
        if not bp.exists():
            continue
        for fp in bp.rglob("*"):
            if fp.is_file() and "__pycache__" not in fp.parts and not fp.name.endswith(".pyc"):
                arc = _canonical_arcname(fp, root)
                mapping[arc] = fp
    for rel in include_files:
        fp = root / rel if not isinstance(rel, Path) else rel
        if fp.is_file():
            arc = _canonical_arcname(fp, root) if fp.is_relative_to(root) else rel.as_posix()
            mapping[arc] = fp
    return mapping


def build_zip_with_manifest(
    *,
    root: Path,
    zip_path: Path,
    include_dirs: Iterable[Path],
    include_files: Iterable[Path],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (file_hashes_before_zip, zip_entry_hashes_including_zip)."""
    root = Path(root)
    zip_path = Path(zip_path)
    files = collect_files(root, include_dirs, include_files)
    pre_zip_hashes: Dict[str, str] = {}

    if zip_path.is_file():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc, fp in sorted(files.items()):
            pre_zip_hashes[arc] = _sha256_bytes(fp.read_bytes())
            zf.write(fp, arc)

    zip_bytes = zip_path.read_bytes()
    zip_digest = _sha256_bytes(zip_bytes)
    entry_hashes: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"UNSAFE_ZIP_ENTRY:{name}")
            entry_hashes[name] = _sha256_bytes(zf.read(info.filename))

    manifest = dict(entry_hashes)
    manifest[zip_path.name] = zip_digest
    coverage_ok = set(entry_hashes.keys()) == set(pre_zip_hashes.keys())
    return pre_zip_hashes, manifest if coverage_ok else manifest
