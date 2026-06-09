"""What Auto is doing on Ubuntu — visible operator trace for dashboard."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_TIMERS_REL = Path("control/linux_operator_timers.json")
_ACTIONS_REL = Path("evidence/linux_operator_actions.jsonl")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_scheduled_timers(root: Path) -> List[Dict[str, str]]:
    doc = _load_json(Path(root) / _TIMERS_REL)
    return list(doc.get("timers") or [])


def load_operator_action_lines(root: Path, *, limit: int = 12) -> List[str]:
    path = Path(root) / _ACTIONS_REL
    if not path.is_file():
        return []
    lines_out: List[str] = []
    raw = path.read_text(encoding="utf-8").strip().splitlines()
    for line in raw[-limit:]:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        at = str(entry.get("at_utc") or "")[:19].replace("T", " ")
        level = str(entry.get("level") or "?")
        action = str(entry.get("action") or "")
        result = str(entry.get("result") or "")
        agent = str(entry.get("agent") or "Auto")
        lines_out.append(f"{at} [{level}] {agent}: {action} → {result}"[:220])
    return lines_out


def systemd_timer_next_lines() -> List[str]:
    """Best-effort next fire times from user systemd."""
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "list-timers", "active-alpha-*", "--no-pager"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if proc.returncode != 0:
            return []
        out: List[str] = []
        for line in (proc.stdout or "").splitlines():
            if "active-alpha-" not in line or "NEXT" in line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0].replace("active-alpha-", "").replace(".timer", "")
                nxt = " ".join(parts[1:3]) if len(parts) > 2 else parts[1]
                out.append(f"⏱ {name}: {nxt}")
        return out[:6]
    except Exception:
        return []


def notify_desktop_if_available(title: str, body: str) -> bool:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    try:
        proc = subprocess.run(
            ["notify-send", "-a", "R3", "-i", "r3-os", title, body[:180]],
            capture_output=True,
            timeout=3,
        )
        return proc.returncode == 0
    except Exception:
        return False


def build_visibility_snapshot(root: Path) -> Dict[str, Any]:
    root = Path(root)
    try:
        from analytics.operator_public_status import load_public_capabilities

        caps = load_public_capabilities(root)
    except Exception:
        caps = {}
    try:
        from analytics.linux_operator_scope import scope_summary_de

        scope = scope_summary_de(root)
    except Exception:
        scope = {}
    try:
        from analytics.h1_governance_status import load_h1_governance_status

        h1 = load_h1_governance_status(root)
    except Exception:
        h1 = {}
    cockpit_next = ""
    circle: Dict[str, Any] = {}
    try:
        import json

        from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

        doc = load_trading_day_cockpit_doc(root)
        if doc:
            cockpit_next = str(doc.get("next_step_de") or "")
            circle = dict(doc.get("circle_score") or {})
    except Exception:
        pass
    if not circle:
        try:
            from analytics.closed_loop_score import load_closed_loop_score

            circle = load_closed_loop_score(root)
        except Exception:
            circle = {}
    timers_cfg = load_scheduled_timers(root)
    systemd_next = systemd_timer_next_lines()
    actions = load_operator_action_lines(root, limit=10)
    headline = "Auto arbeitet im Hintergrund — Details unten und im Activity-Log."
    if actions:
        headline = f"Letzte Aktion: {actions[-1].split(':', 1)[-1].strip()[:100]}"
    if circle.get("headline_de"):
        bn = circle.get("bottleneck_de") or ""
        headline = f"{circle['headline_de']}" + (f" · {bn}" if bn else "")
    chat_next = ""
    try:
        from analytics.chat_evolution_preview import load_chat_evolution_preview

        chat_doc = load_chat_evolution_preview(root)
        chat_next = str(chat_doc.get("next_step_de") or "").strip()
    except Exception:
        pass
    return {
        "generated_at_local": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "headline_de": headline,
        "scope_lines_de": scope.get("summary_lines_de") or [],
        "scheduled_timers": timers_cfg,
        "systemd_next_de": systemd_next,
        "operator_actions_de": actions,
        "h1_status_de": f"H1: {h1.get('status', '—')} ({h1.get('run_dir') or '—'})",
        "h1_banner_de": h1.get("banner_de"),
        "cockpit_next_step_de": cockpit_next,
        "circle_score": circle,
        "circle_headline_de": circle.get("headline_de"),
        "circle_bottleneck_de": circle.get("bottleneck_de"),
        "chat_evolution_next_de": chat_next or None,
        "surface_note_de": "Alles über R3 Cockpit · Arbeitsfläche für System-Apps. Orders nur mit Ihrem Klick.",
        "can_do_de": list(caps.get("can_do_de") or [])[:6],
        "cannot_do_de": list(caps.get("cannot_do_de") or [])[:4],
        "how_to_see_de": list(caps.get("how_to_see_de") or []),
        "evolution_platform_de": caps.get("evolution_platform_de"),
    }


def format_visibility_text(snapshot: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.append(snapshot.get("headline_de") or "")
    parts.append(snapshot.get("h1_status_de") or "")
    for line in snapshot.get("scope_lines_de") or []:
        parts.append(line)
    for t in snapshot.get("scheduled_timers") or []:
        parts.append(f"⏱ {t.get('label_de')}: {t.get('schedule_de')} ({t.get('command')})")
    for line in snapshot.get("systemd_next_de") or []:
        parts.append(line)
    parts.append("— Letzte Operator-Aktionen —")
    for line in snapshot.get("operator_actions_de") or []:
        parts.append(line)
    return "\n".join(p for p in parts if p)
