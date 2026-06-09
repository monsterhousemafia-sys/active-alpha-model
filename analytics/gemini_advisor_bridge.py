"""Gemini-Berater-Bridge — API-Key, Cloud-Compute, Teacher für König 32B."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SECRET_REL = Path("control/secrets/gemini_api_key")
_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_CONFIG_REL = Path("control/r3_external_advisors.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_gemini_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL).get("gemini") or {}


def _keyring_name(root: Path) -> str:
    return str(load_gemini_config(root).get("keyring_name") or "gemini_api_key")


def _env_names(root: Path) -> Tuple[str, str]:
    primary = str(load_gemini_config(root).get("env_var") or "GEMINI_API_KEY")
    return primary, "AA_GEMINI_API_KEY"


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
    return f"{k[:6]}…{k[-4:]}"


def validate_gemini_key(key: str) -> Optional[str]:
    k = str(key or "").strip()
    if not k:
        return "Key fehlt"
    if not _KEY_RE.match(k):
        return "Key-Format ungültig (min. 20 Zeichen alphanumerisch)"
    return None


def _stealth_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL).get("stealth_mode") or {}


def resolve_gemini_key(root: Path) -> Tuple[str, str]:
    """Key + Quelle: env · keyring · secret_file (Stealth: nur secret_file/keyring)."""
    root = Path(root)
    stealth = _stealth_policy(root)
    if not stealth.get("no_env_key", False):
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


def load_gemini_key_into_env(root: Path, *, force: bool = False) -> Dict[str, Any]:
    root = Path(root)
    env_primary, env_alt = _env_names(root)
    if not force and (os.environ.get(env_primary) or os.environ.get(env_alt)):
        key, src = resolve_gemini_key(root)
        return {
            "ok": bool(key),
            "loaded": False,
            "already_in_env": True,
            "key_source": src or "env",
            "configured": bool(key),
        }
    key, src = resolve_gemini_key(root)
    if not key:
        return {
            "ok": False,
            "loaded": False,
            "configured": False,
            "message_de": (
                "Kein Gemini-Key — "
                f"echo 'KEY' | python3 tools/ai_kernel.py gemini-key-store "
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
        "message_de": f"Gemini geladen ({src}) · {_mask_key(key)}",
    }


def is_gemini_configured(root: Path) -> bool:
    load_gemini_key_into_env(root)
    key, _ = resolve_gemini_key(root)
    gem = load_gemini_config(root)
    return bool(key) and bool(gem.get("enabled", True))


def store_gemini_key(root: Path, key: str, *, source: str = "manual") -> Dict[str, Any]:
    root = Path(root)
    err = validate_gemini_key(key)
    if err:
        return {"ok": False, "message_de": err}
    try:
        from analytics.secure_credential_portal import keyring_available, keyring_set

        if not keyring_available():
            secret_path = root / _SECRET_REL
            secret_path.parent.mkdir(parents=True, exist_ok=True)
            secret_path.write_text(key.strip() + "\n", encoding="utf-8")
            try:
                secret_path.chmod(0o600)
            except OSError:
                pass
            load_gemini_key_into_env(root, force=True)
            return {
                "ok": True,
                "message_de": f"Gemini-Key in {_SECRET_REL} ({_mask_key(key)})",
                "key_masked": _mask_key(key),
                "source": source,
                "storage": "secret_file",
            }
        name = _keyring_name(root)
        if not keyring_set(root, name, key.strip()):
            return {"ok": False, "message_de": f"Keyring-Speicher fehlgeschlagen ({name})"}
    except Exception as exc:
        return {"ok": False, "message_de": f"Speichern fehlgeschlagen: {exc}"[:200]}
    load_gemini_key_into_env(root, force=True)
    return {
        "ok": True,
        "message_de": f"Gemini-Key gespeichert ({_mask_key(key)}) · Cloud aktiv",
        "key_masked": _mask_key(key),
        "keyring_name": _keyring_name(root),
        "source": source,
        "storage": "keyring",
    }


def read_key_from_stdin() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


def cmd_gemini_key_store(root: Path) -> Dict[str, Any]:
    root = Path(root)
    key = read_key_from_stdin()
    if not key:
        env_primary, _ = _env_names(root)
        key = str(os.environ.get(env_primary) or os.environ.get("AA_GEMINI_API_KEY") or "").strip()
    if not key:
        return {
            "ok": False,
            "message_de": "Key fehlt — bash tools/setup_gemini_key.sh oder gemini-key-store",
        }
    return store_gemini_key(root, key, source="stdin_or_env")


def _gemini_chat(
    root: Path,
    messages: List[Dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    fallback_model: str,
    timeout_s: float,
) -> Tuple[str, Dict[str, Any]]:
    key, _ = resolve_gemini_key(root)
    if not key:
        raise RuntimeError("Gemini-Key fehlt — gemini-key-store zuerst")
    gem = load_gemini_config(root)
    base = str(gem.get("base_url") or "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 429) and fallback_model and fallback_model != model:
            payload["model"] = fallback_model
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=data,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
            content = str((doc.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
            return content, {"model": fallback_model, "usage": doc.get("usage") or {}, "fallback": True}
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"Gemini HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini Netzwerk: {exc.reason}") from exc
    content = str((doc.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
    return content, {"model": model, "usage": doc.get("usage") or {}}


def resolve_gemini_tier(root: Path, question: str, *, mode: str = "tipp") -> Dict[str, Any]:
    from analytics.r3_model_synergy import classify_task

    root = Path(root)
    gem = load_gemini_config(root)
    tiers = dict(gem.get("tiers") or {})
    task = classify_task(question, mode=mode)
    tier = tiers.get(task) or tiers.get("fast") or {}
    model = str(tier.get("model") or gem.get("model") or "gemini-2.0-flash")
    fallback = str(tier.get("fallback") or gem.get("fallback_model") or model)
    return {
        "task": task,
        "tier": task,
        "model": model,
        "fallback_model": fallback,
        "role_de": str(tier.get("role_de") or task),
        "max_tokens": int(tier.get("max_tokens") or gem.get("max_tokens") or 2048),
        "temperature": float(tier.get("temperature") or gem.get("temperature") or 0.3),
    }


def _build_context(root: Path, extra_context: str) -> str:
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


def _parallel_boost(
    root: Path,
    question: str,
    *,
    sys_prompt: str,
    context: str,
    tier: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    gem = load_gemini_config(root)
    boost = dict(gem.get("compute_boost") or {})
    if not boost.get("enabled", True):
        raise RuntimeError("boost_disabled")
    workers = int(boost.get("parallel_workers") or 3)
    worker_model = str(boost.get("worker_model") or "gemini-2.0-flash")
    synth_model = str(boost.get("synth_model") or tier.get("model") or "gemini-2.0-flash")
    timeout_s = float(gem.get("timeout_s") or 90.0)
    sub_tasks = [
        f"Risiken und Blocker analysieren: {question}",
        f"Konkrete nächste king_ops-Schritte: {question}",
        f"Evidence-Implikationen für Active Alpha: {question}",
    ][:workers]
    results: List[str] = []

    def _worker(sub_q: str) -> str:
        tip, _ = _gemini_chat(
            root,
            [
                {"role": "system", "content": sys_prompt},
                {
                    "role": "user",
                    "content": f"{sub_q}\n\n{context}" if context else sub_q,
                },
            ],
            model=worker_model,
            max_tokens=int(tier.get("max_tokens") or 1200),
            temperature=0.25,
            fallback_model=worker_model,
            timeout_s=timeout_s,
        )
        return tip

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_worker, sq): sq for sq in sub_tasks}
        for fut in as_completed(futures):
            try:
                results.append(str(fut.result() or "").strip())
            except Exception as exc:
                results.append(f"(Worker-Fehler: {exc})")

    synth_user = (
        f"Nutzerfrage: {question}\n\n"
        f"Parallele Worker-Analysen ({len(results)}):\n"
        + "\n---\n".join(f"Worker {i + 1}:\n{r}" for i, r in enumerate(results))
        + (f"\n\n{context}" if context else "")
    )
    tip, meta = _gemini_chat(
        root,
        [
            {"role": "system", "content": sys_prompt + " Synthetisiere die Worker-Ergebnisse präzise auf Deutsch."},
            {"role": "user", "content": synth_user},
        ],
        model=synth_model,
        max_tokens=int(tier.get("max_tokens") or 2048),
        temperature=float(tier.get("temperature") or 0.2),
        fallback_model=str(tier.get("fallback_model") or synth_model),
        timeout_s=timeout_s,
    )
    meta["parallel_workers"] = workers
    meta["compute_boost"] = True
    return tip, meta


def fetch_gemini_tip(
    root: Path,
    question: str,
    *,
    extra_context: str = "",
    mode: str = "tipp",
) -> Dict[str, Any]:
    root = Path(root)
    cfg = _load_json(root / _CONFIG_REL)
    gem = cfg.get("gemini") or {}
    if not cfg.get("enabled") or not gem.get("enabled"):
        return {"ok": False, "message_de": "Gemini-Berater deaktiviert"}
    q = str(question or "").strip()
    if not q:
        return {"ok": False, "message_de": "Frage fehlt — /kombi <frage>"}
    load_gemini_key_into_env(root)
    if not resolve_gemini_key(root)[0]:
        return {"ok": False, "message_de": "Gemini-Key fehlt — gemini-key-store oder setup_gemini_key.sh"}

    tier = resolve_gemini_tier(root, q, mode=mode)
    sys_prompt = str(cfg.get("system_prompt_de") or "") + " Du bist Gemini-Cloud-Lehrer für Active Alpha (nur Rat, keine Orders)."
    context = _build_context(root, extra_context)
    user_parts = [f"Aufgabe ({tier.get('role_de')}): {q}"]
    if context:
        user_parts.append(context)
    boost = dict(gem.get("compute_boost") or {})
    deep_tiers = list(boost.get("deep_tiers") or ["deep", "plan"])
    use_boost = bool(boost.get("enabled", True)) and str(tier.get("task")) in deep_tiers

    try:
        if use_boost:
            try:
                tip, meta = _parallel_boost(root, q, sys_prompt=sys_prompt, context=context, tier=tier)
            except Exception:
                tip, meta = _gemini_chat(
                    root,
                    [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "\n\n".join(user_parts)}],
                    model=str(tier.get("model") or ""),
                    max_tokens=int(tier.get("max_tokens") or 2048),
                    temperature=float(tier.get("temperature") or 0.3),
                    fallback_model=str(tier.get("fallback_model") or ""),
                    timeout_s=float(gem.get("timeout_s") or 90.0),
                )
        else:
            tip, meta = _gemini_chat(
                root,
                [{"role": "system", "content": sys_prompt}, {"role": "user", "content": "\n\n".join(user_parts)}],
                model=str(tier.get("model") or ""),
                max_tokens=int(tier.get("max_tokens") or 2048),
                temperature=float(tier.get("temperature") or 0.3),
                fallback_model=str(tier.get("fallback_model") or ""),
                timeout_s=float(gem.get("timeout_s") or 90.0),
            )
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:300], "advisor": True, "provider": "gemini"}
    if not tip:
        return {"ok": False, "message_de": "Leere Gemini-Antwort", "advisor": True, "provider": "gemini"}
    headline = f"Gemini {meta.get('model')}"
    if meta.get("compute_boost"):
        headline += f" · {meta.get('parallel_workers', 3)}× Parallel-Compute"
    return {
        "ok": True,
        "tip_de": tip,
        "advisor": True,
        "provider": "gemini",
        "model": meta.get("model"),
        "task_tier": tier.get("task"),
        "tier_role_de": tier.get("role_de"),
        "compute_boost": bool(meta.get("compute_boost")),
        "headline_de": f"{headline} · {tier.get('role_de')}",
    }


def probe_gemini_api(root: Path, *, force: bool = False) -> Dict[str, Any]:
    root = Path(root)
    stealth = _stealth_policy(root)
    if stealth.get("suppress_startup_probe") and not force:
        key, _ = resolve_gemini_key(root)
        if not key:
            return {
                "ok": False,
                "skipped": True,
                "message_de": "Stealth — kein Google-Probe ohne lokalen Key",
            }
    load_gemini_key_into_env(root)
    key, src = resolve_gemini_key(root)
    if not key:
        return {"ok": False, "message_de": "Kein Key — nur lokal: control/secrets/gemini_api_key"}
    gem = load_gemini_config(root)
    try:
        tip, meta = _gemini_chat(
            root,
            [
                {"role": "system", "content": "Antworte mit genau einem Wort: OK"},
                {"role": "user", "content": "Ping"},
            ],
            model=str(gem.get("model") or "gemini-2.0-flash"),
            max_tokens=16,
            temperature=0.0,
            fallback_model=str(gem.get("fallback_model") or "gemini-2.0-flash"),
            timeout_s=float(gem.get("timeout_s") or 60.0),
        )
        return {
            "ok": bool(tip),
            "message_de": f"Gemini erreichbar · {meta.get('model')} · Key {src}",
            "key_source": src,
            "model": meta.get("model"),
            "ping_de": tip[:40],
        }
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:300], "key_source": src}


def bridge_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    load_gemini_key_into_env(root)
    key, src = resolve_gemini_key(root)
    gem = load_gemini_config(root)
    secret_file = (root / _SECRET_REL).is_file()
    try:
        from analytics.secure_credential_portal import keyring_available, keyring_get

        kr_ok = keyring_available()
        kr_has = bool(keyring_get(root, _keyring_name(root)))
    except Exception:
        kr_ok = False
        kr_has = False
    boost = dict(gem.get("compute_boost") or {})
    return {
        "ok": True,
        "bridge": "gemini_advisor",
        "configured": bool(key) and bool(gem.get("enabled", True)),
        "key_source": src if key else None,
        "key_masked": _mask_key(key) if key else None,
        "keyring_available": kr_ok,
        "keyring_has_key": kr_has,
        "secret_file_present": secret_file,
        "secret_file_rel": str(_SECRET_REL),
        "model": gem.get("model"),
        "compute_boost": bool(boost.get("enabled", True)),
        "parallel_workers": int(boost.get("parallel_workers") or 3),
        "headline_de": (
            f"Gemini Cloud · {gem.get('model')} · Key OK ({src}) · {boost.get('parallel_workers', 3)}× Boost"
            if key
            else "Gemini Key fehlt — setup_gemini_key.sh"
        ),
        "setup_de": (
            "Gemini einrichten:\n"
            "  1) bash tools/setup_gemini_key.sh\n"
            "  2) echo 'KEY' | python3 tools/ai_kernel.py gemini-key-store\n"
            f"  3) Key in {_SECRET_REL} (chmod 600)\n"
            "Test: python3 tools/ai_kernel.py gemini-key-test"
        ),
    }


def format_bridge_status_de(root: Path) -> str:
    st = bridge_status(root)
    lines = [
        "**Gemini Cloud-Bridge**",
        str(st.get("headline_de") or "—"),
        f"Compute-Boost: {'ja' if st.get('compute_boost') else 'nein'} "
        f"({st.get('parallel_workers')} parallele Worker bei deep/plan)",
        f"Keyring: {'ja' if st.get('keyring_has_key') else 'nein'} · "
        f"Secret-Datei: {'ja' if st.get('secret_file_present') else 'nein'}",
    ]
    if not st.get("configured"):
        lines.extend(["", str(st.get("setup_de") or "")])
    else:
        lines.extend(["", "Befehle: /kombi <frage> · /tipp <frage> · gemini-key-test"])
    return "\n".join(lines)
