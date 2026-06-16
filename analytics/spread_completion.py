"""Spread-Abschluss — alles Automatisierbare ausführen, Rest als Fakten."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/spread_completion_latest.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_spread_completion(
    root: Path,
    *,
    wait_tunnel_s: int = 0,
    anonym: bool | None = None,
) -> Dict[str, Any]:
    """Letzte Spread-Schritte: reparieren, öffnen, messen — ohne Fakes."""
    root = Path(root)
    if anonym is None:
        from analytics.spread_anonym_policy import is_anonym_enforced

        anonym = is_anonym_enforced(root)
    if anonym:
        from analytics.spread_finish_anonym_loop import run_anonym_finish_tick

        tick = run_anonym_finish_tick(root, iteration=1, execute_whatsapp=True)
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": tick.get("done"),
            "done": tick.get("done"),
            "anonym": True,
            "facts": tick.get("facts"),
            "steps": tick.get("steps"),
            "remaining": tick.get("remaining"),
            "headline_de": tick.get("headline_de"),
        }
        atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    steps: List[Dict[str, Any]] = []

    try:
        from analytics.local_control import assume_local_control

        lc = assume_local_control(root, repair=True)
        steps.append({"step": "local_control", "ok": lc.get("ok")})
    except Exception as exc:
        steps.append({"step": "local_control", "ok": False, "error": str(exc)[:120]})

    try:
        from analytics.tunnel_control import tunnel_control_try_apply, tunnel_control_setup

        if wait_tunnel_s > 0:
            tunnel_control_setup(root, wait_s=min(120, wait_tunnel_s))
            deadline = time.monotonic() + wait_tunnel_s
            while time.monotonic() < deadline:
                applied = tunnel_control_try_apply(root, silent=True)
                if applied.get("ok"):
                    steps.append({"step": "tunnel_stable", "ok": True, "method": applied.get("method")})
                    break
                time.sleep(10)
        else:
            applied = tunnel_control_try_apply(root, silent=False)
            steps.append({"step": "tunnel_try_apply", "ok": applied.get("ok"), "detail": applied.get("message_de")})
    except Exception as exc:
        steps.append({"step": "tunnel", "ok": False, "error": str(exc)[:120]})

    try:
        from analytics.reddit_forum_post import open_reddit_submit

        reddit = open_reddit_submit(root)
        steps.append({"step": "reddit_open", "ok": reddit.get("ok")})
    except Exception as exc:
        steps.append({"step": "reddit_open", "ok": False, "error": str(exc)[:120]})

    try:
        from analytics.spread_secure_ops import run_spread_efficient

        spread = run_spread_efficient(root, mode="voll")
        steps.append({"step": "spread_voll", "ok": spread.get("ok")})
    except Exception as exc:
        spread = {"ok": False}
        steps.append({"step": "spread_voll", "ok": False, "error": str(exc)[:120]})

    from analytics.spread_secure_ops import build_spread_facts

    facts = build_spread_facts(root, progress=spread.get("progress"), security=spread.get("security_final"))
    remaining: List[Dict[str, str]] = []

    if not facts.get("tunnel_stable"):
        remaining.append(
            {
                "id": "C_tunnel",
                "blocker_de": "Cloudflare-Token fehlt — Tresor/Browser (Passwort nur dort)",
                "befehl": "bash tools/king_ops.sh tunnel-stable setup",
            }
        )
    if not facts.get("forum_posted"):
        remaining.append(
            {
                "id": "B_reddit",
                "blocker_de": "Reddit-Post + forum-ack mit echter URL",
                "befehl": (
                    "Post in geöffneten Tabs → "
                    "AA_FORUM_POST_URL='https://…' bash tools/king_ops.sh forum-ack"
                ),
            }
        )
    if int(facts.get("remote_compute_workers") or 0) < 1:
        remaining.append(
            {
                "id": "A_adoption",
                "blocker_de": "Externer PC muss ~/world_worker_LITE.zip freiwillig starten",
                "befehl": "ZIP + evidence/spread_whatsapp_de.txt an Menschen mit eigenem PC",
            }
        )

    done = not remaining
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": done,
        "done": done,
        "facts": facts,
        "steps": steps,
        "remaining": remaining,
        "headline_de": (
            "Spread abgeschlossen — alle Messpunkte grün"
            if done
            else f"Spread — {len(remaining)} Schritt(e) brauchen dich (keine Fakes möglich)"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
