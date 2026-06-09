"""R3 Power — ein Werkzeug, alle Kanäle (ML · Cloud · Ollama · Bau)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_CONFIG_REL = Path("control/r3_unified.json")
_EVIDENCE_REL = Path("evidence/r3_unified_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def load_unified_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {"auto_route_freetext": True}


def classify_intent(message: str, *, root: Optional[Path] = None) -> str:
    raw = str(message or "").strip()
    low = raw.lower()
    if not low:
        return "empty"
    if low.startswith("/"):
        return "slash"

    cfg = load_unified_config(root or Path("."))
    for verb in cfg.get("build_strong_verbs") or []:
        if verb in low:
            return "build_strong"
    for verb in cfg.get("status_verbs") or []:
        if re.search(rf"\b{re.escape(verb.strip())}\b", low):
            return "status"

    try:
        from analytics.r3_prognose_secrets import is_prognose_query

        if is_prognose_query(raw):
            return "trading"
    except Exception:
        pass

    try:
        from analytics.r3_model_synergy import classify_task

        task = classify_task(raw, mode="kombi")
        if task == "plan":
            return "build"
        if task in ("deep", "trading"):
            return "advisor_kombi"
    except Exception:
        pass

    if re.search(r"\b(bau|build|code|test|pytest|modul|api|ui)\b", low):
        return "build"

    return "chat"


def build_power_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_unified_config(root)
    modules: List[Dict[str, Any]] = []

    # ML / Prognose
    ml_ok = False
    ml_detail = ""
    try:
        from analytics.r3_prognose_secrets import build_prognose_secrets_doc

        doc = build_prognose_secrets_doc(root)
        ml_ok = bool(doc.get("top_picks"))
        ml_detail = f"{doc.get('champion_id')} · {doc.get('signal_date')}"
    except Exception as exc:
        ml_detail = str(exc)[:80]

    modules.append({"id": "ml", "ok": ml_ok, "detail_de": ml_detail or "trading-day"})

    # Ollama
    ollama_ok = False
    ollama_model = ""
    try:
        from analytics.local_llm_bridge import health_report

        h = health_report(root)
        ollama_ok = bool(h.get("ready"))
        ollama_model = str(h.get("resolved_model") or "")
    except Exception:
        pass
    modules.append({"id": "ollama", "ok": ollama_ok, "detail_de": ollama_model or "llm-setup"})

    # Cloud
    cloud_ok = False
    cloud_model = ""
    try:
        from analytics.r3_external_advisor import advisor_status

        a = advisor_status(root)
        cloud_ok = bool(a.get("configured"))
        tiers = (a.get("synergy") or {}).get("openai_tiers") or {}
        cloud_model = f"fast={tiers.get('fast', '?')} deep={tiers.get('deep', '?')}"
    except Exception:
        pass
    modules.append({"id": "cloud", "ok": cloud_ok, "detail_de": cloud_model or "OPENAI_API_KEY"})

    # Build kernel
    build_ok = ollama_ok
    build_ev = (root / "evidence/r3_build_kernel_latest.json").is_file()
    modules.append(
        {
            "id": "build",
            "ok": build_ok,
            "detail_de": "Lauf vorhanden" if build_ev else "/bau · /beitrag",
        }
    )

    # Pilot
    pilot_open = 0
    try:
        from analytics.r3_pilot_central import build_pilot_board_doc

        board = build_pilot_board_doc(root)
        pilot_open = len([x for x in (board.get("queue") or []) if x.get("status") != "live"])
    except Exception:
        pass
    modules.append({"id": "pilot", "ok": True, "detail_de": f"{pilot_open} in Queue"})

    # Storage
    storage_ok = False
    msgs = 0
    try:
        from analytics.r3_ki_storage import storage_status

        st = storage_status(root)
        storage_ok = bool(st.get("message_count", 0))
        msgs = int(st.get("message_count") or 0)
    except Exception:
        pass
    modules.append({"id": "storage", "ok": storage_ok, "detail_de": f"{msgs} Nachrichten"})

    # Internet
    net_ok = False
    try:
        from analytics.r3_ki_web import probe_internet_generic

        net_ok = probe_internet_generic()
    except Exception:
        pass

    ok_count = sum(1 for m in modules if m.get("ok"))
    power_pct = int(round(100 * ok_count / max(len(modules), 1)))

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "name_de": cfg.get("name_de", "R3 Power"),
        "headline_de": cfg.get("headline_de"),
        "tagline_de": cfg.get("tagline_de"),
        "power_pct": power_pct,
        "modules": modules,
        "internet_ok": net_ok,
        "auto_route": bool(cfg.get("auto_route_freetext")),
        "intent_hint_de": "Freitext → Trading/Status/Bau/Kombi automatisch",
        "commands_de": "Freitext · /r3 · /geheimnis · /beitrag · /kombi · /bau",
    }
    try:
        from aa_safe_io import atomic_write_json

        atomic_write_json(root / _EVIDENCE_REL, doc)
    except Exception:
        pass
    return doc


def format_power_status_de(root: Path) -> str:
    st = build_power_status(root)
    lines = [
        f"⚡ {st.get('name_de')} — {st.get('power_pct')}%",
        str(st.get("headline_de") or ""),
        str(st.get("tagline_de") or ""),
        "",
        "Module:",
    ]
    labels = {
        "ml": "Trading-ML",
        "ollama": "Ollama",
        "cloud": "Cloud-Berater",
        "build": "Bau-Kernel",
        "pilot": "Pilot",
        "storage": "Speicher",
    }
    for m in st.get("modules") or []:
        mark = "✓" if m.get("ok") else "○"
        lines.append(f"  {mark} {labels.get(m.get('id'), m.get('id'))}: {m.get('detail_de')}")
    lines.extend(
        [
            "",
            f"Internet: {'OK' if st.get('internet_ok') else 'offline'}",
            f"Auto-Route: {'an' if st.get('auto_route') else 'aus'}",
            "",
            "Einfach tippen — R3 wählt die Route.",
            "  Trading → ML-Prognose",
            "  Bau stark → /beitrag (Kernel+Test)",
            "  Sonst → /kombi (Cloud+Ollama) oder Ollama",
        ]
    )
    return "\n".join(lines)


def unified_help_de(root: Path) -> str:
    cfg = load_unified_config(root)
    return (
        f"{cfg.get('name_de')} — ein Werkzeug für alles.\n"
        f"{cfg.get('tagline_de')}\n\n"
        "Freitext (Auto-Route):\n"
        "  Aktien/Prognose → ML-Signale (schnell)\n"
        "  implementiere/baue/fix → Pilot+Bau-Kernel\n"
        "  status/warnung → ai_kernel\n"
        "  alles andere → Kombi (Cloud+Ollama) wenn Key da\n\n"
        "Direkt: /r3 /geheimnis /beitrag /kombi /bau /status /synergie\n"
        "CLI: python3 tools/ai_kernel.py r3 [nachricht]\n"
    )


def _wrap(intent: str, out: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(out)
    out["unified"] = True
    out["intent"] = intent
    return out


def dispatch_freetext(
    root: Path,
    message: str,
    *,
    attachment_ids: Optional[List[str]] = None,
    ollama_chat_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Intelligente Freitext-Route — Herzstück R3 Power."""
    root = Path(root)
    cfg = load_unified_config(root)
    if not cfg.get("auto_route_freetext", True):
        if ollama_chat_fn:
            return ollama_chat_fn(root, message, attachment_ids=attachment_ids)
        return {"ok": False, "reply_de": "Auto-Route aus — Slash-Befehl nutzen"}

    intent = classify_intent(message, root=root)
    att = attachment_ids

    if intent == "trading":
        from analytics.r3_prognose_secrets import handle_prognose_chat

        out = handle_prognose_chat(root, message)
        reply = str(out.get("reply_de") or "")
        header = "⚡ R3 Power · Trading-ML\n\n"
        return _wrap(intent, {**out, "reply_de": header + reply, "route_de": "ML-Prognose"})

    if intent == "status":
        from analytics.local_llm_bridge import run_kernel_command

        out = run_kernel_command(root, "status")
        return _wrap(
            intent,
            {
                "ok": True,
                "reply_de": "⚡ R3 Power · Status\n\n" + (out or "")[:6000],
                "route_de": "ai_kernel status",
                "ollama_required": False,
            },
        )

    if intent == "build_strong":
        from analytics.r3_pilot_central import handle_pilot_command

        mandate = message if not message.lower().startswith("/beitrag") else message.split(maxsplit=1)[-1]
        out = handle_pilot_command(root, f"/beitrag {mandate}")
        reply = str(out.get("reply_de") or "")
        return _wrap(
            intent,
            {
                **out,
                "reply_de": "⚡ R3 Power · Bau+Test\n\n" + reply,
                "route_de": "Pilot → Bau-Kernel → pytest",
                "pilot": True,
            },
        )

    if intent == "build":
        from analytics.r3_external_advisor import handle_advisor_command, resolve_openai_api_key

        key, _ = resolve_openai_api_key(root)
        if key:
            out = handle_advisor_command(root, f"/kombi {message}")
            reply = str(out.get("reply_de") or "")
            return _wrap(
                intent,
                {
                    **out,
                    "reply_de": reply + "\n\n→ Umsetzen: /beitrag " + message[:200],
                    "route_de": "Kombi + Bau-Hinweis",
                },
            )

    if intent == "advisor_kombi":
        from analytics.r3_external_advisor import handle_advisor_command, resolve_openai_api_key

        key, _ = resolve_openai_api_key(root)
        if key:
            out = handle_advisor_command(root, f"/kombi {message}")
            return _wrap(intent, {**out, "route_de": "Kombi (deep/trading)"})

    # Default power pipeline
    pipeline = list(cfg.get("default_pipeline") or ["kombi", "ollama", "prognose"])
    for step in pipeline:
        if step == "cursor_handoff":
            try:
                from analytics.alpha_model_interface_kernel import should_use_ollama_fallback

                if not should_use_ollama_fallback(root):
                    from analytics.r3_desktop_migration import cursor_handoff_reply_de

                    return _wrap(
                        "chat",
                        {
                            "ok": True,
                            "reply_de": cursor_handoff_reply_de(root),
                            "route_de": "R3 KI lokal",
                            "ollama_required": True,
                            "local_primary": True,
                        },
                    )
            except Exception:
                pass
            continue
        if step == "kombi":
            from analytics.r3_external_advisor import handle_advisor_command, resolve_openai_api_key

            key, _ = resolve_openai_api_key(root)
            if key:
                try:
                    from analytics.local_llm_bridge import health_report

                    if health_report(root).get("ready"):
                        out = handle_advisor_command(root, f"/kombi {message}")
                        if out.get("ok"):
                            return _wrap("chat", {**out, "route_de": "Kombi (Standard)"})
                except Exception:
                    pass
        if step == "ollama" and ollama_chat_fn:
            try:
                from analytics.alpha_model_interface_kernel import should_use_ollama_fallback

                if not should_use_ollama_fallback(root):
                    continue
            except Exception:
                pass
            out = ollama_chat_fn(root, message, attachment_ids=att)
            if out.get("ok"):
                return _wrap("chat", {**out, "route_de": "Ollama"})
        if step == "prognose":
            from analytics.r3_prognose_secrets import is_prognose_query, handle_prognose_chat

            if is_prognose_query(message):
                out = handle_prognose_chat(root, message)
                return _wrap("trading", {**out, "route_de": "ML-Fallback"})

    return _wrap(
        "blocked",
        {
            "ok": False,
            "reply_de": format_power_status_de(root) + "\n\nSetup: llm-setup + OPENAI_API_KEY",
            "route_de": "Hinweis",
        },
    )


def dispatch_unified(
    root: Path,
    message: str,
    *,
    attachment_ids: Optional[List[str]] = None,
    handlers: Optional[Dict[str, Callable[..., Optional[Dict[str, Any]]]]] = None,
    ollama_chat_fn: Optional[Callable[..., Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Zentraler Router — von handle_ki_message aufgerufen."""
    root = Path(root)
    raw = str(message or "").strip()
    low = raw.lower()

    if raw and not raw.startswith("/"):
        try:
            from analytics.r3_agent_growth import assess_request, build_refusal_reply

            gate = assess_request(root, raw)
            if gate.get("refused"):
                return _wrap(
                    "growth_refusal",
                    {
                        "ok": True,
                        "refused": True,
                        "growth": True,
                        "category_id": gate.get("category_id"),
                        "reply_de": build_refusal_reply(root, gate),
                        "ollama_required": False,
                    },
                )
        except Exception:
            pass

    if low in ("/r3", "/power", "/werkzeug"):
        return _wrap("status", {"ok": True, "reply_de": format_power_status_de(root), "power": build_power_status(root)})

    if low in ("/hilfe", "/help"):
        return _wrap("help", {"ok": True, "reply_de": unified_help_de(root), "help": True, "ollama_required": False})

    handlers = handlers or {}
    for name, fn in handlers.items():
        if fn is None:
            continue
        out = fn(root, raw)
        if out is not None:
            return _wrap(name, out)

    if raw and not raw.startswith("/"):
        return dispatch_freetext(root, raw, attachment_ids=attachment_ids, ollama_chat_fn=ollama_chat_fn)

    return _wrap("unknown", {"ok": False, "reply_de": unified_help_de(root), "help": True})
