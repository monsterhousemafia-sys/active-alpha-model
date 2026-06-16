"""Anonym Finish — Polling-Schleife bis forum-ack + fremder Compute-Host."""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/spread_finish_anonym_loop_latest.json")
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


def _federation_hostnames(root: Path) -> Dict[str, Any]:
    root = Path(root)
    try:
        from analytics.preview_federation import federation_config

        port = int(federation_config(root).get("hub_port") or 17890)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/federation", timeout=8) as resp:
            fed = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "error_de": str(exc)[:120], "hostnames": [], "remote_compute_hosts": []}

    workers = fed.get("workers") or []
    if isinstance(workers, dict):
        workers = list(workers.values())
    hosts = sorted(
        {
            str(w.get("hostname") or "").strip()
            for w in workers
            if isinstance(w, dict) and w.get("hostname")
        }
    )
    king_host = socket.gethostname()
    remote_hosts = [h for h in hosts if h and h.upper() != king_host.upper()]
    remote_compute = 0
    for w in workers:
        if not isinstance(w, dict):
            continue
        role = str(w.get("role") or "").lower()
        host = str(w.get("hostname") or "")
        if role == "compute" and host in remote_hosts:
            remote_compute += 1
    return {
        "ok": True,
        "workers_online": fed.get("workers_online"),
        "hostnames": hosts,
        "remote_compute_hosts": remote_hosts,
        "remote_compute_workers": remote_compute,
        "king_hostname": king_host,
    }


def _build_remaining(root: Path, facts: Dict[str, Any], fed: Dict[str, Any]) -> List[Dict[str, str]]:
    remaining: List[Dict[str, str]] = []
    if not facts.get("forum_posted"):
        remaining.append(
            {
                "id": "B_reddit_anonym",
                "blocker_de": "Reddit anonym posten + AA_FORUM_POST_URL setzen",
                "befehl": "Inkognito: evidence/reddit_post_body_ready.txt → r/selfhosted + r/linux",
            }
        )
    if int(fed.get("remote_compute_workers") or facts.get("remote_compute_workers") or 0) < 1:
        remaining.append(
            {
                "id": "A_adoption",
                "blocker_de": "Fremder PC muss world_worker_LITE.zip starten",
                "befehl": "ZIP + evidence/spread_whatsapp_de.txt an Person mit eigenem PC",
            }
        )
    if not facts.get("tunnel_stable"):
        remaining.append(
            {
                "id": "C_tunnel",
                "blocker_de": "Stabiler Tunnel — Token in control/server.env",
                "befehl": "bash tools/setup_cloudflare_tunnel_token.sh",
            }
        )
    return remaining


def run_anonym_finish_tick(
    root: Path,
    *,
    iteration: int = 1,
    execute_whatsapp: bool = True,
) -> Dict[str, Any]:
    """Ein Tick — anonym, ohne open_reddit_submit."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    try:
        from analytics.spread_autonomous import resume_autonomous_spread

        r = resume_autonomous_spread(root)
        steps.append({"step": "autonom_resume", "ok": r.get("ok")})
    except Exception as exc:
        steps.append({"step": "autonom_resume", "ok": False, "error": str(exc)[:80]})

    broadcast: Dict[str, Any] = {}
    try:
        from analytics.community_spread_plan import broadcast_spread_anonym

        broadcast = broadcast_spread_anonym(root)
        steps.append({"step": "anonym_texts", "ok": broadcast.get("ok")})
    except Exception as exc:
        steps.append({"step": "anonym_texts", "ok": False, "error": str(exc)[:80]})

    spread: Dict[str, Any] = {}
    try:
        from analytics.remote_hub_access import remote_access_status
        from analytics.spread_secure_ops import run_spread_efficient, verify_spread_security

        remote = remote_access_status(root)
        if remote.get("tunnel_pid_alive") and remote.get("remote_ready"):
            spread = {"ok": True, "mode": "verify", "security_final": verify_spread_security(root)}
            steps.append({"step": "spread_verify", "ok": spread.get("ok")})
        else:
            spread = run_spread_efficient(root, "voll")
            steps.append({"step": "spread_voll", "ok": spread.get("ok")})
            from analytics.community_spread_plan import broadcast_spread_anonym

            broadcast_spread_anonym(root)
    except Exception as exc:
        spread = {"ok": False}
        steps.append({"step": "spread", "ok": False, "error": str(exc)[:80]})

    token_doc: Dict[str, Any] = {}
    try:
        from analytics.tunnel_token_setup import apply_from_server_env

        token_doc = apply_from_server_env(root)
        steps.append({"step": "tunnel_token", "ok": token_doc.get("ok")})
        if token_doc.get("ok"):
            from analytics.community_spread_plan import broadcast_spread_anonym

            broadcast_spread_anonym(root)
    except Exception as exc:
        steps.append({"step": "tunnel_token", "ok": False, "error": str(exc)[:80]})

    forum_ack: Dict[str, Any] = {"skipped": True}
    from analytics.spread_finish_operator_evidence import resolve_forum_post_url

    post_url = resolve_forum_post_url(root)
    if post_url:
        try:
            from analytics.reddit_forum_post import complete_reddit_post

            forum_ack = complete_reddit_post(root, post_url=post_url)
            steps.append({"step": "forum_ack", "ok": forum_ack.get("ok")})
        except Exception as exc:
            forum_ack = {"ok": False, "error_de": str(exc)[:80]}
            steps.append({"step": "forum_ack", "ok": False, "error": str(exc)[:80]})

    whatsapp: Dict[str, Any] = {"skipped": True}
    if execute_whatsapp:
        prev = os.environ.get("AA_SPREAD_HUMAN_CONFIRM", "")
        os.environ["AA_SPREAD_HUMAN_CONFIRM"] = "1"
        try:
            from analytics.spread_autonomous import _try_whatsapp_autonomous

            whatsapp = _try_whatsapp_autonomous(root)
            steps.append({"step": "whatsapp", "ok": whatsapp.get("ok")})
        except Exception as exc:
            whatsapp = {"ok": False, "detail_de": str(exc)[:80]}
            steps.append({"step": "whatsapp", "ok": False, "error": str(exc)[:80]})
        finally:
            if prev:
                os.environ["AA_SPREAD_HUMAN_CONFIRM"] = prev
            else:
                os.environ.pop("AA_SPREAD_HUMAN_CONFIRM", None)

    fed = _federation_hostnames(root)
    steps.append({"step": "federation", "ok": fed.get("ok", False)})

    from analytics.spread_secure_ops import build_spread_facts

    facts = build_spread_facts(
        root,
        progress=spread.get("progress") if isinstance(spread, dict) else None,
        security=spread.get("security_final") if isinstance(spread, dict) else None,
    )
    if fed.get("remote_compute_workers") is not None:
        facts["remote_compute_workers"] = fed.get("remote_compute_workers")

    remaining = _build_remaining(root, facts, fed)
    done = (
        bool(facts.get("forum_posted"))
        and int(fed.get("remote_compute_workers") or 0) >= 1
    )

    from analytics.spread_anonym_policy import redact_evidence_doc, redact_federation_export

    doc = redact_evidence_doc(
        {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "iteration": iteration,
        "anonym": True,
        "ok": done,
        "done": done,
        "facts": facts,
        "federation": redact_federation_export(fed),
        "broadcast": broadcast,
        "spread_ok": bool(spread.get("ok")),
        "token": token_doc,
        "forum_ack": forum_ack,
        "whatsapp": whatsapp,
        "steps": steps,
        "remaining": remaining,
        "operator_next_de": [r.get("befehl", "") for r in remaining if r.get("befehl")],
        "headline_de": (
            "Anonym Finish — forum + fremder Host OK"
            if done
            else f"Anonym Finish — {len(remaining)} Blocker, Tick {iteration}"
        ),
        }
    )
    atomic_write_json(root / _EVIDENCE_REL, doc)
    try:
        from analytics.spread_finish_operator_evidence import sync_operator_evidence

        doc["operator_evidence"] = sync_operator_evidence(root, doc)
    except Exception as exc:
        doc["operator_evidence"] = {"error": str(exc)[:120]}
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def run_anonym_finish_loop(
    root: Path,
    *,
    interval_s: int = 300,
    max_duration_s: int = 86400,
) -> Dict[str, Any]:
    """Polling bis done oder Timeout."""
    root = Path(root)
    interval_s = max(60, int(interval_s))
    max_duration_s = max(interval_s, int(max_duration_s))
    started = time.monotonic()
    iteration = 0
    last: Dict[str, Any] = {}

    while time.monotonic() - started < max_duration_s:
        iteration += 1
        last = run_anonym_finish_tick(root, iteration=iteration)
        if last.get("done"):
            last["loop"] = {
                "iterations": iteration,
                "elapsed_s": int(time.monotonic() - started),
                "stopped": "success",
            }
            atomic_write_json(root / _EVIDENCE_REL, last)
            return last
        if iteration * interval_s >= max_duration_s:
            break
        time.sleep(interval_s)

    last = last or run_anonym_finish_tick(root, iteration=max(1, iteration))
    last["loop"] = {
        "iterations": max(1, iteration),
        "elapsed_s": int(time.monotonic() - started),
        "stopped": "timeout",
        "max_duration_s": max_duration_s,
    }
    last["headline_de"] = (
        f"Anonym Finish — Timeout nach {last['loop']['elapsed_s']}s, "
        f"{len(last.get('remaining') or [])} Blocker offen"
    )
    atomic_write_json(root / _EVIDENCE_REL, last)
    return last


def load_anonym_finish_status(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)
