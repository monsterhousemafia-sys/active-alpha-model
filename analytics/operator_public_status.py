"""Public operator status — readable by any Ubuntu user (home + project evidence)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_CAP_REL = Path("control/active_alpha_public_capabilities.json")
_EVIDENCE_REL = Path("evidence/operator_public_latest.json")


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


def load_public_capabilities(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CAP_REL)


def public_status_paths(root: Path) -> Dict[str, str]:
    from analytics.r3_paths import public_status_paths as _r3_paths

    return _r3_paths(root)


def build_public_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.operator_visibility import build_visibility_snapshot, format_visibility_text

    caps = load_public_capabilities(root)
    vis = build_visibility_snapshot(root)
    try:
        from analytics.active_alpha_identity import load_unified_config

        identity = load_unified_config(root)
    except Exception:
        identity = {}
    cockpit_lines: list[str] = []
    cockpit_next = ""
    circle: Dict[str, Any] = {}
    cp = root / "evidence/trading_day_latest.txt"
    if cp.is_file():
        try:
            cockpit_lines = [ln for ln in cp.read_text(encoding="utf-8").splitlines() if ln.strip()]
            from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

            cj = load_trading_day_cockpit_doc(root)
            cockpit_next = str(cj.get("next_step_de") or "")
            circle = dict(cj.get("circle_score") or {})
        except OSError:
            pass
    if not circle:
        try:
            from analytics.closed_loop_score import load_closed_loop_score

            circle = load_closed_loop_score(root)
        except Exception:
            circle = {}
    system_status: Dict[str, Any] = {}
    runtime_profile: Dict[str, Any] = {}
    try:
        from analytics.preview_system_status import build_preview_system_status

        system_status = build_preview_system_status(root, refresh_h1=False)
    except Exception:
        pass
    try:
        from analytics.linux_runtime_unified import runtime_profile as build_runtime_profile

        runtime_profile = build_runtime_profile(root)
    except Exception:
        pass
    return {
        "schema_version": 2,
        "published_at_utc": _utc_now(),
        "agent_name": caps.get("agent_name") or identity.get("agent_name") or "Auto",
        "product_name": caps.get("product_name") or identity.get("product_name") or "Alpha Model",
        "tagline_de": caps.get("tagline_de") or identity.get("tagline_de"),
        "how_to_see_de": list(caps.get("how_to_see_de") or []),
        "can_do_de": list(caps.get("can_do_de") or []),
        "cannot_do_de": list(caps.get("cannot_do_de") or []),
        "evolution_platform_de": caps.get("evolution_platform_de"),
        "cli_commands": list(caps.get("cli_commands") or []),
        "visibility": vis,
        "visibility_text_de": format_visibility_text(vis),
        "circle_score": circle,
        "trading_day_cockpit_de": cockpit_lines,
        "trading_day_next_step_de": cockpit_next,
        "system_status": system_status,
        "runtime_profile": runtime_profile,
    }


def publish_public_status(root: Path, *, notify: bool = False) -> Path:
    root = Path(root)
    doc = build_public_status(root)
    paths = public_status_paths(root)
    user_dir = Path(paths["user_json"]).parent
    user_dir.mkdir(parents=True, exist_ok=True)
    text = _format_public_text(doc)
    for target in (paths["user_json"], paths["project_json"]):
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(paths["user_txt"]).write_text(text + "\n", encoding="utf-8")
    if notify:
        try:
            from analytics.operator_visibility import notify_desktop_if_available

            notify_desktop_if_available(
                f"{doc.get('product_name')} · Auto",
                str(doc.get("visibility", {}).get("headline_de") or "Operator aktiv")[:160],
            )
        except Exception:
            pass
    return Path(paths["user_json"])


def _format_public_text(doc: Dict[str, Any]) -> str:
    product = doc.get("product_name") or "Alpha Model"
    lines = [
        f"=== {product} — Research Operating System ===",
        str(doc.get("tagline_de") or "Ein Kern. Ein Cockpit."),
        "",
    ]
    circle = doc.get("circle_score") or {}
    if circle.get("headline_de"):
        lines.append("— Kreis-Score (Superprogramm) —")
        lines.append(str(circle.get("headline_de")))
        if circle.get("summary_de"):
            lines.append(str(circle.get("summary_de")))
        bn = circle.get("bottleneck_de")
        if bn and int(circle.get("green") or 0) < int(circle.get("total") or 6):
            lines.append(f"→ Engpass: {bn}")
        lines.append("")
    lines.append("— Was Auto kann —")
    for item in doc.get("can_do_de") or []:
        lines.append(f"  ✓ {item}")
    lines.append("")
    lines.append("— Was Auto nicht darf —")
    for item in doc.get("cannot_do_de") or []:
        lines.append(f"  ✗ {item}")
    lines.append("")
    lines.append("— So siehst du es —")
    for item in doc.get("how_to_see_de") or []:
        lines.append(f"  · {item}")
    lines.append("")
    cockpit = doc.get("trading_day_cockpit_de") or []
    if cockpit:
        lines.append("— Tages-Cockpit —")
        lines.extend(cockpit)
        nxt = doc.get("trading_day_next_step_de")
        if nxt:
            lines.append(f"→ {nxt}")
        lines.append("")
    sys_st = doc.get("system_status") or {}
    if sys_st.get("headline_de"):
        lines.append("— Systemstatus (R3 Cockpit) —")
        lines.append(str(sys_st.get("headline_de")))
        lines.append(f"Gesamt: {int(sys_st.get('composite_pct') or 0)}%")
        for tile in (sys_st.get("tiles") or [])[:4]:
            lines.append(f"  · {tile.get('label_de')}: {tile.get('value_de')}")
        lines.append("")
    rp = doc.get("runtime_profile") or {}
    if rp.get("headline_de"):
        lines.append(f"Linux-Stack: {rp.get('headline_de')}")
        lines.append("")
    lines.append(str(doc.get("visibility_text_de") or ""))
    return "\n".join(lines)
