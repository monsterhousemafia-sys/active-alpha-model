#!/usr/bin/env python3
"""Check GITHUB_TOKEN can push to the public mirror (before publish)."""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = os.environ.get("AA_PUBLIC_GIT_REPO", "active-alpha-model")


def mirror_owner(default: str = "monsterhousemafia-sys") -> str:
    env = os.environ.get("AA_PUBLIC_GIT_OWNER", "").strip()
    if env:
        return env
    manifest = ROOT / "control" / "public_github_mirror.json"
    if manifest.is_file():
        browse = json.loads(manifest.read_text(encoding="utf-8")).get("browse_url", "")
        if "github.com/" in browse:
            return browse.split("github.com/", 1)[1].split("/")[0]
    return default


def probe_write(owner: str, token: str) -> tuple[bool, str]:
    path = ".aa_publish_probe"
    url = f"https://api.github.com/repos/{owner}/{REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "active-alpha-verify",
        "Content-Type": "application/json",
    }
    payload = json.dumps(
        {"message": "publish write probe", "content": base64.b64encode(b"ok").decode("ascii")}
    ).encode()
    req = urllib.request.Request(url, data=payload, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            sha = json.loads(resp.read().decode()).get("content", {}).get("sha")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        return False, f"HTTP {exc.code} {body}"
    if sha:
        del_req = urllib.request.Request(
            url,
            data=json.dumps({"message": "remove probe", "sha": sha}).encode(),
            headers=headers,
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(del_req, timeout=20):
                pass
        except urllib.error.HTTPError:
            pass
    return True, "HTTP 200"


def main() -> int:
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        print("GITHUB_TOKEN fehlt.", file=sys.stderr)
        return 2

    owner = mirror_owner()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "active-alpha-verify",
    }

    req = urllib.request.Request("https://api.github.com/user", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            token_user = json.loads(resp.read().decode())["login"]
            scopes = resp.headers.get("X-OAuth-Scopes", "(fine-grained or none listed)")
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} — Token ungültig oder abgelaufen.", file=sys.stderr)
        return 1

    print(f"Token-User:   {token_user}")
    print(f"Mirror-Owner: {owner}")
    print(f"Ziel-Repo:    https://github.com/{owner}/{REPO}")
    print(f"Scopes:       {scopes}")
    if token_user != owner:
        print("Hinweis: Token-User ≠ Mirror-Owner — du brauchst Schreib-Recht auf das Ziel-Repo.")

    repo_req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{REPO}",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(repo_req, timeout=20) as resp:
            info = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"Mirror {owner}/{REPO}: HTTP {exc.code}", file=sys.stderr)
        return 1

    perms = info.get("permissions") or {}
    print(f"API push:     {'YES' if perms.get('push') else 'NO'}")

    ok, detail = probe_write(owner, token)
    print(f"Write-Probe:  {detail}")
    if ok:
        print("[OK] Token kann auf den Mirror schreiben — bash tools/publish_public_access.sh")
        return 0

    print(
        "\n404/403 beim Schreiben = Token hat kein repo-Recht auf DIESEN Mirror.\n"
        "Fix: https://github.com/settings/tokens/new\n"
        "  • Als monsterhousemafia-sys einloggen\n"
        "  • Generate new token (classic)\n"
        "  • Haken repo (volles Kästchen)\n"
        "  • Fine-grained: Repository active-alpha-model + Contents Read/Write\n"
        "  • Falls SSO angezeigt: Token authorisieren",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
