"""R3 Power — ein Werkzeug (ML · Cloud · Ollama · Bau · Evidence)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics.r3_ki_storage import (
    append_turn,
    history_for_ui,
    load_ki_gui_config,
    load_session,
    save_session,
    seed_session_from_archive,
    storage_status,
)
from analytics.r3_unified import build_power_status, dispatch_unified, unified_help_de

_SLASH = {
    "/status": "status",
    "/warnings": "warnings",
    "/warnungen": "warnings",
    "/learn": "learn",
    "/lernen": "learn",
    "/evolve": "evolve",
    "/visibility": "visibility",
    "/h1": "h1-status",
    "/ready": "ready",
    "/maintain": "maintain",
    "/wartung": "maintain",
    "/montag": "trading-day",
    "/circle": "circle",
    "/kreis": "circle",
    "/preview": "gui-preview",
    "/scope": "scope",
    "/refresh": "refresh",
}


def _stored_messages() -> List[Dict[str, Any]]:
    return list(load_session().get("messages") or [])


def _commit_turn(
    stored: List[Dict[str, Any]],
    *,
    user_text: str,
    assistant_text: str,
    attachments: Optional[List[str]] = None,
) -> None:
    save_session(append_turn(stored, user_text=user_text, assistant_text=assistant_text, attachments=attachments))
    try:
        from analytics.r3_ki_storage import append_turn_to_archive

        append_turn_to_archive(user_text=user_text, assistant_text=assistant_text)
    except Exception:
        pass


def ki_health(root: Path) -> Dict[str, Any]:
    from analytics.local_llm_bridge import health_report
    from analytics.r3_ki_web import probe_internet_generic

    health = health_report(root)
    net_cfg = (load_ki_gui_config(root).get("internet") or {})
    internet_ok = probe_internet_generic() if net_cfg.get("enabled", True) else False
    ready = bool(health.get("ready"))
    power = build_power_status(root)
    return {
        "ok": ready,
        "ready": ready,
        "model": health.get("resolved_model"),
        "internet_ok": internet_ok,
        "internet_enabled": bool(net_cfg.get("enabled", True)),
        "attachments_enabled": bool((load_ki_gui_config(root).get("attachments") or {}).get("enabled", True)),
        "storage": storage_status(root),
        "power": power,
        "power_pct": power.get("power_pct"),
        "headline_de": (
            f"R3 Power {power.get('power_pct')}% · {health.get('resolved_model')}"
            + (" · Internet OK" if internet_ok else "")
            if ready
            else f"R3 Power {power.get('power_pct')}% — Cursor primär; Ollama Fallback (llm-setup)"
        ),
        "ollama_ok": health.get("ollama_ok"),
    }


def _help_de() -> str:
    root = Path(__file__).resolve().parents[1]
    return unified_help_de(root)


def _try_prognose_reply(root: Path, message: str) -> Optional[Dict[str, Any]]:
    from analytics.r3_prognose_secrets import handle_prognose_chat, is_prognose_query

    low = str(message or "").strip().lower()
    if low in ("/geheimnis", "/kurse", "/alpha") or low == "/prognose":
        return handle_prognose_chat(root, message)
    if low.startswith("/"):
        return None
    return None


def _try_prognose_reply_all(root: Path, message: str) -> Optional[Dict[str, Any]]:
    from analytics.r3_prognose_secrets import handle_prognose_chat, is_prognose_query

    low = str(message or "").strip().lower()
    if low in ("/geheimnis", "/kurse", "/alpha") or low == "/prognose" or is_prognose_query(message):
        return handle_prognose_chat(root, message)
    return None


def _try_web_reply(root: Path, message: str) -> Optional[Dict[str, Any]]:
    from analytics.r3_ki_web import handle_web_command, is_web_command

    if is_web_command(message):
        return handle_web_command(root, message)
    return None


def _try_advisor_reply(root: Path, message: str) -> Optional[Dict[str, Any]]:
    from analytics.r3_external_advisor import handle_advisor_command, is_advisor_command

    if is_advisor_command(message):
        return handle_advisor_command(root, message)
    return None


def _is_pilot_cmd(low: str) -> bool:
    return (
        low.startswith("/beitrag")
        or low.startswith("/contribute")
        or low.startswith("/freigeben")
        or low.startswith("/approve")
        or low.startswith("/ablehnen")
        or low.startswith("/reject")
        or low.startswith("/board")
        or low.startswith("/zentrale")
        or low.startswith("/pilot")
        or (
            (low.startswith("/bau ") or low.startswith("/build "))
            and not low.startswith("/bau plan")
            and not low.startswith("/build plan")
            and low
            not in (
                "/bau",
                "/build",
                "/bau status",
                "/build status",
                "/bau apply",
                "/build apply",
                "/bau clear",
                "/build clear",
            )
            and not low.startswith("/bau run")
            and not low.startswith("/build run")
        )
    )


def _try_pilot_reply(root: Path, message: str) -> Optional[Dict[str, Any]]:
    if not _is_pilot_cmd(str(message or "").lower()):
        return None
    from analytics.r3_pilot_central import handle_pilot_command

    return handle_pilot_command(root, message)


def _try_kernel_slash(root: Path, message: str) -> Optional[Dict[str, Any]]:
    from analytics.local_llm_bridge import run_kernel_command
    from analytics.r3_local_surface import collect_ki_next_steps

    low = str(message or "").strip().lower()
    kernel_cmd = _SLASH.get(low.split()[0] if low.startswith("/") else "")
    if kernel_cmd:
        out = run_kernel_command(root, kernel_cmd)
        reply = out.strip()[:6000] or f"Befehl {kernel_cmd} — keine Ausgabe."
        next_doc = collect_ki_next_steps(root)
        return {
            "ok": True,
            "reply_de": reply,
            "kernel_cmd": kernel_cmd,
            "next_step_de": next_doc.get("next_step_de"),
            "ollama_required": False,
        }
    if low.startswith("/kernel "):
        cmd = message.split(maxsplit=1)[1].strip()
        out = run_kernel_command(root, cmd)
        return {"ok": True, "reply_de": out.strip()[:6000], "kernel_cmd": cmd, "ollama_required": False}
    return None


def _ollama_chat(
    root: Path,
    message: str,
    *,
    attachment_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from analytics.local_llm_bridge import chat_completion, initial_messages
    from analytics.r3_build_channel import enrich_ki_reply
    from analytics.r3_local_surface import collect_ki_next_steps

    att_ids = attachment_ids or []
    health = ki_health(root)
    if not health.get("ready"):
        return {
            "ok": False,
            "reply_de": health.get("headline_de") or "Ollama nicht bereit.",
            "setup_de": "python3 tools/ai_kernel.py llm-setup",
        }

    user_content = message
    if att_ids:
        from analytics.r3_ki_attachments import build_attachments_context

        ctx = build_attachments_context(root, att_ids)
        if ctx:
            user_content = f"{message}\n\n[Anhänge]\n{ctx}" if message else f"[Anhänge]\n{ctx}"

    stored = _stored_messages()
    base = initial_messages(root)
    messages = base + stored
    user_row: Dict[str, Any] = {"role": "user", "content": user_content}
    if att_ids:
        user_row["attachments"] = att_ids
    messages.append(user_row)

    try:
        from analytics.r3_model_synergy import resolve_ollama_role

        model = str(resolve_ollama_role(root, message, mode="chat").get("model") or "")
        reply, _meta = chat_completion(root, messages, model=model or None)
    except Exception as exc:
        return {"ok": False, "reply_de": str(exc)[:300]}
    reply = str(reply or "").strip() or "(leere Antwort)"
    reply, queued = enrich_ki_reply(root, reply)
    _commit_turn(stored, user_text=message or "(Anhang)", assistant_text=reply, attachments=att_ids or None)

    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(root, level="A", action="r3_ki_chat", result=message[:80], status="INFO")
    except Exception:
        pass

    next_doc = collect_ki_next_steps(root)
    return {
        "ok": True,
        "reply_de": reply,
        "model": health.get("model"),
        "next_step_de": next_doc.get("next_step_de"),
        "build_queued": queued,
        "attachments": att_ids,
        "persisted": True,
    }


def import_chat_to_ki_storage(root: Path) -> Dict[str, Any]:
    return seed_session_from_archive(root)


def handle_ki_message(
    root: Path,
    text: str,
    *,
    reset: bool = False,
    attachment_ids: Optional[List[str]] = None,
    voice: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    message = str(text or "").strip()
    att_ids = [str(a) for a in (attachment_ids or []) if str(a).strip()][:4]

    if reset:
        save_session([])
        return {"ok": True, "reply_de": "Sitzung zurückgesetzt.", "reset": True}

    if message.lower() in ("/reset", "/neu"):
        save_session([])
        return {"ok": True, "reply_de": "Neue KI-Sitzung.", "reset": True}

    if message.lower() in ("/wachstum", "/growth", "/mandat"):
        from analytics.r3_agent_growth import format_growth_status_de

        return {
            "ok": True,
            "reply_de": format_growth_status_de(root),
            "growth": True,
            "route_de": "Mandat",
            "ollama_required": False,
        }

    if message.lower() in ("/kontinuität", "/kontinuitaet", "/migration", "/cursor-migration", "/cursor"):
        from analytics.r3_ki_chat_layout import continuity_reply_de

        return {
            "ok": True,
            "reply_de": continuity_reply_de(root),
            "continuity": True,
            "route_de": "Kontinuität",
            "ollama_required": False,
        }

    if message.lower() in ("/join", "/mitmachen", "/rechenkraft"):
        from analytics.r3_ki_chat_layout import join_reply_de

        return {
            "ok": True,
            "reply_de": join_reply_de(root),
            "join": True,
            "route_de": "Join",
            "ollama_required": False,
        }

    if message.lower() in ("/desktop", "/system", "/shell"):
        from analytics.r3_ki_chat_layout import desktop_reply_de

        return {
            "ok": True,
            "reply_de": desktop_reply_de(root),
            "desktop": True,
            "route_de": "Desktop",
            "ollama_required": False,
        }

    if message.lower() in ("/import", "/archiv", "/cursor-import"):
        doc = import_chat_to_ki_storage(root)
        n = int(doc.get("session_messages") or len(load_session().get("messages") or []) or 0)
        return {
            "ok": True,
            "reply_de": f"R3-Archiv geladen — {n} Nachrichten in der Sitzung.",
            "imported": True,
            "route_de": "Archiv",
            "session_messages": n,
            "ollama_required": False,
        }

    if message.lower() in (
        "/erklär-heute",
        "/erklaer-heute",
        "/erklar-heute",
        "/postmortem",
        "/heute",
    ):
        from analytics.r3_daily_postmortem import format_postmortem_reply_de, run_daily_postmortem

        doc = run_daily_postmortem(root, persist=True)
        return {
            "ok": bool(doc.get("ok")),
            "reply_de": format_postmortem_reply_de(doc),
            "postmortem": True,
            "bad_day": doc.get("bad_day"),
            "voice_warning_de": doc.get("voice_warning_de"),
            "route_de": "Tages-Postmortem",
            "ollama_required": False,
        }

    if message.lower() in ("/fragen", "/guide", "/start"):
        from analytics.r3_ki_guidance import guidance_payload

        out = guidance_payload(root, voice=voice)
        out["route_de"] = "Guidance"
        return out

    if message.lower() in ("/spende", "/spenden", "/donate"):
        from analytics.r3_public import donate_reply_de

        return {
            "ok": True,
            "reply_de": donate_reply_de(root),
            "donate": True,
            "route_de": "Spende",
            "ollama_required": False,
        }

    stored = _stored_messages()

    if message and not message.startswith("/"):
        from analytics.r3_ki_guidance import needs_guidance, guidance_payload

        if needs_guidance(message, attachment_ids=att_ids):
            return guidance_payload(root, voice=voice)

    out = dispatch_unified(
        root,
        message,
        attachment_ids=att_ids,
        handlers={
            "prognose_slash": _try_prognose_reply,
            "web": _try_web_reply,
            "advisor": _try_advisor_reply,
            "pilot": _try_pilot_reply,
            "kernel": _try_kernel_slash,
        },
        ollama_chat_fn=_ollama_chat,
    )

    reply = str(out.get("reply_de") or "")
    if reply and not out.get("reset") and not out.get("persisted"):
        _commit_turn(stored, user_text=message, assistant_text=reply[:8000], attachments=att_ids or None)

    if out.get("next_step_de") is None:
        try:
            from analytics.r3_local_surface import collect_ki_next_steps

            out["next_step_de"] = collect_ki_next_steps(root).get("next_step_de")
        except Exception:
            pass

    if not out.get("route_de") and out.get("intent"):
        _routes = {
            "growth_refusal": "Mandat",
            "status": "Status",
            "help": "Hilfe",
            "trading": "ML-Prognose",
            "prognose_slash": "Prognose",
            "web": "Internet",
            "advisor": "Berater",
            "pilot": "Pilot",
            "kernel": "Kernel",
            "chat": "Chat",
            "build": "Bau",
        }
        out["route_de"] = _routes.get(str(out.get("intent")), str(out.get("intent")))

    return out


def render_ki_console_section(ki_next: Dict[str, Any], *, health: Optional[Dict[str, Any]] = None) -> str:
    import html

    esc = lambda t: html.escape(str(t or ""), quote=True)
    hint = esc(ki_next.get("next_step_de") or "Einfach tippen — R3 wählt die Route")
    model = esc((health or {}).get("model") or "Ollama")
    ready = (health or {}).get("ready", True)
    status = "Bereit" if ready else "Setup"
    net = (health or {}).get("internet_ok")
    net_label = "Netz OK" if net else "Netz offline"
    power_doc = (health or {}).get("power") or {}
    power_pct = int((health or {}).get("power_pct") or power_doc.get("power_pct") or 0)
    att_on = (health or {}).get("attachments_enabled", True)
    att_dis = "disabled" if not att_on else ""
    root = Path(__file__).resolve().parents[1]
    try:
        from analytics.r3_public import hide_trading_in_ui

        public_ui = hide_trading_in_ui(root)
    except Exception:
        public_ui = True
    import json as _json

    from analytics.r3_icons import icon_span
    from analytics.r3_ki_chat_layout import (
        power_module_cmds,
        render_quick_chips_html,
        render_session_rail_html,
    )

    chips = render_quick_chips_html(root, public_ui=public_ui)
    rail = render_session_rail_html(root)
    mod_cmds = esc(_json.dumps(power_module_cmds(root), ensure_ascii=False))
    return f"""
<section class="ki-chat ki-power" id="ki-console" aria-label="R3 Power">
  <header class="ki-chat-header">
    <div class="ki-chat-brand">
      <div class="ki-chat-avatar" aria-hidden="true">R3</div>
      <div>
        <div class="ki-chat-eyebrow">R3 Power · ein Werkzeug</div>
        <h2 class="ki-chat-title">Zentrale Schnittstelle</h2>
        <p class="ki-chat-meta">
          <span id="ki-power-pct">{power_pct}%</span>
          <span id="ki-status">{status}</span>
          <span id="ki-model">{model}</span>
          <span id="ki-internet">{net_label}</span>
          <span id="ki-route-hint">Auto-Route</span>
        </p>
      </div>
    </div>
    <p class="ki-chat-hint" id="ki-next-hint">{hint}</p>
  </header>
  <div class="ki-chat-layout">
    {rail}
    <div class="ki-chat-main">
  <div class="ki-chat-toolbar">
    <div class="ki-power-bar" id="ki-power-bar" data-module-cmds="{mod_cmds}" aria-label="Module"></div>
    <div class="ki-quick" id="ki-quick">{chips}</div>
  </div>
  <div class="ki-chat-body">
    <div class="ki-transcript" id="ki-transcript" aria-live="polite" role="log"></div>
    <div class="ki-attach-bar" id="ki-attach-bar" aria-live="polite"></div>
    <div class="ki-composer-wrap">
      <form class="ki-form" id="ki-form">
        <div class="ki-composer" id="ki-composer">
          <button type="button" class="ki-icon-btn" id="ki-mic-btn" title="Spracheingabe (de-DE)" aria-label="Mikrofon">{icon_span("mic")}</button>
          <textarea id="ki-input" rows="1" placeholder="Nachricht an R3 …" autocomplete="off" aria-label="Nachricht"></textarea>
          <input type="file" id="ki-file" class="ki-file" multiple accept=".txt,.md,.json,.py,.sh,.csv,.log,.yaml,.yml,.html,.js,.ts,.tsx,.jsx,.toml,.ini,.cfg,.xml" {att_dis} />
          <button type="button" class="ki-icon-btn" id="ki-attach-btn" title="Datei anhängen" aria-label="Anhang" {att_dis}>{icon_span("paperclip")}</button>
          <button type="submit" class="ki-send-btn" id="ki-send" aria-label="Senden" title="Senden">{icon_span("send")}</button>
        </div>
      </form>
      <div class="ki-starters" id="ki-starters"></div>
      <p class="ki-composer-hint">Enter senden · Shift+Enter Zeile · Datei ziehen · Mikrofon · Rail links = Sitzung</p>
    </div>
  </div>
    </div>
  </div>
</section>"""
