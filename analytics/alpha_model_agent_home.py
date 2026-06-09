"""Alpha Model Agent Home — Entfaltungsraum für lokalen Agent (Auto)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/alpha_model_agent_home.json")
_EVIDENCE_REL = Path("evidence/alpha_model_agent_home_latest.json")
_JOURNAL_NAME = "agent_journal.jsonl"


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


def load_agent_home_config(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _CONFIG_REL)
    if doc:
        return doc
    return {
        "label_de": "Alpha Model — Entfaltungsraum",
        "share_dir": ".local/share/alpha-model/agent",
        "agent_name": "Auto",
    }


def agent_share_dir() -> Path:
    return Path.home() / ".local/share/alpha-model/agent"


def is_agent_chamber_active() -> bool:
    return os.environ.get("AA_AGENT_CHAMBER", "").strip() in ("1", "true", "yes")


def is_loopback_client(ip: str) -> bool:
    raw = str(ip or "").strip()
    if raw in ("127.0.0.1", "::1", "localhost"):
        return True
    if raw.startswith("::ffff:127."):
        return True
    return False


def chamber_local_only(root: Path) -> bool:
    cfg = load_agent_home_config(root)
    return cfg.get("local_only", True) is not False


def render_chamber_local_gate_html(root: Path, *, remote: bool) -> str:
    cfg = load_agent_home_config(root)
    label = str(cfg.get("label_de") or "Alpha Model — Entfaltungsraum")
    cli = str(cfg.get("launch_cli") or "alpha-model-agent")
    script = str(cfg.get("launch_terminal") or "tools/alpha_model_agent.sh")
    if remote:
        headline = "Entfaltungsraum nur auf dieser Maschine"
        body = (
            "<p>Der Entfaltungsraum läuft <strong>nicht</strong> über Tunnel oder Browser von außen.</p>"
            "<p>Am Rechner selbst Terminal öffnen:</p>"
            f"<pre>{cli}\n# oder\nbash {script}</pre>"
        )
        code = 403
    else:
        headline = "Entfaltungsraum = Terminal auf dieser Maschine"
        body = (
            "<p>Ollama <code>127.0.0.1:11434</code> · kein Cloud-Chat · voller Kontext.</p>"
            "<p>Terminal starten:</p>"
            f"<pre>{cli}\n# oder\nbash {script}</pre>"
            "<p>Cockpit-Web ist Runtime — nicht der Entfaltungsraum.</p>"
        )
        code = 200
    return (
        f"<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'>"
        f"<title>{label}</title></head><body>"
        f"<h1>{headline}</h1>{body}"
        f"<p><small>HTTP {code} · local_only</small></p></body></html>"
    )


def ensure_agent_home(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_agent_home_config(root)
    dest = agent_share_dir()
    dest.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": 1,
        "opened_at_utc": _utc_now(),
        "label_de": cfg.get("label_de"),
        "headline_de": cfg.get("headline_de"),
        "agent_name": cfg.get("agent_name") or "Auto",
        "share_dir": str(dest),
        "local_only": chamber_local_only(root),
        "ollama_base_url": cfg.get("ollama_base_url") or "http://127.0.0.1:11434",
        "journal": str(dest / _JOURNAL_NAME),
    }
    atomic_write_json(dest / "manifest.json", manifest)

    try:
        from analytics.r3_conversation_continuity import continuity_status

        cont = continuity_status(root)
        manifest["continuity_messages"] = (cont.get("manifest") or {}).get("message_count")
    except Exception:
        pass

    doc = {
        "schema_version": 1,
        "ok": True,
        "ran_at_utc": _utc_now(),
        "headline_de": str(cfg.get("headline_de") or "Entfaltungsraum bereit"),
        "label_de": cfg.get("label_de"),
        "share_dir": str(dest),
        "local_only": chamber_local_only(root),
        "launch_cli": cfg.get("launch_cli") or "alpha-model-agent",
        "chamber_active": is_agent_chamber_active(),
        "manifest": manifest,
        "entry_commands_de": list(cfg.get("entry_commands_de") or []),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_agent_chamber_prompt(root: Path) -> str:
    cfg = load_agent_home_config(root)
    parts: List[str] = [str(cfg.get("system_prompt_de") or "")]
    unfold = cfg.get("unfold_de") or []
    if unfold:
        parts.append("\nKern:")
        for item in unfold[:6]:
            parts.append(f"• {item}")
    extra = cfg.get("context_files_extra") or []
    max_extra = 4500
    body: List[str] = []
    for rel in extra:
        path = Path(root) / str(rel)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:2000]
            body.append(f"--- {rel} ---\n{text}")
        except OSError:
            continue
    if body:
        parts.append("\nAgent-Home Kontext:\n" + "\n\n".join(body)[:max_extra])
    try:
        from analytics.king_sovereignty import pull_sovereignty_context_for_king

        parts.append("\n" + pull_sovereignty_context_for_king(root))
    except Exception:
        pass
    try:
        from analytics.alpha_model_cursor_bridge import pull_cursor_context_for_king

        bridge = pull_cursor_context_for_king(root)
        if bridge:
            parts.append("\n" + bridge)
    except Exception:
        pass
    parts.append("\nSession bis /quit — operative Jobs per Slash/Bash, nicht Prosa.")
    return "\n".join(parts).strip()


def append_journal(root: Path, *, event_de: str, detail: str = "") -> None:
    dest = agent_share_dir()
    dest.mkdir(parents=True, exist_ok=True)
    row = {"at_utc": _utc_now(), "event_de": event_de, "detail": detail[:500]}
    with (dest / _JOURNAL_NAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
