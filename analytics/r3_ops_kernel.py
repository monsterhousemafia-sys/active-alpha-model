"""R3 Ops Kernel — einheitliche Orchestrierung, Schritt-Schnittstellen, Evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_ops_kernel_policy.json")
_EVIDENCE_REL = Path("evidence/r3_ops_latest.json")
SYNC_OWNER_DEFAULT = "r3_ops_kernel"


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


def load_ops_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if doc:
        return doc
    return {
        "schema_version": 1,
        "sync_owner_default": SYNC_OWNER_DEFAULT,
        "phases": {
            "pre_us": {"steps": ["quotes", "signal_check", "capital", "prognosis", "top_picks", "gui_light"]},
            "intraday": {"steps": ["quotes", "fall_watch", "swing_theory", "cycle_status", "prognosis_if_stale"]},
            "eod": {"steps": ["eod_signal", "capital", "prognosis", "postmortem", "learning_capture"]},
            "full": {
                "steps": [
                    "quotes",
                    "daytrading_snapshot",
                    "signal_check",
                    "capital",
                    "prognosis",
                    "top_picks",
                    "cycle",
                    "gui_full",
                    "learning_capture",
                ]
            },
            "data_care": {"steps": ["quotes", "daytrading_snapshot", "cycle", "learning_capture"]},
            "prognosis_run": {"steps": ["capital", "prognosis", "top_picks", "gui_light"]},
        },
        "automation": {"max_top_picks": 12, "min_priority_score": 8.0},
        "governance": {"orders_require_gui_confirmation": True},
    }


def resolve_sync_owner(root: Path, *, owner: Optional[str] = None) -> str:
    if owner:
        return str(owner)
    pol = load_ops_policy(root)
    return str(pol.get("sync_owner_default") or SYNC_OWNER_DEFAULT)


def normalize_step(step_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Einheitliches Schritt-Schema für alle Orchestratoren."""
    out = dict(raw)
    out.setdefault("id", step_id)
    out.setdefault("ok", False)
    out.setdefault("detail_de", "")
    return out


def rank_top_picks(
    worthwhile: Dict[str, Any],
    *,
    max_picks: int = 12,
    min_score: float = 8.0,
) -> List[Dict[str, Any]]:
    rows = list(worthwhile.get("worthwhile_buys") or [])
    out: List[Dict[str, Any]] = []
    for row in rows:
        score = float(row.get("priority_score") or 0)
        alpha = float(row.get("alpha_lcb") or 0)
        composite = score + alpha * 5000.0
        if score < min_score and row.get("source") != "investment_plan":
            continue
        out.append(
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "side": str(row.get("side") or "BUY").upper(),
                "priority_score": round(score, 2),
                "composite_score": round(composite, 2),
                "gap_eur": row.get("gap_eur"),
                "target_eur": row.get("target_eur"),
                "alpha_lcb": row.get("alpha_lcb"),
                "model_weight_pct": row.get("model_weight_pct"),
                "action_de": row.get("action_de") or row.get("rationale_de"),
                "source": row.get("source") or "reeval",
            }
        )
    out.sort(key=lambda r: float(r.get("composite_score") or r.get("priority_score") or 0), reverse=True)
    return out[: max(1, int(max_picks))]


def _governance_snapshot(root: Path) -> Dict[str, Any]:
    kernel = _load_json(root / "control/AI_KERNEL.json")
    flags = kernel.get("flags") if isinstance(kernel.get("flags"), dict) else {}
    auto_exec = bool(flags.get("auto_execute_real_money", False))
    pol = load_ops_policy(root)
    gov = pol.get("governance") if isinstance(pol.get("governance"), dict) else {}
    return {
        "auto_execute_real_money": auto_exec,
        "fail_closed": not auto_exec,
        "orders_require_gui_confirmation": bool(gov.get("orders_require_gui_confirmation", True)),
        "message_de": (
            "✓ Fail-closed — Top-Picks vorbereitet, Orders nur per R3-Freigabe"
            if not auto_exec
            else "⚠ auto_execute aktiv — Governance-Konflikt"
        ),
    }


def run_ops_step(
    root: Path,
    step_id: str,
    *,
    force: bool = False,
    sync_owner: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Kanonicaler Schritt — von daily_alpha, data_care, prognosis, cycle."""
    root = Path(root)
    ctx = context if context is not None else {}
    owner = resolve_sync_owner(root, owner=sync_owner)
    sid = str(step_id or "").strip()

    try:
        if sid == "quotes":
            from analytics.r3_quote_keepalive import tick_quote_keepalive

            doc = tick_quote_keepalive(root, force=force, owner=owner, persist=True)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("ok")),
                    "detail_de": doc.get("headline_de") or doc.get("message_de") or "Kurse",
                    "quote_status": (doc.get("assess_after") or {}).get("quote_status"),
                },
            )

        if sid == "signal_check":
            from analytics.prediction_operations import (
                active_profile,
                ensure_prediction_before_orders,
                evaluate_prediction_readiness_for_orders,
                load_prediction_readiness,
            )

            readiness = load_prediction_readiness(root)
            gate = evaluate_prediction_readiness_for_orders(root, readiness=readiness)
            ok = bool(gate.get("ok"))
            detail = gate.get("message_de") or gate.get("reason_de") or "Signal"
            if not ok and force:
                ensured = ensure_prediction_before_orders(root, auto_run=True)
                ok = bool(ensured.get("ok"))
                detail = ensured.get("message_de") or detail
                readiness = load_prediction_readiness(root)
            return normalize_step(
                sid,
                {
                    "ok": ok,
                    "detail_de": detail,
                    "profile": active_profile(root),
                    "signal_date": readiness.get("signal_date"),
                },
            )

        if sid == "eod_signal":
            from analytics.prediction_operations import maybe_run_eod_prediction_switch

            doc = maybe_run_eod_prediction_switch(root, force=force)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("ok")),
                    "skipped": bool(doc.get("skipped")),
                    "detail_de": doc.get("message_de") or "EOD-Signal",
                    "signal_date": doc.get("signal_date"),
                },
            )

        if sid == "capital":
            from analytics.r3_live_capital import compute_worthwhile_positions

            doc = compute_worthwhile_positions(root, force_sync=force, persist=True, sync_owner=owner)
            basis = doc.get("capital_basis") or {}
            ctx["worthwhile"] = doc
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("ok")),
                    "detail_de": doc.get("headline_de") or doc.get("message_de") or "Kapital",
                    "investable_eur": basis.get("investable_eur"),
                    "worthwhile_buy_count": doc.get("worthwhile_buy_count"),
                    "risk_on": doc.get("risk_on"),
                    "signal_date": doc.get("signal_date"),
                },
            )

        if sid in ("prognosis", "prognosis_if_stale"):
            from analytics.r3_prognosis_pipeline import ensure_r3_prognosis_fresh, run_prognosis_automation

            step_force = force if sid == "prognosis" else False
            doc = ensure_r3_prognosis_fresh(root, force=step_force, persist=True)
            if doc.get("skipped") and step_force:
                doc = run_prognosis_automation(root, persist=True)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("ok")),
                    "detail_de": doc.get("headline_de") or "Prognose",
                    "package_ready": doc.get("package_ready"),
                    "worthwhile_buys": doc.get("worthwhile_buys"),
                    "skipped": bool(doc.get("skipped")),
                },
            )

        if sid == "daytrading_snapshot":
            from analytics.pilot_integrated_refresh import run_integrated_refresh

            ir = run_integrated_refresh(root, force=force, auto_enqueue=False)
            snap = ir.trading_snapshot
            health: Dict[str, Any] = {}
            if hasattr(snap, "as_dict"):
                health = (snap.as_dict() or {}).get("health") or {}
            elif isinstance(snap, dict):
                health = snap.get("health") or {}
            return normalize_step(
                sid,
                {
                    "ok": not bool(health.get("blocks_execute")) or bool(health.get("ok")),
                    "detail_de": str((ir.refresh_status or {}).get("headline_de") or "Snapshot aktualisiert")[:160],
                    "blocks_execute": bool(health.get("blocks_execute")),
                    "reevaluation_urgency": (ir.reevaluation or {}).get("urgency"),
                },
            )

        if sid == "gui_light":
            from analytics.desktop_shell_cache import warm_desktop_cache

            nbytes = warm_desktop_cache(root, fast=True, block=False, live_prep=True)
            return normalize_step(sid, {"ok": True, "detail_de": f"GUI-Cache warm ({int(nbytes or 0)} B)"})

        if sid == "gui_full":
            from analytics.r3_full_refresh import run_r3_full_refresh

            doc = run_r3_full_refresh(root, force=force, persist=True)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("gui_ok")),
                    "detail_de": doc.get("headline_de") or doc.get("desktop_url_de") or "R3 vollständig",
                    "desktop_url_de": doc.get("desktop_url_de"),
                },
            )

        if sid == "cycle":
            from analytics.r3_trading_cycle import run_trading_cycle

            doc = run_trading_cycle(root)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("closed")),
                    "detail_de": doc.get("headline_de") or f"Kreislauf {doc.get('cycle_pct') or 0}%",
                    "cycle_pct": doc.get("cycle_pct"),
                },
            )

        if sid == "cycle_status":
            doc = _load_json(root / "evidence/r3_trading_cycle_latest.json")
            pct = float(doc.get("cycle_pct") or 0)
            return normalize_step(
                sid,
                {
                    "ok": pct >= 70,
                    "detail_de": doc.get("headline_de") or f"Kreislauf {pct:.0f}%",
                    "cycle_pct": pct,
                },
            )

        if sid == "fall_watch":
            from analytics.prognosis_fall_watch import run_fall_watch

            doc = run_fall_watch(root, persist=True, fetch_live=True)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("ok")),
                    "detail_de": doc.get("headline_de") or "Fall-Wächter",
                    "fall_detected": doc.get("fall_detected"),
                    "portfolio_return_pct": doc.get("portfolio_return_pct"),
                },
            )

        if sid == "swing_theory":
            from analytics.swing_trading_theory_check import run_swing_trading_theory_check

            doc = run_swing_trading_theory_check(root, persist=True)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("ok")),
                    "detail_de": doc.get("headline_de") or "Swing-Theorie",
                    "shows_today": doc.get("shows_today"),
                },
            )

        if sid == "postmortem":
            from analytics.r3_daily_postmortem import run_daily_postmortem

            doc = run_daily_postmortem(root, persist=True)
            return normalize_step(
                sid,
                {
                    "ok": bool(doc.get("ok")),
                    "detail_de": doc.get("headline_de") or "Tagesbilanz",
                    "bad_day": doc.get("bad_day"),
                },
            )

        if sid == "learning_capture":
            from analytics.public_learning_kernel import run_capture_only

            doc = run_capture_only(root)
            ready = doc.get("readiness") or {}
            return normalize_step(
                sid,
                {
                    "ok": bool(ready.get("learning_healthy") or ready.get("learning_collection_active")),
                    "detail_de": "Learning-Ledger observe-only",
                },
            )

        if sid == "top_picks":
            ww = ctx.get("worthwhile") or _load_json(root / "evidence/r3_worthwhile_positions_latest.json")
            auto = load_ops_policy(root).get("automation") or {}
            picks = rank_top_picks(
                ww if isinstance(ww, dict) else {},
                max_picks=int(auto.get("max_top_picks") or 12),
                min_score=float(auto.get("min_priority_score") or 8.0),
            )
            syms = ", ".join(p["symbol"] for p in picks[:5] if p.get("symbol")) or "—"
            return normalize_step(
                sid,
                {
                    "ok": len(picks) > 0,
                    "detail_de": f"{len(picks)} Top-Picks: {syms}",
                    "top_picks": picks,
                },
            )

        return normalize_step(sid, {"ok": False, "detail_de": f"Unbekannter Schritt {sid}"})
    except Exception as exc:
        return normalize_step(sid, {"ok": False, "detail_de": str(exc)[:160]})


def resolve_phase_steps(root: Path, phase: str) -> List[str]:
    pol = load_ops_policy(root)
    key = str(phase or "pre_us").strip().lower().replace("-", "_")
    phase_def = (pol.get("phases") or {}).get(key) or {}
    steps = list(phase_def.get("steps") or [])
    if steps:
        return [str(s) for s in steps]
    fallback = (pol.get("phases") or {}).get("pre_us") or {}
    return [str(s) for s in (fallback.get("steps") or [])]


def run_ops_pipeline(
    root: Path,
    *,
    phase: str = "pre_us",
    force: bool = False,
    persist: bool = True,
    sync_owner: Optional[str] = None,
    evidence_rel: Optional[Path] = None,
    source: str = "r3_ops_kernel",
) -> Dict[str, Any]:
    """Harmonisierter Pipeline-Einstieg für alle king_ops-Orchestratoren."""
    root = Path(root)
    phase_key = str(phase or "pre_us").strip().lower().replace("-", "_")
    step_ids = resolve_phase_steps(root, phase_key)
    owner = resolve_sync_owner(root, owner=sync_owner)
    gov = _governance_snapshot(root)
    ctx: Dict[str, Any] = {}
    steps: List[Dict[str, Any]] = []
    top_picks: List[Dict[str, Any]] = []

    for sid in step_ids:
        step = run_ops_step(root, sid, force=force, sync_owner=owner, context=ctx)
        if sid == "capital" and ctx.get("worthwhile"):
            pass
        steps.append(step)
        if step.get("id") == "top_picks":
            top_picks = list(step.get("top_picks") or [])

    if not top_picks:
        auto = load_ops_policy(root).get("automation") or {}
        ww = ctx.get("worthwhile") or _load_json(root / "evidence/r3_worthwhile_positions_latest.json")
        top_picks = rank_top_picks(
            ww if isinstance(ww, dict) else {},
            max_picks=int(auto.get("max_top_picks") or 12),
            min_score=float(auto.get("min_priority_score") or 8.0),
        )

    core_ids = {"capital", "prognosis", "eod_signal", "signal_check", "top_picks"}
    core_ok = all(s.get("ok") for s in steps if s.get("id") in core_ids and s.get("id") in step_ids)
    steps_ok = sum(1 for s in steps if s.get("ok"))
    investable = None
    ww_doc = ctx.get("worthwhile") or _load_json(root / "evidence/r3_worthwhile_positions_latest.json")
    if isinstance(ww_doc, dict):
        investable = (ww_doc.get("capital_basis") or {}).get("investable_eur")

    headline = (
        f"✓ Ops {phase_key}: {len(top_picks)} Top-Picks auf {float(investable or 0):.0f} €"
        if core_ok and top_picks
        else f"Ops {phase_key}: {steps_ok}/{len(steps)} — {gov.get('message_de') or 'siehe steps'}"
    )

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": core_ok or steps_ok >= max(1, len(steps) - 2),
        "source": source,
        "phase": phase_key,
        "sync_owner": owner,
        "headline_de": headline,
        "governance": gov,
        "investable_eur": investable,
        "top_picks": top_picks,
        "top_pick_count": len(top_picks),
        "steps": steps,
        "steps_ok": steps_ok,
        "steps_total": len(steps),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "interfaces_ref": (load_ops_policy(root).get("interfaces") or {}),
        "desktop_url_de": "http://127.0.0.1:17890/desktop",
        "next_action_de": (
            "R3 → Freigabe bestätigen (kein auto_execute)"
            if top_picks
            else "T212 sync + bash tools/king_ops.sh daily-alpha full"
        ),
    }
    out_rel = evidence_rel or _EVIDENCE_REL
    if persist:
        atomic_write_json(root / out_rel, doc)
    return doc
