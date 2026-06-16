"""R3 T212 Operator-API — Zugangsdaten, State, Gates (Domain; kein UI)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json, atomic_write_text

from analytics.r3_operator_surface_text import (
    OPERATOR_API_ENTER,
    OPERATOR_SAVED,
    start_hint_de,
)

OPERATOR_SETUP_REL = Path("control/r3_t212_operator_setup.json")


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


def credentials_configured(root: Path) -> bool:
    root = Path(root)
    try:
        from analytics.r3_t212_account_identity import credentials_fingerprint

        return bool(credentials_fingerprint(root))
    except Exception:
        return False


def load_operator_setup(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / OPERATOR_SETUP_REL)


def needs_operator_api_setup(root: Path) -> bool:
    """Einmalige Web-Eingabe — unabhängig von stiller .env ohne Setup-Marker."""
    doc = load_operator_setup(root)
    if not doc.get("web_setup_complete"):
        return True
    try:
        from analytics.r3_t212_account_identity import credentials_fingerprint

        fp = credentials_fingerprint(root)
    except Exception:
        fp = None
    saved_fp = str(doc.get("credentials_fingerprint") or "")
    if fp and saved_fp and fp != saved_fp:
        return True
    return False


def resolve_operator_api_state(root: Path) -> Dict[str, Any]:
    """SSoT — Web-Setup vs. gespeicherte Zugangsdaten."""
    root = Path(root)
    creds_ok = credentials_configured(root)
    needs = needs_operator_api_setup(root)
    ready = bool(creds_ok and not needs)
    setup = load_operator_setup(root)
    return {
        "schema_version": 1,
        "needs_api_setup": needs,
        "credentials_configured": creds_ok,
        "operator_api_ready": ready,
        "web_setup_complete": bool(setup.get("web_setup_complete")),
        "completed_at_utc": setup.get("completed_at_utc"),
        "message_de": OPERATOR_API_ENTER if needs or not ready else "",
        "setup_ref": str(OPERATOR_SETUP_REL).replace("\\", "/"),
    }


def operator_api_ready(root: Path) -> bool:
    return bool(resolve_operator_api_state(root).get("operator_api_ready"))


def mark_operator_api_setup_complete(root: Path) -> Dict[str, Any]:
    root = Path(root)
    try:
        from analytics.r3_t212_account_identity import credentials_fingerprint

        fp = credentials_fingerprint(root)
    except Exception:
        fp = None
    doc = {
        "schema_version": 1,
        "web_setup_complete": True,
        "completed_at_utc": _utc_now(),
        "credentials_fingerprint": fp,
        "via": "web",
    }
    atomic_write_json(root / OPERATOR_SETUP_REL, doc)
    return doc


def persist_operator_credentials_env(root: Path, *, api_key: str, api_secret: str) -> bool:
    """Zugangsdaten in root/.env — überlebt Neustart."""
    root = Path(root)
    key = str(api_key or "").strip()
    secret = str(api_secret or "").strip()
    if not key or not secret:
        return False
    env_path = root / ".env"
    keys = {"TRADING212_API_KEY": key, "TRADING212_API_SECRET": secret}
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            name = line.split("=", 1)[0].strip()
            if name in keys:
                out.append(f"{name}={keys[name]}")
                seen.add(name)
                continue
        out.append(line)
    for name, val in keys.items():
        if name not in seen:
            out.append(f"{name}={val}")
    atomic_write_text(env_path, "\n".join(out).rstrip() + "\n")
    os.environ["TRADING212_API_KEY"] = key
    os.environ["TRADING212_API_SECRET"] = secret
    return True


def operator_api_gate_block(root: Path, **extra: Any) -> Optional[Dict[str, Any]]:
    """Fail-closed wenn Web-Zugangsdaten fehlen — sonst None."""
    if not needs_operator_api_setup(root):
        return None
    return {
        "ok": False,
        "needs_api_setup": True,
        "operator_api_ready": False,
        "message_de": OPERATOR_API_ENTER,
        "error_de": OPERATOR_API_ENTER,
        **extra,
    }


def operator_api_account_block(root: Path) -> Optional[Dict[str, Any]]:
    block = operator_api_gate_block(
        root,
        t212_trusted=False,
        t212_trust_reason="NOT_CONFIGURED",
        planning_cash_eur=None,
        investable_eur=None,
        t212_trust_message_de=OPERATOR_API_ENTER,
    )
    return block


def merge_operator_api_fields(doc: Dict[str, Any], root: Path, *, persist_path: Optional[Path] = None) -> Dict[str, Any]:
    """Bond-/API-Docs mit Operator-State anreichern."""
    state = resolve_operator_api_state(root)
    out = {**doc, **state}
    if not state.get("needs_api_setup"):
        return out
    out.update(
        {
            "credentials_configured": False,
            "t212_trusted": False,
            "investable_eur": None,
            "cash_eur": None,
            "confirmation_de": OPERATOR_API_ENTER,
            "message_de": OPERATOR_API_ENTER,
            "state": "fail",
        }
    )
    if persist_path is not None:
        atomic_write_json(persist_path, out)
    return out


def operator_status_message(root: Path, *, reason_code: str | None = None) -> str:
    state = resolve_operator_api_state(root)
    if state.get("needs_api_setup"):
        return OPERATOR_API_ENTER
    return start_hint_de(needs_api=False, trusted=False, reason_code=reason_code)


def save_t212_credentials_from_web(
    root: Path,
    *,
    api_key: str,
    api_secret: str,
) -> Dict[str, Any]:
    root = Path(root)
    key = str(api_key or "").strip()
    secret = str(api_secret or "").strip()
    if not key or not secret:
        return {"ok": False, "message_de": OPERATOR_API_ENTER}
    try:
        from integrations.trading212.t212_credentials_ui_controller import apply_credentials_from_gui

        res = apply_credentials_from_gui(
            api_key=key,
            api_secret=secret,
            mode="LIVE_READ_ONLY",
            connection_name="Trading 212",
            persist=True,
            session_only=False,
            root=root,
        )
        env_ok = persist_operator_credentials_env(root, api_key=key, api_secret=secret)
        stored = str(res.get("stored") or "")
        layers = list(res.get("persisted_layers") or [])
        if not credentials_configured(root) and not env_ok:
            return {"ok": False, "message_de": OPERATOR_API_ENTER}
        if stored == "SESSION_ONLY" and not layers and not env_ok:
            return {"ok": False, "message_de": OPERATOR_API_ENTER}
        mark_operator_api_setup_complete(root)
        from analytics.r3_t212_api_bond import ensure_r3_t212_api_bond

        bond = ensure_r3_t212_api_bond(root, persist=True)
        if bond.get("account_fingerprint"):
            try:
                from analytics.r3_t212_account_identity import confirm_t212_account

                confirm_t212_account(root, bond=bond)
            except Exception:
                pass
        state = resolve_operator_api_state(root)
        return {
            "ok": True,
            "message_de": OPERATOR_SAVED,
            "needs_api_setup": False,
            "operator_api_ready": bool(state.get("operator_api_ready")),
            "setup_ok": bool(bond.get("setup_ok")),
            "t212_trusted": bool(bond.get("t212_trusted")),
            "headline_de": str(bond.get("headline_de") or OPERATOR_SAVED),
            "next_de": str(bond.get("next_de") or ""),
        }
    except Exception:
        return {"ok": False, "message_de": OPERATOR_API_ENTER}


def ensure_operator_bond_lock(root: Path, bond: Dict[str, Any], api_state: Dict[str, Any]) -> Dict[str, Any]:
    """Bond-Lock setzen sobald Operator-Zugangsdaten bereit."""
    if not api_state.get("operator_api_ready") or bond.get("bonded"):
        return bond
    from analytics.r3_t212_api_bond import load_bond_lock

    _BOND_LOCK = Path("control/r3_t212_api_bond.json")
    lock = load_bond_lock(root)
    lock = {
        **lock,
        "bonded": True,
        "bonded_at_utc": lock.get("bonded_at_utc") or _utc_now(),
        "last_confirmed_at_utc": _utc_now(),
        "credentials_fingerprint": bond.get("credentials_fingerprint") or lock.get("credentials_fingerprint"),
    }
    atomic_write_json(Path(root) / _BOND_LOCK, lock)
    return {**bond, "bonded": True}
