#!/usr/bin/env python3
"""Marktanalyse Bash — read-only text views (fail-closed, no orders)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SNAPSHOT_REL = Path("control/review_snapshot/v5r_decision_cockpit_snapshot.json")
_READINESS_REL = Path("control/prediction_readiness.json")
_H1_GOV_REL = Path("control/h1_governance_status.json")
_STATUS_REL = Path("evidence/king_status_latest.json")
_PULSE_REL = Path("evidence/king_network_pulse_latest.json")


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


def run_preflight(root: Path) -> Dict[str, Any]:
    from aa_pilot_launch import run_preflight

    report = run_preflight(root)
    report["checked_at_utc"] = _utc_now()
    return report


def _collect_gates(root: Path) -> List[str]:
    blockers: List[str] = []
    readiness = _load_json(root / _READINESS_REL)
    blockers.extend(str(b) for b in (readiness.get("blockers") or []) if b)
    h1 = _load_json(root / _H1_GOV_REL)
    blockers.extend(str(b) for b in (h1.get("gate_blockers") or []) if b)
    snap = _load_json(root / _SNAPSHOT_REL)
    blockers.extend(str(b) for b in (snap.get("blockers") or []) if b)
    try:
        from analytics.prediction_operations import evaluate_prediction_readiness_for_orders

        gate = evaluate_prediction_readiness_for_orders(root)
        blockers.extend(str(b) for b in (gate.get("blockers") or []) if b)
    except Exception:
        pass
    return sorted(set(blockers))


def format_preflight_de(report: Dict[str, Any]) -> str:
    ok = bool(report.get("overall_pass", report.get("pilot_core_ready")))
    lines = [
        f"Preflight: {'PASS' if ok else 'BLOCK'}",
        f"Live-Trading bereit: {report.get('live_trading_ready', '—')}",
        f"Pilot-Core bereit: {report.get('pilot_core_ready', '—')}",
    ]
    blockers = report.get("blockers") or []
    if blockers:
        lines.append("Blocker:")
        lines.extend(f"  • {b}" for b in blockers[:12])
    guard = report.get("champion_guard") or {}
    if guard:
        lines.append(f"Champion-Guard: hard_block={guard.get('hard_block')} signals_ok={guard.get('signals_ok')}")
    return "\n".join(lines)


def format_picks_de(root: Path) -> str:
    readiness = _load_json(root / _READINESS_REL)
    picks = readiness.get("top_picks") or []
    if not picks:
        return "Keine Top-Picks — zuerst: bash tools/marktanalyse_bash.sh predict"
    lines = [
        f"Profil: {readiness.get('profile_used') or '—'}",
        f"Signal: {readiness.get('signal_date') or '—'} · Preise: {readiness.get('price_latest') or '—'}",
        f"Predict OK: {readiness.get('ok')}",
        "—" * 44,
        f"{'Ticker':<8} {'Gewicht':>10}",
    ]
    for row in picks[:15]:
        ticker = str(row.get("ticker") or row.get("Ticker") or "—")
        weight = float(row.get("target_weight") or row.get("weight") or 0.0)
        lines.append(f"{ticker:<8} {weight:>10.4f}")
    lines.append("—" * 44)
    lines.append("Research-Signal — keine Orders von Linux.")
    return "\n".join(lines)


def format_cockpit_de(root: Path) -> str:
    snap = _load_json(root / _SNAPSHOT_REL)
    if not snap:
        return "Cockpit-Snapshot fehlt — predict oder Cockpit-Refresh ausführen."
    exec_ov = (snap.get("cockpit_data") or {}).get("executive_overview") or {}
    champ = exec_ov.get("active_champion") or snap.get("authoritative_champion") or "—"
    stage = exec_ov.get("evidence_stage") or snap.get("evidence_stage") or "—"
    lines = [
        "Decision Cockpit (read-only)",
        f"Champion: {champ}",
        f"Evidence-Stage: {stage}",
        f"Live-Trading: {snap.get('live_trading_allowed')}",
        f"Auto-Promotion: {snap.get('auto_promotion_allowed')}",
    ]
    banners = snap.get("banners") or (snap.get("cockpit_data") or {}).get("banners") or []
    if banners:
        lines.append("Banner:")
        lines.extend(f"  • {b}" for b in banners[:6])
    blockers = snap.get("blockers") or []
    if blockers:
        lines.append(f"Governance-Blocker ({len(blockers)}):")
        lines.extend(f"  • {b}" for b in blockers[:8])
    return "\n".join(lines)


def format_gates_de(root: Path) -> str:
    blockers = _collect_gates(root)
    if not blockers:
        return "Gates: keine operativen Blocker (Orders weiterhin fail-closed auf Linux)."
    lines = ["Operative Gates / Blocker:", "—" * 44]
    lines.extend(f"  • {b}" for b in blockers)
    return "\n".join(lines)


def build_status_bundle(root: Path) -> Dict[str, Any]:
    from analytics.active_alpha_identity import product_name, status_line_de

    readiness = _load_json(root / _READINESS_REL)
    king = _load_json(root / _STATUS_REL)
    pulse = _load_json(root / _PULSE_REL)
    h1 = _load_json(root / _H1_GOV_REL)
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "product": product_name(root),
        "status_line_de": status_line_de(root),
        "prediction_ok": bool(readiness.get("ok")),
        "signal_date": readiness.get("signal_date"),
        "profile_used": readiness.get("profile_used"),
        "h1_status": h1.get("status") or king.get("h1_status"),
        "h1_sealed": bool(h1.get("sealed") or king.get("h1_sealed")),
        "governance_champion": king.get("governance_champion"),
        "network_phase": pulse.get("phase"),
        "next_action_de": king.get("next_action_de") or pulse.get("next_action_de"),
        "blockers": _collect_gates(root),
        "safety": {
            "dry_run": king.get("safety_dry_run"),
            "no_orders": True,
        },
    }


def format_status_de(bundle: Dict[str, Any]) -> str:
    lines = [
        bundle.get("status_line_de") or bundle.get("product") or "Marktanalyse",
        "—" * 44,
        f"H1: {bundle.get('h1_status')} · Sealed: {bundle.get('h1_sealed')}",
        f"Champion: {bundle.get('governance_champion')}",
        f"Predict: {'OK' if bundle.get('prediction_ok') else 'FEHLT'} · Signal {bundle.get('signal_date') or '—'}",
        f"Netzwerk: {bundle.get('network_phase') or '—'}",
        f"Nächster Schritt: {bundle.get('next_action_de') or '—'}",
    ]
    blockers = bundle.get("blockers") or []
    if blockers:
        lines.append(f"Blocker ({len(blockers)}): {blockers[0]}" + (f" (+{len(blockers)-1})" if len(blockers) > 1 else ""))
    lines.append("—" * 44)
    lines.append("Safety: dry_run · keine Linux-Orders")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Marktanalyse Bash views")
    p.add_argument("command", choices=["preflight", "cockpit", "picks", "gates", "status", "bundle"])
    p.add_argument("--root", default=str(ROOT))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "preflight":
        report = run_preflight(root)
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(format_preflight_de(report))
        return 0 if report.get("overall_pass", report.get("pilot_core_ready")) else 1

    if args.command == "cockpit":
        text = format_cockpit_de(root)
        print(text)
        return 0

    if args.command == "picks":
        print(format_picks_de(root))
        return 0

    if args.command == "gates":
        print(format_gates_de(root))
        return 0

    bundle = build_status_bundle(root)
    if args.command == "bundle":
        print(json.dumps(bundle, indent=2, default=str))
        return 0

    print(format_status_de(bundle))
    return 0 if bundle.get("prediction_ok") or bundle.get("h1_status") == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
