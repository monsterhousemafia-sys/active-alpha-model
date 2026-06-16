#!/usr/bin/env python3
"""Preflight scan before publishing this repo to a public Git host."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "publish_public_git_preflight_latest.json"

BLOCK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_ip", re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b")),
    ("jwt_token", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "literal_secret_assignment",
        re.compile(
            r"(?i)(?:api[_-]?key|password|tunnel[_-]?token)\s*=\s*['\"][^'\"#\s]{12,}['\"]"
        ),
    ),
    ("cloudflare_token_env", re.compile(r"AA_CLOUDFLARE_TUNNEL_TOKEN\s*=\s*eyJ")),
)

WARN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("home_path", re.compile(r"/home/[a-z0-9_-]+/")),
    ("windows_user_path", re.compile(r"[A-Z]:\\Users\\[^\\]+\\")),
    ("trycloudflare_url", re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")),
)

SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "model_output",
    "paper_output",
    "validation_runs",
    "dist",
    "build",
    "evidence/archive",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_tracked_and_candidates(root: Path) -> list[Path]:
    paths: list[Path] = []
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        status = None
    if status is not None and status.returncode == 0:
        for line in status.stdout.splitlines():
            if len(line) < 4:
                continue
            rel = line[3:].strip().strip('"')
            if " -> " in rel:
                rel = rel.split(" -> ", 1)[1]
            paths.append(root / rel)
        return paths

    try:
        from dulwich.repo import Repo

        repo = Repo(str(root))
        idx = repo.open_index()
        for p, _entry in idx.iteritems():
            path = root / p.decode()
            if path.is_file():
                paths.append(path)
        if paths:
            return paths
    except Exception:
        pass

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        paths.append(p)
    return paths


def _scan_file(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".zip", ".parquet", ".feather"}:
        return [], []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], []
    if len(text) > 2_000_000:
        return [], []
    blocks: list[dict[str, str]] = []
    warns: list[dict[str, str]] = []
    for label, pattern in BLOCK_PATTERNS:
        for match in pattern.finditer(text):
            blocks.append({"pattern": label, "snippet": match.group(0)[:120]})
            if len(blocks) >= 5:
                return blocks, warns
    for label, pattern in WARN_PATTERNS:
        for match in pattern.finditer(text):
            warns.append({"pattern": label, "snippet": match.group(0)[:120]})
            if len(warns) >= 3:
                break
    return blocks, warns


def run_preflight(root: Path | None = None) -> dict:
    root = root or ROOT
    block_findings: list[dict[str, object]] = []
    warn_findings: list[dict[str, object]] = []
    for path in sorted(_git_tracked_and_candidates(root), key=lambda p: str(p)):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel.startswith("evidence/archive/"):
            continue
        if rel in {".gitignore", "tools/publish_public_git_preflight.py", "control/server.env.example"}:
            continue
        if rel.startswith("tests/"):
            blocks, warns = _scan_file(path)
            blocks = [h for h in blocks if h["pattern"] != "private_ip"]
        else:
            blocks, warns = _scan_file(path)
        if blocks:
            block_findings.append({"path": rel, "hits": blocks})
        elif warns:
            warn_findings.append({"path": rel, "hits": warns})

    ok = len(block_findings) == 0
    doc = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "ok": ok,
        "block_count": len(block_findings),
        "warn_count": len(warn_findings),
        "block_findings": block_findings[:200],
        "warn_findings": warn_findings[:50],
        "headline_de": "Preflight OK — keine kritischen Leaks"
        if ok
        else f"Preflight BLOCK — {len(block_findings)} Datei(en) mit kritischen Leaks",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def main() -> int:
    doc = run_preflight()
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0 if doc.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
