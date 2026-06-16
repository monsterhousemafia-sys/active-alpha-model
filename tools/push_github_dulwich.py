#!/usr/bin/env python3
"""Push local main branch to GitHub using dulwich (no system git required)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    try:
        from dulwich import porcelain
    except ImportError:
        print("dulwich fehlt: .venv/bin/pip install dulwich", file=sys.stderr)
        return 1

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print(
            "Kein GitHub-Token. Setze GITHUB_TOKEN oder GH_TOKEN, dann erneut ausführen.\n"
            "Token erstellen: GitHub → Settings → Developer settings → Fine-grained/classic token (repo).",
            file=sys.stderr,
        )
        return 2

    repo_name = os.environ.get("AA_PUBLIC_GIT_REPO", "active-alpha-model")
    private = os.environ.get("AA_PUBLIC_GIT_PRIVATE", "0") == "1"

    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "active-alpha-publish",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        login = json.loads(resp.read().decode())["login"]

    create_req = urllib.request.Request(
        "https://api.github.com/user/repos",
        data=json.dumps(
            {
                "name": repo_name,
                "private": private,
                "description": "Active Alpha / Marktanalyse Decision Cockpit (read-only, fail-closed)",
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "active-alpha-publish",
        },
        method="POST",
    )
    url = f"https://github.com/{login}/{repo_name}"
    try:
        with urllib.request.urlopen(create_req, timeout=30) as resp:
            url = json.loads(resp.read().decode()).get("html_url") or url
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        if exc.code != 422 or "already exists" not in body:
            print(f"Repo-Erstellung fehlgeschlagen: {exc.code} {body[:200]}", file=sys.stderr)
            return 3

    remote = f"https://x-access-token:{token}@github.com/{login}/{repo_name}.git"
    print(f"Pushing main → {url}")
    porcelain.push(str(ROOT), remote, refspecs=[b"refs/heads/main:refs/heads/main"])
    print(f"[OK] {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
