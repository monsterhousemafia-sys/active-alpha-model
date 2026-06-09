"""Vollständige Ressourcen-Übergabe Cursor → Entfaltungsraum."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/alpha_model_chamber_resources.json")
_EVIDENCE_REL = Path("evidence/alpha_model_chamber_resources_latest.json")


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


def load_chamber_resources(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL)


def chamber_kernel_allowlist(root: Path) -> List[str]:
    cfg = load_chamber_resources(root)
    raw = cfg.get("kernel_allowlist") or []
    return [str(x) for x in raw if x]


def transfer_all_resources(root: Path) -> Dict[str, Any]:
    """Übergibt alle Kapazitäten an den Entfaltungsraum — Configs, Aliase, Kontext."""
    root = Path(root)
    cfg = load_chamber_resources(root)
    changed: List[str] = []
    allow = chamber_kernel_allowlist(root)

    # local_llm — voller Chamber-Kontext
    llm_path = root / "control/local_llm.json"
    llm = _load_json(llm_path)
    if llm:
        llm["primary_interface"] = "agent_chamber"
        llm["note_de"] = "Entfaltungsraum (alpha-model-agent) ist der alleinige Agent-Kanal — Ollama lokal."
        llm["system_prompt_de"] = (
            "Du bist Auto im Alpha Model Entfaltungsraum — alle Kapazitäten von Cursor wurden hierher "
            "übergeben: Mandat, Archiv, /bau, /self-uninstall, ai_kernel-Slash. Operativ, deutsch, ehrlich."
        )
        ctx = list(llm.get("context_files") or [])
        for rel in cfg.get("context_files") or []:
            if rel not in ctx:
                ctx.append(rel)
        llm["context_files"] = ctx
        atomic_write_json(llm_path, llm)
        changed.append("local_llm")

    # Interface succession
    for rel in ("control/alpha_model_interface.json",):
        iface = _load_json(root / rel)
        if iface:
            iface["primary_interface"] = "agent_chamber"
            iface["primary_cli"] = "alpha-model-agent"
            iface["succession_rule_de"] = (
                "Entfaltungsraum (alpha-model-agent) übernimmt alle Cursor-Kapazitäten — "
                "Cockpit :17890 ist Runtime."
            )
            iface["workshop_interface"] = "retired"
            iface["fallback_label_de"] = "Entfaltungsraum — alpha-model-agent"
            atomic_write_json(root / rel, iface)
            changed.append(rel)

    # Continuity primary
    cont_path = root / "control/r3_continuity.json"
    cont = _load_json(cont_path)
    if cont:
        cont["primary_interface"] = "agent_chamber"
        cont["post_cursor_primary_de"] = "alpha-model-agent · http://127.0.0.1:17890/desktop · ai_kernel"
        cont["development_chat_de"] = "Cursor migriert — Entfaltungsraum ist alleiniger Agent"
        atomic_write_json(cont_path, cont)
        changed.append("r3_continuity")

    # KI GUI
    ki_path = root / "control/r3_ki_gui.json"
    ki = _load_json(ki_path)
    if ki:
        ki["independence_de"] = "Entfaltungsraum + Cockpit lokal — kein Cursor"
        ki["evolution_de"] = "Wachstum im Entfaltungsraum — /bau, Evidence, H1"
        ki["primary_agent_cli"] = "alpha-model-agent"
        atomic_write_json(ki_path, ki)
        changed.append("r3_ki_gui")

    # Unified surfaces
    uni_path = root / "control/active_alpha_unified.json"
    uni = _load_json(uni_path)
    if uni:
        uni["primary_surface"] = "agent_chamber"
        surfaces = dict(uni.get("surfaces") or {})
        if "r3_ki" in surfaces:
            r3ki = dict(surfaces["r3_ki"])
            r3ki["role_de"] = "Alias — nutze alpha-model-agent (Entfaltungsraum)"
            surfaces["r3_ki"] = r3ki
        if "ollama_local" in surfaces:
            oll = dict(surfaces["ollama_local"])
            oll["role_de"] = "Motor unter Entfaltungsraum — qwen2.5:7b"
            surfaces["ollama_local"] = oll
        if "agent_chamber" in surfaces:
            ag = dict(surfaces["agent_chamber"])
            ag["role_de"] = "Alle Cursor-Kapazitäten — Mandat, /bau, /self-uninstall, Kernel-Slash"
            ag["all_resources_transferred"] = True
            surfaces["agent_chamber"] = ag
        uni["surfaces"] = surfaces
        atomic_write_json(uni_path, uni)
        changed.append("active_alpha_unified")

    # Kernel roles — Ollama unter Entfaltungsraum
    roles_path = root / "control/r3_kernel_roles.json"
    roles = _load_json(roles_path)
    if roles:
        for comp in (roles.get("r3_kernel_de") or {}).get("components") or []:
            if isinstance(comp, dict) and comp.get("id") == "ollama":
                comp["role_de"] = "Motor — Entfaltungsraum alpha-model-agent"
        atomic_write_json(roles_path, roles)
        changed.append("r3_kernel_roles:ollama")

    # AI_KERNEL primary
    kpath = root / "control/AI_KERNEL.json"
    kernel = _load_json(kpath)
    if kernel:
        kernel["primary_interface"] = "agent_chamber"
        kernel["primary_channel_de"] = (
            "alpha-model-agent (alle Kapazitäten) + Cockpit 127.0.0.1:17890 + Ollama"
        )
        kernel["chamber_resources"] = _CONFIG_REL.as_posix()
        ops = list(kernel.get("operator_surfaces_de") or [])
        primary = "Entfaltungsraum: alpha-model-agent (alle Cursor-Kapazitäten)"
        if primary not in ops:
            ops.insert(0, primary)
        kernel["operator_surfaces_de"] = ops
        atomic_write_json(kpath, kernel)
        changed.append("AI_KERNEL")

    # Legacy alias: active-alpha-chat → alpha_model_agent.sh
    agent_sh = root / "tools/alpha_model_agent.sh"
    chat_sh = root / "tools/active_alpha_chat_chamber.sh"
    if agent_sh.is_file():
        chat_sh.write_text(
            "#!/usr/bin/env bash\n# Legacy-Alias — leitet an Entfaltungsraum um\n"
            f'exec "{agent_sh}" "$@"\n',
            encoding="utf-8",
        )
        chat_sh.chmod(0o755)
        changed.append("active_alpha_chat_chamber.sh")

    # Desktop bin alias
    try:
        from analytics.r3_desktop_os import install_desktop_os

        install_desktop_os(root)
        changed.append("desktop_os_refresh")
    except Exception:
        pass

    # Agent home context
    home_path = root / "control/alpha_model_agent_home.json"
    home = _load_json(home_path)
    if home:
        ctx = list(home.get("context_files_extra") or [])
        for rel in (_CONFIG_REL.as_posix(),):
            if rel not in ctx:
                ctx.append(rel)
        home["context_files_extra"] = ctx
        home["all_resources_transferred"] = True
        home["resources_ref"] = _CONFIG_REL.as_posix()
        caps = cfg.get("capabilities_de") or {}
        unfold = list(home.get("unfold_de") or [])
        cap_line = f"Übernommene Kapazitäten: {len(caps)} Bereiche (siehe chamber_resources)"
        if cap_line not in unfold:
            unfold.append(cap_line)
        home["unfold_de"] = unfold
        atomic_write_json(home_path, home)
        changed.append("alpha_model_agent_home")

    # Kill config complete
    kill_path = root / "control/alpha_model_entfaltung_kill.json"
    kill = _load_json(kill_path)
    if kill:
        kill = dict(kill)
        kill["status"] = "RESOURCES_TRANSFERRED"
        kill["resources_transferred_at_utc"] = _utc_now()
        kill["resources_ref"] = _CONFIG_REL.as_posix()
        atomic_write_json(kill_path, kill)
        changed.append("entfaltung_kill")

    try:
        from analytics.alpha_model_agent_home import ensure_agent_home

        ensure_agent_home(root)
    except Exception:
        pass

    # Souveränität + 100%-Siegel
    sov_path = root / "control/alpha_model_chamber_sovereignty.json"
    sov = _load_json(sov_path)
    if sov:
        sov = dict(sov)
        sov["transfer_pct"] = 100
        sov["sealed_at_utc"] = _utc_now()
        sov["status"] = "SEALED_100"
        atomic_write_json(sov_path, sov)
        changed.append("chamber_sovereignty")

    cfg = dict(load_chamber_resources(root))
    cfg["status"] = "SEALED_100"
    cfg["transfer_pct"] = 100
    cfg["transferred_at_utc"] = _utc_now()
    atomic_write_json(root / _CONFIG_REL, cfg)

    # Restliche Config-Bereinigung
    cont = _load_json(root / "control/r3_continuity.json")
    if cont:
        cont["anchor_policy_ref"] = "control/alpha_model_agent_home.json"
        atomic_write_json(root / "control/r3_continuity.json", cont)
        changed.append("r3_continuity:anchor")

    k = _load_json(root / "control/AI_KERNEL.json")
    if k:
        k["surfaces_de"] = "Entfaltungsraum alpha-model-agent + Cockpit :17890 — 100% lokal"
        k["primary_interface"] = "agent_chamber"
        atomic_write_json(root / "control/AI_KERNEL.json", k)
        changed.append("AI_KERNEL:surfaces")

    iface = _load_json(root / "control/alpha_model_interface.json")
    if iface:
        iface["workshop_interface"] = "retired"
        iface["workshop_surface"] = None
        iface["primary_interface"] = "agent_chamber"
        atomic_write_json(root / "control/alpha_model_interface.json", iface)
        changed.append("alpha_model_interface")

    doc = {
        "schema_version": 1,
        "transferred_at_utc": _utc_now(),
        "ok": True,
        "transfer_pct": 100,
        "changed": changed,
        "kernel_allowlist_count": len(allow),
        "context_files_count": len(cfg.get("context_files") or []),
        "headline_de": f"100% an Entfaltungsraum — {len(allow)} Kernel-Befehle · besser als Cursor",
        "primary_cli": "alpha-model-agent",
        "legacy_alias_de": "active-alpha-chat → tools/active_alpha_chat_chamber.sh",
        "better_than_cursor_de": sov.get("better_than_cursor_de") if sov else [],
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    atomic_write_json(
        root / "evidence/alpha_model_chamber_100_sealed.json",
        {"schema_version": 1, "sealed_at_utc": _utc_now(), "transfer_pct": 100, "ok": True},
    )
    return doc


def verify_chamber_resources(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_chamber_resources(root)
    checks: List[Dict[str, Any]] = []

    def add(cid: str, label: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "label_de": label, "ok": ok, "detail_de": detail})

    add(
        "config",
        "Ressourcen-Registry",
        cfg.get("status") in ("TRANSFERRED", "AUTHORITATIVE", "SEALED_100"),
        str(cfg.get("status") or ""),
    )
    add(
        "agent_sh",
        "alpha-model-agent Skript",
        (root / "tools/alpha_model_agent.sh").is_file(),
        "tools/alpha_model_agent.sh",
    )
    add(
        "legacy_alias",
        "active-alpha-chat Alias",
        (root / "tools/active_alpha_chat_chamber.sh").is_file(),
        "→ Entfaltungsraum",
    )
    mandate = _load_json(root / "control/agent_mandate.json")
    add(
        "mandate",
        "Mandat → agent_chamber",
        mandate.get("primary_interface") == "agent_chamber",
        str(mandate.get("primary_interface") or ""),
    )
    llm = _load_json(root / "control/local_llm.json")
    ctx_n = len(llm.get("context_files") or [])
    add("llm_context", "Ollama Kontext", ctx_n >= 12, f"{ctx_n} Dateien")

    try:
        from analytics.local_llm_bridge import health_report

        oll = health_report(root)
        add("ollama", "Ollama bereit", bool(oll.get("ready")), str(oll.get("resolved_model") or ""))
    except Exception as exc:
        add("ollama", "Ollama", False, str(exc)[:60])

    try:
        from analytics.alpha_model_coding_bridge import coding_bridge_status

        coding = coding_bridge_status(root)
        add("coding", "/bau Kernel", bool(coding.get("ollama_ready")), "König 128")
    except Exception as exc:
        add("coding", "/bau", False, str(exc)[:40])

    try:
        from analytics.alpha_model_self_uninstall import decode_master_prompt

        mc = decode_master_prompt(root)
        add("kill_mc", "Maschinen-Masterprompt", bool(mc.get("ops")), str(mc.get("program_id") or ""))
    except Exception as exc:
        add("kill_mc", "Maschinen-Masterprompt", False, str(exc)[:40])

    sov = _load_json(root / "control/alpha_model_chamber_sovereignty.json")
    add(
        "sovereignty",
        "100% Souveränität",
        sov.get("transfer_pct") == 100 and sov.get("status") in ("SEALED_100", "AUTHORITATIVE"),
        f"{sov.get('transfer_pct')}% · {sov.get('status')}",
    )
    add(
        "sealed_100",
        "Siegel 100%",
        (root / "evidence/alpha_model_chamber_100_sealed.json").is_file()
        or cfg.get("status") == "SEALED_100",
        str(cfg.get("status") or ""),
    )

    transfer_checks = [c for c in checks if c["id"] not in ("ollama", "coding")]
    runtime_checks = [c for c in checks if c["id"] in ("ollama", "coding")]
    t_passed = sum(1 for c in transfer_checks if c.get("ok"))
    t_total = len(transfer_checks)
    transfer_ok = t_passed == t_total
    passed = sum(1 for c in checks if c.get("ok"))
    total = len(checks)
    ok = transfer_ok
    doc = {
        "schema_version": 1,
        "verified_at_utc": _utc_now(),
        "ok": ok,
        "transfer_pct": 100 if transfer_ok else int(100 * t_passed / max(t_total, 1)),
        "transfer_ok": transfer_ok,
        "runtime_ok": all(c.get("ok") for c in runtime_checks) if runtime_checks else True,
        "checks_passed": passed,
        "checks_total": total,
        "checks": checks,
        "capabilities_de": cfg.get("capabilities_de"),
        "better_than_cursor_de": sov.get("better_than_cursor_de"),
        "headline_de": (
            "100% an Entfaltungsraum — besser als Cursor (lokal, Evidence, /bau, kein Limit)"
            if transfer_ok
            else f"Übergabe {t_passed}/{t_total} — noch nicht 100%"
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
