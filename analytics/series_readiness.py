"""Serienreife — lokales R3-Produkt fail-closed prüfen und Evidence schreiben."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/series_readiness_policy.json")
_EVIDENCE_REL = Path("evidence/series_readiness_latest.json")
_SCAN_COOLDOWN_SEC = 120.0

_SAFETY_KEYS = (
    "auto_research_enabled",
    "auto_promote_paper_enabled",
    "auto_promote_signal_enabled",
    "auto_execute_real_money_enabled",
)


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


def load_series_readiness_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _evidence_fresh(path: Path, max_age_sec: float = _SCAN_COOLDOWN_SEC) -> bool:
    if not path.is_file():
        return False
    try:
        return (time.time() - path.stat().st_mtime) < float(max_age_sec)
    except OSError:
        return False


def _load_safety_flags(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg_path = root / "promotion_gate_config.yaml"
    flags: Dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            import yaml

            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                flags = {k: raw.get(k) for k in _SAFETY_KEYS}
        except Exception:
            pass
    return flags


def _gate(
    gate_id: str,
    *,
    label_de: str,
    ok: bool,
    detail_de: str,
    tier: str = "critical",
) -> Dict[str, Any]:
    return {
        "id": gate_id,
        "label_de": label_de,
        "tier": tier,
        "ok": bool(ok),
        "detail_de": str(detail_de or "—")[:160],
    }


def _check_safety_flags(root: Path) -> Dict[str, Any]:
    flags = _load_safety_flags(root)
    bad = [k for k in _SAFETY_KEYS if flags.get(k) is True]
    ok = not bad and bool(flags)
    detail = "alle Auto-Flags aus" if ok else f"aktiv: {', '.join(bad)}"
    return _gate("safety_flags", label_de="Safety-Flags", ok=ok, detail_de=detail)


def _check_governance_locked(root: Path) -> Dict[str, Any]:
    root = Path(root)
    ok = False
    detail = "Governance prüfen"
    try:
        from analytics.strategic_governance import resolve_governance_champion

        champion = str(resolve_governance_champion(root) or "").strip()
        lineage = _load_json(root / "control/champion_lineage_policy.json")
        ops = _load_json(root / "control/operational_champion_status.json")
        auto_promo = str(ops.get("auto_promotion") or "").upper()
        lineage_ok = str(lineage.get("status") or "") in ("M9_SYNCED", "SYNCED", "AUTHORITATIVE")
        ok = bool(champion) and lineage_ok and auto_promo in ("", "DISABLED", "OFF", "FALSE")
        detail = f"{champion} · auto_promotion={auto_promo or 'DISABLED'}"
    except Exception as exc:
        detail = str(exc)[:80]
    return _gate("governance_locked", label_de="Governance gesperrt", ok=ok, detail_de=detail)


def _check_local_runtime(root: Path) -> Dict[str, Any]:
    rt = _load_json(Path(root) / "control/alpha_model_local_runtime.json")
    ok = rt.get("local_only") is True and str(rt.get("hub_bind") or "") == "127.0.0.1"
    detail = str(rt.get("hub_url") or "127.0.0.1:17890")
    return _gate("local_runtime", label_de="Lokal-first Runtime", ok=ok, detail_de=detail)


def _check_stack_integrity(root: Path, *, fast: bool) -> Dict[str, Any]:
    root = Path(root)
    stack = _load_json(root / "evidence/stack_integrity_latest.json")
    if fast and stack:
        ok = bool(stack.get("stack_ok"))
        detail = "OK" if ok else ", ".join((stack.get("failures_de") or [])[:2]) or "Stack prüfen"
        return _gate("stack_integrity", label_de="Stack-Integrität", ok=ok, detail_de=detail)
    try:
        from analytics.stack_integrity import build_integrity_report

        doc = build_integrity_report(root)
        ok = bool(doc.get("stack_ok"))
        detail = "OK" if ok else ", ".join((doc.get("failures_de") or [])[:2]) or "Stack prüfen"
    except Exception as exc:
        ok = bool(stack.get("stack_ok"))
        detail = str(exc)[:80] if not ok else "OK (cache)"
    return _gate("stack_integrity", label_de="Stack-Integrität", ok=ok, detail_de=detail)


def _stack_ok(root: Path) -> bool:
    return bool(_load_json(Path(root) / "evidence/stack_integrity_latest.json").get("stack_ok"))


def _check_r3_growth(root: Path, *, min_pct: int, fast: bool) -> Dict[str, Any]:
    root = Path(root)
    use_fast = bool(fast) or _stack_ok(root)
    try:
        from analytics.r3_local_growth import scan_local_growth

        doc = scan_local_growth(root, persist=True, force=True, fast=use_fast)
    except Exception:
        doc = _load_json(root / "evidence/r3_local_growth_latest.json")
    pct = int(doc.get("growth_pct") or 0)
    ms_ok = int(doc.get("milestones_ok") or 0)
    ms_tot = int(doc.get("milestones_total") or 0)
    ok = pct >= int(min_pct)
    detail = f"{pct}% · {ms_ok}/{ms_tot} Meilensteine"
    return _gate("r3_growth", label_de="R3 lokales Wachstum", ok=ok, detail_de=detail)


def _check_mirror_operational(root: Path) -> Dict[str, Any]:
    root = Path(root)
    stack = _load_json(root / "evidence/stack_integrity_latest.json")
    r3 = stack.get("r3") or {}
    if bool(stack.get("stack_ok")) and bool(r3.get("mirror_api_ok") or r3.get("mirror_state_ok")):
        return _gate("mirror_operational", label_de="Mirror operativ", ok=True, detail_de="Stack + Mirror OK")
    try:
        from analytics.r3_local_growth import verify_local_operational

        doc = verify_local_operational(root)
        ok = bool(doc.get("ok"))
        missing = list(doc.get("missing_de") or [])
        detail = "Kern lokal bereit" if ok else f"fehlt: {missing[0]}" if missing else "prüfen"
    except Exception as exc:
        ok = False
        detail = str(exc)[:80]
    return _gate("mirror_operational", label_de="Mirror operativ", ok=ok, detail_de=detail)


def _check_dry_run_guard(root: Path) -> Dict[str, Any]:
    flags = _load_safety_flags(root)
    no_auto_money = flags.get("auto_execute_real_money_enabled") is False
    dry = os.environ.get("AA_EXECUTION_DRY_RUN", "").strip() in ("1", "true", "yes")
    no_live = os.environ.get("AA_NO_LIVE_ORDER_SUBMISSION", "").strip() in ("1", "true", "yes")
    verify = _load_json(Path(root) / "evidence/king_verify_latest.json")
    ok = bool(no_auto_money) and (dry or no_live or bool(verify.get("ok")))
    detail = []
    if no_auto_money:
        detail.append("auto_execute=false")
    if dry:
        detail.append("AA_EXECUTION_DRY_RUN=1")
    if no_live:
        detail.append("AA_NO_LIVE_ORDER_SUBMISSION=1")
    if verify.get("ok"):
        detail.append("king_verify OK")
    if not detail:
        detail.append("promotion_gate + verify prüfen")
    return _gate("dry_run_guard", label_de="Ausführungsschutz", ok=ok, detail_de=" · ".join(detail))


def _check_linux_potential(root: Path, *, min_warn_pct: int) -> Dict[str, Any]:
    doc = _load_json(Path(root) / "evidence/linux_potential_latest.json")
    if not doc:
        try:
            from analytics.linux_potential import scan_linux_potential

            doc = scan_linux_potential(root, persist=False)
        except Exception:
            doc = {}
    pct = int(doc.get("potential_pct") or 0)
    ok = pct >= int(min_warn_pct)
    detail = str(doc.get("headline_de") or f"{pct}%")[:100]
    return _gate("linux_potential", label_de="Linux-Potenzial", ok=ok, detail_de=detail, tier="warn")


def _check_pending_upgrade(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / "evidence/r3_runtime_upgrade_latest.json")
    pending = doc.get("pending") or {}
    awaiting = pending.get("status") == "awaiting_confirmation"
    ok = not awaiting
    detail = (
        f"bereit: {pending.get('label_de') or pending.get('proposal_id')}"
        if awaiting
        else f"Profil: {doc.get('applied_label_de') or doc.get('applied_profile_id') or '—'}"
    )
    return _gate("pending_upgrade", label_de="R3-Upgrade offen", ok=ok, detail_de=detail, tier="warn")


def _check_king_verify(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / "evidence/king_verify_latest.json")
    ok = bool(doc.get("ok"))
    detail = str(doc.get("verified_at_utc") or "noch nicht gelaufen")[:40]
    return _gate("king_verify", label_de="König verify", ok=ok, detail_de=detail, tier="warn")


def scan_series_readiness(
    root: Path,
    *,
    persist: bool = True,
    force: bool = False,
    fast: bool = True,
) -> Dict[str, Any]:
    """Serienreife-Gates sammeln — kritisch fail-closed, Warnungen separat."""
    root = Path(root)
    policy = load_series_readiness_policy(root)
    evidence_path = root / _EVIDENCE_REL
    if not force and persist and _evidence_fresh(evidence_path):
        cached = _load_json(evidence_path)
        if cached.get("gates"):
            return cached

    min_growth = int(policy.get("min_growth_pct") or 100)
    min_linux = int(policy.get("min_linux_potential_pct_warn") or 100)

    gates: List[Dict[str, Any]] = [
        _check_safety_flags(root),
        _check_governance_locked(root),
        _check_local_runtime(root),
        _check_stack_integrity(root, fast=fast),
        _check_r3_growth(root, min_pct=min_growth, fast=fast),
        _check_mirror_operational(root),
        _check_dry_run_guard(root),
        _check_linux_potential(root, min_warn_pct=min_linux),
        _check_pending_upgrade(root),
        _check_king_verify(root),
    ]

    critical_ids = set(policy.get("critical_gate_ids") or [])
    warn_ids = set(policy.get("warn_gate_ids") or [])
    critical = [g for g in gates if g["id"] in critical_ids or g.get("tier") == "critical"]
    warnings = [g for g in gates if g["id"] in warn_ids or g.get("tier") == "warn"]

    crit_ok = sum(1 for g in critical if g.get("ok"))
    crit_total = len(critical) or 1
    warn_open = [g for g in warnings if not g.get("ok")]

    readiness_pct = int(round(100 * crit_ok / crit_total))
    series_ready = crit_ok == crit_total
    blockers = [g["label_de"] for g in critical if not g.get("ok")]
    warn_labels = [g["label_de"] for g in warn_open]

    if series_ready and not warn_open:
        headline = f"Serienreife {readiness_pct}% — lokales R3 betriebsbereit"
    elif series_ready:
        headline = f"Serienreife {readiness_pct}% — Warnungen: {', '.join(warn_labels[:2])}"
    else:
        headline = f"Serienreife {readiness_pct}% — Blocker: {', '.join(blockers[:2])}"

    next_de = "Betrieb unter http://127.0.0.1:17890/r3"
    if blockers:
        next_de = f"Beheben: {blockers[0]} — bash tools/king_ops.sh series-ready --repair"
    elif warn_open:
        cmds = list(policy.get("operator_commands_de") or ["bash tools/king_ops.sh verify"])
        next_de = f"Optional: {warn_labels[0]} — {cmds[0] if cmds else 'bash tools/king_ops.sh verify'}"

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "series_ready": series_ready,
        "readiness_pct": readiness_pct,
        "critical_ok": crit_ok,
        "critical_total": crit_total,
        "warnings_open": len(warn_open),
        "gates": gates,
        "blockers_de": blockers,
        "warnings_de": warn_labels,
        "headline_de": headline,
        "next_de": next_de,
        "confirmation_de": headline,
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "local_surface_de": "http://127.0.0.1:17890/r3",
        "scope_de": "Lokales R3-Produkt — kein Public-Launch-Gate",
    }

    if persist:
        atomic_write_json(evidence_path, doc)
    return doc


def apply_series_readiness_repair(root: Path) -> Dict[str, Any]:
    """Sichere Reparatur-Schritte für Serienreife (kein Champion, keine Orders)."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    def _step(step_id: str, label_de: str, fn) -> None:
        try:
            result = fn()
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else bool(result)
            steps.append({"id": step_id, "label_de": label_de, "ok": ok, "detail": result})
        except Exception as exc:
            steps.append({"id": step_id, "label_de": label_de, "ok": False, "error_de": str(exc)[:120]})

    _step(
        "hub",
        "Hub sicherstellen",
        lambda: {
            "ok": True,
            "port": __import__("analytics.hub_runtime", fromlist=["ensure_running"]).ensure_running(root),
        },
    )
    _step(
        "r3_local",
        "Lokal-first Runtime",
        lambda: __import__(
            "analytics.r3_local_first", fromlist=["apply_r3_local_first"]
        ).apply_r3_local_first(root),
    )
    _step(
        "r3_align",
        "R3 Abgleich",
        lambda: __import__("analytics.r3_runtime_upgrade", fromlist=["align_r3_surface"]).align_r3_surface(
            root, scan_upgrades=True, warm_cache=True, sync_flow=False, persist=True
        ),
    )
    _step(
        "stack",
        "Stack prüfen",
        lambda: __import__("analytics.stack_integrity", fromlist=["verify_or_repair"]).verify_or_repair(
            root, auto_repair=True, persist=True
        ),
    )
    _step(
        "ollama",
        "König 32B lokal (Ollama)",
        lambda: __import__(
            "analytics.local_llm_bridge", fromlist=["ensure_ollama_running"]
        ).ensure_ollama_running(root),
    )
    _step(
        "growth",
        "R3 Wachstum neu scannen",
        lambda: __import__(
            "analytics.r3_local_growth", fromlist=["scan_local_growth"]
        ).scan_local_growth(
            root,
            persist=True,
            force=True,
            fast=bool(_load_json(root / "evidence/stack_integrity_latest.json").get("stack_ok")),
        ),
    )

    checklist: Dict[str, Any] = {}
    try:
        checklist = __import__(
            "analytics.r3_operational_checklist", fromlist=["scan_operational_checklist"]
        ).scan_operational_checklist(root, persist=True)
    except Exception as exc:
        checklist = {"ok": False, "error_de": str(exc)[:120]}

    _step(
        "operator_readiness",
        "R3 Operator-Readiness (100 %)",
        lambda: __import__(
            "analytics.r3_operator_readiness", fromlist=["sync_r3_operator_readiness"]
        ).sync_r3_operator_readiness(root, persist=True, repair=True),
    )

    _step(
        "community_stealth",
        "Community-Stealth Autostart",
        lambda: __import__(
            "analytics.r3_community_stealth", fromlist=["install_community_stealth"]
        ).install_community_stealth(root, persist=True),
    )

    scan = scan_series_readiness(root, persist=True, force=True, fast=True)
    ok_n = sum(1 for s in steps if s.get("ok"))
    series_ready = bool(scan.get("series_ready"))
    operator = _load_json(root / Path("evidence/r3_operator_readiness_latest.json"))
    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok_n == len(steps) and series_ready,
        "steps": steps,
        "steps_ok": ok_n,
        "steps_total": len(steps),
        "checklist_ok": bool(checklist.get("checklist_ok")),
        "checklist_ref": "evidence/r3_operational_checklist_latest.json",
        "series_ready": series_ready,
        "readiness_pct": scan.get("readiness_pct"),
        "operator_readiness_pct": operator.get("operational_pct"),
        "operator_readiness_ok": bool(operator.get("operational_ok")),
        "operator_readiness_ref": "evidence/r3_operator_readiness_latest.json",
        "headline_de": scan.get("headline_de"),
        "next_de": scan.get("next_de"),
    }
