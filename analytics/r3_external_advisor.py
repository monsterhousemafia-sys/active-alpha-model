"""R3 — externe Berater (ChatGPT) + Ollama-Kombi."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CONFIG_REL = Path("control/r3_external_advisors.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_advisor_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {"enabled": False}


def is_keyless_advisor(root: Path) -> bool:
    oai = load_advisor_config(root).get("openai") or {}
    return bool(oai.get("keyless_mode"))


def resolve_primary_cloud_provider(root: Path) -> str:
    """local/keyless · gemini · openai — Stealth: lokal bis Secret-Key gesetzt."""
    root = Path(root)
    cfg = load_advisor_config(root)
    primary = str(cfg.get("primary_cloud_provider") or "local").lower()
    stealth = dict(cfg.get("stealth_mode") or {})
    gem = cfg.get("gemini") or {}
    if primary in ("local", "keyless", "stealth"):
        if gem.get("enabled", True):
            try:
                from analytics.gemini_advisor_bridge import is_gemini_configured

                if is_gemini_configured(root):
                    return "gemini"
            except Exception:
                pass
        if is_keyless_advisor(root):
            return "keyless"
        return "keyless"
    if primary == "gemini" and gem.get("enabled", True):
        try:
            from analytics.gemini_advisor_bridge import is_gemini_configured

            if is_gemini_configured(root):
                return "gemini"
        except Exception:
            pass
    key, _ = resolve_openai_api_key(root)
    if key and not stealth.get("no_env_key"):
        return "openai"
    if is_keyless_advisor(root):
        return "keyless"
    return "none"


def resolve_openai_api_key(root: Path) -> Tuple[str, str]:
    """Returns (key, source) — env · keyring · secret_file."""
    try:
        from analytics.alpha_model_advisor_bridge import load_openai_key_into_env, resolve_advisor_key

        load_openai_key_into_env(root)
        return resolve_advisor_key(root)
    except Exception:
        pass
    cfg = load_advisor_config(root)
    oai = cfg.get("openai") or {}
    env_name = str(oai.get("env_var") or "OPENAI_API_KEY")
    env_val = str(os.environ.get(env_name) or os.environ.get("AA_OPENAI_API_KEY") or "").strip()
    if env_val:
        return env_val, "env"
    kr_name = str(oai.get("keyring_name") or "openai_api_key")
    try:
        from analytics.secure_credential_portal import keyring_get

        kr_val = keyring_get(root, kr_name)
        if kr_val:
            return kr_val, "keyring"
    except Exception:
        pass
    return "", ""


def advisor_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_advisor_config(root)
    oai = cfg.get("openai") or {}
    try:
        from analytics.r3_model_synergy import build_synergy_status

        synergy = build_synergy_status(root)
    except Exception:
        synergy = {}
    key, source = resolve_openai_api_key(root)
    ollama_ready = False
    ollama_model = ""
    try:
        from analytics.local_llm_bridge import health_report

        h = health_report(root)
        ollama_ready = bool(h.get("ready"))
        ollama_model = str(h.get("resolved_model") or "")
    except Exception:
        pass
    net_ok = False
    try:
        from analytics.r3_ki_web import probe_internet_generic

        net_ok = probe_internet_generic()
    except Exception:
        pass
    has_key = bool(key)
    keyless = is_keyless_advisor(root)
    provider = resolve_primary_cloud_provider(root)
    gem_cfg = cfg.get("gemini") or {}
    gem_ok = provider == "gemini"
    configured = gem_ok or has_key or (keyless and ollama_ready)
    boost = dict(gem_cfg.get("compute_boost") or {})
    return {
        "ok": bool(cfg.get("enabled")),
        "configured": configured,
        "primary_provider": provider,
        "gemini_configured": gem_ok,
        "keyless_mode": keyless and not gem_ok and not has_key,
        "key_source": source if has_key else ("gemini" if gem_ok else ("ollama_keyless" if keyless else None)),
        "model": gem_cfg.get("model") if gem_ok else oai.get("model"),
        "compute_boost": bool(boost.get("enabled", True)) if gem_ok else False,
        "parallel_workers": int(boost.get("parallel_workers") or 3) if gem_ok else 0,
        "synergy": synergy,
        "ollama_ready": ollama_ready,
        "ollama_model": ollama_model,
        "internet_ok": net_ok,
        "commands_de": cfg.get("commands_de"),
        "auto_tips_on_freetext": bool(cfg.get("auto_tips_on_freetext")),
        "headline_de": (
            f"Berater: Gemini ({gem_cfg.get('model')}) · {boost.get('parallel_workers', 3)}× Boost · Ollama {ollama_model or '—'}"
            if gem_ok
            else (
                f"Berater: ChatGPT ({oai.get('model')}) · Key OK · Ollama {ollama_model or '—'}"
                if has_key and ollama_ready
                else (
                    str(oai.get("keyless_label_de") or "GPT-4o lokal via Ollama — kein Key")
                    + (f" · {ollama_model}" if ollama_ready else " · Ollama Setup nötig")
                    if keyless
                    else (
                        "Berater: Gemini-Key fehlt — bash tools/setup_gemini_key.sh"
                        if not has_key
                        else f"Berater: Key OK · Ollama Setup nötig (llm-setup)"
                    )
                )
            )
        ),
        "setup_de": (
            "Gemini aktiv — /kombi und /tipp nutzen Google Cloud-Compute + Evidence-RAG."
            if gem_ok
            else (
                "Keyless aktiv — /tipp und /kombi nutzen Ollama lokal. "
                "Gemini: bash tools/setup_gemini_key.sh"
                if keyless
                else (
                    "bash tools/setup_gemini_key.sh — Gemini API-Key (AI Studio) "
                    f"oder export {gem_cfg.get('env_var', 'GEMINI_API_KEY')}=…"
                )
            )
        ),
    }


def is_advisor_command(text: str) -> bool:
    low = str(text or "").strip().lower()
    return (
        low.startswith("/tipp ")
        or low.startswith("/chatgpt ")
        or low.startswith("/kombi ")
        or low.startswith("/gemini ")
        or low in (
            "/berater",
            "/advisor",
            "/synergie",
            "/synergy",
            "/tipp",
            "/chatgpt",
            "/kombi",
            "/gemini",
            "/gemini-key",
        )
    )


def _openai_chat(
    root: Path,
    messages: List[Dict[str, str]],
    *,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    fallback_model: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    cfg = load_advisor_config(root)
    oai = cfg.get("openai") or {}
    key, _src = resolve_openai_api_key(root)
    if not key:
        raise RuntimeError(
            f"OpenAI-Key fehlt — {oai.get('env_var', 'OPENAI_API_KEY')} oder keyring openai_api_key"
        )
    base = str(oai.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    model = str(model or oai.get("model") or "gpt-4o-mini")
    fb = str(fallback_model or oai.get("fallback_model") or "gpt-4o")
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": int(max_tokens or oai.get("max_tokens") or 900),
        "temperature": float(temperature if temperature is not None else oai.get("temperature") or 0.35),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    timeout = float(oai.get("timeout_s") or 45.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 429) and fb and fb != model:
            payload["model"] = fb
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
            content = str((doc.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
            return content, {"model": fb, "usage": doc.get("usage") or {}, "fallback": True}
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI Netzwerk: {exc.reason}") from exc
    content = str((doc.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
    usage = doc.get("usage") or {}
    return content, {"model": model, "usage": usage}


def _local_advisor_context(root: Path, extra_context: str) -> str:
    parts: List[str] = []
    try:
        from analytics.king_evidence_rag import rag_context_for_prompt

        rag = rag_context_for_prompt(root)
        if rag.strip():
            parts.append(rag[:8000])
    except Exception:
        pass
    if extra_context:
        parts.append(f"Zusatz-Kontext:\n{extra_context[:6000]}")
    return "\n\n".join(parts)


def _fetch_local_advisor_tip(
    root: Path,
    question: str,
    *,
    extra_context: str = "",
    mode: str = "tipp",
) -> Dict[str, Any]:
    """Lokaler Berater — Evidence-RAG + optional 3× Parallel-Compute bei deep/plan."""
    root = Path(root)
    cfg = load_advisor_config(root)
    q = str(question or "").strip()
    from analytics.local_llm_bridge import chat_completion, health_report
    from analytics.r3_model_synergy import resolve_local_model_for_openai_tier, resolve_openai_tier

    if not health_report(root).get("ready"):
        return {"ok": False, "message_de": "Ollama nicht bereit — llm-setup zuerst", "advisor": True}
    tier = resolve_openai_tier(root, q, mode=mode)
    pick = resolve_local_model_for_openai_tier(root, tier)
    sys_prompt = (
        str(cfg.get("system_prompt_de") or "")
        + " Du arbeitest als lokaler Berater (Ollama, kein Cloud-Key)."
    )
    context = _local_advisor_context(root, extra_context)
    gem = cfg.get("gemini") or {}
    boost = dict(gem.get("compute_boost") or {})
    deep_tiers = list(boost.get("deep_tiers") or ["deep", "plan"])
    use_parallel = bool(boost.get("enabled", True)) and str(tier.get("task")) in deep_tiers
    try:
        if use_parallel:
            from analytics.ollama_parallel_compute import fetch_local_parallel_tip

            tip, meta = fetch_local_parallel_tip(
                root,
                q,
                sys_prompt=sys_prompt,
                context=context,
                tier=tier,
                pick=pick,
                mode=mode,
            )
        else:
            user_parts = [f"Aufgabe ({tier.get('role_de')} · Tier {pick.get('display_model')}): {q}"]
            if context:
                user_parts.append(context)
            tip, meta = chat_completion(
                root,
                [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": "\n\n".join(user_parts)},
                ],
                model=str(pick.get("model") or ""),
                role="kombi_synthesis" if mode == "kombi" else "chat",
                num_ctx=pick.get("num_ctx"),
                timeout_s=180.0,
            )
            meta = {"model": meta.get("model") if isinstance(meta, dict) else pick.get("model")}
    except Exception as exc:
        return {"ok": False, "message_de": f"Lokaler Berater Fehler: {exc}"[:300], "advisor": True}
    tip = str(tip or "").strip()
    if not tip:
        return {"ok": False, "message_de": "Leere lokale Berater-Antwort", "advisor": True}
    local_model = meta.get("model") if isinstance(meta, dict) else pick.get("model")
    headline = f"Berater {pick.get('display_model')} (lokal · {local_model}) · {tier.get('role_de')}"
    if meta.get("compute_boost"):
        headline += f" · {meta.get('parallel_workers', 3)}× Parallel"
    return {
        "ok": True,
        "tip_de": tip,
        "advisor": True,
        "provider": "ollama_parallel" if meta.get("compute_boost") else "ollama_keyless",
        "model": pick.get("display_model"),
        "local_model": local_model,
        "keyless": True,
        "compute_boost": bool(meta.get("compute_boost")),
        "task_tier": tier.get("task"),
        "tier_role_de": tier.get("role_de"),
        "headline_de": headline,
    }


def fetch_cloud_tip(
    root: Path,
    question: str,
    *,
    extra_context: str = "",
    mode: str = "tipp",
) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_advisor_config(root)
    if not cfg.get("enabled"):
        return {"ok": False, "message_de": "Externer Berater deaktiviert"}
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "message_de": "Frage fehlt — /tipp <frage>"}
    provider = resolve_primary_cloud_provider(root)
    if provider == "gemini":
        from analytics.gemini_advisor_bridge import fetch_gemini_tip

        return fetch_gemini_tip(root, q, extra_context=extra_context, mode=mode)
    oai = cfg.get("openai") or {}
    if not oai.get("enabled"):
        return {"ok": False, "message_de": "OpenAI-Fallback deaktiviert — Gemini-Key setzen"}
    key, _src = resolve_openai_api_key(root)
    if not key and is_keyless_advisor(root):
        return _fetch_local_advisor_tip(root, q, extra_context=extra_context, mode=mode)
    from analytics.r3_model_synergy import resolve_openai_tier

    tier = resolve_openai_tier(root, q, mode=mode)
    sys_prompt = str(cfg.get("system_prompt_de") or "")
    user_parts = [f"Aufgabe ({tier.get('role_de')}): {q}"]
    if extra_context:
        user_parts.append(f"Kontext (R3/Ollama):\n{extra_context[:6000]}")
    try:
        tip, meta = _openai_chat(
            root,
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            model=str(tier.get("model") or ""),
            max_tokens=int(tier.get("max_tokens") or 900),
            temperature=float(tier.get("temperature") or 0.35),
            fallback_model=str(tier.get("fallback_model") or ""),
        )
    except Exception as exc:
        if is_keyless_advisor(root):
            return _fetch_local_advisor_tip(root, q, extra_context=extra_context, mode=mode)
        return {"ok": False, "message_de": str(exc)[:300], "advisor": True}
    if not tip:
        return {"ok": False, "message_de": "Leere Cloud-Antwort", "advisor": True}
    return {
        "ok": True,
        "tip_de": tip,
        "advisor": True,
        "provider": "openai",
        "model": meta.get("model"),
        "task_tier": tier.get("task"),
        "tier_role_de": tier.get("role_de"),
        "headline_de": f"Berater {meta.get('model')} · {tier.get('role_de')}",
    }


def fetch_chatgpt_tip(
    root: Path,
    question: str,
    *,
    extra_context: str = "",
    mode: str = "tipp",
) -> Dict[str, Any]:
    """Kompatibilitäts-Alias — Gemini zuerst, dann OpenAI/keyless."""
    return fetch_cloud_tip(root, question, extra_context=extra_context, mode=mode)


def handle_advisor_command(root: Path, text: str) -> Dict[str, Any]:
    root = Path(root)
    raw = str(text or "").strip()
    low = raw.lower()
    if low in ("/synergie", "/synergy"):
        from analytics.r3_model_synergy import format_synergy_reply_de

        return {"ok": True, "reply_de": format_synergy_reply_de(root), "advisor": True, "synergy": True}

    if low in ("/berater", "/advisor", "/gemini-key"):
        st = advisor_status(root)
        syn = st.get("synergy") or {}
        lines = [
            st.get("headline_de") or "—",
            f"Provider: {st.get('primary_provider') or '—'}"
            + (f" · Boost {st.get('parallel_workers')}×" if st.get("compute_boost") else ""),
            f"Internet: {'OK' if st.get('internet_ok') else 'offline'}",
            f"Ollama: {'bereit' if st.get('ollama_ready') else 'Setup nötig'} ({st.get('ollama_model') or '—'})",
            f"Cloud: {'ja' if st.get('configured') else 'nein'}"
            + (f" ({st.get('key_source')})" if st.get("configured") else ""),
            "",
            "Gemini-Tiers: " + ", ".join(f"{k}={v}" for k, v in (syn.get("gemini_tiers") or {}).items()),
            "Ollama: " + ", ".join(f"{k}={v}" for k, v in (syn.get("ollama_roles") or {}).items()),
            "",
            "Befehle:",
            "  /synergie         — Modell-Paare",
            "  /kombi <frage>    — Gemini Cloud + Ollama",
            "  /tipp <frage>     — nur Cloud-Berater",
            "  gemini-key-test   — API prüfen",
        ]
        if not st.get("configured"):
            lines.append("")
            lines.append(str(st.get("setup_de") or ""))
        return {"ok": True, "reply_de": "\n".join(lines), "advisor": True, "status": st}

    for prefix in ("/tipp ", "/chatgpt ", "/kombi ", "/gemini "):
        if low.startswith(prefix):
            question = raw[len(prefix) :].strip()
            mode = "kombi" if prefix.startswith("/kombi") else "tipp"
            break
    else:
        return {"ok": False, "reply_de": "Nutze /tipp <frage> oder /kombi <frage>", "advisor": True}

    if mode == "tipp":
        out = fetch_cloud_tip(root, question)
        if not out.get("ok"):
            return {**out, "reply_de": out.get("message_de", "Fehler")}
        if out.get("provider") == "gemini":
            boost = " · Parallel-Compute" if out.get("compute_boost") else ""
            reply = (
                f"💡 Gemini Cloud ({out.get('model')}{boost})\n\n"
                f"{out.get('tip_de')}\n\n— {out.get('tier_role_de')} · König bleibt lokal."
            )
        elif out.get("keyless") or out.get("provider") == "ollama_parallel":
            boost = f" · {out.get('parallel_workers', 3)}× Parallel" if out.get("compute_boost") else ""
            reply = (
                f"💡 Berater (lokal · {out.get('local_model')}{boost} · kein Cloud-Key)\n\n"
                f"{out.get('tip_de')}\n\n— Tier {out.get('model')} · R3 Kernel bleibt Ollama."
            )
        else:
            reply = f"💡 Cloud-Berater\n\n{out.get('tip_de')}\n\n— R3 Kernel bleibt Ollama; Tipp nur als Rat."
        return {**out, "reply_de": reply, "ollama_required": False}

    # /kombi — ChatGPT tip then Ollama synthesis
    ctx = ""
    try:
        from analytics.r3_conversation_continuity import load_continuity_context

        ctx = load_continuity_context(root, max_chars=3000)
    except Exception:
        pass
    tip_out = fetch_cloud_tip(root, question, extra_context=ctx, mode="kombi")
    if not tip_out.get("ok"):
        try:
            from analytics.alpha_model_advisor_bridge import local_kombi_reply

            local = local_kombi_reply(root, question)
            if local.get("ok"):
                return local
        except Exception:
            pass
        return {**tip_out, "reply_de": tip_out.get("message_de", "ChatGPT nicht erreichbar")}

    from analytics.local_llm_bridge import chat_completion, initial_messages

    health_st = advisor_status(root)
    if not health_st.get("ollama_ready"):
        tip = str(tip_out.get("tip_de") or "")
        return {
            "ok": True,
            "reply_de": (
                f"💡 ChatGPT-Tipp (Ollama offline — nur Berater):\n\n{tip}\n\n"
                "Ollama: python3 tools/ai_kernel.py llm-setup"
            ),
            "advisor": True,
            "kombi": True,
            "ollama_required": False,
            "tip_de": tip,
        }

    cfg = load_advisor_config(root)
    kombi_sys = str(cfg.get("kombi_prompt_de") or "")
    tip = str(tip_out.get("tip_de") or "")
    messages = initial_messages(root)
    messages.append(
        {
            "role": "user",
            "content": (
                f"{kombi_sys}\n\n"
                f"--- ChatGPT-Berater ---\n{tip}\n\n"
                f"--- Nutzerfrage ---\n{question}"
            ),
        }
    )
    from analytics.r3_model_synergy import resolve_ollama_role

    ollama_pick = resolve_ollama_role(root, question, mode="kombi")
    try:
        reply, meta = chat_completion(root, messages, model=str(ollama_pick.get("model") or ""))
    except Exception as exc:
        return {
            "ok": True,
            "reply_de": f"ChatGPT-Tipp:\n{tip}\n\n(Ollama-Fehler: {str(exc)[:200]})",
            "advisor": True,
            "kombi": True,
            "tip_de": tip,
        }
    reply = str(reply or "").strip()
    if tip_out.get("provider") == "gemini":
        advisor_label = f"Gemini {tip_out.get('model')}"
        if tip_out.get("compute_boost"):
            advisor_label += " (3× Parallel)"
    elif tip_out.get("keyless"):
        advisor_label = f"lokal ({tip_out.get('local_model')})"
    else:
        advisor_label = f"Cloud {tip_out.get('model')}"
    full = (
        f"💡 Berater ({advisor_label}):\n{tip[:1200]}"
        + ("…" if len(tip) > 1200 else "")
        + f"\n\n🤖 R3 KI (Ollama {ollama_pick.get('model')} · {ollama_pick.get('role_de')}):\n{reply}"
    )
    return {
        "ok": True,
        "reply_de": full,
        "advisor": True,
        "kombi": True,
        "tip_de": tip,
        "ollama_reply_de": reply,
        "model": meta.get("model") if isinstance(meta, dict) else health_st.get("ollama_model"),
    }
