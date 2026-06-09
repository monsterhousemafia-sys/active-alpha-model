"""Spread-Schott — fail-closed gegen unautorisierte externe Aktionen."""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/spread_shield.json")
_EVIDENCE_REL = Path("evidence/spread_shield_latest.json")
_RATE_REL = Path("evidence/spread_shield_rate.json")
_SECRET_PATTERNS = (
    r"api[_-]?key",
    r"secret",
    r"password",
    r"token\s*=",
    r"BEGIN\s+(RSA|OPENSSH)\s+PRIVATE",
    r"sk-[a-zA-Z0-9]{10,}",
)
_LOCAL_WAHA_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


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


def load_shield_config(root: Path) -> Dict[str, Any]:
    cfg = _load_json(Path(root) / _CONFIG_REL)
    if not cfg:
        return {
            "schema_version": 1,
            "enabled": True,
            "self_only": True,
            "own_account_only": True,
            "allowed_providers": ["wa_me", "waha"],
            "waha_localhost_only": True,
            "require_human_confirm_for_api_send": True,
            "require_dry_run_env_for_agents": True,
            "block_bot_providers": True,
            "block_direct_send": True,
            "rate_limit_seconds": 60,
            "autonomous_rate_limit_seconds": 21600,
            "require_url_sync_for_send": True,
            "require_spread_security_for_autonomous": True,
            "max_text_bytes": 4096,
            "zip_max_bytes": 5_242_880,
        }
    return cfg


def _extract_join_url(text: str) -> str:
    for line in str(text or "").splitlines():
        raw = line.strip().rstrip("/")
        if raw.startswith(("http://", "https://")):
            if not raw.endswith("/join"):
                raw = f"{raw}/join"
            return raw
    return ""


def _canonical_join_urls(root: Path) -> List[str]:
    try:
        from analytics.community_spread_plan import collect_spread_urls

        urls = collect_spread_urls(root)
        out: List[str] = []
        for key in ("join_remote", "join_lan", "remote_url", "lan_url"):
            raw = str(urls.get(key) or "").strip().rstrip("/")
            if not raw:
                continue
            if key in {"remote_url", "lan_url"}:
                raw = f"{raw}/join"
            if raw not in out:
                out.append(raw)
        return out
    except Exception:
        return []


def _human_confirm() -> bool:
    return os.environ.get("AA_SPREAD_HUMAN_CONFIRM", "").strip().lower() in ("1", "true", "yes")


def _agent_dry_run_env() -> bool:
    dry = os.environ.get("AA_EXECUTION_DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    no_live = os.environ.get("AA_NO_LIVE_ORDER_SUBMISSION", "").strip().lower() in ("1", "true", "yes")
    return dry and no_live


def _zip_allowed(root: Path, zip_path: Optional[Path], cfg: Dict[str, Any]) -> Dict[str, Any]:
    if zip_path is None:
        return {"id": "zip_path", "ok": True, "detail_de": "kein ZIP"}
    try:
        resolved = zip_path.resolve()
    except OSError:
        return {"id": "zip_path", "ok": False, "detail_de": "ZIP-Pfad ungültig"}
    if not resolved.is_file():
        return {"id": "zip_path", "ok": False, "detail_de": "ZIP fehlt"}
    max_bytes = int(cfg.get("zip_max_bytes") or 5_242_880)
    size = resolved.stat().st_size
    if size > max_bytes:
        return {"id": "zip_path", "ok": False, "detail_de": f"ZIP zu groß ({size} > {max_bytes})"}
    allowed_roots = [Path(root).resolve(), Path.home().resolve()]
    if not any(str(resolved).startswith(str(base)) for base in allowed_roots):
        return {"id": "zip_path", "ok": False, "detail_de": "ZIP außerhalb erlaubter Wurzeln"}
    return {"id": "zip_path", "ok": True, "detail_de": str(resolved), "path": str(resolved)}


def _text_safe(text: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    payload = str(text or "")
    max_bytes = int(cfg.get("max_text_bytes") or 4096)
    if len(payload.encode("utf-8")) > max_bytes:
        return {"id": "text_safe", "ok": False, "detail_de": "Text zu lang"}
    lowered = payload.lower()
    for pat in _SECRET_PATTERNS:
        if re.search(pat, lowered, flags=re.IGNORECASE):
            return {"id": "text_safe", "ok": False, "detail_de": f"Verdächtiges Muster blockiert ({pat})"}
    return {"id": "text_safe", "ok": True, "detail_de": "Text sauber"}


def _phone_allowed(root: Path, phone: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.whatsapp_spread import load_whatsapp_config, normalize_phone_e164, resolve_self_phone

    wa = load_whatsapp_config(root)
    target = normalize_phone_e164(phone)
    if not target:
        return {"id": "phone", "ok": False, "detail_de": "Nummer leer"}
    if not cfg.get("self_only", True):
        return {"id": "phone", "ok": True, "detail_de": target}
    self_phone = resolve_self_phone(wa)
    if not self_phone:
        return {"id": "phone", "ok": False, "detail_de": "self_phone_e164 fehlt"}
    ok = target == self_phone
    return {
        "id": "phone",
        "ok": ok,
        "detail_de": "nur eigene Nummer" if ok else f"BLOCK: {target} ≠ {self_phone}",
    }


def _provider_allowed(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.whatsapp_spread import load_whatsapp_config

    wa = load_whatsapp_config(root)
    provider = str(wa.get("provider") or "wa_me").strip().lower()
    allowed = {str(x).strip().lower() for x in (cfg.get("allowed_providers") or ["wa_me", "waha"])}
    bot = provider in {"callmebot", "green_api"}
    if cfg.get("block_bot_providers", True) and bot:
        return {"id": "provider", "ok": False, "detail_de": f"Bot-Provider blockiert: {provider}"}
    if cfg.get("own_account_only", True) and provider not in allowed:
        return {"id": "provider", "ok": False, "detail_de": f"Provider nicht erlaubt: {provider}"}
    if provider == "waha" and cfg.get("waha_localhost_only", True):
        base = str((wa.get("waha") or {}).get("base_url") or "")
        host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0].lower()
        if host not in _LOCAL_WAHA_HOSTS:
            return {"id": "provider", "ok": False, "detail_de": f"WAHA nur localhost — nicht {host}"}
    return {"id": "provider", "ok": True, "detail_de": provider}


def _safety_flags(root: Path) -> Dict[str, Any]:
    from analytics.spread_secure_ops import _check_join_token, _check_safety_flags

    checks = [_check_safety_flags(root), _check_join_token(root)]
    hard = [c for c in checks if not c.get("ok")]
    ok = not hard
    return {
        "id": "safety_flags",
        "ok": ok,
        "detail_de": "Safety OK" if ok else f"BLOCK: {[c.get('id') for c in hard]}",
        "blockers": [c.get("id") for c in hard],
    }


def _autonomous_spread_allows(root: Path, *, action: str) -> bool:
    spread_actions = {"auto_send", "prepare_send"}
    if action not in spread_actions:
        return False
    try:
        from analytics.spread_autonomous import (
            is_autonomous_spread_enabled,
            is_autonomous_spread_paused,
            operator_stock_veto_active,
        )

        return (
            is_autonomous_spread_enabled(root)
            and not is_autonomous_spread_paused(root)
            and operator_stock_veto_active(root)
        )
    except Exception:
        return False


def _autonomous_pause(root: Path, *, action: str, dry_run: bool) -> Dict[str, Any]:
    if dry_run or action not in {"auto_send", "prepare_send"}:
        return {"id": "autonomous_pause", "ok": True, "detail_de": "n/a"}
    try:
        from analytics.spread_autonomous import is_autonomous_spread_enabled, is_autonomous_spread_paused

        if not is_autonomous_spread_enabled(root):
            return {"id": "autonomous_pause", "ok": True, "detail_de": "autonom aus"}
        paused = is_autonomous_spread_paused(root)
        return {
            "id": "autonomous_pause",
            "ok": not paused,
            "detail_de": "Spread autonom pausiert — resume zum Fortsetzen" if paused else "nicht pausiert",
        }
    except Exception as exc:
        return {"id": "autonomous_pause", "ok": False, "detail_de": str(exc)[:80]}


def _spread_security_gate(root: Path, cfg: Dict[str, Any], *, action: str, dry_run: bool) -> Dict[str, Any]:
    if dry_run or action not in {"auto_send", "prepare_send"}:
        return {"id": "spread_security", "ok": True, "detail_de": "n/a"}
    if not cfg.get("require_spread_security_for_autonomous", True):
        return {"id": "spread_security", "ok": True, "detail_de": "nicht erzwungen"}
    if not _autonomous_spread_allows(root, action=action):
        return {"id": "spread_security", "ok": True, "detail_de": "nur autonom"}
    from analytics.spread_secure_ops import verify_spread_security

    sec = verify_spread_security(root)
    ok = bool(sec.get("ok"))
    return {
        "id": "spread_security",
        "ok": ok,
        "detail_de": sec.get("headline_de") or ("OK" if ok else "Security rot"),
    }


def _url_sync_gate(root: Path, cfg: Dict[str, Any], *, action: str, text: str, dry_run: bool) -> Dict[str, Any]:
    if dry_run or not text or action not in {"auto_send", "prepare_send"}:
        return {"id": "url_sync", "ok": True, "detail_de": "n/a"}
    if not cfg.get("require_url_sync_for_send", True):
        return {"id": "url_sync", "ok": True, "detail_de": "nicht erzwungen"}
    text_url = _extract_join_url(text)
    if not text_url:
        return {"id": "url_sync", "ok": False, "detail_de": "Join-URL in Text fehlt"}
    canonical = _canonical_join_urls(root)
    if not canonical:
        return {"id": "url_sync", "ok": True, "detail_de": "keine kanonische URL — übersprungen"}
    ok = text_url in canonical
    return {
        "id": "url_sync",
        "ok": ok,
        "detail_de": "URL synchron" if ok else f"BLOCK: Text {text_url[:48]} ≠ kanonisch",
        "text_url": text_url,
        "canonical": canonical[:3],
    }


def _autonomous_rate_limit(root: Path, cfg: Dict[str, Any], *, action: str, dry_run: bool) -> Dict[str, Any]:
    if dry_run or action not in {"auto_send", "prepare_send"}:
        return {"id": "autonomous_rate", "ok": True, "detail_de": "n/a"}
    if not _autonomous_spread_allows(root, action=action):
        return {"id": "autonomous_rate", "ok": True, "detail_de": "nur autonom"}
    window = int(cfg.get("autonomous_rate_limit_seconds") or 21600)
    path = Path(root) / _RATE_REL
    now = time.time()
    doc = _load_json(path)
    last = float(doc.get("autonomous_last_action_at") or 0)
    if last and now - last < window:
        return {
            "id": "autonomous_rate",
            "ok": False,
            "detail_de": f"Autonom-Limit {window}s — warte {int(window - (now - last))}s",
        }
    return {"id": "autonomous_rate", "ok": True, "detail_de": f"OK ({window}s)"}


def _agent_env(root: Path, cfg: Dict[str, Any], *, dry_run: bool, action: str = "verify") -> Dict[str, Any]:
    if _autonomous_spread_allows(root, action=action) and not dry_run:
        return {"id": "agent_env", "ok": True, "detail_de": "Spread autonom freigegeben — nur Verbreitung"}
    if not cfg.get("require_dry_run_env_for_agents", True):
        return {"id": "agent_env", "ok": True, "detail_de": "Agent-Env nicht erzwungen"}
    if dry_run:
        return {"id": "agent_env", "ok": True, "detail_de": "Dry-run — Agent-Env optional"}
    if _human_confirm():
        return {"id": "agent_env", "ok": True, "detail_de": "Human-Confirm gesetzt"}
    ok = _agent_dry_run_env()
    return {
        "id": "agent_env",
        "ok": ok,
        "detail_de": "AA_EXECUTION_DRY_RUN + AA_NO_LIVE_ORDER_SUBMISSION" if ok else "Agent ohne Dry-Run-Env blockiert",
    }


def _human_confirm_gate(
    root: Path,
    cfg: Dict[str, Any],
    *,
    action: str,
    dry_run: bool,
) -> Dict[str, Any]:
    api_actions = {"api_send", "waha_send", "green_send", "callmebot_send", "auto_send"}
    if action not in api_actions:
        return {"id": "human_confirm", "ok": True, "detail_de": "Prepare-only — kein API-Send"}
    if dry_run:
        return {"id": "human_confirm", "ok": True, "detail_de": "Dry-run"}
    if _autonomous_spread_allows(root, action=action):
        return {
            "id": "human_confirm",
            "ok": True,
            "detail_de": "Spread autonom — Operator-Veto nur bei Aktien",
        }
    if not cfg.get("require_human_confirm_for_api_send", True):
        return {"id": "human_confirm", "ok": True, "detail_de": "Confirm nicht erzwungen"}
    if action == "auto_send" and (_human_confirm() or _agent_dry_run_env()):
        return {"id": "human_confirm", "ok": True, "detail_de": "Auto-Send (Self) — Agent-Env oder Confirm"}
    ok = _human_confirm()
    return {
        "id": "human_confirm",
        "ok": ok,
        "detail_de": "AA_SPREAD_HUMAN_CONFIRM=1" if ok else "API-Send ohne Human-Confirm blockiert",
    }


def _rate_limit(root: Path, cfg: Dict[str, Any], *, action: str, dry_run: bool) -> Dict[str, Any]:
    if dry_run or action == "verify":
        return {"id": "rate_limit", "ok": True, "detail_de": "kein Rate-Limit"}
    window = int(cfg.get("rate_limit_seconds") or 60)
    path = Path(root) / _RATE_REL
    now = time.time()
    doc = _load_json(path)
    last = float(doc.get("last_action_at") or 0)
    if now - last < window:
        return {
            "id": "rate_limit",
            "ok": False,
            "detail_de": f"Rate-Limit {window}s — warte {int(window - (now - last))}s",
        }
    return {"id": "rate_limit", "ok": True, "detail_de": f"OK ({window}s)"}


def touch_rate_limit(root: Path, *, autonomous: bool = False) -> None:
    path = Path(root) / _RATE_REL
    doc = _load_json(path)
    now = time.time()
    doc.update(
        {
            "schema_version": 1,
            "last_action_at": now,
            "updated_at_utc": _utc_now(),
        }
    )
    if autonomous:
        doc["autonomous_last_action_at"] = now
    atomic_write_json(path, doc)


def evaluate_spread_shield(
    root: Path,
    *,
    action: str = "verify",
    phone: str = "",
    text: str = "",
    zip_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_shield_config(root)
    if not cfg.get("enabled", True):
        return {"ok": True, "enabled": False, "checks": [], "headline_de": "Schott deaktiviert"}

    checks: List[Dict[str, Any]] = [
        _safety_flags(root),
        _provider_allowed(root, cfg),
        _autonomous_pause(root, action=action, dry_run=dry_run),
        _spread_security_gate(root, cfg, action=action, dry_run=dry_run),
        _agent_env(root, cfg, dry_run=dry_run, action=action),
        _human_confirm_gate(root, cfg, action=action, dry_run=dry_run),
        _rate_limit(root, cfg, action=action, dry_run=dry_run),
        _autonomous_rate_limit(root, cfg, action=action, dry_run=dry_run),
    ]
    if phone:
        checks.append(_phone_allowed(root, phone, cfg))
    if text:
        checks.append(_text_safe(text, cfg))
        checks.append(_url_sync_gate(root, cfg, action=action, text=text, dry_run=dry_run))
    if zip_path is not None:
        checks.append(_zip_allowed(root, zip_path, cfg))

    ok = all(c.get("ok") for c in checks)
    doc = {
        "schema_version": 1,
        "ok": ok,
        "enabled": True,
        "action": action,
        "dry_run": dry_run,
        "checks": checks,
        "headline_de": "Schott geschlossen — sicher" if ok else "Schott BLOCKIERT",
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def shield_block_response(shield: Dict[str, Any]) -> Dict[str, Any]:
    blockers = [c for c in shield.get("checks") or [] if not c.get("ok")]
    return {
        "ok": False,
        "shield_blocked": True,
        "detail_de": shield.get("headline_de") or "Schott blockiert",
        "blockers": blockers,
        "hint_de": "Dry-run erlaubt · API-Send: AA_SPREAD_HUMAN_CONFIRM=1 · Nur eigene Nummer",
    }


def assert_shield(
    root: Path,
    *,
    action: str,
    phone: str = "",
    text: str = "",
    zip_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Optional[Dict[str, Any]]:
    shield = evaluate_spread_shield(
        root,
        action=action,
        phone=phone,
        text=text,
        zip_path=zip_path,
        dry_run=dry_run,
    )
    if shield.get("ok"):
        return None
    return shield_block_response(shield)
