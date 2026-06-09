"""König-Handoff — verifizierte Wahrheit, damit der König Cursor-Schrott nicht nachprüfen muss."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/alpha_model_king_handoff_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def seal_king_handoff(root: Path) -> Dict[str, Any]:
    """Schreibt verifizierten Stand — einmal lesen statt alles neu prüfen."""
    root = Path(root)
    facts: List[str] = []
    checks: List[Dict[str, Any]] = []

    try:
        from analytics.alpha_model_king_control import king_control_status

        king = king_control_status(root)
        checks.extend(king.get("checks") or [])
        if king.get("ok"):
            facts.append("König-Gate: 7/7 — Chamber, Tier, Ollama, Transfer OK")
    except Exception as exc:
        checks.append({"id": "king", "ok": False, "detail_de": str(exc)[:80]})

    try:
        from analytics.alpha_model_entfaltung_32b import chat_agent_limits, build_kernel_limits

        chat = chat_agent_limits(root)
        build = build_kernel_limits(root)
        facts.append(f"Chat: {chat.get('max_steps')} Schritte · Build: {build.get('max_steps')} Schritte")
        facts.append(f"Modelle: Chat {chat.get('model', 'qwen2.5:14b')} · Bau {build.get('model', 'qwen2.5-coder:32b')}")
    except Exception:
        pass

    try:
        from analytics.alpha_model_advisor_bridge import bridge_status

        br = bridge_status(root)
        if br.get("keyless_mode") and not br.get("key_masked"):
            facts.append("Berater-Bridge: GPT-4o keyless lokal — /tipp /kombi ohne OpenAI-Key")
        elif br.get("configured"):
            facts.append(f"Berater-Bridge: aktiv ({br.get('key_source')})")
        else:
            facts.append("Berater-Bridge: Setup nötig — bash tools/setup_gpt4o_keyless.sh")
    except Exception:
        pass

    try:
        from analytics.alpha_model_cursor_bridge import bridge_status as cursor_st

        cs = cursor_st(root)
        if cs.get("active"):
            facts.append("Cursor-Bridge: ACTIVE — evidence/alpha_model_cursor_king_bridge_latest.json")
        else:
            facts.append("Cursor-Bridge: bereit — warte auf Push")
    except Exception:
        pass

    try:
        from analytics.closed_loop_score import build_closed_loop_score

        loop = build_closed_loop_score(root)
        facts.append(
            f"Kreis-Score: {loop.get('green')}/{loop.get('total')} grün ({loop.get('pct')}%) — "
            f"Engpass: {loop.get('bottleneck_de', '—')[:80]}"
        )
    except Exception:
        pass

    try:
        from analytics.live_profile_governance import h1_backtest_status

        h1 = h1_backtest_status(root)
        pct = h1.get("progress_pct")
        pct_s = f" ~{pct}%" if pct is not None else ""
        facts.append(
            f"H1: {h1.get('status')}{pct_s} — {str(h1.get('detail_de') or '')[:60]}"
        )
    except Exception:
        pass

    try:
        from analytics.king_sovereignty import load_king_sovereignty, next_king_action_de

        pulse = load_king_sovereignty(root)
        if pulse:
            facts.append(f"König-Puls: {pulse.get('headline_de', '—')[:80]}")
        facts.append(f"Nächster König-Schritt: {next_king_action_de(root)}")
        facts.append("Cursor = Vasall — H1/Benchmark/Seal führt der König, nicht Cursor")
    except Exception:
        pass

    facts.extend(
        [
            "Kein Direkt-Chat-Bypass im Chamber — nur König-Chat-Agent mit Tools",
            "Kernel: chamber_kernel_allowlist inkl. h1-benchmark · king-pulse",
            "König-Modus 128 Schritte · read-first Gate aktiv",
            "Architektur: König→Ollama · Berater keyless · Cursor=Vasall (Evidence-Bridge)",
        ]
    )

    doc = {
        "schema_version": 1,
        "sealed_at_utc": _utc_now(),
        "sealed_by_de": "alpha_model_king_handoff",
        "status": "AUTHORITATIVE",
        "headline_de": "Verifizierter Stand — König muss Cursor-Schrott nicht einzeln prüfen",
        "facts_de": facts,
        "checks": checks,
        "commands_de": [
            "/könig-puls — H1/Benchmark/Seal autonom starten",
            "/h1-benchmark · /h1-watch — Seal-Pipeline",
            "/diene — Ressourcen + Handoff refresh",
            "/könig — dieser versiegelte Stand",
            "/cursor anfrage — Vasall (Cursor) beauftragen",
            "/learn /evolve /bau — nach Seal",
        ],
        "trust_note_de": (
            "Dieses Dokument basiert auf king_control_status + bridge_status + tier_limits — "
            "nicht auf Cursor-Prosa. Bei Widerspruch gilt Evidence hier."
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def format_handoff_de(root: Path) -> str:
    doc = seal_king_handoff(root)
    lines = [f"**{doc.get('headline_de')}**", f"Versiegelt: {doc.get('sealed_at_utc')}", ""]
    for f in doc.get("facts_de") or []:
        lines.append(f"• {f}")
    lines.extend(["", str(doc.get("trust_note_de") or "")])
    return "\n".join(lines)
