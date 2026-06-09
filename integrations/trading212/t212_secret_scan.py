"""Secret scan for packages and build artifacts."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List

FORBIDDEN_PATTERNS = (
    re.compile(r"authorization\s*:\s*basic\s+", re.I),
    re.compile(r"api_secret\s*[:=]\s*['\"]?[a-zA-Z0-9+/=]{8,}", re.I),
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", re.I),
    re.compile(r"password\s*[:=]\s*['\"][^'\"]{4,}['\"]", re.I),
)


def scan_text(text: str) -> List[str]:
    hits = []
    for pat in FORBIDDEN_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits


def scan_file(path: Path) -> List[str]:
    try:
        raw = path.read_bytes()
    except OSError:
        return ["UNREADABLE"]
    if b"\x00" in raw[:8192]:
        return []
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return []
    return scan_text(text)


def scan_directory(root: Path, *, globs: Iterable[str] = ("**/*",)) -> Dict[str, Any]:
    root = Path(root)
    findings: List[Dict[str, str]] = []
    for pattern in globs:
        for p in root.glob(pattern):
            if not p.is_file():
                continue
            if "__pycache__" in p.parts or p.suffix == ".pyc":
                findings.append({"path": str(p.relative_to(root)), "issue": "BYTECODE"})
                continue
            hits = scan_file(p)
            for h in hits:
                findings.append({"path": str(p.relative_to(root)), "issue": h[:80]})
    secret_hits = [f for f in findings if f.get("issue") != "BYTECODE"]
    bytecode_hits = [f for f in findings if f.get("issue") == "BYTECODE"]
    return {
        "passed": len(secret_hits) == 0 and len(bytecode_hits) == 0,
        "secret_findings": secret_hits,
        "bytecode_findings": bytecode_hits,
        "scanned_root": str(root),
    }


def scan_zip(zip_path: Path) -> Dict[str, Any]:
    findings: List[Dict[str, str]] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if "__pycache__" in name or name.endswith(".pyc"):
                findings.append({"path": name, "issue": "BYTECODE"})
                continue
            if info.file_size > 2_000_000:
                continue
            try:
                text = zf.read(info.filename).decode("utf-8", errors="ignore")
            except Exception:
                continue
            for h in scan_text(text):
                findings.append({"path": name, "issue": h[:80]})
    secret_hits = [f for f in findings if f.get("issue") != "BYTECODE"]
    return {
        "passed": len(secret_hits) == 0 and not any(f["issue"] == "BYTECODE" for f in findings),
        "findings": findings,
        "zip_sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest() if zip_path.is_file() else None,
    }
