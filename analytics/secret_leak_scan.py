"""Scannt Projekt auf ausgelaufene Geheimnisse (JWT, Tokens in Logs)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json
from analytics.secret_redaction import redact_text

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_SCAN_ROOTS = (
    "evidence",
    "live_pilot",
    "control",
    "logs",
)
_SKIP_NAMES = {
    "tunnel_token.vault",
    ".tunnel_vault_key",
    "cloudflare_tunnel.token",
}
_EVIDENCE_REL = Path("evidence/secret_leak_scan_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def scan_for_leaks(root: Path, *, max_files: int = 400) -> Dict[str, Any]:
    root = Path(root)
    hits: List[Dict[str, Any]] = []
    scanned = 0
    for rel_root in _SCAN_ROOTS:
        base = root / rel_root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or scanned >= max_files:
                break
            if path.name in _SKIP_NAMES or path.suffix in {".vault", ".pem"}:
                continue
            if "secrets" in path.parts and path.name.startswith("."):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            scanned += 1
            for match in _JWT_RE.finditer(text):
                hits.append(
                    {
                        "file": str(path.relative_to(root)),
                        "preview": redact_text(text[max(0, match.start() - 20) : match.end() + 20]),
                    }
                )
                break

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": len(hits) == 0,
        "files_scanned": scanned,
        "leak_count": len(hits),
        "hits": hits[:30],
        "headline_de": (
            "Keine Token-Leaks gefunden"
            if not hits
            else f"{len(hits)} mögliche Leak(s) — sofort bereinigen"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
