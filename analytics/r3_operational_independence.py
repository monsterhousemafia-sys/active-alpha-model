"""R3 operativ abnabeln — Laufzeit ohne Cursor (König + Bash + Autostart)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_operational_independence.json")
_EVIDENCE_REL = Path("evidence/r3_operational_independence_latest.json")


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


def load_operational_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _gate(
    gate_id: str,
    *,
    label_de: str,
    ok: bool,
    detail_de: str,
) -> Dict[str, Any]:
    return {
        "id": gate_id,
        "label_de": label_de,
        "ok": bool(ok),
        "detail_de": str(detail_de or "—")[:160],
    }


def scan_r3_operational_independence(root: Path) -> Dict[str, Any]:
    """Fail-closed: Ist R3 ohne Cursor betriebsfähig?"""
    root = Path(root).resolve()
    home = Path.home()
    gates: List[Dict[str, Any]] = []

    hooks = _load_json(root / ".cursor/hooks.json")
    gates.append(
        _gate(
            "cursor_hooks_empty",
            label_de="Cursor-Hooks inaktiv",
            ok=hooks == {} or not hooks,
            detail_de=".cursor/hooks.json leer" if (hooks == {} or not hooks) else "Hooks aktiv — verbieten",
        )
    )

    agent_home = _load_json(root / "control/alpha_model_agent_home.json")
    gates.append(
        _gate(
            "cursor_retired",
            label_de="Cursor als Agent zurückgebaut",
            ok=bool(agent_home.get("cursor_retired")),
            detail_de=str(agent_home.get("label_de") or "alpha-model-agent"),
        )
    )

    try:
        from analytics.r3_community_stealth import community_stealth_enabled, session_autostart_path

        autostart = session_autostart_path(root)
        autostart_label = (
            "Login-Autostart (Community-Stealth)"
            if community_stealth_enabled(root)
            else "Login-Autostart R3"
        )
    except Exception:
        autostart = home / ".config/autostart/r3-os-session.desktop"
        autostart_label = "Login-Autostart R3"
    gates.append(
        _gate(
            "session_autostart",
            label_de=autostart_label,
            ok=autostart.is_file(),
            detail_de=str(autostart) if autostart.is_file() else "fehlt",
        )
    )

    desktop = home / ".local/share/applications/R3.desktop"
    gates.append(
        _gate(
            "desktop_entry",
            label_de="Menü R3.desktop",
            ok=desktop.is_file(),
            detail_de=str(desktop) if desktop.is_file() else "fehlt",
        )
    )

    r3_bin = home / ".local/bin/r3"
    gates.append(
        _gate(
            "r3_command",
            label_de="Befehl r3",
            ok=r3_bin.is_symlink() or r3_bin.is_file(),
            detail_de=str(r3_bin) if r3_bin.exists() else "fehlt",
        )
    )

    own_doc = _load_json(home / ".local/share/r3-os/post_login_ownership_latest.json")
    if not own_doc:
        own_doc = _load_json(root / "evidence/r3_home_ownership_latest.json")
    gates.append(
        _gate(
            "home_ownership",
            label_de="~/.local Besitz OK",
            ok=bool(own_doc.get("ok")) if own_doc else True,
            detail_de=str(own_doc.get("headline_de") or "nicht geprüft"),
        )
    )

    stack = _load_json(root / "evidence/stack_integrity_latest.json")
    stack_ok = bool(stack.get("stack_ok"))
    gates.append(
        _gate(
            "stack_ok",
            label_de="Integritäts-Stack",
            ok=stack_ok,
            detail_de=str(stack.get("headline_de") or stack.get("detail_de") or "—")[:120],
        )
    )

    hub_ok = bool(stack.get("hub_ok")) or stack_ok
    systemd_unit = home / ".config/systemd/user/active-alpha-preview-hub.service"
    gates.append(
        _gate(
            "hub_service",
            label_de="Preview-Hub",
            ok=hub_ok or systemd_unit.is_file(),
            detail_de="systemd+stack" if systemd_unit.is_file() else "stack/cache",
        )
    )

    r3_surface = (stack.get("r3") or {}) if isinstance(stack.get("r3"), dict) else {}
    mirror_ok = bool(r3_surface.get("mirror_api_ok")) or bool(r3_surface.get("surface_page_ok"))
    gates.append(
        _gate(
            "r3_surface",
            label_de="R3 Oberfläche /r3",
            ok=mirror_ok or stack_ok,
            detail_de=str(r3_surface.get("surface_path") or "/r3"),
        )
    )

    policy = load_operational_policy(root)
    gates.append(
        _gate(
            "policy_authoritative",
            label_de="Betriebs-Policy",
            ok=str(policy.get("status") or "").upper() == "AUTHORITATIVE",
            detail_de=str(policy.get("headline_de") or "—"),
        )
    )

    build_policy = _load_json(root / "control/king_32b_autonomous_build.json")
    gates.append(
        _gate(
            "autonomous_build_32b",
            label_de="32B baut autonom",
            ok=bool(build_policy.get("autonomous_build_enabled"))
            and str(build_policy.get("status") or "").upper() == "AUTHORITATIVE",
            detail_de=str(build_policy.get("headline_de") or "—"),
        )
    )

    ok_n = sum(1 for g in gates if g.get("ok"))
    total = len(gates)
    pct = int(round(100 * ok_n / total)) if total else 0
    detached = ok_n == total

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "cursor_runtime_required": False,
        "operational_detach": detached,
        "detach_pct": pct,
        "gates_ok": ok_n,
        "gates_total": total,
        "gates": gates,
        "headline_de": (
            "R3 operativ abgenabelt — Cursor nicht nötig"
            if detached
            else f"R3 Abnabelung {pct}% — {total - ok_n} Gate(s) offen"
        ),
        "operator_de": str(policy.get("operator_primary_de") or "king_ops · r3 · agent"),
        "king_de": str(policy.get("king_primary_de") or "König 32B"),
        "message_de": (
            "Laufzeit: Autostart + Hub + König. Cursor nur Schicht-4-Code auf Anfrage."
            if detached
            else "bash tools/king_ops.sh r3-detach --repair"
        ),
    }


def seal_operational_detach_bridge(root: Path, scan: Dict[str, Any]) -> Dict[str, Any]:
    """Bridge: R3-Laufzeit an König, Cursor aus dem Betriebsweg."""
    root = Path(root)
    facts = [
        f"Abnabelung: {scan.get('detach_pct')}% ({scan.get('gates_ok')}/{scan.get('gates_total')})",
        "Cursor runtime_required: false",
        str(scan.get("operator_de") or ""),
    ]
    for g in scan.get("gates") or []:
        if g.get("ok"):
            facts.append(f"✓ {g.get('label_de')}")
    try:
        from analytics.alpha_model_cursor_bridge import push_cursor_to_king, push_king_to_cursor

        push_cursor_to_king(
            root,
            summary_de=str(scan.get("headline_de") or "R3 Betrieb abgenabelt"),
            verified_facts_de=facts[:12],
            tasks_for_king_de=[],
            source="r3_operational_detach",
        )
        return push_king_to_cursor(
            root,
            request_de="",
            status_de="R3 Laufzeit souverän — Vasall nur bei /cursor anfrage (Schicht 4)",
        )
    except Exception as exc:
        return {"ok": False, "error_de": str(exc)[:160]}


def apply_r3_operational_detach(
    root: Path,
    *,
    repair: bool = True,
    seal_bridge: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Einmalig: Install, Hooks, Hub, Stack — dann Evidence."""
    root = Path(root).resolve()
    steps: List[Dict[str, Any]] = []

    if repair:
        try:
            from analytics.r3_home_ownership import run_post_login_hook

            own = run_post_login_hook(root)
            steps.append({"step": "post_login_ownership", "ok": bool(own.get("ok"))})
        except Exception as exc:
            steps.append({"step": "post_login_ownership", "ok": False, "error_de": str(exc)[:120]})

        try:
            from analytics.r3_desktop_os import install_r3_exec_mirror_app

            app = install_r3_exec_mirror_app(root, session_autostart=True)
            steps.append({"step": "desktop_install", "ok": bool(app.get("ok"))})
        except Exception as exc:
            steps.append({"step": "desktop_install", "ok": False, "error_de": str(exc)[:120]})

        try:
            from analytics.r3_community_stealth import install_community_stealth

            stealth = install_community_stealth(root, persist=True)
            steps.append({"step": "community_stealth", "ok": bool(stealth.get("ok"))})
        except Exception as exc:
            steps.append({"step": "community_stealth", "ok": False, "error_de": str(exc)[:120]})

        try:
            from analytics.linux_runtime_unified import ensure_preview_hub_boot

            hub = ensure_preview_hub_boot(root)
            steps.append({"step": "hub_boot", "ok": bool(hub.get("ok", True))})
        except Exception as exc:
            steps.append({"step": "hub_boot", "ok": False, "error_de": str(exc)[:120]})

        try:
            from analytics.stack_integrity import repair_stack

            stack = repair_stack(root, launch_cockpit_window=False, persist=True)
            steps.append({"step": "stack_repair", "ok": bool(stack.get("stack_ok"))})
        except Exception as exc:
            steps.append({"step": "stack_repair", "ok": False, "error_de": str(exc)[:120]})

    scan = scan_r3_operational_independence(root)
    bridge: Dict[str, Any] = {}
    if seal_bridge:
        bridge = seal_operational_detach_bridge(root, scan)

    doc: Dict[str, Any] = {
        **scan,
        "repair_applied": bool(repair),
        "steps": steps,
        "bridge": bridge,
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
