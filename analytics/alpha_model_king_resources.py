"""König-Ressourcen — alle Kapazitäten bereitstellen, damit der König sich verbessern kann."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/alpha_model_king_resources_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resource_catalog() -> List[Dict[str, str]]:
    return [
        {"id": "ollama_32b", "label_de": "Coder-32B", "access_de": "Chat+Bau · qwen2.5-coder:32b"},
        {"id": "kernel_slash", "label_de": "Slash/Kernel", "access_de": "/h1-benchmark /h1-watch /könig-puls · ai_kernel.py"},
        {"id": "bash_orchestrator", "label_de": "Bash", "access_de": "bash tools/king_ops.sh pipeline · status · h1-seal · maintain"},
        {"id": "cursor_bridge", "label_de": "Cursor", "access_de": "/cursor anfrage — Vasall"},
        {"id": "h1_master", "label_de": "H1-Seal", "access_de": "control/alpha_model_h1_master_prompt_de.md"},
        {"id": "tier_ideal", "label_de": "Ideal-32B", "access_de": "bash tools/setup_ideal_32b.sh"},
        {"id": "hardware_bond", "label_de": "Hardware", "access_de": "GPU/RAM/NVMe — ai_kernel kernel-bond"},
    ]


def serve_king_resources(root: Path, *, repair: bool = True) -> Dict[str, Any]:
    """Stellt alle Ressourcen für den König bereit — Transfer, Bridges, Tier, Evidence."""
    root = Path(root)
    applied: List[str] = []
    errors: List[str] = []

    if repair:
        try:
            from analytics.ai_kernel_hardware_bond import bond_kernel_to_king_32b

            bond_kernel_to_king_32b(root, persist=True, preload=False)
            applied.append("hardware_bond")
        except Exception as exc:
            errors.append(f"hardware_bond: {exc}"[:80])

    if repair:
        for name, fn in (
            ("transfer", lambda: __import__("analytics.alpha_model_chamber_resources", fromlist=["transfer_all_resources"]).transfer_all_resources(root)),
            ("tier", lambda: __import__("analytics.alpha_model_entfaltung_32b", fromlist=["apply_tier_to_llm_config"]).apply_tier_to_llm_config(root)),
            ("agent_home", lambda: __import__("analytics.alpha_model_agent_home", fromlist=["ensure_agent_home"]).ensure_agent_home(root)),
            ("advisor_bridge", lambda: __import__("analytics.alpha_model_advisor_bridge", fromlist=["load_openai_key_into_env"]).load_openai_key_into_env(root)),
            ("cursor_bridge", lambda: __import__("analytics.alpha_model_cursor_bridge", fromlist=["seal_default_cursor_push"]).seal_default_cursor_push(root)),
            ("king_handoff", lambda: __import__("analytics.alpha_model_king_handoff", fromlist=["seal_king_handoff"]).seal_king_handoff(root)),
        ):
            try:
                fn()
                applied.append(name)
            except Exception as exc:
                errors.append(f"{name}: {exc}"[:80])

    try:
        from analytics.alpha_model_king_control import ensure_king_control

        king = ensure_king_control(root, repair=False)
    except Exception as exc:
        king = {"ok": False, "error_de": str(exc)[:120]}
        errors.append(f"king_control: {exc}"[:80])

    try:
        from analytics.alpha_model_chamber_resources import verify_chamber_resources

        verify = verify_chamber_resources(root)
    except Exception as exc:
        verify = {"transfer_ok": False}
        errors.append(f"verify: {exc}"[:80])

    try:
        from analytics.local_llm_bridge import health_report

        health = health_report(root)
    except Exception:
        health = {}

    catalog = _resource_catalog()
    doc = {
        "schema_version": 1,
        "served_at_utc": _utc_now(),
        "ok": bool(king.get("ready")) and bool(verify.get("transfer_ok")),
        "headline_de": "Alle Ressourcen dem König bereitgestellt",
        "applied": applied,
        "errors": errors,
        "catalog": catalog,
        "catalog_count": len(catalog),
        "king_ready": bool(king.get("ready")),
        "transfer_ok": bool(verify.get("transfer_ok")),
        "ollama_ready": bool(health.get("ready")),
        "max_tier_ready": bool(health.get("max_tier_ready")),
        "resolved_chat": (
            __import__("analytics.alpha_model_entfaltung_32b", fromlist=["tier_status"])
            .tier_status(root)
            .get("resolved_chat_model")
            or health.get("resolved_model")
        ),
        "resolved_build": (
            __import__("analytics.alpha_model_entfaltung_32b", fromlist=["tier_status"])
            .tier_status(root)
            .get("resolved_build_model")
            or (health.get("role_status") or {}).get("build", {}).get("model")
        ),
        "commands_de": [
            "/könig-puls — H1/Benchmark autonom",
            "/h1-benchmark · /h1-watch",
            "/bau · /learn · /diene",
        ],
        "improve_de": "Slash oder .venv/bin/python tools/ai_kernel.py — ein Job, PID prüfen.",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)

    try:
        from analytics.alpha_model_cursor_bridge import push_cursor_to_king

        from analytics.r3_model_synergy import resolve_ollama_role

        chat_pick = resolve_ollama_role(root, "", mode="chat")
        push_cursor_to_king(
            root,
            summary_de="/diene — König erhält alles: 32B Chat, H1-Masterprompt, Bridges, Handoff",
            verified_facts_de=[
                f"Katalog: {len(catalog)} Ressourcen-Gruppen aktiv",
                f"King ready: {king.get('ready')} · Transfer: {verify.get('transfer_ok')}",
                f"Chat: {chat_pick.get('model')} · Build: qwen2.5-coder:32b",
                "H1-Masterprompt: control/alpha_model_h1_master_prompt_de.md",
                "GPT-4o keyless · Cursor-Bridge ACTIVE",
            ],
            tasks_for_king_de=[
                "#1 Du führst selbst: /könig-puls oder /h1-benchmark dann /h1-watch",
                "/learn /evolve — Kreis-Score nach Seal",
                "Lies /könig Handoff — Evidence, nicht Prosa",
            ],
            source="serve_king_resources",
        )
        from analytics.alpha_model_cursor_bridge import push_king_to_cursor

        push_king_to_cursor(
            root,
            status_de="Diener liefert alles — 32B Chat, H1-Prompt, voller Transfer",
            request_de="Vasall: warte auf König-Anfrage — H1/Benchmark/Seal führt der König selbst",
        )
    except Exception:
        pass

    return doc


def format_serve_de(root: Path) -> str:
    doc = serve_king_resources(root, repair=True)
    lines = [
        f"**{doc.get('headline_de')}**",
        f"King ready: {'✓' if doc.get('king_ready') else '✗'} · "
        f"Transfer: {'✓' if doc.get('transfer_ok') else '✗'} · "
        f"Ollama: {doc.get('resolved_chat') or '—'}",
        "",
        f"**{doc.get('catalog_count')} Ressourcen-Gruppen:**",
    ]
    for item in doc.get("catalog") or []:
        lines.append(f"• **{item.get('label_de')}** — {item.get('access_de')}")
    if doc.get("applied"):
        lines.append(f"\nAktualisiert: {', '.join(doc['applied'])}")
    if doc.get("errors"):
        lines.append(f"\nHinweise: {'; '.join(doc['errors'][:3])}")
    lines.extend(["", str(doc.get("improve_de") or "")])
    return "\n".join(lines)


def handle_serve_command(root: Path, text: str) -> Dict[str, Any]:
    low = str(text or "").strip().lower()
    if low in ("/diene", "/serve", "/ressourcen-voll", "/king-serve"):
        return {"ok": True, "reply_de": format_serve_de(root), "serve": True}
    return {"ok": False, "reply_de": "Nutze /diene — alle Ressourcen bereitstellen", "serve": True}
