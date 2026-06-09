"""Chat-gestützte Evolution im GUI-Preview — lokales Ollama (Stufe 3)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_EVIDENCE_REL = Path("evidence/chat_evolution_preview_latest.json")

_EVOLUTION_PROMPT_DE = """Du bist Auto, lokaler Active-Alpha-Operator auf Ubuntu.
Aufgabe: Evolution (Sportwagen → sport_plus → …) einen Schritt voranbringen — ohne Live-Orders, ohne Echtgeld-Freigabe.

Analysiere den Kontext und antworte KURZ auf Deutsch mit genau dieser Struktur:
1) IST: Kreis-Score + Stufe + größter Engpass (1 Satz)
2) AUTO: Was der soeben gelaufene evolve-Pass getan hat (1 Satz)
3) NÄCHSTER SCHRITT: Ein konkreter Befehl oder GUI-Aktion für den Nutzer (z. B. ai_kernel learn, Montag Rebalance)
4) CHAT: Welcher Slash-Befehl im active-alpha-chat hilft (/circle /evolve /h1 /trading-day)

Keine erfundenen Metriken. Kein Autotrading vorschlagen."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_evolution_chat_context(root: Path) -> str:
    """Rich context for local LLM — circle, learning, H1, evolution gaps."""
    root = Path(root)
    chunks: List[str] = []

    try:
        from analytics.closed_loop_score import load_closed_loop_score

        circle = load_closed_loop_score(root)
        chunks.append(
            f"Kreis-Score: {circle.get('headline_de')} · Engpass: {circle.get('bottleneck_de')}"
        )
    except Exception:
        pass

    try:
        from analytics.evolution_stage_runner import stage_criteria_progress

        prog = stage_criteria_progress(root)
        chunks.append(
            f"Evolution: {prog.get('current_stage_id')} → {prog.get('next_stage_id')} · "
            f"Gaps: {', '.join(prog.get('gaps_de') or [])}"
        )
    except Exception:
        pass

    for rel in (
        "evidence/public_learning_report_latest.json",
        "control/h1_governance_status.json",
        "evidence/closed_loop_score_latest.json",
        "evidence/evolution_cycle_latest.json",
    ):
        path = root / rel
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            chunks.append(f"{rel}:\n{json.dumps(doc, ensure_ascii=False)[:2000]}")
        except (json.JSONDecodeError, OSError):
            continue

    try:
        from analytics.local_llm_bridge import build_project_context

        chunks.append(build_project_context(root)[:4000])
    except Exception:
        pass

    return "\n\n".join(chunks)[:14000]


def run_chat_evolution_drive(
    root: Path,
    *,
    apply_evolve: bool = True,
    ask_llm: bool = True,
    chat_timeout_s: int = 120,
) -> Dict[str, Any]:
    """
    Preview-Schritt: sicheren evolve-Pass + lokale KI-Empfehlung für nächsten Evolution-Schritt.
    """
    root = Path(root)
    from analytics.local_llm_bridge import chat_completion, health_report, load_llm_config

    health = health_report(root)
    out: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "llm_health": health,
        "evolve": {},
        "chat_reply_de": "",
        "next_step_de": "",
        "ok": False,
    }

    if apply_evolve:
        try:
            from analytics.evolution_stage_runner import run_evolution_cycle

            out["evolve"] = run_evolution_cycle(root, apply_improvements=True)
        except Exception as exc:
            out["evolve"] = {"ok": False, "error": str(exc)[:300]}

    if not health.get("ready"):
        out["reason_de"] = "Ollama offline — nur evolve (active-alpha-chat / llm-setup)"
        out["next_step_de"] = str((out.get("evolve") or {}).get("message_de") or out["reason_de"])
        out["ok"] = bool((out.get("evolve") or {}).get("ok", True))
        _write_evidence(root, out)
        return out

    if not ask_llm:
        out["ok"] = bool(health.get("ready"))
        out["next_step_de"] = str((out.get("evolve") or {}).get("message_de") or "evolve ohne Chat")
        _write_evidence(root, out)
        return out

    ctx = build_evolution_chat_context(root)
    cfg = load_llm_config(root)
    system = str(cfg.get("system_prompt_de") or "") + "\n\n" + _EVOLUTION_PROMPT_DE
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                "GUI-Preview: Evolution vorantreiben. Kontext:\n\n"
                + ctx
                + "\n\nWas ist der nächste sichere Schritt?"
            ),
        },
    ]
    try:
        reply, raw = chat_completion(root, messages, timeout_s=float(chat_timeout_s))
        out["chat_reply_de"] = reply.strip()[:2000]
        out["llm_raw"] = {"model": (raw.get("model") if isinstance(raw, dict) else None)}
        for line in reply.splitlines():
            low = line.lower()
            if "nächster" in low or "nächste" in low or line.strip().startswith("3)"):
                out["next_step_de"] = line.strip()[:300]
                break
        if not out["next_step_de"]:
            out["next_step_de"] = reply.strip().split("\n")[-1][:300]
        out["ok"] = True
    except Exception as exc:
        out["chat_error"] = str(exc)[:400]
        out["chat_reply_de"] = f"(Chat-Timeout/Fehler — evolve-only) {str(exc)[:120]}"
        out["next_step_de"] = str((out.get("evolve") or {}).get("message_de") or "Chat fehlgeschlagen")
        out["ok"] = bool((out.get("evolve") or {}).get("ok", True))

    try:
        from analytics.closed_loop_score import refresh_closed_loop_score

        out["circle_refreshed"] = True
        refresh_closed_loop_score(root)
    except Exception:
        pass

    _write_evidence(root, out)
    return out


def load_chat_evolution_preview(root: Path) -> Dict[str, Any]:
    path = Path(root) / _EVIDENCE_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_evidence(root: Path, doc: Dict[str, Any]) -> None:
    path = Path(root) / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
