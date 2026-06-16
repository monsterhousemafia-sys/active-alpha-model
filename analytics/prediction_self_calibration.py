"""Read-only prognosis self-calibration — facts vs. opinion, no model changes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/prediction_self_calibration_policy.json")
_EVIDENCE_REL = Path("evidence/prediction_self_calibration_latest.json")


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


def load_self_calibration_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {"enabled": True, "thresholds": {"min_h1_daily_hit_rate_inform": 0.52}}
    return doc


def _integrity_checks(root: Path) -> List[Dict[str, Any]]:
    """Lightweight governance / fake-authority checks (read-only)."""
    root = Path(root)
    checks: List[Dict[str, Any]] = []

    tmpl = list(root.glob("TEMPLATE_EXTERNAL_REVIEW_APPROVAL*.md"))
    fake_approvals = list(root.glob("EXTERNAL_REVIEW_APPROVAL_*.md"))
    real_approvals = [p for p in fake_approvals if not p.name.startswith("TEMPLATE_")]
    checks.append(
        {
            "id": "phase_approvals",
            "pass": True,
            "detail_de": f"{len(real_approvals)} Freigabe-MD, {len(tmpl)} Template(s) ignoriert",
            "template_count": len(tmpl),
            "approval_count": len(real_approvals),
        }
    )

    try:
        from aa_evidence_schema import resolve_locked_champion

        champ = resolve_locked_champion(root)
        checks.append(
            {
                "id": "champion_locked",
                "pass": bool(champ),
                "detail_de": f"Governance-Champion: {champ or '—'}",
                "champion": champ,
            }
        )
    except Exception as exc:
        checks.append({"id": "champion_locked", "pass": False, "detail_de": str(exc)[:80]})

    cc = _load_json(root / "evidence/price_crosscheck_latest.json")
    verdict = str(cc.get("verdict") or "missing")
    checks.append(
        {
            "id": "price_crosscheck",
            "pass": verdict in ("pass", "warn", "skipped"),
            "detail_de": f"Stufe B: {verdict}",
            "verdict": verdict,
            "block_signal_refresh": cc.get("block_signal_refresh"),
        }
    )

    diag = _load_json(root / "model_output_sp500_pit_t212/r3_daily_diagnosis.json")
    regime_match = diag.get("regime_match")
    checks.append(
        {
            "id": "regime_match",
            "pass": regime_match is True,
            "detail_de": f"Regime-Match: {regime_match}",
            "live_regime": (diag.get("live_regime") or {}).get("regime_label"),
            "signal_date": diag.get("signal_date"),
        }
    )

    trust = _load_json(root / "evidence/t212_trust_latest.json")
    checks.append(
        {
            "id": "t212_trust",
            "pass": bool(trust.get("trusted")) if trust else None,
            "detail_de": "T212 trusted" if trust.get("trusted") else "T212 nicht trusted oder fehlt",
            "trusted": trust.get("trusted"),
        }
    )

    return checks


def build_prediction_self_calibration(
    root: Path,
    *,
    policy: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    pol = dict(policy or load_self_calibration_policy(root))
    if not pol.get("enabled", True):
        return {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": True,
            "skipped": True,
            "headline_de": "Selbstkalibrierung deaktiviert",
        }

    readiness = _load_json(root / "control/prediction_readiness.json")
    h1 = _load_json(root / "control/h1_governance_status.json")
    diag = _load_json(root / "model_output_sp500_pit_t212/r3_daily_diagnosis.json")
    post = _load_json(root / "evidence/r3_daily_postmortem_latest.json")
    cc = _load_json(root / "evidence/price_crosscheck_latest.json")
    refine = _load_json(root / "control/operational_refinement_state.json")

    h1_metrics = dict(h1.get("metrics_strategy") or {})
    h1_eval = dict(readiness.get("h1_evaluation") or {}).get("metrics_strategy") or h1_metrics
    daily_hit = h1_eval.get("daily_hit_rate") or h1_metrics.get("daily_hit_rate")

    fb = diag.get("feedback_by_regime") or {}
    ro = fb.get("risk_on") or {}
    rf = fb.get("risk_off") or {}
    mature_n = int(fb.get("n_mature") or 0)

    try:
        daily_hit_f = float(daily_hit) if daily_hit is not None else None
    except (TypeError, ValueError):
        daily_hit_f = None

    wrong_day_pct = None
    if daily_hit_f is not None:
        wrong_day_pct = round((1.0 - daily_hit_f) * 100.0, 2)

    integrity = _integrity_checks(root)
    integrity_ok = all(c.get("pass") is not False for c in integrity if c.get("pass") is not None)

    post_delta = post.get("delta_vs_benchmark_pct")
    regime_match = diag.get("regime_match")
    signal_date = readiness.get("signal_date") or diag.get("signal_date")
    price_latest = diag.get("price_latest") or post.get("as_of_date")

    claims: List[Dict[str, str]] = [
        {
            "claim_de": "Das Modell liegt nicht immer richtig",
            "status": "fact",
            "evidence_de": f"H1 daily_hit_rate ≈ {daily_hit_f:.1%}" if daily_hit_f else "Hit-Rate fehlt",
        },
        {
            "claim_de": "Regime-Diagnose stimmt mit Signal überein",
            "status": "fact" if regime_match else "open",
            "evidence_de": f"regime_match={regime_match}, signal={signal_date}",
        },
        {
            "claim_de": "Letzter Plan-Tag vs SPY",
            "status": "fact" if post.get("ok") else "missing",
            "evidence_de": str(post.get("headline_de") or post.get("message_de") or "—")[:120],
        },
        {
            "claim_de": "Preis-Cross-Check (Stufe B)",
            "status": "fact" if cc else "missing",
            "evidence_de": f"verdict={cc.get('verdict')}, spy={cc.get('spy_status')}",
        },
    ]

    min_hit = float((pol.get("thresholds") or {}).get("min_h1_daily_hit_rate_inform") or 0.52)
    calibrated = daily_hit_f is not None and daily_hit_f >= min_hit and regime_match is True

    headline = (
        f"Selbstkalibrierung — ~{daily_hit_f:.0%} Tage-Treffer, "
        f"~{wrong_day_pct}% daneben (H1, kein Orakel)"
        if daily_hit_f is not None
        else "Selbstkalibrierung — Hit-Rate noch nicht messbar"
    )

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": headline,
        "ok": calibrated and integrity_ok,
        "calibrated_de": (
            "Prognose-Edge messbar, Regime konsistent — trotzdem ~45% Fehltage normal."
            if calibrated
            else "Kalibrierung unvollständig oder Regime/Hit-Rate offen."
        ),
        "honesty_de": (
            "Kein System (Modell, KI, Schlagzeile) hat immer recht — nur messbare Edge über viele Tage."
        ),
        "metrics": {
            "h1_daily_hit_rate": daily_hit_f,
            "h1_wrong_day_pct": wrong_day_pct,
            "h1_sharpe_0rf": h1_eval.get("sharpe_0rf") or h1_metrics.get("sharpe_0rf"),
            "risk_on_signed_hit_rate": ro.get("signed_hit_rate"),
            "risk_off_signed_hit_rate": rf.get("signed_hit_rate"),
            "outcomes_n_mature": mature_n,
            "postmortem_delta_vs_spy_pct": post_delta,
            "regime_match": regime_match,
            "signal_date": signal_date,
            "price_latest": price_latest,
            "price_crosscheck_verdict": cc.get("verdict"),
            "stale_primary_count": (cc.get("counts") or {}).get("stale_primary"),
        },
        "integrity_checks": integrity,
        "claims_vs_facts": claims,
        "refs": {
            "readiness": "control/prediction_readiness.json",
            "diagnosis": "model_output_sp500_pit_t212/r3_daily_diagnosis.json",
            "postmortem": "evidence/r3_daily_postmortem_latest.json",
            "price_crosscheck": "evidence/price_crosscheck_latest.json",
            "refinement_state": "control/operational_refinement_state.json",
            "last_refinement_ok": refine.get("ok"),
            "last_regime_match": refine.get("r3_regime_match"),
        },
        "policy_ref": str(_POLICY_REL),
    }


def run_prediction_self_calibration(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    doc = build_prediction_self_calibration(root)
    if persist and not doc.get("skipped"):
        path = root / _EVIDENCE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, doc)
    return doc
