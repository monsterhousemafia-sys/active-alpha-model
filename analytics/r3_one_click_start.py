"""R3 Ein-Klick-Start — T212 live, Prognose, Paket (Orders weiterhin ein Klick Freigabe)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_one_click_start_latest.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_one_click_start(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """
    Ein Operator-Klick in R3:
    Internet → T212 Sync (coalesced) → Prognose-Pipeline → Freigabe vorbereiten.
    """
    root = Path(root)
    steps: List[Dict[str, Any]] = []

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

        freigabe = auto_prepare_freigabe_for_desktop(root)
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
    trusted = bool(pipeline.get("t212_trusted"))
    core_ok = pkg_ready and trusted

    notional = freigabe.get("notional_eur") or pipeline.get("investable_eur")
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": core_ok,
        "package_ready": pkg_ready,
        "t212_trusted": trusted,
        "investable_eur": pipeline.get("investable_eur"),
        "notional_eur": notional,
        "worthwhile_buys": pipeline.get("worthwhile_buys"),
        "headline_de": (
            f"Bereit — {float(notional or 0):.0f} € mit einem Klick an T212"
            if pkg_ready and trusted
            else (
                "T212 API prüfen — Key speichern, dann erneut Start"
                if not trusted
                else "Paket wird vorbereitet — erneut Start oder Freigabe prüfen"
            )
        ),
        "cta_de": (
            f"{float(notional or 0):.0f} € → T212"
            if pkg_ready
            else "Erneut starten"
        ),
        "steps": steps,
        "next_de": (
            "Unten «€ → T212» tippen — einmal bestätigen, dann läuft das Zielportfolio"
            if pkg_ready
            else "bash tools/king_ops.sh r3-t212 · API-Key in R3 speichern"
        ),
        "bash_de": "bash tools/king_ops.sh r3-start",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
