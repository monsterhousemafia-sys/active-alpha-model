"""Operator-Evidence — synchronisiert Finish-Dateien aus Anonym-Tick."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_FORUM_URL_FILE = Path("evidence/forum_post_url.txt")
_FINISH_REL = Path("evidence/spread_finish_latest.json")
_FED_REL = Path("evidence/spread_finish_federation_latest.json")
_STATUS_REL = Path("evidence/operator_finish_status_de.txt")
_HANDOFF_REL = Path("evidence/spread_external_worker_handoff_de.txt")
_FORUM_PENDING_REL = Path("evidence/forum_post_pending_de.txt")
_TUNNEL_OP_REL = Path("evidence/tunnel_token_operator_de.txt")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_forum_post_url(root: Path) -> str:
    """Env oder evidence/forum_post_url.txt (eine Zeile)."""
    import os

    url = str(os.environ.get("AA_FORUM_POST_URL") or "").strip()
    if url:
        return url
    path = Path(root) / _FORUM_URL_FILE
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "reddit.com" in line:
                return line
    return ""


def sync_operator_evidence(root: Path, tick: Dict[str, Any]) -> Dict[str, str]:
    """Schreibt alle Finish-Operator-Artefakte — anonym, Internet-only."""
    root = Path(root)
    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)

    broadcast = tick.get("broadcast") if isinstance(tick.get("broadcast"), dict) else {}
    urls = broadcast.get("urls") if isinstance(broadcast.get("urls"), dict) else {}
    remote = str(urls.get("remote_url") or "").strip().rstrip("/")
    join = f"{remote}/join" if remote.startswith("https://") else ""
    fed = tick.get("federation") if isinstance(tick.get("federation"), dict) else {}
    facts = tick.get("facts") if isinstance(tick.get("facts"), dict) else {}
    token = tick.get("token") if isinstance(tick.get("token"), dict) else {}
    whatsapp = tick.get("whatsapp") if isinstance(tick.get("whatsapp"), dict) else {}
    forum_posted = bool(facts.get("forum_posted"))
    tunnel_stable = bool(facts.get("tunnel_stable"))
    remote_compute = int(fed.get("remote_compute_workers") or facts.get("remote_compute_workers") or 0)
    adoption_ok = remote_compute >= 1

    sec = {}
    spread = tick.get("spread_ok")
    for step in tick.get("steps") or []:
        if isinstance(step, dict) and step.get("step") in ("spread_verify", "spread_voll"):
            spread = step.get("ok")

    verify_label = "6/6" if facts.get("verify_ok") else ("ok" if spread else "pending")

    finish = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "anonym": True,
        "spread_verify": verify_label,
        "tunnel_url": join or None,
        "tunnel_stable": tunnel_stable,
        "whatsapp_send_ok": bool(whatsapp.get("ok")),
        "reddit_ready": True,
        "reddit_anonym_ref": "evidence/reddit_post_operator_anonym_de.txt",
        "reddit_body_ref": "evidence/reddit_post_body_ready.txt",
        "forum_ack": "ok" if forum_posted else "pending_operator_url",
        "forum_ack_ref": "evidence/forum_post_ack.json" if forum_posted else "evidence/forum_post_pending_de.txt",
        "remote_compute_workers": remote_compute,
        "adoption_ok": adoption_ok,
        "tunnel_token": "ok" if token.get("ok") else "pending_operator_server_env",
        "tunnel_token_ref": "evidence/tunnel_token_operator_de.txt",
        "headline_de": tick.get("headline_de") or "Anonym Finish",
        "operator_next_de": tick.get("operator_next_de") or [],
        "done": bool(tick.get("done")),
    }
    atomic_write_json(root / _FINISH_REL, finish)

    fed_doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "workers_online": fed.get("workers_online"),
        "remote_compute_workers": remote_compute,
        "remote_compute_hosts": fed.get("remote_compute_hosts") or [],
        "adoption_ok": adoption_ok,
        "join_remote": join or None,
    }
    atomic_write_json(root / _FED_REL, fed_doc)

    if not forum_posted:
        pending = (
            "=== forum-ack — wartet auf deinen Reddit-Post ===\n\n"
            "Status: PENDING (kein forum_post_ack.json)\n\n"
            "Nach anonymem Post in r/selfhosted + r/linux:\n\n"
            "Option A — Env:\n"
            "AA_FORUM_POST_URL='https://reddit.com/r/selfhosted/comments/DEIN_POST_ID/titel/' \\\n"
            "  bash tools/king_ops.sh forum-ack\n\n"
            "Option B — Datei (Schleife liest automatisch):\n"
            "echo 'https://reddit.com/r/selfhosted/comments/...' > evidence/forum_post_url.txt\n"
            "bash tools/king_ops.sh spread-finish-anonym once\n\n"
            "Erfolg: evidence/forum_post_ack.json erzeugt.\n"
        )
        (root / _FORUM_PENDING_REL).write_text(pending, encoding="utf-8")

    from analytics.tunnel_token_setup import wizard_status

    wiz = wizard_status(root)
    tunnel_txt = (
        "=== Stabiler Tunnel — Operator (diese Woche) ===\n\n"
        f"Status: {'OK' if tunnel_stable else 'Token fehlt (control/server.env)'}\n\n"
        "1. Cloudflare Zero Trust → Tunnel → Public Hostname http://127.0.0.1:17890\n"
        "2. control/server.env bearbeiten:\n"
        "   AA_CLOUDFLARE_TUNNEL_TOKEN=<token>\n"
        "   AA_CLOUDFLARE_TUNNEL_URL=https://dein-fester-name.example.com\n"
        "3. bash tools/setup_cloudflare_tunnel_token.sh\n"
        "4. bash tools/king_ops.sh spread-finish-anonym once\n\n"
        f"Wizard: {wiz.get('headline_de', '')}\n"
    )
    (root / _TUNNEL_OP_REL).write_text(tunnel_txt, encoding="utf-8")

    handoff = (
        "=== Externer PC-Worker — Handoff (anonym, Internet-only) ===\n\n"
        f"Status: {'ADOPTION OK' if adoption_ok else 'BEREIT ZUM VERSCHICKEN'}\n"
        f"Stand: {_utc_now()[:10]}\n\n"
        "## Was du jetzt machst\n\n"
        "1. Schick ~/world_worker_LITE.zip + HTTPS-Join an Person mit **eigenem PC**.\n"
        "2. Empfänger entpackt → Windows_START.bat / Linux_START.sh\n"
        "3. Federation muss **fremden** Hostname zeigen.\n\n"
        "## Join (Internet)\n\n"
        f"- Join: {join or '— (spread voll ausführen)'}\n"
        + (f"- Health: curl -fsS {remote}/api/health\n\n" if remote else "\n")
        + "## Dateien\n\n"
        "- Welt-ZIP: ~/world_worker_LITE.zip\n"
        "- WhatsApp: evidence/spread_whatsapp_de.txt\n"
        "- Reddit: evidence/reddit_post_body_ready.txt\n"
    )
    (root / _HANDOFF_REL).write_text(handoff, encoding="utf-8")

    remaining = tick.get("remaining") or []
    blockers = "\n".join(f"- {r.get('blocker_de', '')}: {r.get('befehl', '')}" for r in remaining if isinstance(r, dict))
    status = (
        "=== Operator-Finish — Status (auto-sync) ===\n\n"
        f"Stand: {_utc_now()}\n"
        f"done: {tick.get('done')}\n"
        f"verify: {verify_label}\n"
        f"forum_posted: {forum_posted}\n"
        f"adoption_ok: {adoption_ok}\n"
        f"tunnel_stable: {tunnel_stable}\n"
        f"whatsapp_ok: {whatsapp.get('ok')}\n\n"
        "## Offene Blocker\n\n"
        f"{blockers or '(keine)'}\n\n"
        "## Befehle\n\n"
        "bash tools/king_ops.sh spread-finish-anonym once\n"
        "bash tools/king_ops.sh spread-finish-anonym status\n"
    )
    (root / _STATUS_REL).write_text(status, encoding="utf-8")

    return {
        "finish": _FINISH_REL.as_posix(),
        "federation": _FED_REL.as_posix(),
        "status": _STATUS_REL.as_posix(),
        "handoff": _HANDOFF_REL.as_posix(),
    }
