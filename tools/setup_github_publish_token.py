#!/usr/bin/env python3
"""Create control/secrets/github_publish_token (interactive, editor, or stdin)."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "control" / "secrets" / "github_publish_token"


def _save_token(token: str) -> int:
    token = token.strip()
    if not token or (not token.startswith("ghp_") and not token.startswith("github_pat_")):
        print("Abbruch: kein gültiger Token-Prefix (ghp_ oder github_pat_).", file=sys.stderr)
        return 2
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(token + "\n", encoding="utf-8")
    TARGET.chmod(0o600)
    print(f"[OK] Gespeichert: {TARGET}")
    print("Danach: bash tools/publish_public_access.sh")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub publish token → control/secrets/")
    parser.add_argument(
        "--editor",
        action="store_true",
        help="Token in Cursor/Editor in diese Datei einfügen, speichern, dann erneut ohne --editor",
    )
    parser.add_argument(
        "--from-stdin",
        action="store_true",
        help="Token aus stdin (eine Zeile), z.B. aus Editor-Datei",
    )
    args = parser.parse_args()

    if args.editor:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        if not TARGET.exists():
            TARGET.write_text("# Token in NÄCHSTE Zeile einfügen (ghp_...), diese Zeile löschen, speichern.\n", encoding="utf-8")
            TARGET.chmod(0o600)
        print(f"1) In Cursor öffnen: {TARGET}")
        print("2) Token in neue Zeile einfügen (nur ghp_..., keine Anführungszeichen)")
        print("3) Speichern (Strg+S)")
        print("4) Dann: .venv/bin/python3 tools/setup_github_publish_token.py --from-stdin < control/secrets/github_publish_token")
        print("   Oder erneut: bash tools/publish_public_access.sh (liest die Datei direkt)")
        return 0

    if args.from_stdin or not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("ghp_") or line.startswith("github_pat_"):
                return _save_token(line)
        print("Abbruch: keine Token-Zeile in stdin.", file=sys.stderr)
        return 2

    print("GitHub Personal Access Token (ghp_...) — Eingabe ist verborgen.")
    print("Token: https://github.com/settings/tokens/new  Scope: repo")
    print("Falls Terminal-Eingabe nicht geht: tools/setup_github_publish_token.py --editor")
    token = getpass.getpass("Token: ").strip()
    return _save_token(token)


if __name__ == "__main__":
    raise SystemExit(main())
