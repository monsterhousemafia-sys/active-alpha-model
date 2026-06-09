"""WhatsApp-Spread — Text + ZIP per API (WAHA / Green API / CallMeBot) oder wa.me-Fallback."""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/whatsapp_spread.json")
_EVIDENCE_REL = Path("evidence/whatsapp_spread_latest.json")
_DEFAULT_TEXT_REL = Path("evidence/spread_whatsapp_de.txt")
_OWN_ACCOUNT_PROVIDERS = frozenset({"wa_me", "waha"})


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


def load_whatsapp_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL)


def resolve_self_phone(cfg: Dict[str, Any]) -> str:
    direct = normalize_phone_e164(str(cfg.get("self_phone_e164") or ""))
    if direct:
        return direct
    for rec in cfg.get("recipients") or []:
        if not isinstance(rec, dict):
            continue
        phone = normalize_phone_e164(str(rec.get("phone_e164") or ""))
        if phone:
            return phone
    return ""


def normalize_phone_e164(phone: str) -> str:
    raw = re.sub(r"[^\d+]", "", str(phone or "").strip())
    if raw.startswith("+"):
        raw = raw[1:]
    if raw.startswith("00"):
        raw = raw[2:]
    if raw.startswith("0") and len(raw) >= 10:
        raw = "49" + raw[1:]
    return re.sub(r"\D", "", raw)


def phone_to_chat_id(phone: str) -> str:
    digits = normalize_phone_e164(phone)
    if not digits:
        return ""
    return f"{digits}@c.us"


def build_wa_me_url(phone: str, text: str) -> str:
    digits = normalize_phone_e164(phone)
    if not digits:
        return ""
    query = urllib.parse.urlencode({"text": text})
    return f"https://wa.me/{digits}?{query}"


def _keyring_get(root: Path, name: str) -> str:
    try:
        from analytics.secure_credential_portal import keyring_get

        return str(keyring_get(root, name) or "").strip()
    except Exception:
        return ""


def _http_json(
    method: str,
    url: str,
    *,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 20.0,
) -> Tuple[int, Dict[str, Any], str]:
    data = None
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 0) or 0)
            try:
                parsed = json.loads(body) if body.strip() else {}
            except json.JSONDecodeError:
                parsed = {"raw": body}
            return status, parsed if isinstance(parsed, dict) else {"raw": parsed}, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return int(exc.code or 0), parsed if isinstance(parsed, dict) else {"raw": parsed}, body
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return 0, {}, str(exc)


def _resolve_spread_text(root: Path, cfg: Dict[str, Any]) -> str:
    rel = Path(str(cfg.get("text_ref") or _DEFAULT_TEXT_REL))
    path = root / rel
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _resolve_zip_path(root: Path, cfg: Dict[str, Any]) -> Optional[Path]:
    explicit = str(cfg.get("zip_path") or "").strip()
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
    prefs = [str(x) for x in (cfg.get("zip_preference") or ["world", "home", "lite"])]
    candidates: List[Path] = []
    try:
        from analytics.community_spread_plan import collect_spread_urls

        urls = collect_spread_urls(root)
        mapping = {
            "world": urls.get("world_zip") or urls.get("lite_zip") or urls.get("home_zip"),
            "home": urls.get("home_zip"),
            "lite": urls.get("lite_zip"),
        }
        for key in prefs:
            val = mapping.get(key)
            if val:
                candidates.append(Path(str(val)))
    except Exception:
        pass
    candidates.extend(
        [
            Path.home() / "world_worker_LITE.zip",
            Path.home() / "glasfaser_NOTFALL_worker_LITE.zip",
            root / "active_alpha_worker_LITE.zip",
        ]
    )
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand
    return None


def _waha_headers(root: Path, cfg: Dict[str, Any]) -> Dict[str, str]:
    waha = cfg.get("waha") or {}
    key_name = str(waha.get("api_key_keyring") or "waha_api_key")
    api_key = _keyring_get(root, key_name) or os.environ.get("WAHA_API_KEY", "").strip()
    if api_key:
        return {"X-Api-Key": api_key}
    return {}


def verify_waha_binding(root: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_whatsapp_config(root)
    waha = cfg.get("waha") or {}
    base = str(waha.get("base_url") or "http://127.0.0.1:3000").rstrip("/")
    session = str(waha.get("session") or "default")
    headers = _waha_headers(root, cfg)
    status, body, raw = _http_json("GET", f"{base}/api/sessions", headers=headers, timeout=4.0)
    ok = status == 200
    session_ok = False
    detail = "WAHA nicht erreichbar"
    if ok:
        sessions = body if isinstance(body, list) else body.get("sessions") or body.get("data") or []
        if isinstance(sessions, dict):
            sessions = list(sessions.values())
        for item in sessions if isinstance(sessions, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("session") or "")
            state = str(item.get("status") or item.get("state") or "").upper()
            if name == session and state in ("WORKING", "CONNECTED", "STARTED", "OPEN"):
                session_ok = True
                break
        detail = "Session verbunden" if session_ok else f"WAHA OK — Session '{session}' nicht verbunden (QR scannen)"
    elif raw:
        detail = f"WAHA FAIL ({status}): {raw[:120]}"
    return {
        "id": "waha",
        "ok": ok and session_ok,
        "reachable": ok,
        "session_connected": session_ok,
        "detail_de": detail,
        "base_url": base,
        "session": session,
        "qr_hint_de": f"QR: curl -H 'X-Api-Key:…' {base}/api/{session}/auth/qr -o /tmp/waha-qr.png",
    }


def verify_green_api_binding(root: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_whatsapp_config(root)
    green = cfg.get("green_api") or {}
    instance = _keyring_get(root, str(green.get("instance_id_keyring") or "green_api_instance_id"))
    token = _keyring_get(root, str(green.get("token_keyring") or "green_api_token"))
    if not instance or not token:
        return {
            "id": "green_api",
            "ok": False,
            "detail_de": "Green-API instance_id/token fehlen (Keyring)",
        }
    base = str(green.get("base_url") or "https://api.green-api.com").rstrip("/")
    url = f"{base}/waInstance{instance}/getStateInstance/{token}"
    status, body, raw = _http_json("GET", url, timeout=8.0)
    state = str(body.get("stateInstance") or "")
    ok = status == 200 and state.lower() in ("authorized", "connected", "starting")
    return {
        "id": "green_api",
        "ok": ok,
        "detail_de": f"Green-API {state or raw[:80]}",
        "state": state,
    }


def verify_callmebot_binding(root: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or load_whatsapp_config(root)
    cb = cfg.get("callmebot") or {}
    api_key = _keyring_get(root, str(cb.get("api_key_keyring") or "callmebot_api_key"))
    ok = len(api_key) >= 8
    return {
        "id": "callmebot",
        "ok": ok,
        "detail_de": "CallMeBot API-Key im Keyring" if ok else "CallMeBot API-Key fehlt",
        "text_only": True,
    }


def verify_whatsapp_binding(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_whatsapp_config(root)
    provider = str(cfg.get("provider") or "waha").strip().lower()
    enabled = bool(cfg.get("enabled"))
    checks: List[Dict[str, Any]] = []
    if provider == "waha":
        checks.append(verify_waha_binding(root, cfg))
    elif provider == "green_api":
        checks.append(verify_green_api_binding(root, cfg))
    elif provider == "callmebot":
        checks.append(verify_callmebot_binding(root, cfg))
    elif provider == "wa_me":
        checks.append(
            {
                "id": "wa_me",
                "ok": True,
                "detail_de": "wa.me-Fallback — kein API-Versand, nur Link öffnen",
            }
        )
    else:
        checks.append({"id": provider, "ok": False, "detail_de": f"Unbekannter Provider: {provider}"})

    text_ok = bool(_resolve_spread_text(root, cfg))
    zip_path = _resolve_zip_path(root, cfg) if cfg.get("attach_zip", True) else None
    checks.extend(
        [
            {
                "id": "spread_text",
                "ok": text_ok,
                "detail_de": "WhatsApp-Text vorhanden" if text_ok else "Text fehlt",
            },
            {
                "id": "spread_zip",
                "ok": zip_path is not None or not cfg.get("attach_zip", True),
                "detail_de": str(zip_path) if zip_path else "ZIP fehlt (optional wenn attach_zip=false)",
                "path": str(zip_path) if zip_path else None,
            },
        ]
    )
    provider_ok = any(c.get("ok") for c in checks[:1])
    ok = enabled and provider_ok and text_ok
    doc = {
        "schema_version": 1,
        "ok": ok,
        "enabled": enabled,
        "provider": provider,
        "checks": checks,
        "headline_de": "WhatsApp-Anbindung bereit" if ok else "WhatsApp-Anbindung unvollständig",
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _send_waha_text(
    root: Path,
    cfg: Dict[str, Any],
    chat_id: str,
    text: str,
) -> Dict[str, Any]:
    waha = cfg.get("waha") or {}
    base = str(waha.get("base_url") or "http://127.0.0.1:3000").rstrip("/")
    session = str(waha.get("session") or "default")
    headers = _waha_headers(root, cfg)
    status, body, raw = _http_json(
        "POST",
        f"{base}/api/sendText",
        payload={"session": session, "chatId": chat_id, "text": text},
        headers=headers,
    )
    return {"ok": 200 <= status < 300, "status": status, "body": body, "raw": raw}


def _send_waha_file(
    root: Path,
    cfg: Dict[str, Any],
    chat_id: str,
    zip_path: Path,
    *,
    caption: str = "",
) -> Dict[str, Any]:
    waha = cfg.get("waha") or {}
    base = str(waha.get("base_url") or "http://127.0.0.1:3000").rstrip("/")
    session = str(waha.get("session") or "default")
    headers = _waha_headers(root, cfg)
    data_b64 = base64.b64encode(zip_path.read_bytes()).decode("ascii")
    status, body, raw = _http_json(
        "POST",
        f"{base}/api/sendFile",
        payload={
            "session": session,
            "chatId": chat_id,
            "caption": caption,
            "file": {
                "mimetype": "application/zip",
                "filename": zip_path.name,
                "data": data_b64,
            },
        },
        headers=headers,
        timeout=60.0,
    )
    return {"ok": 200 <= status < 300, "status": status, "body": body, "raw": raw}


def _send_green_text(
    root: Path,
    cfg: Dict[str, Any],
    chat_id: str,
    text: str,
) -> Dict[str, Any]:
    green = cfg.get("green_api") or {}
    instance = _keyring_get(root, str(green.get("instance_id_keyring") or "green_api_instance_id"))
    token = _keyring_get(root, str(green.get("token_keyring") or "green_api_token"))
    base = str(green.get("base_url") or "https://api.green-api.com").rstrip("/")
    url = f"{base}/waInstance{instance}/sendMessage/{token}"
    status, body, raw = _http_json(
        "POST",
        url,
        payload={"chatId": chat_id, "message": text},
    )
    return {"ok": 200 <= status < 300, "status": status, "body": body, "raw": raw}


def _send_green_file(
    root: Path,
    cfg: Dict[str, Any],
    chat_id: str,
    zip_path: Path,
    *,
    caption: str = "",
) -> Dict[str, Any]:
    green = cfg.get("green_api") or {}
    instance = _keyring_get(root, str(green.get("instance_id_keyring") or "green_api_instance_id"))
    token = _keyring_get(root, str(green.get("token_keyring") or "green_api_token"))
    base = str(green.get("base_url") or "https://api.green-api.com").rstrip("/")
    url = f"{base}/waInstance{instance}/sendFileByUpload/{token}"
    boundary = "----activealpha" + secrets_token()
    body_parts: List[bytes] = []
    for name, val in (("chatId", chat_id), ("caption", caption)):
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body_parts.append(f"{val}\r\n".encode())
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{zip_path.name}"\r\n'.encode()
    )
    body_parts.append(b"Content-Type: application/zip\r\n\r\n")
    body_parts.append(zip_path.read_bytes())
    body_parts.append(f"\r\n--{boundary}--\r\n".encode())
    payload = b"".join(body_parts)
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", 0) or 0)
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            return {"ok": 200 <= status < 300, "status": status, "body": parsed, "raw": raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": int(exc.code or 0), "body": {}, "raw": raw}
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"ok": False, "status": 0, "body": {}, "raw": str(exc)}


def secrets_token() -> str:
    import secrets as _secrets

    return _secrets.token_hex(8)


def _send_callmebot_text(
    root: Path,
    cfg: Dict[str, Any],
    phone: str,
    text: str,
) -> Dict[str, Any]:
    cb = cfg.get("callmebot") or {}
    api_key = _keyring_get(root, str(cb.get("api_key_keyring") or "callmebot_api_key"))
    query = urllib.parse.urlencode(
        {
            "phone": f"+{normalize_phone_e164(phone)}",
            "text": text,
            "apikey": api_key,
        }
    )
    url = f"https://api.callmebot.com/whatsapp.php?{query}"
    status, body, raw = _http_json("GET", url, timeout=20.0)
    ok = status == 200 and "error" not in raw.lower()
    return {"ok": ok, "status": status, "body": body, "raw": raw, "text_only": True}


def _run_opener(target: str) -> Dict[str, Any]:
    if not target:
        return {"ok": False, "detail_de": "Ziel leer"}
    opened = False
    err = ""
    for cmd in (["xdg-open", target], ["gio", "open", target], ["wslview", target]):
        if not shutil_which(cmd[0]):
            continue
        try:
            subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            opened = True
            break
        except (OSError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            err = str(exc)
    return {"ok": opened, "detail_de": "geöffnet" if opened else f"Öffnen fehlgeschlagen: {err or target}", "target": target}


def shutil_which(cmd: str) -> Optional[str]:
    import shutil

    return shutil.which(cmd)


def copy_to_clipboard(text: str) -> Dict[str, Any]:
    from analytics.x11_send import copy_clipboard as x11_copy

    return x11_copy(text)


def _http_ok(url: str, timeout: float = 8.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _join_page_ok(base_url: str, timeout: float = 12.0) -> bool:
    base = str(base_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        return False
    try:
        with urllib.request.urlopen(f"{base}/join", timeout=timeout) as resp:
            body = resp.read()
            return int(getattr(resp, "status", 0) or 0) == 200 and len(body) > 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def verify_join_reachable(join_url: str, timeout: float = 12.0) -> Dict[str, Any]:
    raw = str(join_url or "").strip().rstrip("/")
    if not raw.startswith(("http://", "https://")):
        return {"ok": False, "detail_de": "Join-URL fehlt"}
    base = raw[:-5] if raw.endswith("/join") else raw
    health = f"{base}/api/health"
    health_ok = _http_ok(health, timeout=timeout)
    join_ok = _join_page_ok(base, timeout=timeout)
    ok = health_ok and join_ok
    return {
        "ok": ok,
        "detail_de": f"health={'OK' if health_ok else 'FAIL'} join={'OK' if join_ok else 'FAIL'}",
        "join_url": f"{base}/join",
        "health_url": health,
    }


def open_wa_me_link(url: str) -> Dict[str, Any]:
    step = _run_opener(url)
    step["url"] = url
    if step.get("ok"):
        step["detail_de"] = "wa.me geöffnet"
    else:
        step["detail_de"] = step.get("detail_de") or "wa.me fehlgeschlagen"
    return step


def complete_self_send(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    """Join prüfen → Text+ZIP vorbereiten → Clipboard + wa.me + ZIP öffnen."""
    root = Path(root)
    cfg = load_whatsapp_config(root)
    phone = resolve_self_phone(cfg)
    text = _resolve_spread_text(root, cfg)
    zip_path = _resolve_zip_path(root, cfg) if cfg.get("attach_zip", True) else None
    from analytics.spread_shield import assert_shield, touch_rate_limit

    blocked = assert_shield(
        root,
        action="auto_send" if not dry_run and str(cfg.get("auto_send_mode") or "auto") != "manual" else "prepare_send",
        phone=phone,
        text=text,
        zip_path=zip_path,
        dry_run=dry_run,
    )
    if blocked:
        return blocked
    join_url = ""
    for line in text.splitlines():
        if line.strip().startswith(("http://", "https://")):
            join_url = line.strip().rstrip("/")
            if not join_url.endswith("/join"):
                join_url = join_url + ("" if "/join" in join_url else "/join")
            break

    from analytics.terminal_runtime import detect_runtime_context

    runtime = detect_runtime_context()
    doc: Dict[str, Any] = {
        "send_mode": "self",
        "phone_e164": phone,
        "text": text,
        "zip_path": str(zip_path) if zip_path else None,
        "runtime": runtime,
        "steps": [],
    }
    if not phone:
        doc.update({"ok": False, "detail_de": "self_phone_e164 fehlt"})
        return doc

    join_check = verify_join_reachable(join_url) if join_url else {"ok": False, "detail_de": "Join-Zeile fehlt"}
    doc["steps"].append({"kind": "join_check", **join_check})
    if dry_run:
        from analytics.whatsapp_auto_send import auto_send_capabilities

        doc.update(
            {
                "ok": join_check.get("ok"),
                "dry_run": True,
                "wa_me_url": build_wa_me_url(phone, text),
                "auto_capabilities": auto_send_capabilities(root, cfg),
                "detail_de": "Dry-run — Join + Text + ZIP bereit",
            }
        )
        return doc

    from analytics.whatsapp_auto_send import auto_send_self

    auto = auto_send_self(root, phone=phone, text=text, zip_path=zip_path, cfg=cfg)
    doc["steps"].append({"kind": "auto_send", **auto})
    if auto.get("ok"):
        doc["ok"] = bool(join_check.get("ok"))
        doc["send_ok"] = True
        doc["prepare_ok"] = False
        doc["delivery_mode"] = "auto"
        doc["detail_de"] = auto.get("detail_de") or "Auto-Send OK"
        doc["engine"] = auto.get("engine")
        doc["updated_at_utc"] = _utc_now()
        atomic_write_json(root / _EVIDENCE_REL, doc)
        if doc.get("ok"):
            try:
                from analytics.spread_autonomous import is_autonomous_spread_enabled

                touch_rate_limit(root, autonomous=is_autonomous_spread_enabled(root))
            except Exception:
                touch_rate_limit(root)
        return doc

    clip = copy_to_clipboard(text)
    doc["steps"].append({"kind": "clipboard", **clip})
    wa = open_wa_me_link(build_wa_me_url(phone, text))
    doc["steps"].append({"kind": "wa_me", **wa})
    zip_step: Dict[str, Any] = {"kind": "zip", "ok": False, "detail_de": "ZIP fehlt"}
    if zip_path and zip_path.is_file():
        zip_step = _run_opener(str(zip_path))
        zip_step["kind"] = "zip"
        zip_step["path"] = str(zip_path)
    doc["steps"].append(zip_step)

    manual_ok = bool(join_check.get("ok")) and bool(wa.get("ok")) and bool(zip_step.get("ok"))
    doc["send_ok"] = False
    doc["prepare_ok"] = manual_ok
    doc["delivery_mode"] = "manual_prepare"
    doc["ok"] = False
    doc["detail_de"] = (
        "Vorbereitet: Chat + ZIP offen — Senden-Button noch manuell (Auto-Send nicht verfügbar)"
        if manual_ok
        else "Unvollständig — siehe steps"
    )
    if manual_ok and not clip.get("ok"):
        doc["detail_de"] += " · wa.me hat Text vorausgefüllt"
    if not runtime.get("can_auto_send"):
        doc["detail_de"] += f" · Laufzeit: {runtime.get('headline_de')}"
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def send_spread_message(
    root: Path,
    phone: str,
    *,
    name: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_whatsapp_config(root)
    provider = str(cfg.get("provider") or "waha").strip().lower()
    text = _resolve_spread_text(root, cfg)
    zip_path = _resolve_zip_path(root, cfg) if cfg.get("attach_zip", True) else None
    chat_id = phone_to_chat_id(phone)
    phone_norm = normalize_phone_e164(phone)

    if not text:
        return {"ok": False, "detail_de": "Spread-Text fehlt", "provider": provider}
    if not phone_norm:
        return {"ok": False, "detail_de": "Telefonnummer ungültig", "provider": provider}

    from analytics.spread_shield import assert_shield, touch_rate_limit

    api_action = "api_send" if provider == "waha" else ("green_send" if provider == "green_api" else "prepare_send")
    blocked = assert_shield(
        root,
        action=api_action if provider != "wa_me" else "prepare_send",
        phone=phone_norm,
        text=text,
        zip_path=zip_path,
        dry_run=dry_run,
    )
    if blocked:
        return {**blocked, "provider": provider}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "provider": provider,
            "phone_e164": phone_norm,
            "chat_id": chat_id,
            "text_preview": text[:200],
            "zip_path": str(zip_path) if zip_path else None,
            "wa_me_url": build_wa_me_url(phone_norm, text),
        }

    results: Dict[str, Any] = {
        "provider": provider,
        "phone_e164": phone_norm,
        "name": name,
        "steps": [],
    }

    if provider == "wa_me":
        self_mode = str(cfg.get("send_mode") or "").strip().lower() == "self"
        if self_mode:
            return complete_self_send(root, dry_run=False)
        url = build_wa_me_url(phone_norm, text)
        step = open_wa_me_link(url)
        results["steps"].append({"kind": "wa_me", **step})
        results["ok"] = step.get("ok")
        results["detail_de"] = step.get("detail_de")
        results["manual_zip"] = str(zip_path) if zip_path else None
        results["send_mode"] = "direct"
        atomic_write_json(root / _EVIDENCE_REL, {**results, "updated_at_utc": _utc_now()})
        return results

    if not cfg.get("enabled"):
        return {
            "ok": False,
            "detail_de": "WhatsApp deaktiviert — bash tools/setup_whatsapp_spread.sh",
            "provider": provider,
        }

    if provider not in _OWN_ACCOUNT_PROVIDERS:
        return {
            "ok": False,
            "detail_de": "Nur wa_me/waha — eigene Nummer, kein Bot-Absender (CallMeBot/Green blockiert)",
            "provider": provider,
        }

    text_result: Dict[str, Any]
    if provider == "waha":
        text_result = _send_waha_text(root, cfg, chat_id, text)
    elif provider == "green_api":
        text_result = _send_green_text(root, cfg, chat_id, text)
    elif provider == "callmebot":
        text_result = _send_callmebot_text(root, cfg, phone_norm, text)
    else:
        return {"ok": False, "detail_de": f"Provider unbekannt: {provider}"}

    results["steps"].append({"kind": "text", **text_result})
    ok = bool(text_result.get("ok"))

    if zip_path and provider in ("waha", "green_api"):
        file_result: Dict[str, Any]
        if provider == "waha":
            file_result = _send_waha_file(root, cfg, chat_id, zip_path, caption="Active Alpha Worker ZIP")
        else:
            file_result = _send_green_file(root, cfg, chat_id, zip_path, caption="Active Alpha Worker ZIP")
        results["steps"].append({"kind": "file", **file_result})
        ok = ok and bool(file_result.get("ok"))
    elif zip_path and provider == "callmebot":
        results["steps"].append(
            {
                "kind": "file",
                "ok": False,
                "detail_de": "CallMeBot: ZIP manuell anhängen",
                "path": str(zip_path),
            }
        )

    results["ok"] = ok
    results["detail_de"] = "Versendet" if ok else "Versand fehlgeschlagen — verify ausführen"
    results["updated_at_utc"] = _utc_now()
    atomic_write_json(root / _EVIDENCE_REL, results)
    if ok:
        touch_rate_limit(root)
    return results


def send_to_self(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    cfg = load_whatsapp_config(root)
    phone = resolve_self_phone(cfg)
    if not phone:
        return {"ok": False, "detail_de": "self_phone_e164 fehlt in control/whatsapp_spread.json"}
    doc = send_spread_message(root, phone, name="self", dry_run=dry_run)
    doc["send_mode"] = "self"
    return doc


def send_to_recipient(
    root: Path,
    *,
    name: str = "",
    phone: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    cfg = load_whatsapp_config(root)
    if str(cfg.get("send_mode") or "").strip().lower() == "self" and not phone:
        return send_to_self(root, dry_run=dry_run)

    recipients = [r for r in (cfg.get("recipients") or []) if isinstance(r, dict)]
    target = None
    if name:
        for rec in recipients:
            if str(rec.get("name") or "").lower() == name.lower():
                target = rec
                break
    if target is None and phone:
        target = {"name": name or "custom", "phone_e164": phone}
    if target is None and recipients:
        target = recipients[0]
    if target is None:
        self_phone = resolve_self_phone(cfg)
        if self_phone:
            return send_spread_message(root, self_phone, name="self", dry_run=dry_run)
        return {"ok": False, "detail_de": "Kein Empfänger konfiguriert"}
    return send_spread_message(
        root,
        str(target.get("phone_e164") or phone),
        name=str(target.get("name") or name),
        dry_run=dry_run,
    )


def enable_whatsapp(root: Path, *, provider: str = "waha") -> Dict[str, Any]:
    root = Path(root)
    path = root / _CONFIG_REL
    cfg = load_whatsapp_config(root)
    cfg["enabled"] = True
    cfg["provider"] = provider
    cfg["schema_version"] = 1
    atomic_write_json(path, cfg)
    return {"ok": True, "provider": provider, "config": str(path)}
