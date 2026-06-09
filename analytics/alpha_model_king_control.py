"""König-Kontrolle — Entfaltungsraum läuft nur mit 100% Souveränität."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/alpha_model_king_control_latest.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_king_control_active() -> bool:
    return os.environ.get("AA_KING_CONTROL", "").strip().lower() in ("1", "true", "yes")


def force_king_env() -> None:
    """König-Umgebung erzwingen — ein Kanal, ein Agent."""
    os.environ["AA_AGENT_CHAMBER"] = "1"
    os.environ["AA_KING_CONTROL"] = "1"
    os.environ["AA_OPERATOR_CHANNEL"] = "conversational"
    if os.environ.get("AA_AGENT_NO_SERVE", "").strip().lower() not in ("1", "true", "yes"):
        os.environ.setdefault("AA_AGENT_SERVE", "1")


def king_control_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    force_king_env()
    checks: List[Dict[str, Any]] = []

    def add(cid: str, label: str, ok: bool, detail: str = "") -> None:
        checks.append({"id": cid, "label_de": label, "ok": ok, "detail_de": detail})

    add("env_chamber", "AA_AGENT_CHAMBER", os.environ.get("AA_AGENT_CHAMBER") == "1", "1")
    add("env_king", "AA_KING_CONTROL", is_king_control_active(), "1")
    add(
        "env_channel",
        "Operator-Kanal = Gespräch",
        os.environ.get("AA_OPERATOR_CHANNEL", "").strip().lower() == "conversational",
        os.environ.get("AA_OPERATOR_CHANNEL") or "—",
    )

    try:
        from analytics.alpha_model_chamber_resources import verify_chamber_resources

        verify = verify_chamber_resources(root)
        add(
            "transfer",
            "100% Ressourcen-Übergabe",
            bool(verify.get("transfer_ok")),
            str(verify.get("headline_de") or ""),
        )
        add(
            "ollama",
            "Ollama bereit",
            bool(verify.get("runtime_ok")),
            "Ideal-32B",
        )
    except Exception as exc:
        add("transfer", "Ressourcen-Verify", False, str(exc)[:80])

    try:
        from analytics.alpha_model_entfaltung_32b import tier_status

        tier = tier_status(root)
        add("tier", "Ideal-32B Tier", bool(tier.get("tier_ready")), str(tier.get("tier_de") or ""))
    except Exception as exc:
        add("tier", "Tier", False, str(exc)[:60])

    try:
        from analytics.ai_kernel_hardware_bond import bond_kernel_to_king_32b

        bond = bond_kernel_to_king_32b(root, persist=True, preload=False)
        add(
            "hardware_bond",
            "Kernel ↔ 32B ↔ Hardware",
            bool(bond.get("hardware_access") and bond.get("king_model")),
            str(bond.get("headline_de") or "")[:120],
        )
    except Exception as exc:
        add("hardware_bond", "Hardware-Bond", False, str(exc)[:60])

    try:
        from analytics.alpha_model_advisor_bridge import bridge_status

        br = bridge_status(root)
        add(
            "advisor_bridge",
            "Berater-Bridge",
            True,
            "Key OK" if br.get("configured") else "Key optional — /berater-key",
        )
    except Exception as exc:
        add("advisor_bridge", "Berater-Bridge", False, str(exc)[:60])

    passed = sum(1 for c in checks if c.get("ok"))
    total = len(checks)
    required_ids = {"env_chamber", "env_king", "env_channel", "transfer", "ollama", "tier", "hardware_bond"}
    required_ok = all(c.get("ok") for c in checks if c.get("id") in required_ids)
    return {
        "schema_version": 1,
        "checked_at_utc": _utc_now(),
        "ok": required_ok,
        "king_control": is_king_control_active(),
        "checks_passed": passed,
        "checks_total": total,
        "checks": checks,
        "headline_de": (
            "König kontrolliert alles — bereit"
            if required_ok
            else "König-Kontrolle unvollständig — Reparatur nötig"
        ),
    }


def ensure_king_control(root: Path, *, repair: bool = True) -> Dict[str, Any]:
    """
    König startet nur mit voller Kontrolle.
    repair=True: transfer, tier, bridge, agent-home automatisch anwenden.
    """
    root = Path(root)
    force_king_env()
    repaired: List[str] = []

    if repair:
        try:
            from analytics.alpha_model_agent_home import ensure_agent_home

            ensure_agent_home(root)
            repaired.append("agent_home")
        except Exception:
            pass
        try:
            from analytics.alpha_model_king_resources import serve_king_resources

            served = serve_king_resources(root, repair=True)
            if served.get("applied"):
                repaired.extend(served["applied"])
        except Exception:
            pass
        try:
            from analytics.king_sovereignty import pulse_king_sovereignty

            pulse_king_sovereignty(root, auto_execute=True)
            repaired.append("king_pulse")
        except Exception:
            pass

    status = king_control_status(root)
    doc = {
        **status,
        "repaired": repaired,
        "ready": bool(status.get("ok")),
    }
    try:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    except Exception:
        pass
    try:
        from analytics.alpha_model_agent_home import append_journal

        append_journal(
            root,
            event_de="König-Kontrolle" if doc.get("ready") else "König-Kontrolle blockiert",
            detail=doc.get("headline_de") or "",
        )
    except Exception:
        pass
    return doc


def format_king_gate_de(root: Path) -> str:
    doc = ensure_king_control(root, repair=True)
    lines = [f"**{doc.get('headline_de')}**", ""]
    for chk in doc.get("checks") or []:
        mark = "✓" if chk.get("ok") else "✗"
        detail = str(chk.get("detail_de") or "")
        lines.append(f"{mark} {chk.get('label_de')}" + (f" — {detail}" if detail else ""))
    if doc.get("repaired"):
        lines.extend(["", f"Repariert: {', '.join(doc['repaired'])}"])
    if not doc.get("ready"):
        lines.extend(
            [
                "",
                "König läuft nicht ohne volle Kontrolle.",
                "Fix: bash tools/setup_ideal_32b.sh · python3 tools/ai_kernel.py chamber-resources",
            ]
        )
    return "\n".join(lines)


def require_king_ready(root: Path) -> bool:
    """True nur wenn König alle Pflicht-Checks hat."""
    doc = ensure_king_control(root, repair=True)
    return bool(doc.get("ready"))
