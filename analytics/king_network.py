"""König-Netzwerk — getaktete Schicht-Synchronisation über Evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from aa_safe_io import atomic_write_json

_NETWORK_REL = Path("control/king_network.json")
_PULSE_REL = Path("evidence/king_network_pulse_latest.json")
_STATUS_REL = Path("evidence/king_status_latest.json")
_EVAL_REL = Path("evidence/daily_alpha_h1_evaluation_latest.json")
_BRIDGE_REL = Path("evidence/alpha_model_cursor_king_bridge_latest.json")
_BUILD_POLICY_REL = Path("control/king_32b_autonomous_build.json")


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


def load_network_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _NETWORK_REL)


def load_network_pulse(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _PULSE_REL)


def _parse_utc(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def autonomous_build_enabled(root: Path) -> bool:
    """32B ist Standard-Bauer — Cursor nur bei explizitem Fallback."""
    doc = _load_json(Path(root) / _BUILD_POLICY_REL)
    if str(doc.get("status") or "").upper() != "AUTHORITATIVE":
        return False
    return bool(doc.get("autonomous_build_enabled")) and not bool(doc.get("cursor_build_fallback"))


def bridge_pending_cursor(root: Path) -> Tuple[bool, str]:
    """True wenn König-Anfrage an Cursor noch nicht beantwortet."""
    doc = _load_json(Path(root) / _BRIDGE_REL)
    king = doc.get("last_king_push") or {}
    request = str(king.get("request_de") or "").strip()
    if not request:
        return False, ""
    king_at = _parse_utc(str(king.get("at_utc") or ""))
    cursor = doc.get("last_cursor_push") or {}
    cursor_at = _parse_utc(str(cursor.get("at_utc") or ""))
    if king_at and cursor_at and cursor_at >= king_at:
        return False, ""
    return True, request


def _evaluation_ready(root: Path) -> bool:
    ev = _load_json(Path(root) / _EVAL_REL)
    path = ev.get("benchmark_returns_path")
    if path is None or str(path).strip() in ("", "null"):
        return False
    return bool(ev.get("evaluated_at_utc"))


def compute_takt(root: Path) -> Dict[str, Any]:
    """Leitet Phase, aktive Schicht und Handoff aus Evidence ab."""
    root = Path(root)
    status = _load_json(root / _STATUS_REL)
    sealed = bool(status.get("h1_sealed"))
    csv_ok = bool(status.get("benchmark_csv_ok"))
    bench_running = bool(status.get("benchmark_running"))
    bench_hung = bool(status.get("benchmark_hung"))
    bench_over_eta = bool(status.get("benchmark_over_eta"))
    next_action = str(status.get("next_action_de") or "").strip()
    next_layer = str(status.get("next_layer") or "bash").strip()

    pending, bridge_request = bridge_pending_cursor(root)
    if pending:
        if autonomous_build_enabled(root):
            hint = bridge_request[:180] if bridge_request else "Mandat lesen"
            return {
                "phase": "build",
                "active_node": "koenig",
                "active_layer": "koenig",
                "handoff_to": "bash",
                "next_action_de": (
                    f"König 32B autonom: /bau {hint} · bash tools/king_ops.sh r3-bau"
                ),
                "next_layer": "koenig",
                "reason_de": "32B baut autonom — Bridge-Hinweis, kein Cursor-Standard",
                "build_owner": "koenig_32b",
            }
        return {
            "phase": "build",
            "active_node": "cursor",
            "active_layer": "cursor",
            "handoff_to": "bash",
            "next_action_de": f"Bridge: {bridge_request[:200]}",
            "next_layer": "cursor",
            "reason_de": "König-Anfrage in Bridge — Cursor-Schicht (Fallback)",
        }

    h1_status = str(status.get("h1_status") or "")
    seal_optional = False
    try:
        from analytics.h1_seal_policy import is_h1_seal_required

        seal_optional = not is_h1_seal_required(root)
    except Exception:
        pass
    if sealed or (seal_optional and h1_status == "COMPLETE"):
        reason = "H1 sealed — König-Schicht" if sealed else "H1 COMPLETE — Seal optional (Policy)"
        action = next_action or (
            "/ready — H1 sealed; /learn · /predict"
            if sealed
            else "/ready — H1 COMPLETE; Seal optional · /predict"
        )
        return {
            "phase": "ready",
            "active_node": "koenig",
            "active_layer": "koenig",
            "handoff_to": "koenig",
            "next_action_de": action,
            "next_layer": "koenig",
            "reason_de": reason,
            "seal_optional": seal_optional,
        }

    if bench_hung or bench_over_eta:
        reason = "Benchmark hung — Operator-Urteil" if bench_hung else "Benchmark über ETA — Operator-Urteil"
        return {
            "phase": "decide",
            "active_node": "koenig",
            "active_layer": "koenig",
            "handoff_to": "bash",
            "next_action_de": next_action or "bash tools/king_ops.sh status — Benchmark prüfen",
            "next_layer": "koenig",
            "reason_de": reason,
        }

    if _evaluation_ready(root):
        ev = _load_json(root / _EVAL_REL)
        action = next_action or "PASS/FAIL aus evaluation_latest erklären"
        if not ev.get("pass_full_seal"):
            action = "Sharpe-FAIL dokumentieren; Forschung vorschlagen — kein Champion-Wechsel"
        return {
            "phase": "decide",
            "active_node": "koenig",
            "active_layer": "koenig",
            "handoff_to": "koenig",
            "next_action_de": action,
            "next_layer": "koenig",
            "reason_de": "Evaluation frisch — König interpretiert",
            "pass_full_seal": bool(ev.get("pass_full_seal")),
        }

    if csv_ok:
        return {
            "phase": "prove",
            "active_node": "python",
            "active_layer": "bash",
            "handoff_to": "koenig",
            "next_action_de": next_action or "bash tools/king_ops.sh h1-seal",
            "next_layer": "bash",
            "reason_de": "CSV da — Bash startet h1-watch (Python beweist)",
        }

    if bench_running:
        return {
            "phase": "observe",
            "active_node": "bash",
            "active_layer": "bash",
            "handoff_to": "python",
            "next_action_de": next_action or "bash tools/king_ops.sh watch-bg",
            "next_layer": "bash",
            "reason_de": "Benchmark läuft — Bash beobachtet",
        }

    return {
        "phase": "execute",
        "active_node": "bash",
        "active_layer": "bash",
        "handoff_to": "python",
        "next_action_de": next_action or "bash tools/king_ops.sh h1-seal",
        "next_layer": next_layer or "bash",
        "reason_de": "Pipeline starten — Bash führt aus",
    }


def sync_network_pulse(root: Path, *, source_node: str = "bash") -> Dict[str, Any]:
    """Schreibt getakteten Netzwerk-Puls — nach jedem status/tune/h1-watch."""
    root = Path(root)
    network = load_network_config(root)
    prev = load_network_pulse(root)
    takt = compute_takt(root)
    hardware: Dict[str, Any] = {}
    try:
        from analytics.king_hardware import sync_hardware_with_phase

        hardware = sync_hardware_with_phase(root, phase=str(takt.get("phase") or "sync"))
    except Exception:
        pass
    prev_phase = str(prev.get("phase") or "")
    beat = int(prev.get("beat") or 0)
    if takt["phase"] != prev_phase:
        beat += 1

    status = _load_json(root / _STATUS_REL)
    out: Dict[str, Any] = {
        "ok": True,
        "schema_version": 1,
        "synced_at_utc": _utc_now(),
        "source_node": str(source_node or "bash"),
        "network_ref": "control/king_network.json",
        "matrix_ref": network.get("matrix_ref") or "control/king_responsibility_matrix_de.md",
        "beat": beat,
        "phase": takt["phase"],
        "active_node": takt["active_node"],
        "active_layer": takt["active_layer"],
        "handoff_to": takt["handoff_to"],
        "next_action_de": takt["next_action_de"],
        "next_layer": takt["next_layer"],
        "reason_de": takt.get("reason_de"),
        "h1_sealed": bool(status.get("h1_sealed")),
        "h1_status": status.get("h1_status"),
        "benchmark_running": bool(status.get("benchmark_running")),
        "benchmark_csv_ok": bool(status.get("benchmark_csv_ok")),
        "headline_de": (
            f"Takt {beat} · {takt['phase']} · Schicht {takt['active_layer']} "
            f"→ {takt['handoff_to']}"
        ),
    }
    if hardware:
        out["hardware_ref"] = "evidence/king_hardware_latest.json"
        out["gpu_returns_enabled"] = bool((hardware.get("gpu_returns") or {}).get("enabled"))
        out["vram_policy_de"] = hardware.get("vram_policy_de")
        out["benchmark_over_eta"] = bool((hardware.get("benchmark") or {}).get("benchmark_over_eta"))
        out["benchmark_hung"] = bool((hardware.get("benchmark") or {}).get("benchmark_hung"))
        gpu_on = "GPU-ON" if out.get("gpu_returns_enabled") else "GPU-OFF"
        out["headline_de"] = f"{out['headline_de']} · {gpu_on}"
    if "pass_full_seal" in takt:
        out["pass_full_seal"] = takt["pass_full_seal"]
    atomic_write_json(root / _PULSE_REL, out)
    return out


def format_network_banner_de(root: Path) -> str:
    pulse = load_network_pulse(root)
    if not pulse:
        pulse = sync_network_pulse(root)
    lines = [
        f"**Netzwerk:** {pulse.get('headline_de')}",
        f"Aktion: {pulse.get('next_action_de')}",
        f"Grund: {pulse.get('reason_de')}",
    ]
    return "\n".join(lines)


def aligned_next_action_de(root: Path) -> str:
    """Einheitliche nächste Aktion — Pulse vor Sovereignty."""
    pulse = load_network_pulse(root)
    if pulse.get("next_action_de"):
        return str(pulse["next_action_de"])
    return sync_network_pulse(root).get("next_action_de") or "bash tools/king_ops.sh status"
