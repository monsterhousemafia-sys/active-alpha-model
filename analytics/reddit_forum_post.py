"""Reddit-Forum-Post — Entwurf öffnen, Ack mit Post-URL abschließen."""
from __future__ import annotations

import json
import re
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_FORUM_REL = Path("evidence/community_spread_forum_de.txt")
_ACK_REL = Path("evidence/forum_post_ack.json")
_PREPARE_REL = Path("evidence/reddit_post_prepare_latest.json")
_DEFAULT_SUBS = ("selfhosted", "linux")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_forum_draft(root: Path) -> Dict[str, Any]:
    """Title + Body aus community_spread_forum_de.txt."""
    root = Path(root)
    path = root / _FORUM_REL
    if not path.is_file():
        return {"ok": False, "detail_de": "Forum-Entwurf fehlt"}
    lines = path.read_text(encoding="utf-8").splitlines()
    title = ""
    body_lines: List[str] = []
    in_body = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("**Title:**"):
            title = line.replace("**Title:**", "").strip()
            in_body = True
            continue
        if not in_body:
            continue
        if line.startswith("===") or line.startswith("---"):
            if body_lines:
                break
            continue
        if line.startswith("**"):
            continue
        body_lines.append(raw.rstrip())
    body = "\n".join(body_lines).strip()
    while body.endswith("\n\n"):
        body = body.strip()
    if not title or not body:
        return {"ok": False, "detail_de": "Title oder Body leer"}
    return {"ok": True, "title": title, "body": body, "forum_ref": str(_FORUM_REL)}


def _copy_clipboard(text: str) -> Dict[str, Any]:
    # xclip/xsel only — wl-copy kann xdg-desktop-portal-gnome auf Ubuntu crashen
    for cmd in (
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ):
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=3)
            return {"ok": True, "detail_de": cmd[0]}
        except (OSError, subprocess.CalledProcessError):
            continue
    return {"ok": False, "detail_de": "Clipboard nicht verfügbar — Body in Evidence-Datei"}


def _submit_url(subreddit: str, title: str) -> str:
    sub = subreddit.lstrip("r/")
    q = urllib.parse.quote(title, safe="")
    return f"https://www.reddit.com/r/{sub}/submit/?type=TEXT&title={q}"


def open_reddit_submit(root: Path, *, subreddits: Optional[List[str]] = None) -> Dict[str, Any]:
    """Body in Zwischenablage, Submit-Seiten in Firefox öffnen."""
    root = Path(root)
    draft = parse_forum_draft(root)
    if not draft.get("ok"):
        return draft
    title = str(draft["title"])
    body = str(draft["body"])
    subs = [s.lstrip("r/") for s in (subreddits or list(_DEFAULT_SUBS))]

    clip = _copy_clipboard(body)
    body_fallback = root / "evidence/reddit_post_body_ready.txt"
    body_fallback.write_text(f"{title}\n\n{body}\n", encoding="utf-8")

    opened: List[Dict[str, Any]] = []
    try:
        from analytics.terminal_runtime import bootstrap_graphical_env, graphical_env_dict
        from analytics.whatsapp_auto_send import _firefox_binary, bootstrap_firefox_profile, firefox_profile_dir
        from analytics.whatsapp_spread import load_whatsapp_config

        bootstrap_graphical_env()
        cfg = load_whatsapp_config(root)
        browser = _firefox_binary()
        profile = firefox_profile_dir(root, cfg)
        bootstrap_firefox_profile(profile)
        env = graphical_env_dict()
        if browser:
            for sub in subs:
                url = _submit_url(sub, title)
                cmd = [browser, "-no-remote", "-profile", str(profile), url]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                opened.append({"subreddit": f"r/{sub}", "url": url, "ok": True})
        else:
            for sub in subs:
                url = _submit_url(sub, title)
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                opened.append({"subreddit": f"r/{sub}", "url": url, "ok": True})
    except Exception as exc:
        return {"ok": False, "detail_de": str(exc)[:120], "draft": draft}

    doc = {
        "schema_version": 1,
        "ok": True,
        "title": title,
        "body_preview": body[:240],
        "clipboard": clip,
        "body_file": str(body_fallback),
        "opened": opened,
        "headline_de": (
            "Reddit Submit geöffnet — Body in evidence/reddit_post_body_ready.txt"
            + (" (Zwischenablage OK)" if clip.get("ok") else " (manuell kopieren)")
        ),
        "next_de": (
            "In beiden Tabs: Strg+V → Post. Danach: "
            "AA_FORUM_POST_URL='https://reddit.com/...' bash tools/king_ops.sh forum-ack"
        ),
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _PREPARE_REL, doc)
    return doc


def complete_reddit_post(
    root: Path,
    *,
    post_url: str = "",
    post_urls: Optional[List[str]] = None,
    detail_de: str = "",
) -> Dict[str, Any]:
    """Nach echtem Post — Ack + Progress (post_url Pflicht)."""
    root = Path(root)
    urls = [u.strip() for u in (post_urls or []) if str(u).strip()]
    if post_url.strip():
        urls.insert(0, post_url.strip())
    urls = list(dict.fromkeys(urls))
    if not urls:
        return {
            "ok": False,
            "detail_de": "post_url fehlt — Reddit erst posten, dann URL setzen",
            "hint_de": "AA_FORUM_POST_URL='https://reddit.com/r/...' bash tools/king_ops.sh forum-ack",
        }
    from analytics.community_spread_plan import ack_forum_post

    detail = detail_de or f"Reddit live — {len(urls)} Post(s)"
    doc = ack_forum_post(root, detail_de=detail, post_url=urls[0])
    doc["post_urls"] = urls
    atomic_write_json(root / _ACK_REL, doc)
    return doc
