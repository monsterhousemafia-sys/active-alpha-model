"""Alpha Model — strikt lokaler Runtime-Modus (kein Tunnel/LAN-Pflicht)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/alpha_model_local_runtime.json")
_EVIDENCE_REL = Path("evidence/alpha_model_local_runtime_latest.json")


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


def load_local_runtime(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _CONFIG_REL)
    if doc:
        return doc
    return {
        "local_only": True,
        "hub_bind": "127.0.0.1",
        "hub_url": "http://127.0.0.1:17890",
        "tunnel_required": False,
    }


def is_local_only(root: Path) -> bool:
    return load_local_runtime(root).get("local_only", True) is not False


def enable_world_runtime(root: Path) -> Dict[str, Any]:
    """Schaltet von lokal-only auf Welt-Erreichbarkeit (Tunnel + Remote-Worker)."""
    root = Path(root)
    cfg_path = root / _CONFIG_REL
    cfg = load_local_runtime(root)
    changed: List[str] = []

    updates = {
        "local_only": False,
        "remote_workers_expected": True,
        "tunnel_required": True,
        "headline_de": "Welt-Modus — Remote-Worker über Tunnel/Internet erwartet",
    }
    for k, v in updates.items():
        if cfg.get(k) != v:
            cfg[k] = v
            changed.append(f"local_runtime:{k}")
    cfg["world_enabled_at_utc"] = _utc_now()
    atomic_write_json(cfg_path, cfg)

    fed_path = root / "control/preview_federation.json"
    fed = _load_json(fed_path) or {"schema_version": 1, "enabled": True}
    fed_updates = {
        "remote_workers_expected": True,
        "note_de": "Welt aktiv — Worker weltweit via Tunnel-URL + join_token",
    }
    for k, v in fed_updates.items():
        if fed.get(k) != v:
            fed[k] = v
            changed.append(f"preview_federation:{k}")
    atomic_write_json(fed_path, fed)

    kernel_path = root / "control/AI_KERNEL.json"
    kernel = _load_json(kernel_path)
    if kernel:
        tunnel = dict(kernel.get("tunnel") or {})
        if tunnel.get("local_only") is not False:
            tunnel["local_only"] = False
            tunnel["tunnel_required"] = True
            tunnel["mode"] = tunnel.get("mode") or "cloudflared"
            changed.append("AI_KERNEL:tunnel")
        kernel["tunnel"] = tunnel
        atomic_write_json(kernel_path, kernel)

    doc = {
        "schema_version": 1,
        "applied_at_utc": _utc_now(),
        "ok": True,
        "local_only": False,
        "remote_workers_expected": True,
        "changed": changed,
        "headline_de": "Welt-Runtime aktiv — öffentliche Join-URL für Worker",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def apply_local_runtime(root: Path) -> Dict[str, Any]:
    """Synchronisiert Federation, Kernel und Adaptive-Runtime auf lokal-only."""
    root = Path(root)
    cfg = load_local_runtime(root)
    if not is_local_only(root):
        return {"ok": False, "headline_de": "local_only deaktiviert — nichts geändert"}

    hub_bind = str(cfg.get("hub_bind") or "127.0.0.1")
    hub_url = str(cfg.get("hub_url") or "http://127.0.0.1:17890").rstrip("/")
    hub_port = int(cfg.get("hub_port") or 17890)
    changed: List[str] = []

    fed_path = root / "control/preview_federation.json"
    fed = _load_json(fed_path) or {"schema_version": 1, "enabled": True}
    fed_updates = {
        "lan_bind": False,
        "bind_host": hub_bind,
        "hub_port": hub_port,
        "public_base_url": hub_url,
        "public_base_url_locked": False,
        "remote_access_mode": "local_only",
        "remote_workers_expected": False,
        "note_de": "Lokal-only — kein Cloudflare/Tunnel-Pflicht; Remote optional später",
    }
    for k, v in fed_updates.items():
        if fed.get(k) != v:
            fed[k] = v
            changed.append(f"preview_federation:{k}")
    atomic_write_json(fed_path, fed)

    kernel_path = root / "control/AI_KERNEL.json"
    kernel = _load_json(kernel_path)
    if kernel:
        kernel["primary_channel_de"] = (
            "alpha-model-agent + Cockpit 127.0.0.1:17890 + Ollama 127.0.0.1 (lokal only)"
        )
        kernel["local_runtime"] = _CONFIG_REL.as_posix()
        kernel["operator_surfaces_de"] = list(cfg.get("operator_surfaces_de") or [])
        tunnel = dict(kernel.get("tunnel") or {})
        tunnel.update(
            {
                "local_only": True,
                "tunnel_required": False,
                "local_hub": hub_url,
                "public_base_url": None,
                "stable": None,
                "mode": "local_only",
            }
        )
        kernel["tunnel"] = tunnel
        atomic_write_json(kernel_path, kernel)
        changed.append("AI_KERNEL")

    unified_path = root / "control/active_alpha_unified.json"
    unified = _load_json(unified_path)
    if unified:
        unified["local_runtime"] = _CONFIG_REL.as_posix()
        unified["tunnel"] = {
            "local_only": True,
            "tunnel_required": False,
            "local_hub": hub_url,
            "public_base_url": None,
        }
        atomic_write_json(unified_path, unified)
        changed.append("active_alpha_unified")

    adaptive_path = root / "control/adaptive_runtime.json"
    adaptive = _load_json(adaptive_path)
    if adaptive:
        if adaptive.get("prefer_internet_when_available") is not False:
            adaptive["prefer_internet_when_available"] = False
            changed.append("adaptive_runtime:prefer_internet")
        adaptive.setdefault("local_only_note_de", str(cfg.get("price_data_local_de") or ""))
        atomic_write_json(adaptive_path, adaptive)

    runtime_path = root / "control/linux_runtime_unified.json"
    runtime = _load_json(runtime_path)
    if runtime:
        policies = dict(runtime.get("policies") or {})
        if policies.get("cursor_interface") == "control/cursor_interface_foundation.json":
            policies["cursor_interface"] = "control/alpha_model_interface.json"
            runtime["policies"] = policies
            changed.append("linux_runtime_unified:policies")
        atomic_write_json(runtime_path, runtime)

    doc = {
        "schema_version": 1,
        "applied_at_utc": _utc_now(),
        "ok": True,
        "local_only": True,
        "hub_bind": hub_bind,
        "hub_url": hub_url,
        "changed": changed,
        "headline_de": "Lokal-only aktiv — Hub loopback, Tunnel optional, fictive Kurse erlaubt bis Go-Live",
        "restart_hint_de": "Hub neu starten wenn bind noch 0.0.0.0: bash run_marktanalyse_linux.sh --dev",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def verify_local_runtime(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_local_runtime(root)
    checks: List[Dict[str, Any]] = []

    def add(cid: str, label: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "label_de": label, "ok": ok, "detail_de": detail})

    if not is_local_only(root):
        add("local_only", "Lokal-only aktiv", False, "local_only=false")
    else:
        add("local_only", "Lokal-only aktiv", True, "AUTHORITATIVE")

    from analytics.preview_federation import federation_config, hub_bind_host

    fed = federation_config(root)
    bind = hub_bind_host(root)
    add(
        "hub_bind",
        "Hub nur loopback",
        bind in ("127.0.0.1", "localhost") and not fed.get("lan_bind", True),
        bind,
    )
    add(
        "no_remote_workers",
        "Keine Remote-Worker Pflicht",
        fed.get("remote_workers_expected") is False,
        str(fed.get("remote_access_mode") or ""),
    )
    add(
        "hub_url_local",
        "Öffentliche URL lokal",
        str(fed.get("public_base_url") or "").startswith("http://127.0.0.1"),
        str(fed.get("public_base_url") or "")[:80],
    )

    try:
        from analytics.local_llm_bridge import health_report

        llm = health_report(root)
        add("ollama", "Ollama lokal", bool(llm.get("ready")), str(llm.get("resolved_model") or ""))
    except Exception as exc:
        add("ollama", "Ollama lokal", False, str(exc)[:80])

    kernel = _load_json(root / "control/AI_KERNEL.json")
    tunnel = kernel.get("tunnel") or {}
    add(
        "tunnel_optional",
        "Tunnel nicht Pflicht",
        tunnel.get("tunnel_required") is False or tunnel.get("local_only") is True,
        str(tunnel.get("mode") or ""),
    )

    passed = sum(1 for c in checks if c.get("ok"))
    total = len(checks)
    ok = passed == total
    doc = {
        "schema_version": 1,
        "verified_at_utc": _utc_now(),
        "ok": ok,
        "checks_passed": passed,
        "checks_total": total,
        "checks": checks,
        "headline_de": (
            "Alles lokal konfiguriert"
            if ok
            else f"Lokal-only unvollständig — {passed}/{total}"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def dampen_warning_for_local(root: Path, code: str, severity: str) -> str:
    """Senkt Severity für erwartete PRE_GO_LIVE-Lokalzustände."""
    if not is_local_only(root):
        return severity
    cfg = load_local_runtime(root)
    if code not in (cfg.get("dampen_warning_codes") or []):
        return severity
    if severity == "critical":
        return "info"
    return severity
