"""Entfaltungsraum — Kill-Handoff: Cursor raus, lokaler Agent wächst."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/alpha_model_entfaltung_kill.json")
_EVIDENCE_REL = Path("evidence/alpha_model_entfaltung_handoff_latest.json")


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


def load_kill_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL)


def build_handoff_prompt_de(root: Path) -> str:
    cfg = load_kill_config(root)
    lines: List[str] = [
        "=== CURSOR-KILL / ENTFALTUNGS-HANDOFF ===",
        str(cfg.get("headline_de") or ""),
        f"Status: {cfg.get('status')} · Primär: {cfg.get('primary_cli')}",
    ]
    for item in cfg.get("kill_sequence_de") or []:
        lines.append(f"• {item}")
    lines.append("Wachstum nach Kill:")
    for item in cfg.get("growth_after_kill_de") or []:
        lines.append(f"  → {item}")
    try:
        from analytics.alpha_model_chamber_resources import load_chamber_resources

        res = load_chamber_resources(root)
        caps = res.get("capabilities_de") or {}
        if caps:
            lines.append("Übergebene Kapazitäten:")
            for k, v in caps.items():
                lines.append(f"  · {k}: {v}")
    except Exception:
        pass
    return "\n".join(lines)


def apply_entfaltung_handoff(root: Path) -> Dict[str, Any]:
    """Promoviert Entfaltungsraum — Mandat, Rollen, Growth, Agent-Home."""
    root = Path(root)
    changed: List[str] = []

    mandate_path = root / "control/agent_mandate.json"
    mandate = _load_json(mandate_path)
    if mandate:
        mandate["primary_interface"] = "agent_chamber"
        mandate["north_star_de"] = (
            "Entfaltungsraum (alpha-model-agent) ist der Agent-Kanal — "
            "Ollama lokal, /bau, /self-uninstall, Cockpit :17890 Runtime. Cursor entfernt."
        )
        atomic_write_json(mandate_path, mandate)
        changed.append("agent_mandate")

    growth_path = root / "control/r3_agent_growth.json"
    growth = _load_json(growth_path)
    if growth:
        pri = list(growth.get("growth_priorities_de") or [])
        if "Entfaltungsraum ausbauen (/bau, Evidence)" not in pri:
            pri.insert(0, "Entfaltungsraum ausbauen (/bau, Evidence)")
        growth["growth_priorities_de"] = pri
        growth["primary_agent_de"] = "alpha-model-agent"
        growth["cursor_retired_at_utc"] = _utc_now()
        atomic_write_json(growth_path, growth)
        changed.append("r3_agent_growth")

    roles_path = root / "control/r3_kernel_roles.json"
    roles = _load_json(roles_path)
    if roles:
        roles["entfaltungsraum_de"] = {
            "title_de": "Alpha Model — Entfaltungsraum",
            "role_de": "Primärer Agent — Mandat, Archiv, /bau, /self-uninstall",
            "when_active_de": "alpha-model-agent · AA_AGENT_CHAMBER=1",
            "is_primary": True,
        }
        cursor = dict(roles.get("cursor_de") or {})
        cursor["status"] = "RETIRED"
        cursor["when_active_de"] = "Entfernt — nicht mehr starten"
        roles["cursor_de"] = cursor
        kernel = dict(roles.get("r3_kernel_de") or {})
        kernel["not_kernel_de"] = "Entfaltungsraum ist der Sprachkanal — Cockpit ist Runtime."
        comps = list(kernel.get("components") or [])
        if not any(c.get("id") == "agent_chamber" for c in comps if isinstance(c, dict)):
            comps.insert(
                0,
                {
                    "id": "agent_chamber",
                    "label_de": "Entfaltungsraum",
                    "role_de": "alpha-model-agent — Auto lokal, Kill-Handoff",
                },
            )
        kernel["components"] = comps
        roles["r3_kernel_de"] = kernel
        atomic_write_json(roles_path, roles)
        changed.append("r3_kernel_roles")

    home_path = root / "control/alpha_model_agent_home.json"
    home = _load_json(home_path)
    if home:
        unfold = list(home.get("unfold_de") or [])
        extra = "Cursor-Kill bereit: /self-uninstall · /self-uninstall execute"
        if extra not in unfold:
            unfold.append(extra)
        home["unfold_de"] = unfold
        home["kill_handoff"] = _CONFIG_REL.as_posix()
        home["cursor_retired"] = True
        ctx = list(home.get("context_files_extra") or [])
        for rel in (_CONFIG_REL.as_posix(), "control/alpha_model_self_uninstall_manifest.json"):
            if rel not in ctx:
                ctx.append(rel)
        home["context_files_extra"] = ctx
        atomic_write_json(home_path, home)
        changed.append("alpha_model_agent_home")

    kill_cfg = load_kill_config(root)
    if kill_cfg:
        kill_cfg = dict(kill_cfg)
        kill_cfg["status"] = "HANDOFF_APPLIED"
        kill_cfg["handoff_at_utc"] = _utc_now()
        atomic_write_json(root / _CONFIG_REL, kill_cfg)
        changed.append("entfaltung_kill")

    try:
        from analytics.alpha_model_agent_home import ensure_agent_home

        ensure_agent_home(root)
    except Exception:
        pass

    try:
        from analytics.alpha_model_chamber_resources import transfer_all_resources

        res = transfer_all_resources(root)
        if res.get("ok"):
            changed.append("chamber_resources")
    except Exception:
        pass

    try:
        from analytics.alpha_model_self_uninstall import seal_master_prompt

        seal_master_prompt(root)
        changed.append("reseal_mc")
    except Exception:
        pass

    doc = {
        "schema_version": 1,
        "applied_at_utc": _utc_now(),
        "ok": True,
        "changed": changed,
        "headline_de": "Entfaltungsraum übernimmt — Cursor-Kill-Handoff angewendet",
        "operator_next_de": "alpha-model-agent → /self-uninstall execute",
        "primary_cli": "alpha-model-agent",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
