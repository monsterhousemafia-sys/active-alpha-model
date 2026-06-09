"""König-Souveränität — Wichtigstes führt der König selbst aus; Cursor ist Vasall."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/king_sovereignty_latest.json")
_MIN_PULSE_INTERVAL_S = 300


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_king_sovereignty(root: Path) -> Dict[str, Any]:
    return _load_last_pulse(root)


def _load_last_pulse(root: Path) -> Dict[str, Any]:
    path = Path(root) / _EVIDENCE_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def sovereignty_model_de() -> str:
    return (
        "Orchestrator = König (Coder-32B) auf diesem Host. "
        "Jobs: bash tools/king_ops.sh pipeline (status→maintain→h1-seal). "
        "Einzeln: king_ops status|h1-seal|maintain|distribute|pulse. "
        "mom_1 lokal (king_h1) — flock, ein Benchmark. Cursor = Vasall (/cursor anfrage)."
    )


def next_king_action_de(root: Path) -> str:
    root = Path(root)
    try:
        from analytics.king_network import aligned_next_action_de

        aligned = aligned_next_action_de(root)
        if aligned:
            return aligned
    except Exception:
        pass
    try:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        h1 = h1_backtest_status(root)
        st = str(h1.get("status") or "MISSING")
        if is_h1_backtest_sealed(root):
            return "/ready — H1 sealed; Predict/Order-Gates prüfen"
        if st == "RUNNING":
            return "/h1-watch — Backtest läuft; nur beobachten"
        if st == "COMPLETE":
            from analytics.h1_benchmark import benchmark_status

            bench = benchmark_status(root)
            if not bench.get("exists"):
                if bench.get("generating"):
                    return "Benchmark läuft — warten, dann /h1-watch"
                return "/h1-benchmark — mom_1_top12 erzeugen, dann /h1-watch"
            return "/h1-watch — Evaluate + Seal"
        if st in ("ZOMBIE", "FAILED", "MISSING"):
            return "/h1-watch — Recovery zuerst"
    except Exception:
        pass
    return "/h1-status — IST lesen"


def pulse_king_sovereignty(
    root: Path,
    *,
    auto_execute: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """Ein Puls: König führt den nächsten kritischen Schritt selbst aus."""
    root = Path(root)
    last = _load_last_pulse(root)
    if not force:
        try:
            prev = str(last.get("pulsed_at_utc") or "")
            if prev:
                t0 = datetime.fromisoformat(prev.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - t0).total_seconds() < _MIN_PULSE_INTERVAL_S:
                    return {**last, "skipped": True, "reason_de": "Puls kürzlich — Throttle aktiv"}
        except Exception:
            pass

    actions: List[Dict[str, Any]] = []
    h1_doc: Dict[str, Any] = {}
    sealed = False
    try:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        h1_doc = h1_backtest_status(root)
        sealed = is_h1_backtest_sealed(root)
    except Exception as exc:
        h1_doc = {"status": "ERROR", "detail_de": str(exc)[:120]}

    st = str(h1_doc.get("status") or "MISSING")

    if auto_execute and st == "COMPLETE" and not sealed:
        try:
            from analytics.h1_unified_connect import connect_h1_pipeline

            connected = connect_h1_pipeline(root, auto_execute=True)
            actions.extend(connected.get("actions_taken") or [])
            sealed = bool(connected.get("sealed"))
        except Exception as exc:
            actions.append({"id": "h1_pulse_error", "error_de": str(exc)[:160]})
    elif auto_execute and st in ("ZOMBIE", "FAILED", "MISSING") and not sealed:
        try:
            from analytics.h1_watch import run_h1_watch

            watch = run_h1_watch(root)
            actions.append({"id": "h1-watch-recovery", "status": watch.get("status")})
        except Exception as exc:
            actions.append({"id": "recovery_error", "error_de": str(exc)[:160]})

    out = {
        "ok": True,
        "schema_version": 1,
        "pulsed_at_utc": _utc_now(),
        "sovereignty_de": sovereignty_model_de(),
        "h1_status": st,
        "sealed": sealed,
        "actions_taken": actions,
        "next_action_de": next_king_action_de(root),
        "cursor_role_de": "Vasall — nur auf König-Anfrage (/cursor anfrage), keine H1-Jobs",
        "headline_de": (
            f"König-Puls: H1 {st}" + (" — SEALED" if sealed else f" → {next_king_action_de(root)}")
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, out)
    try:
        from analytics.king_network import sync_network_pulse

        sync_network_pulse(root, source_node="koenig")
    except Exception:
        pass
    try:
        from analytics.alpha_model_agent_home import append_journal

        append_journal(
            root,
            event_de="König-Puls",
            detail=out.get("headline_de") or "",
        )
    except Exception:
        pass
    return out


def format_pulse_banner_de(root: Path) -> str:
    doc = _load_last_pulse(root) or pulse_king_sovereignty(root, auto_execute=True)
    lines = [
        f"**{doc.get('headline_de')}**",
        f"Nächster Schritt (König): {doc.get('next_action_de')}",
        f"Cursor: {doc.get('cursor_role_de')}",
    ]
    for act in doc.get("actions_taken") or []:
        aid = act.get("id") or act.get("action")
        msg = act.get("message_de") or act.get("status") or act.get("error_de") or ""
        if aid and msg:
            lines.append(f"• {aid}: {msg}")
    return "\n".join(lines)


def pull_sovereignty_context_for_king(root: Path, *, max_chars: int = 2500) -> str:
    root = Path(root)
    doc = _load_last_pulse(root)
    if not doc:
        doc = pulse_king_sovereignty(root, auto_execute=False)
    net_line = "—"
    try:
        from analytics.king_network import load_network_pulse, sync_network_pulse

        pulse = load_network_pulse(root) or sync_network_pulse(root, source_node="koenig")
        net_line = str(pulse.get("headline_de") or "—")
    except Exception:
        pass
    parts = [
        "=== KÖNIG-SOUVERÄNITÄT ===",
        sovereignty_model_de(),
        f"Netzwerk-Takt: {net_line}",
        f"Letzter Puls: {doc.get('pulsed_at_utc', '—')}",
        f"H1: {doc.get('h1_status')} · sealed={doc.get('sealed')}",
        f"Dein nächster Schritt: {doc.get('next_action_de') or next_king_action_de(root)}",
        "Schicht 1=Bash king_ops · Schicht 4=Cursor Bridge — du orchestrierst, Bash führt aus.",
    ]
    text = "\n".join(parts)
    return text[:max_chars]
