"""R3 Local-First — alles lokal wirksam, genau eine HTTPS-Spiegelung."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_local_first_policy.json")
_MIRROR_REL = Path("control/r3_https_mirror.json")
_EVIDENCE_REL = Path("evidence/r3_local_first_latest.json")
_TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


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


def load_local_first_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def is_r3_local_first(root: Path) -> bool:
    policy = load_local_first_policy(root)
    if policy.get("status") == "AUTHORITATIVE":
        return True
    try:
        from analytics.alpha_model_local_runtime import is_local_only

        return is_local_only(root)
    except Exception:
        return False


def local_hub_authoritative_url(root: Path, *, port: int = 17890, path: str = "") -> str:
    root = Path(root)
    cfg = _load_json(root / "control/alpha_model_local_runtime.json")
    base = str(cfg.get("hub_url") or f"http://127.0.0.1:{int(port)}").rstrip("/")
    if path:
        p = path if str(path).startswith("/") else f"/{path}"
        return f"{base}{p}"
    return base


def load_https_mirror(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _MIRROR_REL)


def https_mirror_base_url(root: Path) -> Optional[str]:
    mirror = load_https_mirror(root)
    url = str(mirror.get("public_base_url") or "").strip().rstrip("/")
    if url.startswith("https://") and mirror.get("enabled", True):
        return url
    fed = _load_json(Path(root) / "control/preview_federation.json")
    fed_url = str(fed.get("public_base_url") or "").strip().rstrip("/")
    if fed_url.startswith("https://"):
        return fed_url
    return None


def _collect_mirror_candidates(root: Path) -> List[str]:
    root = Path(root)
    found: List[str] = []
    for rel in (
        "control/preview_federation.json",
        "control/cloudflare_tunnel.json",
        "evidence/ki_tunnel_connection_latest.json",
        "control/r3_https_mirror.json",
    ):
        doc = _load_json(root / rel)
        for key in ("public_base_url", "public_url"):
            val = str(doc.get(key) or "").strip().rstrip("/")
            if val.startswith("https://") and val not in found:
                found.append(val)
    return found


def _pick_canonical_mirror(root: Path) -> Optional[str]:
    root = Path(root)
    existing = load_https_mirror(root)
    locked = str(existing.get("public_base_url") or "").strip().rstrip("/")
    if locked.startswith("https://") and existing.get("locked"):
        return locked
    fed = _load_json(root / "control/preview_federation.json")
    if fed.get("public_base_url_locked"):
        fed_url = str(fed.get("public_base_url") or "").strip().rstrip("/")
        if fed_url.startswith("https://"):
            return fed_url
    candidates = _collect_mirror_candidates(root)
    return candidates[0] if candidates else None


def _rewrite_ki_tunnel(root: Path, mirror: str) -> bool:
    path = root / "evidence/ki_tunnel_connection_latest.json"
    doc = _load_json(path)
    if not doc:
        return False
    base = mirror.rstrip("/")
    doc["public_base_url"] = base
    doc["primary_channel"] = "r3_local"
    doc["local"] = {
        "desktop": local_hub_authoritative_url(root, path="/desktop"),
        "hub": local_hub_authoritative_url(root),
        "tunnel_watcher": "tools/run_remote_tunnel.py",
    }
    doc["endpoints"] = {
        "desktop": f"{base}/desktop",
        "health": f"{base}/api/health",
        "join": f"{base}/join",
        "ki_chat_api": f"{base}/api/ki/chat",
        "ki_guidance_api": f"{base}/api/ki/guidance",
        "ki_status_api": f"{base}/api/ki/status",
        "step_b": f"{base}/api/desktop/step-b",
    }
    doc["freedom_path_de"] = [
        "Lokal: http://127.0.0.1:17890/desktop",
        f"HTTPS-Spiegel: {base}/desktop",
        "CLI: python3 tools/ai_kernel.py status|learn|h1-status",
    ]
    doc["headline_de"] = "Lokal wirksam — eine HTTPS-Spiegelung"
    doc["security_note_de"] = "Nur eine Spiegel-URL — alles andere lokal"
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(path, doc)
    return True


def apply_r3_local_first(root: Path) -> Dict[str, Any]:
    """Lokal authoritative + eine HTTPS-Spiegelung — Duplikate entfernen."""
    root = Path(root)
    policy = load_local_first_policy(root)
    hub_bind = "127.0.0.1"
    hub_port = 17890
    hub_url = f"http://{hub_bind}:{hub_port}"
    mirror = _pick_canonical_mirror(root)
    changed: List[str] = []

    runtime_path = root / "control/alpha_model_local_runtime.json"
    runtime = _load_json(runtime_path) or {"schema_version": 1}
    runtime_updates = {
        "status": "AUTHORITATIVE",
        "local_only": True,
        "remote_workers_expected": False,
        "tunnel_required": False,
        "hub_bind": hub_bind,
        "hub_port": hub_port,
        "hub_url": hub_url,
        "headline_de": "Lokal wirksam — eine HTTPS-Spiegelung",
        "apply_command_de": str(policy.get("apply_command_de") or "bash tools/king_ops.sh r3-local"),
        "local_first_policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "https_mirror_ref": str(_MIRROR_REL).replace("\\", "/"),
    }
    for k, v in runtime_updates.items():
        if runtime.get(k) != v:
            runtime[k] = v
            changed.append(f"alpha_model_local_runtime:{k}")
    atomic_write_json(runtime_path, runtime)

    fed_path = root / "control/preview_federation.json"
    fed = _load_json(fed_path) or {"schema_version": 1, "enabled": True}
    fed_updates: Dict[str, Any] = {
        "bind_host": hub_bind,
        "lan_bind": False,
        "hub_port": hub_port,
        "remote_access_mode": "local_first_single_mirror",
        "remote_workers_expected": False,
        "note_de": "Lokal wirksam — genau eine HTTPS-Spiegelung (extern only)",
    }
    if mirror:
        fed_updates["public_base_url"] = mirror
        fed_updates["public_base_url_locked"] = True
    else:
        fed_updates["public_base_url"] = hub_url
        fed_updates["public_base_url_locked"] = False
    for k, v in fed_updates.items():
        if fed.get(k) != v:
            fed[k] = v
            changed.append(f"preview_federation:{k}")
    atomic_write_json(fed_path, fed)

    mirror_doc = {
        "schema_version": 1,
        "enabled": bool(mirror),
        "locked": True,
        "public_base_url": mirror,
        "local_hub": hub_url,
        "mode": "single_mirror",
        "stable": False,
        "note_de": "Einzige HTTPS-Spiegelung — UI und Cockpit bleiben lokal",
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _MIRROR_REL, mirror_doc)
    changed.append("r3_https_mirror")

    cf_path = root / "control/cloudflare_tunnel.json"
    if mirror:
        cf = _load_json(cf_path)
        if cf.get("public_url") != mirror:
            cf["public_url"] = mirror
            cf["note_de"] = "Spiegel synchronisiert — siehe r3_https_mirror.json"
            atomic_write_json(cf_path, cf)
            changed.append("cloudflare_tunnel:sync")
    elif cf_path.is_file():
        cf_path.unlink()
        changed.append("cloudflare_tunnel:removed")

    for rel in (
        "control/AI_KERNEL.json",
        "control/active_alpha_unified.json",
    ):
        doc = _load_json(root / rel)
        if not doc:
            continue
        tunnel = dict(doc.get("tunnel") or {})
        tunnel.update(
            {
                "local_only": True,
                "tunnel_required": False,
                "local_hub": hub_url,
                "public_base_url": mirror,
                "mode": "local_first_single_mirror",
                "mirror_ref": str(_MIRROR_REL).replace("\\", "/"),
            }
        )
        doc["tunnel"] = tunnel
        if str(rel).endswith("AI_KERNEL.json"):
            doc["primary_channel_de"] = "R3 lokal 127.0.0.1:17890 — eine HTTPS-Spiegelung extern"
        atomic_write_json(root / rel, doc)
        changed.append(Path(rel).stem)

    if mirror and _rewrite_ki_tunnel(root, mirror):
        changed.append("ki_tunnel_connection:dedupe")

    try:
        from analytics.alpha_model_local_runtime import apply_local_runtime

        apply_local_runtime(root)
        changed.append("alpha_model_local_runtime:apply")
    except Exception:
        pass

    if mirror:
        fed_after = _load_json(fed_path)
        fed_after["public_base_url"] = mirror
        fed_after["public_base_url_locked"] = True
        atomic_write_json(fed_path, fed_after)

    doc = {
        "schema_version": 1,
        "applied_at_utc": _utc_now(),
        "ok": True,
        "local_hub": hub_url,
        "https_mirror": mirror,
        "mirror_count": 1 if mirror else 0,
        "changed": changed,
        "headline_de": (
            f"Lokal aktiv · HTTPS-Spiegel: {mirror}"
            if mirror
            else "Lokal aktiv — keine HTTPS-Spiegelung konfiguriert"
        ),
        "confirmation_de": (
            f"Alles lokal · {hub_url}/r3 — wächst mit der Zeit · Spiegel optional"
            if mirror
            else f"Alles lokal · {hub_url}/r3 — wächst mit der Zeit"
        ),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def verify_r3_local_first(root: Path) -> Dict[str, Any]:
    root = Path(root)
    checks: List[Dict[str, Any]] = []

    def add(cid: str, label: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "label_de": label, "ok": ok, "detail_de": detail})

    runtime = _load_json(root / "control/alpha_model_local_runtime.json")
    add("local_only", "Lokal authoritative", runtime.get("local_only") is True, str(runtime.get("hub_url") or ""))

    fed = _load_json(root / "control/preview_federation.json")
    add(
        "loopback_bind",
        "Hub nur loopback",
        str(fed.get("bind_host") or "") in ("127.0.0.1", "localhost") and not fed.get("lan_bind"),
        str(fed.get("bind_host") or ""),
    )
    add(
        "no_remote_workers",
        "Keine Remote-Worker Pflicht",
        fed.get("remote_workers_expected") is False,
        str(fed.get("remote_access_mode") or ""),
    )

    mirrors = _collect_mirror_candidates(root)
    unique = sorted(set(mirrors))
    add(
        "single_mirror",
        "Max. eine HTTPS-Spiegelung",
        len(unique) <= 1,
        ", ".join(unique) if unique else "keine",
    )

    mirror_cfg = load_https_mirror(root)
    canonical = str(mirror_cfg.get("public_base_url") or "").rstrip("/")
    if unique:
        add(
            "mirror_locked",
            "Spiegel in r3_https_mirror.json",
            canonical in unique,
            canonical or "—",
        )

    ki = _load_json(root / "evidence/ki_tunnel_connection_latest.json")
    if ki:
        ki_urls = set(_TUNNEL_RE.findall(json.dumps(ki, ensure_ascii=False)))
        add(
            "ki_tunnel_deduped",
            "KI-Tunnel ohne URL-Duplikate",
            len(ki_urls) <= 1,
            str(len(ki_urls)),
        )

    passed = sum(1 for c in checks if c.get("ok"))
    total = len(checks)
    ok = passed == total
    return {
        "schema_version": 1,
        "verified_at_utc": _utc_now(),
        "ok": ok,
        "checks_passed": passed,
        "checks_total": total,
        "checks": checks,
        "https_mirror": canonical or (unique[0] if unique else None),
        "local_hub": local_hub_authoritative_url(root),
        "headline_de": "Lokal + eine Spiegelung OK" if ok else f"Local-First unvollständig — {passed}/{total}",
    }


R3_LOCAL_FIRST_CSS = """
.r3-local-first {
  text-align: center; font-size: 11px; color: var(--muted); margin: 0 0 8px;
}
.r3-local-first.ok { color: var(--ok, #32d74b); }
"""


def render_r3_local_first_confirmation(root: Path) -> str:
    doc = _load_json(Path(root) / _EVIDENCE_REL)
    if not doc:
        doc = {"confirmation_de": "Lokal wirksam", "ok": True}
    text = str(doc.get("confirmation_de") or doc.get("headline_de") or "Lokal wirksam")
    import html

    cls = "ok" if doc.get("ok", True) else ""
    return (
        f'<p class="r3-local-first {cls}" id="r3-local-first" '
        f'aria-label="Lokal und HTTPS-Spiegel">{html.escape(text)}</p>'
    )
