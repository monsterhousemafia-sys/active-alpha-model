"""Berater-Bridge — OpenAI-Key finden, speichern, in König-Dienst laden."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_SECRET_REL = Path("control/secrets/openai_api_key")
_KEY_RE = re.compile(r"^sk-[A-Za-z0-9_-]{20,}$")


def _load_advisor_openai_cfg(root: Path) -> Dict[str, Any]:
    from analytics.r3_external_advisor import load_advisor_config

    return load_advisor_config(root).get("openai") or {}


def _keyring_name(root: Path) -> str:
    return str(_load_advisor_openai_cfg(root).get("keyring_name") or "openai_api_key")


def _env_names(root: Path) -> Tuple[str, str]:
    oai = _load_advisor_openai_cfg(root)
    primary = str(oai.get("env_var") or "OPENAI_API_KEY")
    return primary, "AA_OPENAI_API_KEY"


def _read_secret_file(root: Path) -> str:
    path = Path(root) / _SECRET_REL
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if raw.startswith("export "):
            raw = raw.split("=", 1)[-1].strip().strip('"').strip("'")
        return raw
    except OSError:
        return ""


def _mask_key(key: str) -> str:
    k = str(key or "").strip()
    if len(k) < 12:
        return "(ungültig)"
    return f"{k[:7]}…{k[-4:]}"


def validate_openai_key(key: str) -> Optional[str]:
    k = str(key or "").strip()
    if not k:
        return "Key fehlt"
    if not _KEY_RE.match(k):
        return "Key-Format ungültig (erwartet sk-…)"
    return None


def store_openai_key(root: Path, key: str, *, source: str = "manual") -> Dict[str, Any]:
    root = Path(root)
    err = validate_openai_key(key)
    if err:
        return {"ok": False, "message_de": err}
    try:
        from analytics.secure_credential_portal import keyring_available, keyring_set

        if not keyring_available():
            return {
                "ok": False,
                "message_de": "Keyring nicht verfügbar — pip install keyring SecretStorage",
            }
        name = _keyring_name(root)
        if not keyring_set(root, name, key.strip()):
            return {"ok": False, "message_de": f"Keyring-Speicher fehlgeschlagen ({name})"}
    except Exception as exc:
        return {"ok": False, "message_de": f"Speichern fehlgeschlagen: {exc}"[:200]}
    load_openai_key_into_env(root, force=True)
    return {
        "ok": True,
        "message_de": f"OpenAI-Key gespeichert ({_mask_key(key)}) · Bridge aktiv",
        "key_masked": _mask_key(key),
        "keyring_name": _keyring_name(root),
        "source": source,
    }


def migrate_secret_file_to_keyring(root: Path) -> Dict[str, Any]:
    root = Path(root)
    raw = _read_secret_file(root)
    if not raw:
        return {
            "ok": False,
            "message_de": f"Keine Datei {_SECRET_REL} — Key dort ablegen (chmod 600) oder stdin store",
        }
    out = store_openai_key(root, raw, source="secret_file")
    if out.get("ok"):
        out["message_de"] = (
            f"Key aus {_SECRET_REL} nach Keyring migriert · {_mask_key(raw)}"
        )
    return out


def resolve_advisor_key(root: Path) -> Tuple[str, str]:
    """Key + Quelle: env · keyring · secret_file."""
    root = Path(root)
    env_primary, env_alt = _env_names(root)
    for name, label in ((env_primary, "env"), (env_alt, "env_aa")):
        val = str(os.environ.get(name) or "").strip()
        if val:
            return val, label
    try:
        from analytics.secure_credential_portal import keyring_get

        kr = keyring_get(root, _keyring_name(root))
        if kr:
            return kr, "keyring"
    except Exception:
        pass
    file_val = _read_secret_file(root)
    if file_val:
        return file_val, "secret_file"
    return "", ""


def load_openai_key_into_env(root: Path, *, force: bool = False) -> Dict[str, Any]:
    """Lädt Key in Prozess-ENV — König-Dienst nutzt /kombi /tipp sofort."""
    root = Path(root)
    env_primary, env_alt = _env_names(root)
    if not force and (os.environ.get(env_primary) or os.environ.get(env_alt)):
        key, src = resolve_advisor_key(root)
        return {
            "ok": bool(key),
            "loaded": False,
            "already_in_env": True,
            "key_source": src or "env",
            "configured": bool(key),
        }
    key, src = resolve_advisor_key(root)
    if not key:
        return {
            "ok": False,
            "loaded": False,
            "configured": False,
            "message_de": (
                "Kein OpenAI-Key — "
                f"echo 'sk-…' | python3 tools/ai_kernel.py advisor-key-store "
                f"oder Datei {_SECRET_REL}"
            ),
        }
    os.environ[env_primary] = key
    os.environ[env_alt] = key
    return {
        "ok": True,
        "loaded": True,
        "configured": True,
        "key_source": src,
        "key_masked": _mask_key(key),
        "message_de": f"Bridge geladen ({src}) · {_mask_key(key)}",
    }


def probe_openai_api(root: Path) -> Dict[str, Any]:
    root = Path(root)
    load_openai_key_into_env(root)
    key, src = resolve_advisor_key(root)
    if not key:
        return {"ok": False, "message_de": "Kein Key — advisor-key-store zuerst"}
    oai = _load_advisor_openai_cfg(root)
    base = str(oai.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    req = urllib.request.Request(
        f"{base}/models",
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    timeout = float(oai.get("timeout_s") or 30.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        models = [m.get("id") for m in (doc.get("data") or []) if isinstance(m, dict)]
        return {
            "ok": True,
            "message_de": f"OpenAI erreichbar · {len(models)} Modelle · Key {src}",
            "key_source": src,
            "models_sample": models[:5],
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        return {
            "ok": False,
            "message_de": f"OpenAI HTTP {exc.code}: {body}",
            "key_source": src,
        }
    except urllib.error.URLError as exc:
        return {"ok": False, "message_de": f"Netzwerk: {exc.reason}", "key_source": src}


def bridge_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.r3_external_advisor import advisor_status, is_keyless_advisor

    load_openai_key_into_env(root)
    key, src = resolve_advisor_key(root)
    adv = advisor_status(root)
    keyless = is_keyless_advisor(root)
    secret_file = (root / _SECRET_REL).is_file()
    try:
        from analytics.secure_credential_portal import keyring_available, keyring_get

        kr_ok = keyring_available()
        kr_has = bool(keyring_get(root, _keyring_name(root)))
    except Exception:
        kr_ok = False
        kr_has = False
    return {
        "ok": True,
        "bridge": "alpha_model_advisor",
        "configured": bool(key) or bool(adv.get("configured")),
        "keyless_mode": keyless,
        "key_source": src or adv.get("key_source"),
        "key_masked": _mask_key(key) if key else None,
        "keyring_available": kr_ok,
        "keyring_has_key": kr_has,
        "secret_file_present": secret_file,
        "secret_file_rel": str(_SECRET_REL),
        "advisor": adv,
        "setup_de": (
            "Key speichern:\n"
            "  1) echo 'sk-…' | python3 tools/ai_kernel.py advisor-key-store\n"
            f"  2) Key in {_SECRET_REL} (chmod 600) → advisor-key-migrate\n"
            "  3) export OPENAI_API_KEY=sk-… (Session)\n"
            "Test: python3 tools/ai_kernel.py advisor-key-test\n"
            "Im Agent: /berater-key · /kombi <frage> · /tipp <frage>"
        ),
    }


def format_bridge_status_de(root: Path) -> str:
    st = bridge_status(root)
    adv = st.get("advisor") or {}
    keyless = bool(st.get("keyless_mode"))
    has_cloud_key = bool(st.get("key_masked"))
    lines = [
        "**Berater-Bridge**",
        (
            f"Modus: GPT-4o lokal (keyless) · Ollama {'OK' if adv.get('ollama_ready') else 'Setup'}"
            if keyless and not has_cloud_key
            else (
                f"Key: OK ({st.get('key_source')}) · {st.get('key_masked')}"
                if has_cloud_key
                else "Key: fehlt"
            )
        ),
        f"Keyring: {'ja' if st.get('keyring_has_key') else 'nein'} · "
        f"Secret-Datei: {'ja' if st.get('secret_file_present') else 'nein'}",
        f"Internet: {'OK' if adv.get('internet_ok') else 'offline'} · "
        f"Ollama: {'OK' if adv.get('ollama_ready') else 'Setup'}",
        f"Berater-Tiers: fast=mini · plan/deep/trading=gpt-4o (lokal wenn kein Key)",
    ]
    if keyless:
        lines.append(str(adv.get("headline_de") or "GPT-4o lokal aktiv"))
    if not st.get("configured"):
        lines.extend(["", str(st.get("setup_de") or adv.get("setup_de") or "")])
    else:
        lines.extend(["", "Befehle: /kombi <frage> · /tipp <frage> · /berater-key test"])
    return "\n".join(lines)


def handle_bridge_command(root: Path, text: str) -> Dict[str, Any]:
    root = Path(root)
    raw = str(text or "").strip()
    low = raw.lower()
    if low in ("/berater-key", "/advisor-key", "/key", "/key status", "/berater-key status"):
        return {"ok": True, "reply_de": format_bridge_status_de(root), "bridge": True}
    if low in ("/berater-key test", "/advisor-key test", "/key test"):
        probe = probe_openai_api(root)
        return {
            "ok": bool(probe.get("ok")),
            "reply_de": str(probe.get("message_de") or "—"),
            "bridge": True,
            "probe": probe,
        }
    if low.startswith("/berater-key migrate") or low.startswith("/advisor-key migrate"):
        doc = migrate_secret_file_to_keyring(root)
        return {"ok": bool(doc.get("ok")), "reply_de": str(doc.get("message_de") or "—"), "bridge": True}
    if low in ("/berater-key einrichten", "/advisor-key setup", "/berater-key setup", "/key setup"):
        from analytics.r3_external_advisor import is_keyless_advisor

        if is_keyless_advisor(root):
            return {
                "ok": True,
                "reply_de": (
                    "**GPT-4o keyless aktiv** — kein OpenAI-Key nötig.\n\n"
                    "/tipp und /kombi nutzen GPT-4o-Tiers über lokales Ollama.\n"
                    "Optional Cloud-Key: bash tools/setup_advisor_key.sh"
                ),
                "bridge": True,
            }
        return {
            "ok": True,
            "reply_de": (
                "**Key einrichten (nicht im Chat tippen!)**\n\n"
                "Im Terminal:\n"
                "  bash tools/setup_advisor_key.sh\n"
                "oder:\n"
                "  python3 tools/ai_kernel.py advisor-key-setup\n\n"
                "Ohne Key: bash tools/setup_gpt4o_keyless.sh"
            ),
            "bridge": True,
        }
    return {
        "ok": False,
        "reply_de": "Nutze /berater-key · /berater-key einrichten · /berater-key test · /berater-key migrate",
        "bridge": True,
    }


def read_key_from_stdin() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


def interactive_store_key(root: Path) -> Dict[str, Any]:
    """TTY: Key sicher eingeben (nicht im Chat-Verlauf)."""
    import getpass

    root = Path(root)
    if not sys.stdin.isatty():
        return {
            "ok": False,
            "message_de": "Interaktiv nur im Terminal — bash tools/setup_advisor_key.sh",
        }
    print("OpenAI API Key (sk-…) — Eingabe unsichtbar, nur Keyring:", flush=True)
    key = getpass.getpass("Key: ").strip()
    if not key:
        return {"ok": False, "message_de": "Abgebrochen — kein Key eingegeben"}
    out = store_openai_key(root, key, source="interactive")
    if out.get("ok"):
        probe = probe_openai_api(root)
        out["probe_ok"] = bool(probe.get("ok"))
        out["probe_de"] = probe.get("message_de")
        if not probe.get("ok"):
            out["message_de"] = (
                f"{out.get('message_de')} — gespeichert, aber API-Test fehlgeschlagen: "
                f"{probe.get('message_de')}"
            )
    return out


def local_kombi_reply(root: Path, question: str) -> Dict[str, Any]:
    """Ollama-only Berater wenn kein Cloud-Key — Bridge bleibt nutzbar."""
    root = Path(root)
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "message_de": "Frage fehlt"}
    from analytics.local_llm_bridge import chat_completion, health_report

    if not health_report(root).get("ready"):
        return {"ok": False, "message_de": "Ollama nicht bereit — llm-setup zuerst"}
    try:
        from analytics.r3_conversation_continuity import load_continuity_context
        from analytics.r3_model_synergy import resolve_ollama_role

        ctx = load_continuity_context(root, max_chars=4000)
        pick = resolve_ollama_role(root, q, mode="kombi")
        sys_de = (
            "Du bist der lokale König-Berater (Ollama, kein Cloud-Key). "
            "Antworte konkret für active_alpha_model auf Deutsch mit Evidence-Pfaden."
        )
        user = q
        if ctx:
            user = f"Kontext:\n{ctx}\n\nFrage: {q}"
        reply, meta = chat_completion(
            root,
            [{"role": "system", "content": sys_de}, {"role": "user", "content": user}],
            model=str(pick.get("model") or ""),
            role="kombi_synthesis",
            num_ctx=pick.get("num_ctx"),
            timeout_s=180.0,
        )
        text = str(reply or "").strip()
        if not text:
            return {"ok": False, "message_de": "Leere Ollama-Antwort"}
        return {
            "ok": True,
            "reply_de": f"🤖 Lokaler Berater ({pick.get('model')} · kein Cloud-Key):\n\n{text}",
            "advisor": True,
            "kombi": True,
            "local_fallback": True,
            "model": meta.get("model") if isinstance(meta, dict) else pick.get("model"),
        }
    except Exception as exc:
        return {"ok": False, "message_de": f"Lokaler Berater Fehler: {exc}"[:300]}


def cmd_advisor_key_store(root: Path) -> Dict[str, Any]:
    root = Path(root)
    key = read_key_from_stdin()
    if not key:
        env_primary, _ = _env_names(root)
        key = str(os.environ.get(env_primary) or os.environ.get("AA_OPENAI_API_KEY") or "").strip()
    if not key:
        return {
            "ok": False,
            "message_de": "Key fehlt — bash tools/setup_advisor_key.sh oder advisor-key-setup",
        }
    return store_openai_key(root, key, source="stdin_or_env")
