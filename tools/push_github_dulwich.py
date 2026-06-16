#!/usr/bin/env python3
"""Push local main branch to GitHub and configure public access (dulwich, no system git)."""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Set

from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo

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


def _mode_to_type(mode: int) -> str:
    if mode == 0o40000:
        return "tree"
    if mode == 0o160000:
        return "commit"
    return "blob"


def _mode_str(mode: int) -> str:
    if mode == 0o40000:
        return "040000"
    return f"{mode:o}"


def _sha_hex(sha: bytes) -> str:
    return sha.decode("ascii") if len(sha) == 40 else sha.hex()


def _collect_objects(repo: Repo, stop_at: bytes | None, head: bytes) -> Set[bytes]:
    seen: Set[bytes] = set()
    stack = [head]
    while stack:
        sha = stack.pop()
        if sha in seen or (stop_at and sha == stop_at):
            continue
        seen.add(sha)
        obj = repo.object_store[sha]
        if isinstance(obj, Commit):
            stack.append(obj.tree)
            stack.extend(obj.parents)
        elif isinstance(obj, Tree):
            for _name, mode, entry_sha in obj.iteritems():
                if mode == 0o40000:
                    stack.append(entry_sha)
                elif mode != 0o160000:
                    stack.append(entry_sha)
    if stop_at:
        seen.discard(stop_at)
    return seen


def _commit_chain(repo: Repo, remote_sha: bytes | None, local_sha: bytes) -> list[bytes]:
    chain: list[bytes] = []
    sha = local_sha
    while sha and sha != remote_sha:
        obj = repo.object_store[sha]
        if not isinstance(obj, Commit):
            break
        chain.append(sha)
        sha = obj.parents[0] if obj.parents else b""
    chain.reverse()
    return chain


def _upload_blob(repo: Repo, sha: bytes, login: str, repo_name: str, token: str) -> None:
    obj = repo.object_store[sha]
    if not isinstance(obj, Blob):
        return
    _api_json(
        "POST",
        f"https://api.github.com/repos/{login}/{repo_name}/git/blobs",
        token,
        {"content": base64.b64encode(obj.data).decode("ascii"), "encoding": "base64"},
    )


def _upload_tree(repo: Repo, sha: bytes, login: str, repo_name: str, token: str) -> None:
    obj = repo.object_store[sha]
    if not isinstance(obj, Tree):
        return
    tree_entries = []
    for name, mode, entry_sha in obj.iteritems():
        tree_entries.append(
            {
                "path": name.decode("utf-8", errors="surrogateescape"),
                "mode": _mode_str(mode),
                "type": _mode_to_type(mode),
                "sha": _sha_hex(entry_sha),
            }
        )
    _api_json(
        "POST",
        f"https://api.github.com/repos/{login}/{repo_name}/git/trees",
        token,
        {"tree": tree_entries},
    )


def _upload_commit(repo: Repo, sha: bytes, login: str, repo_name: str, token: str) -> None:
    obj = repo.object_store[sha]
    if not isinstance(obj, Commit):
        return
    payload: Dict[str, Any] = {
        "message": obj.message.decode("utf-8", errors="surrogateescape"),
        "tree": _sha_hex(obj.tree),
        "parents": [_sha_hex(p) for p in obj.parents],
    }
    _api_json(
        "POST",
        f"https://api.github.com/repos/{login}/{repo_name}/git/commits",
        token,
        payload,
    )


def _fetch_remote_main_sha(login: str, repo_name: str, token: str) -> bytes | None:
    ref_api = f"https://api.github.com/repos/{login}/{repo_name}/git/ref/heads/main"
    try:
        return _api_json("GET", ref_api, token)["object"]["sha"].encode("ascii")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    public_req = urllib.request.Request(
        ref_api,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "active-alpha-publish"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(public_req, timeout=30) as resp:
            return json.loads(resp.read().decode())["object"]["sha"].encode("ascii")
    except urllib.error.HTTPError:
        return None


def _flat_tree_paths(repo: Repo, tree_sha: bytes, prefix: str = "") -> Dict[str, bytes]:
    paths: Dict[str, bytes] = {}
    obj = repo.object_store[tree_sha]
    if not isinstance(obj, Tree):
        return paths
    for name, mode, entry_sha in obj.iteritems():
        rel = f"{prefix}{name.decode('utf-8', errors='surrogateescape')}"
        if mode == 0o40000:
            paths.update(_flat_tree_paths(repo, entry_sha, f"{rel}/"))
        elif mode != 0o160000:
            paths[rel] = entry_sha
    return paths


def _remote_tree_paths_github(owner: str, repo_name: str, commit_sha: str, token: str) -> Dict[str, str]:
    """Remote file path → blob sha (hex) via GitHub API (works when commit is not local)."""
    commit = _api_json(
        "GET",
        f"https://api.github.com/repos/{owner}/{repo_name}/git/commits/{commit_sha}",
        token,
    )
    tree_sha = commit["tree"]["sha"]
    data = _api_json(
        "GET",
        f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{tree_sha}?recursive=1",
        token,
    )
    paths: Dict[str, str] = {}
    for entry in data.get("tree", []):
        if entry.get("type") == "blob":
            paths[entry["path"]] = entry["sha"]
    return paths


def _remote_content_sha(login: str, repo_name: str, path: str, token: str) -> str | None:
    url = f"https://api.github.com/repos/{login}/{repo_name}/contents/{urllib.parse.quote(path)}"
    try:
        return _api_json("GET", url, token).get("sha")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def push_via_contents_api(repo_path: Path, login: str, repo_name: str, token: str) -> None:
    """Upload changed files only (Contents API) — one commit per file, needs repo write scope."""
    repo = Repo(str(repo_path))
    local_sha = repo.head()
    remote_sha = _fetch_remote_main_sha(login, repo_name, token)
    if remote_sha is None:
        raise RuntimeError("Remote branch main nicht gefunden.")

    if remote_sha == local_sha:
        print("Remote already at local HEAD.")
        return

    local_commit = repo.object_store[local_sha]
    if not isinstance(local_commit, Commit):
        raise RuntimeError("Local HEAD ist kein Commit.")

    local_files = _flat_tree_paths(repo, local_commit.tree)
    local_hex = {p: _sha_hex(s) for p, s in local_files.items()}
    remote_hex = _sha_hex(remote_sha)

    if remote_sha in repo.object_store:
        remote_commit = repo.object_store[remote_sha]
        if isinstance(remote_commit, Commit):
            remote_files = _flat_tree_paths(repo, remote_commit.tree)
            remote_hex_map = {p: _sha_hex(s) for p, s in remote_files.items()}
        else:
            remote_hex_map = _remote_tree_paths_github(login, repo_name, remote_hex, token)
    else:
        print(f"Remote-Commit nur auf GitHub ({remote_hex[:12]}…) — Tree per API")
        remote_hex_map = _remote_tree_paths_github(login, repo_name, remote_hex, token)

    paths = sorted(p for p, blob_sha in local_hex.items() if remote_hex_map.get(p) != blob_sha)

    if not paths:
        print("Keine Dateiänderungen gegenüber remote main.")
        return

    print(f"Contents API: {len(paths)} geänderte Datei(en)")
    for path in paths:
        blob = repo.object_store[local_files[path]]
        if not isinstance(blob, Blob):
            continue
        payload: Dict[str, Any] = {
            "message": f"Publish: {path}",
            "content": base64.b64encode(blob.data).decode("ascii"),
        }
        existing = _remote_content_sha(login, repo_name, path, token)
        if existing:
            payload["sha"] = existing
        _api_json(
            "PUT",
            f"https://api.github.com/repos/{login}/{repo_name}/contents/{urllib.parse.quote(path)}",
            token,
            payload,
        )
        print(f"  uploaded: {path}")
    print("Contents API push successful.")


def push_via_github_api(repo_path: Path, login: str, repo_name: str, token: str) -> None:
    """Fast-forward push using GitHub Git Data API (Bearer token, no git-receive-pack)."""
    repo = Repo(str(repo_path))
    local_sha = repo.head()
    remote_sha = _fetch_remote_main_sha(login, repo_name, token)
    if remote_sha is None:
        raise RuntimeError("Remote branch main nicht gefunden.")

    if remote_sha == local_sha:
        print("Remote already at local HEAD.")
        return

    objects = _collect_objects(repo, remote_sha, local_sha)
    blobs = [s for s in objects if isinstance(repo.object_store[s], Blob)]
    trees = [s for s in objects if isinstance(repo.object_store[s], Tree)]
    commits = _commit_chain(repo, remote_sha, local_sha)

    print(f"API push: {len(blobs)} blobs, {len(trees)} trees, {len(commits)} commits")
    for sha in blobs:
        _upload_blob(repo, sha, login, repo_name, token)

    pending = set(trees)
    while pending:
        progressed = False
        for sha in list(pending):
            obj = repo.object_store[sha]
            assert isinstance(obj, Tree)
            child_trees = [entry_sha for _n, mode, entry_sha in obj.iteritems() if mode == 0o40000]
            if all(child not in pending for child in child_trees):
                _upload_tree(repo, sha, login, repo_name, token)
                pending.remove(sha)
                progressed = True
        if not progressed and pending:
            raise RuntimeError(f"Tree upload stuck ({len(pending)} remaining)")

    for sha in commits:
        _upload_commit(repo, sha, login, repo_name, token)

    ref_api = f"https://api.github.com/repos/{login}/{repo_name}/git/ref/heads/main"
    _api_json("PATCH", ref_api, token, {"sha": _sha_hex(local_sha), "force": False})
    print("API push successful.")


def _use_api_fallback(exc: Exception) -> bool:
    if exc.__class__.__name__ in {"DivergedBranches"}:
        return True
    return "403" in str(exc)


def _push_api_fallbacks(exc: Exception, owner: str, repo_name: str, token: str, login: str) -> int | None:
    """Return exit code on failure, None on success."""
    label = exc.__class__.__name__
    if label == "DivergedBranches":
        print(
            "Branch divergiert (lokal vs GitHub, z.B. Plan-B-Upload) — Contents API …",
            file=sys.stderr,
        )
        try:
            push_via_contents_api(ROOT, owner, repo_name, token)
            return None
        except urllib.error.HTTPError as contents_exc:
            cbody = contents_exc.read().decode(errors="replace")
            print(
                f"Contents API fehlgeschlagen: HTTP {contents_exc.code} {cbody[:240]}\n"
                "Optional: AA_PUBLIC_GIT_FORCE=1 bash tools/publish_public_access.sh",
                file=sys.stderr,
            )
            return 5
        except Exception as contents_exc:
            print(f"Contents API fehlgeschlagen: {contents_exc}", file=sys.stderr)
            return 5

    print("Git-HTTP 403 — versuche GitHub API Push …", file=sys.stderr)
    try:
        push_via_github_api(ROOT, owner, repo_name, token)
        return None
    except urllib.error.HTTPError as api_exc:
        body = api_exc.read().decode(errors="replace")
        print(
            f"Git-Data-API fehlgeschlagen: HTTP {api_exc.code} — versuche Contents API …",
            file=sys.stderr,
        )
        try:
            push_via_contents_api(ROOT, owner, repo_name, token)
            return None
        except urllib.error.HTTPError as contents_exc:
            cbody = contents_exc.read().decode(errors="replace")
            print(
                f"Contents API fehlgeschlagen: HTTP {contents_exc.code} {cbody[:240]}\n"
                f"Token-User={login}, Mirror-Owner={owner}",
                file=sys.stderr,
            )
            return 5
        except Exception as contents_exc:
            print(f"Contents API fehlgeschlagen: {contents_exc}", file=sys.stderr)
            return 5
    except Exception as api_exc:
        print(f"Git-Data-API fehlgeschlagen: {api_exc} — versuche Contents API …", file=sys.stderr)
        try:
            push_via_contents_api(ROOT, owner, repo_name, token)
            return None
        except Exception as contents_exc:
            print(f"Contents API fehlgeschlagen: {contents_exc}", file=sys.stderr)
            return 5


def push_with_dulwich(repo_path: Path, login: str, repo_name: str, token: str, url: str) -> None:
    from dulwich import porcelain

    force = os.environ.get("AA_PUBLIC_GIT_FORCE", "0") == "1"
    quoted = urllib.parse.quote(token, safe="")
    remotes = [
        f"https://x-access-token:{quoted}@github.com/{login}/{repo_name}.git",
        f"https://{quoted}@github.com/{login}/{repo_name}.git",
        f"https://{login}:{quoted}@github.com/{login}/{repo_name}.git",
    ]
    last_exc: Exception | None = None
    for remote in remotes:
        try:
            print(f"Pushing main → {url}" + (" (force)" if force else ""))
            porcelain.push(
                str(repo_path),
                remote,
                refspecs=[b"refs/heads/main:refs/heads/main"],
                force=force,
            )
            print("Push successful.")
            return
        except Exception as exc:  # noqa: BLE001 — try next auth form / API fallback
            last_exc = exc
            print(f"WARN: Push-Versuch fehlgeschlagen ({exc.__class__.__name__})", file=sys.stderr)
    if last_exc:
        raise last_exc


def main() -> int:
    try:
        from dulwich import porcelain  # noqa: F401 — import check
    except ImportError:
        print("dulwich fehlt: .venv/bin/pip install dulwich", file=sys.stderr)
        return 1

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
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
    owner = mirror_owner()
    if login != owner:
        print(f"Hinweis: Token-User={login}, Mirror-Owner={owner}", file=sys.stderr)
    url = f"https://github.com/{owner}/{repo_name}"

    if not skip_push:
        repo_api = f"https://api.github.com/repos/{owner}/{repo_name}"
        repo_exists = False
        try:
            with urllib.request.urlopen(
                urllib.request.Request(repo_api, headers=_headers(token), method="GET"),
                timeout=30,
            ) as resp:
                repo_exists = True
                url = json.loads(resp.read().decode()).get("html_url") or url
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 403}:
                body = exc.read().decode(errors="replace")
                print(f"Repo-Abfrage fehlgeschlagen: {exc.code} {body[:200]}", file=sys.stderr)
                return 3

        if not repo_exists:
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
                if exc.code == 422 and "already exists" in body:
                    print("Repo existiert bereits — Push wird fortgesetzt.")
                elif exc.code in {404, 403}:
                    print(
                        f"WARN: Repo-Erstellung {exc.code} — versuche Push zum bestehenden Mirror.",
                        file=sys.stderr,
                    )
                else:
                    print(f"Repo-Erstellung fehlgeschlagen: {exc.code} {body[:200]}", file=sys.stderr)
                    return 3
        else:
            print(f"Repo existiert bereits — Push → {url}")

        perms = {}
        try:
            repo_info = _api_json("GET", f"https://api.github.com/repos/{owner}/{repo_name}", token)
            perms = repo_info.get("permissions") or {}
            url = repo_info.get("html_url") or url
        except urllib.error.HTTPError as exc:
            print(f"WARN: Repo-Berechtigungen nicht lesbar: HTTP {exc.code}", file=sys.stderr)

        if not perms.get("push"):
            print(
                f"Token-User={login} hat kein push-Recht auf {owner}/{repo_name}.\n"
                "Classic PAT (Scope repo) als Repo-Owner erstellen.\n"
                "Prüfen: .venv/bin/python3 tools/verify_github_push_token.py",
                file=sys.stderr,
            )
            return 4

        try:
            push_with_dulwich(ROOT, owner, repo_name, token, url)
        except Exception as exc:
            if not _use_api_fallback(exc):
                raise
            fail = _push_api_fallbacks(exc, owner, repo_name, token, login)
            if fail is not None:
                return fail

    if not want_private:
        configure_public_repo(owner, repo_name, token, force_public=True)
        print(f"[OK] Öffentlich konfiguriert: {url}")
    else:
        print(f"[OK] Privates Repo: {url}")

    write_public_access_manifest(owner, repo_name, url)
    print(f"Clone: git clone https://github.com/{owner}/{repo_name}.git")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
