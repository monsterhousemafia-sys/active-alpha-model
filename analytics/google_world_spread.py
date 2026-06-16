"""Weltweite Ausbreitung — Google Gemini (Cloud-Compute) + Internet-Tunnel + Worker-ZIP."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/google_world_spread_policy.json")
_EVIDENCE_REL = Path("evidence/google_world_spread_latest.json")
_GLOBAL_EN_REL = Path("evidence/spread_google_world_en.txt")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_global_en_copy(root: Path, text: str) -> Path:
    out_path = Path(root) / _GLOBAL_EN_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(str(text or "").strip() + "\n", encoding="utf-8")
    return out_path


def _resolve_join_url(root: Path) -> tuple[str, str]:
    """Join-URL aus live Tunnel-State + collect_spread_urls (nach Internet-Spread)."""
    from analytics.community_spread_plan import collect_spread_urls
    from analytics.remote_hub_access import load_tunnel_state

    root = Path(root)
    tunnel = load_tunnel_state(root)
    urls = collect_spread_urls(root)
    remote_url = str(urls.get("remote_url") or tunnel.get("public_url") or "").strip().rstrip("/")
    join_url = str(urls.get("join_remote") or "").strip().rstrip("/") or (
        f"{remote_url}/join" if remote_url else ""
    )
    return join_url, remote_url


def _generate_global_copy_template(root: Path, *, join_url: str) -> Dict[str, Any]:
    """Deterministic EN outreach when Cloud/LLM unavailable."""
    from analytics.community_spread_plan import _FORUM_TITLE

    join_line = join_url or "Join URL follows after spread-remote"
    text = "\n".join(
        [
            _FORUM_TITLE,
            "",
            "We are building a decentralized open research federation — not another chatbot subscription.",
            "",
            "Facts:",
            f"- Join: {join_line}",
            "- ~100 KB worker ZIP, Python 3, Windows / macOS / Linux",
            "- No broker keys, no real money, pilot research only",
            "- Federated compute with fail-closed safety gates",
            "",
            "Self-hosters and Linux folks: unzip, run START, lend spare CPU cycles.",
            "Phones spread the link; PCs do the work.",
        ]
    )
    _write_global_en_copy(root, text)
    return {
        "ok": True,
        "provider": "template",
        "fallback": True,
        "path": str(_GLOBAL_EN_REL),
        "message_de": f"Template-Copy (kein Gemini) → {_GLOBAL_EN_REL.as_posix()}",
    }


def _generate_global_copy_ollama(root: Path, *, join_url: str) -> Dict[str, Any]:
    """Local Ollama fallback — same facts, no Google traffic."""
    from analytics.local_llm_bridge import chat_completion, health_report

    health = health_report(root)
    if not health.get("ready"):
        return {"ok": False, "skipped": True, "message_de": "Ollama nicht bereit"}

    prompt = (
        "Write a concise English forum post inviting CPU donors to join a decentralized "
        "open research federation. Facts only:\n"
        f"- Join URL: {join_url or 'TBD'}\n"
        "- ~100 KB worker ZIP, Python 3, Win/Mac/Linux\n"
        "- No broker, no real money, pilot research\n"
        "- Federated compute, fail-closed gates\n"
        "Format: Title line, blank line, body (~180 words), no markdown except raw URL."
    )
    try:
        body, meta = chat_completion(
            root,
            [
                {
                    "role": "system",
                    "content": "Factual open-source community outreach. No hype, no investment advice.",
                },
                {"role": "user", "content": prompt},
            ],
            role="chat",
            temperature=0.35,
            timeout_s=120.0,
        )
        text = str(body or "").strip()
        if not text:
            return {"ok": False, "message_de": "Ollama lieferte leeren Text"}
        _write_global_en_copy(root, text)
        return {
            "ok": True,
            "provider": "ollama",
            "fallback": True,
            "model": (meta.get("model") or health.get("resolved_model")),
            "path": str(_GLOBAL_EN_REL),
            "message_de": f"Lokal Ollama (Gemini-Key fehlt) → {_GLOBAL_EN_REL.as_posix()}",
        }
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:240]}


def _generate_global_copy_gemini(root: Path, *, join_url: str) -> Dict[str, Any]:
    """Gemini on Google servers — EN forum/WhatsApp variants for worldwide channels."""
    from analytics.gemini_advisor_bridge import _gemini_chat, is_gemini_configured, load_gemini_config

    if not is_gemini_configured(root):
        return {
            "ok": False,
            "skipped": True,
            "message_de": "Gemini-Key fehlt — bash tools/setup_gemini_key.sh --from-env",
        }

    gem = load_gemini_config(root)
    prompt = (
        "Write a concise English forum post (r/selfhosted, r/linux) inviting CPU donors "
        "to join a decentralized open research federation. Facts only:\n"
        f"- Join URL: {join_url}\n"
        "- ~100 KB worker ZIP, Python 3, Win/Mac/Linux\n"
        "- No broker, no real money, pilot research\n"
        "- Federated compute, fail-closed gates\n"
        "Format: Title line, blank line, body (~180 words), no markdown links except raw URL."
    )
    try:
        body, meta = _gemini_chat(
            root,
            [
                {
                    "role": "system",
                    "content": "You write factual open-source community outreach. No hype, no investment advice.",
                },
                {"role": "user", "content": prompt},
            ],
            model=str(gem.get("model") or "gemini-2.0-flash"),
            max_tokens=900,
            temperature=0.35,
            fallback_model=str(gem.get("fallback_model") or "gemini-2.0-flash"),
            timeout_s=float(gem.get("timeout_s") or 90.0),
        )
        text = str(body or "").strip()
        if not text:
            return {"ok": False, "message_de": "Gemini lieferte leeren Text"}
        _write_global_en_copy(root, text)
        return {
            "ok": True,
            "provider": "gemini",
            "fallback": False,
            "model": meta.get("model"),
            "path": str(_GLOBAL_EN_REL),
            "message_de": f"Google Cloud Copy → {_GLOBAL_EN_REL.as_posix()}",
        }
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:240]}


def _generate_global_copy(root: Path, *, join_url: str) -> Dict[str, Any]:
    """Gemini first; Ollama/template fallback so spread_google_world_en.txt always exists."""
    gem = _generate_global_copy_gemini(root, join_url=join_url)
    if gem.get("ok"):
        return gem
    ollama = _generate_global_copy_ollama(root, join_url=join_url)
    if ollama.get("ok"):
        ollama["gemini_blocked_de"] = gem.get("message_de")
        return ollama
    tpl = _generate_global_copy_template(root, join_url=join_url)
    tpl["gemini_blocked_de"] = gem.get("message_de")
    if not ollama.get("skipped"):
        tpl["ollama_blocked_de"] = ollama.get("message_de")
    return tpl


def _operator_next_de(root: Path, *, join_url: str, gemini_doc: Dict[str, Any]) -> List[str]:
    steps = [
        f"Welt-ZIP teilen: ~/world_worker_LITE.zip",
        f"Join weltweit: {join_url or '—'}",
        "Forum: evidence/community_spread_forum_anonym_en.txt",
        f"Global EN: {_GLOBAL_EN_REL.as_posix()}",
    ]
    provider = str(gemini_doc.get("provider") or "")
    if provider == "gemini":
        steps.append("Gemini Cloud-Copy aktiv — kein weiterer Key-Schritt nötig")
    else:
        steps.extend(
            [
                "Später — echte Google-Copy: export GEMINI_API_KEY=… && bash tools/setup_gemini_key.sh --from-env",
                "Danach: bash tools/king_ops.sh google-spread (provider=gemini)",
            ]
        )
    steps.append("Stabile URL: bash tools/setup_cloudflare_tunnel_token.sh")
    return steps


def run_google_world_spread(
    root: Path,
    *,
    use_gemini: bool = True,
    force_export: bool = True,
) -> Dict[str, Any]:
    """
    Weltweit ausbreiten:
    1) Tunnel + Hub + Welt-ZIP (bestehende Pipeline)
    2) Anonym-Broadcast (Forum/WhatsApp) mit synchroner Join-URL
    3) Global-Copy (Gemini → Ollama → Template) mit finaler Join-URL
    """
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    from analytics.spread_secure_ops import expand_internet_spread

    internet = expand_internet_spread(root)
    steps.append({"step": "internet_spread", "ok": bool(internet.get("ok"))})

    from analytics.community_spread_plan import broadcast_spread_anonym
    from analytics.remote_hub_access import remote_access_status

    broadcast = broadcast_spread_anonym(root)
    steps.append({"step": "broadcast_anonym", "ok": bool(broadcast.get("ok"))})

    join_url, remote_url = _resolve_join_url(root)
    status = remote_access_status(root)

    gemini_doc: Dict[str, Any] = {"skipped": True}
    if use_gemini:
        gemini_doc = _generate_global_copy(root, join_url=join_url)
        steps.append({"step": "gemini_global_copy", "ok": bool(gemini_doc.get("ok")), **gemini_doc})

    checks = internet.get("internet_checks") or {}
    spread_ok = bool(internet.get("ok")) or bool(
        checks.get("health_ok") and checks.get("join_ok") and status.get("tunnel_pid_alive")
    )
    if not spread_ok:
        spread_ok = bool(status.get("remote_ready"))
    copy_ok = bool(gemini_doc.get("ok")) and (root / _GLOBAL_EN_REL).is_file()

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": spread_ok,
        "spread_ok": spread_ok,
        "copy_ok": copy_ok,
        "headline_de": (
            f"Google-Welt-Spread — Join {join_url or '—'}"
            if spread_ok
            else "Google-Welt-Spread — Tunnel/Join noch rot"
        ),
        "join_url": join_url,
        "public_base_url": remote_url or status.get("public_base_url"),
        "tunnel_stable": bool(status.get("tunnel_stable")),
        "world_zip": (internet.get("welt") or {}).get("home_world_zip")
        or (internet.get("welt") or {}).get("world_zip"),
        "gemini": gemini_doc,
        "internet": {
            "ok": internet.get("ok"),
            "headline_de": internet.get("headline_de"),
            "operator_de": internet.get("operator_de"),
            "internet_checks": checks,
        },
        "broadcast": broadcast,
        "steps": steps,
        "operator_next_de": _operator_next_de(root, join_url=join_url, gemini_doc=gemini_doc),
        "policy_ref": str(_POLICY_REL),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
