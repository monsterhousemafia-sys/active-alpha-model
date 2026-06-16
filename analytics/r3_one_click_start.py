"""R3 Ein-Klick-Start — T212 API fest einrichten, dann Prognose + Paket."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_one_click_start_latest.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


from analytics.r3_operator_surface_text import OPERATOR_API_ENTER, OPERATOR_RETRY, OPERATOR_SYNC_WAIT


def run_one_click_start(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """
    Ein Operator-Klick in R3:
    Internet → T212 API fest einrichten → Prognose-Pipeline → Freigabe vorbereiten.
    """
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    try:
        from analytics.r3_t212_operator_api import operator_api_gate_block

        block = operator_api_gate_block(
            root,
            headline_de=OPERATOR_API_ENTER,
            next_de=OPERATOR_API_ENTER,
            steps=steps,
        )
        if block:
            doc = {"schema_version": 1, "updated_at_utc": _utc_now(), **block}
            if persist:
                atomic_write_json(root / _EVIDENCE_REL, doc)
            return doc
    except Exception:
        pass

    net: Dict[str, Any] = {}
    try:
        from analytics.r3_internet_requirement import require_internet_for

        net = require_internet_for(root, consumer="r3_start")
        steps.append({"step": "internet", "ok": bool(net.get("allowed")), "detail": net.get("message_de")})
        if not net.get("allowed"):
            doc = {
                "schema_version": 1,
                "updated_at_utc": _utc_now(),
                "ok": False,
                "headline_de": "Kein Internet — Start blockiert",
                "steps": steps,
                "next_de": "Internet prüfen und erneut «Start»",
            }
            if persist:
                atomic_write_json(root / _EVIDENCE_REL, doc)
            return doc
    except Exception as exc:
        steps.append({"step": "internet", "ok": False, "error": str(exc)[:80]})

    api_setup: Dict[str, Any] = {}
    try:
        from analytics.r3_t212_api_bond import ensure_r3_t212_api_bond

        api_setup = ensure_r3_t212_api_bond(root, persist=persist)
        steps.extend(list(api_setup.get("steps") or []))
        if not api_setup.get("setup_ok"):
            headline = (
                OPERATOR_SYNC_WAIT
                if api_setup.get("operator_api_ready")
                else OPERATOR_API_ENTER
            )
            doc = {
                "schema_version": 1,
                "updated_at_utc": _utc_now(),
                "ok": False,
                "setup_ok": False,
                "operator_api_ready": bool(api_setup.get("operator_api_ready")),
                "t212_trusted": False,
                "credentials_configured": bool(api_setup.get("credentials_configured")),
                "headline_de": headline,
                "next_de": headline,
                "steps": steps,
                "bash_de": "bash tools/king_ops.sh r3-t212",
            }
            if persist:
                atomic_write_json(root / _EVIDENCE_REL, doc)
            return doc
        if not api_setup.get("t212_trusted"):
            doc = {
                "schema_version": 1,
                "updated_at_utc": _utc_now(),
                "ok": False,
                "setup_ok": True,
                "t212_trusted": False,
                "credentials_configured": bool(api_setup.get("credentials_configured")),
                "headline_de": OPERATOR_SYNC_WAIT,
                "next_de": OPERATOR_RETRY,
                "steps": steps,
                "bash_de": "bash tools/king_ops.sh r3-t212",
            }
            if persist:
                atomic_write_json(root / _EVIDENCE_REL, doc)
            return doc
    except Exception as exc:
        steps.append({"step": "t212_api_setup", "ok": False, "error": str(exc)[:120]})
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": False,
            "headline_de": OPERATOR_API_ENTER,
            "next_de": OPERATOR_RETRY,
            "steps": steps,
        }
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    pipeline: Dict[str, Any] = {}
    try:
        from analytics.r3_prognosis_pipeline import run_prognosis_automation

        pipeline = run_prognosis_automation(root, persist=True)
        steps.append(
            {
                "step": "prognosis_pipeline",
                "ok": bool(pipeline.get("ok")),
                "trusted": pipeline.get("t212_trusted"),
                "buys": pipeline.get("worthwhile_buys"),
            }
        )
    except Exception as exc:
        steps.append({"step": "prognosis_pipeline", "ok": False, "error": str(exc)[:120]})

    freigabe: Dict[str, Any] = {}
    try:
        from analytics.r3_freigabe import auto_prepare_freigabe_for_desktop

        freigabe = auto_prepare_freigabe_for_desktop(root, force=True)
        steps.append(
            {
                "step": "freigabe",
                "ok": bool(freigabe.get("package_ready")),
                "notional_eur": freigabe.get("notional_eur"),
            }
        )
    except Exception as exc:
        steps.append({"step": "freigabe", "ok": False, "error": str(exc)[:80]})

    pkg_ready = bool(freigabe.get("package_ready"))
    trusted = bool(pipeline.get("t212_trusted")) or bool(api_setup.get("t212_trusted"))
    core_ok = pkg_ready and trusted
    setup_ok = bool(api_setup.get("setup_ok"))

    notional = freigabe.get("notional_eur") or pipeline.get("investable_eur") or api_setup.get("investable_eur")
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": core_ok,
        "setup_ok": setup_ok,
        "package_ready": pkg_ready,
        "t212_trusted": trusted,
        "credentials_configured": bool(api_setup.get("credentials_configured")),
        "investable_eur": pipeline.get("investable_eur") or api_setup.get("investable_eur"),
        "notional_eur": notional,
        "worthwhile_buys": pipeline.get("worthwhile_buys"),
        "headline_de": (
            f"Bereit — {float(notional or 0):.0f} €"
            if pkg_ready and trusted
            else (
                OPERATOR_SYNC_WAIT
                if setup_ok and not trusted
                else (
                    OPERATOR_API_ENTER
                    if not setup_ok
                    else OPERATOR_RETRY
                )
            )
        ),
        "cta_de": (
            f"{float(notional or 0):.0f} €"
            if pkg_ready and trusted
            else OPERATOR_RETRY
        ),
        "steps": steps,
        "next_de": (
            OPERATOR_RETRY
            if pkg_ready
            else (OPERATOR_SYNC_WAIT if setup_ok and not trusted else OPERATOR_API_ENTER)
        ),
        "bash_de": "bash tools/king_ops.sh r3-start",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
