#!/usr/bin/env python3
"""Push local main branch to GitHub and configure public access (dulwich, no system git)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = (
    "Active Alpha / Marktanalyse Decision Cockpit — read-only research, governance gates, fail-closed safety"
)
TOPICS = (
    "quantitative-finance",
    "decision-support",
    "python",
    "governance",
    "read-only",
    "trading-research",
)


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "active-alpha-publish",
    }


def _api_json(method: str, url: str, token: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=_headers(token), method=method)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}


def configure_public_repo(login: str, repo_name: str, token: str, *, force_public: bool) -> None:
    base = f"https://api.github.com/repos/{login}/{repo_name}"
    patch: Dict[str, Any] = {
        "description": DESCRIPTION,
        "homepage": f"https://github.com/{login}/{repo_name}#readme",
        "has_issues": True,
        "has_projects": False,
        "has_wiki": False,
        "allow_forking": True,
        "visibility": "public",
    }
    if force_public:
        patch["private"] = False
    try:
        _api_json("PATCH", base, token, patch)
    except urllib.error.HTTPError as exc:
        print(f"WARN: Repo-Metadaten: {exc.code} {exc.read().decode(errors='replace')[:120]}", file=sys.stderr)

    try:
        topics_req = urllib.request.Request(
            f"{base}/topics",
            data=json.dumps({"names": list(TOPICS)}).encode(),
            headers={
                **_headers(token),
                "Content-Type": "application/json",
                "Accept": "application/vnd.github.mercy-preview+json",
            },
            method="PUT",
        )
        with urllib.request.urlopen(topics_req, timeout=30):
            pass
    except urllib.error.HTTPError as exc:
        print(f"WARN: Topics: {exc.code}", file=sys.stderr)


def write_public_access_manifest(login: str, repo_name: str, html_url: str) -> None:
    doc = {
        "schema_version": 1,
        "public": True,
        "clone_https": f"https://github.com/{login}/{repo_name}.git",
        "browse_url": html_url,
        "default_branch": "main",
        "headline_de": "Öffentlicher Read-only Mirror — clone, lesen, Tests lokal; keine Secrets im Repo",
    }
    path = ROOT / "control" / "public_github_mirror.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    try:
        from dulwich import porcelain
    except ImportError:
        print("dulwich fehlt: .venv/bin/pip install dulwich", file=sys.stderr)
        return 1

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print(
            "Kein GitHub-Token. Setze GITHUB_TOKEN oder GH_TOKEN.\n"
            "Token: https://github.com/settings/tokens/new (Scope: repo)",
            file=sys.stderr,
        )
        return 2

    repo_name = os.environ.get("AA_PUBLIC_GIT_REPO", "active-alpha-model")
    want_private = os.environ.get("AA_PUBLIC_GIT_PRIVATE", "0") == "1"
    skip_push = os.environ.get("AA_PUBLIC_GIT_SKIP_PUSH", "0") == "1"

    login = _api_json("GET", "https://api.github.com/user", token)["login"]
    url = f"https://github.com/{login}/{repo_name}"

    if not skip_push:
        create_req = urllib.request.Request(
            "https://api.github.com/user/repos",
            data=json.dumps(
                {
                    "name": repo_name,
                    "private": want_private,
                    "description": DESCRIPTION,
                    "auto_init": False,
                }
            ).encode(),
            headers={**_headers(token), "Content-Type": "application/json"},
            method="POST",
        )
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

    if not want_private:
        configure_public_repo(login, repo_name, token, force_public=True)
        print(f"[OK] Öffentlich konfiguriert: {url}")
    else:
        print(f"[OK] Privates Repo: {url}")

    write_public_access_manifest(login, repo_name, url)
    print(f"Clone: git clone https://github.com/{login}/{repo_name}.git")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
