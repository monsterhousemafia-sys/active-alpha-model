#!/usr/bin/env python3
"""Create control/secrets/github_publish_token (interactive, local only)."""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "control" / "secrets" / "github_publish_token"


def main() -> int:
    print("GitHub Personal Access Token (ghp_...) — Eingabe ist verborgen.")
    print("Token: https://github.com/settings/tokens/new  Scope: repo")
    token = getpass.getpass("Token: ").strip()
    if not token or token.startswith("ghp_") is False and not token.startswith("github_pat_"):
        print("Abbruch: kein gültiger Token-Prefix (ghp_ oder github_pat_).", file=sys.stderr)
        return 2
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(token + "\n", encoding="utf-8")
    TARGET.chmod(0o600)
    print(f"[OK] Gespeichert: {TARGET}")
    print("Danach: bash tools/publish_public_access.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
