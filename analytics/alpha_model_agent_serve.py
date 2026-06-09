"""Dauerhafter Entfaltungsraum-Dienst — Agent wird immer bedient, startet neu statt zu sterben."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_SERVE_REL = Path("evidence/alpha_model_agent_serve_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log_serve_event(root: Path, event_de: str, **extra: Any) -> None:
    root = Path(root)
    try:
        from analytics.alpha_model_agent_home import append_journal

        append_journal(root, event_de=event_de, detail=json.dumps(extra, ensure_ascii=False)[:500])
    except Exception:
        pass
    doc = {
        "event_de": event_de,
        "at_utc": _utc_now(),
        **extra,
    }
    try:
        from aa_safe_io import atomic_write_json

        atomic_write_json(root / _SERVE_REL, doc)
    except Exception:
        pass


def run_agent_serve(
    root: Path,
    *,
    repl_fn,
    model: Optional[str] = None,
    restart_delay_s: float = 0.0,
    ollama_retry_s: float = 10.0,
) -> int:
    """
    Bedient den Agenten dauerhaft.
    repl_fn(root, *, model, serve_mode) -> int
      0 = Session-Ende (ohne Serve) / 1 = Session neu / 2 = Ollama fehlt / 3 = Dienst-Stopp
    """
    root = Path(root)
    log_serve_event(root, "Dienst gestartet — Agent wird dauerhaft bedient")
    print(
        "[Agent-Dienst] Läuft dauerhaft — /quit = neue Session · /dienst-stop = Dienst beenden\n",
        flush=True,
    )
    restarts = 0
    while True:
        rc = repl_fn(root, model=model, serve_mode=True)
        if rc == 3:
            log_serve_event(root, "Dienst beendet", reason="dienst-stop")
            print("\n[Agent-Dienst] Beendet. Zum Fortsetzen: alpha-model-agent\n", flush=True)
            return 0
        if rc == 2:
            print(
                f"\n[Agent-Dienst] Ollama nicht bereit — erneuter Versuch in {int(ollama_retry_s)}s …\n",
                flush=True,
            )
            log_serve_event(root, "Ollama wartet", retry_s=ollama_retry_s)
            time.sleep(ollama_retry_s)
            continue
        if rc in (0, 1):
            restarts += 1
            log_serve_event(root, "Session neu", restarts=restarts, rc=rc)
            print(
                f"\n[Agent-Dienst] Bleibe beim Agenten — neue Session in {int(restart_delay_s)}s "
                f"(#{restarts}) · /dienst-stop zum Beenden\n",
                flush=True,
            )
            time.sleep(restart_delay_s)
            continue
        restarts += 1
        log_serve_event(root, "Unerwarteter Exit — Neustart", rc=rc, restarts=restarts)
        time.sleep(restart_delay_s)
