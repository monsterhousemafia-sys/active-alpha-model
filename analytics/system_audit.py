"""Umfassendes Systemaudit — Safety, R3, Serienreife, Linux (read-only + Evidence)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/system_audit_latest.json")
_CORE_TEST_FILES = (
    "tests/test_p0_safety_control_plane.py",
    "tests/test_series_readiness.py",
    "tests/test_r3_local_growth.py",
    "tests/test_r3_runtime_upgrade.py",
    "tests/test_r3_exec_mirror.py",
    "tests/test_linux_potential.py",
    "tests/test_stack_integrity.py",
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


def _py(root: Path) -> Path:
    p = root / ".venv/bin/python3"
    return p if p.is_file() else Path(sys.executable)


def _section(
    section_id: str,
    *,
    label_de: str,
    ok: bool,
    detail_de: str,
    data: Optional[Dict[str, Any]] = None,
    tier: str = "critical",
) -> Dict[str, Any]:
    return {
        "id": section_id,
        "label_de": label_de,
        "tier": tier,
        "ok": bool(ok),
        "detail_de": str(detail_de or "—")[:200],
        "data": data or {},
    }


def _audit_safety(root: Path) -> Dict[str, Any]:
    flags: Dict[str, Any] = {}
    try:
        import yaml

        raw = yaml.safe_load((root / "promotion_gate_config.yaml").read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            flags = raw
    except Exception:
        pass
    auto_keys = (
        "auto_research_enabled",
        "auto_promote_paper_enabled",
        "auto_promote_signal_enabled",
        "auto_execute_real_money_enabled",
    )
    bad = [k for k in auto_keys if flags.get(k) is True]
    ok = not bad
    return _section(
        "safety_flags",
        label_de="Safety-Automation",
        ok=ok,
        detail_de="alle aus" if ok else f"aktiv: {', '.join(bad)}",
        data={k: flags.get(k) for k in auto_keys},
    )


def _audit_governance(root: Path) -> Dict[str, Any]:
    try:
        from analytics.strategic_governance import resolve_governance_champion

        champion = resolve_governance_champion(root)
        lineage = _load_json(root / "control/champion_lineage_policy.json")
        ok = bool(champion) and str(lineage.get("status") or "") in (
            "M9_SYNCED",
            "SYNCED",
            "AUTHORITATIVE",
        )
        detail = f"{champion} · {lineage.get('status') or '—'}"
    except Exception as exc:
        ok = False
        detail = str(exc)[:100]
        champion = ""
        lineage = {}
    return _section(
        "governance",
        label_de="Champion-Governance",
        ok=ok,
        detail_de=detail,
        data={"champion": champion, "lineage_status": lineage.get("status")},
    )


def _audit_stack(root: Path, *, live: bool) -> Dict[str, Any]:
    cached = _load_json(root / "evidence/stack_integrity_latest.json")
    if live:
        try:
            from analytics.stack_integrity import build_integrity_report

            doc = build_integrity_report(root)
            ok = bool(doc.get("stack_ok"))
            detail = "live OK" if ok else ", ".join((doc.get("failures_de") or [])[:2])
            return _section("stack", label_de="Stack-Integrität", ok=ok, detail_de=detail, data=doc)
        except Exception as exc:
            pass
    ok = bool(cached.get("stack_ok"))
    detail = "OK" if ok else ", ".join((cached.get("failures_de") or [])[:2]) or "fehlt"
    return _section("stack", label_de="Stack-Integrität", ok=ok, detail_de=detail, data=cached)


def _audit_series(root: Path) -> Dict[str, Any]:
    try:
        from analytics.series_readiness import scan_series_readiness

        doc = scan_series_readiness(root, persist=True, force=True, fast=True)
    except Exception as exc:
        doc = _load_json(root / "evidence/series_readiness_latest.json")
        return _section(
            "series_readiness",
            label_de="Serienreife",
            ok=False,
            detail_de=str(exc)[:100],
            data=doc,
        )
    ok = bool(doc.get("series_ready"))
    detail = str(doc.get("headline_de") or "")
    return _section("series_readiness", label_de="Serienreife", ok=ok, detail_de=detail, data=doc)


def _audit_growth(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_local_growth import scan_local_growth

        stack_ok = bool(_load_json(root / "evidence/stack_integrity_latest.json").get("stack_ok"))
        doc = scan_local_growth(root, persist=True, force=True, fast=stack_ok)
    except Exception:
        doc = _load_json(root / "evidence/r3_local_growth_latest.json")
    pct = int(doc.get("growth_pct") or 0)
    ok = pct >= 100
    return _section(
        "r3_growth",
        label_de="R3 lokales Wachstum",
        ok=ok,
        detail_de=str(doc.get("headline_de") or f"{pct}%"),
        data=doc,
    )


def _audit_linux(root: Path) -> Dict[str, Any]:
    doc = _load_json(root / "evidence/linux_potential_latest.json")
    if not doc:
        try:
            from analytics.linux_potential import scan_linux_potential

            doc = scan_linux_potential(root, persist=True)
        except Exception:
            doc = {}
    pct = int(doc.get("potential_pct") or 0)
    open_dims = [d for d in (doc.get("dimensions") or []) if not d.get("ok")]
    return _section(
        "linux_potential",
        label_de="Linux-Potenzial",
        ok=pct >= 100,
        detail_de=str(doc.get("headline_de") or f"{pct}%"),
        data={"potential_pct": pct, "open_de": [d.get("label_de") for d in open_dims[:3]]},
        tier="warn",
    )


def _audit_runtime(root: Path) -> Dict[str, Any]:
    doc = _load_json(root / "evidence/r3_runtime_upgrade_latest.json")
    pending = doc.get("pending") or {}
    awaiting = pending.get("status") == "awaiting_confirmation"
    ok = not awaiting
    detail = (
        f"Update: {pending.get('label_de')}"
        if awaiting
        else f"Profil: {doc.get('applied_label_de') or doc.get('applied_profile_id')}"
    )
    return _section("runtime_upgrade", label_de="R3-Laufzeitprofil", ok=ok, detail_de=detail, data=doc)


def _audit_king_verify(root: Path) -> Dict[str, Any]:
    doc = _load_json(root / "evidence/king_verify_latest.json")
    ok = bool(doc.get("ok"))
    return _section(
        "king_verify",
        label_de="König verify",
        ok=ok,
        detail_de=str(doc.get("verified_at_utc") or "nicht gelaufen"),
        data=doc,
        tier="warn",
    )


def _audit_launch_scope(root: Path) -> Dict[str, Any]:
    doc = _load_json(root / "evidence/launch_readiness_latest.json")
    blockers = list(doc.get("remaining_de") or doc.get("blockers_de") or [])[:4]
    return _section(
        "launch_scope",
        label_de="Public-Launch (Info)",
        ok=True,
        detail_de=f"separat — {len(blockers)} offene Remote-Punkte" if blockers else "kein Remote-Blocker in Evidence",
        data={"blockers_de": blockers, "note_de": "Nicht Teil der lokalen Serienreife"},
        tier="info",
    )


def _run_core_tests(root: Path, *, timeout: int = 180) -> Dict[str, Any]:
    root = Path(root)
    paths = [str(root / p) for p in _CORE_TEST_FILES if (root / p).is_file()]
    if not paths:
        return _section("core_tests", label_de="Kern-Tests", ok=False, detail_de="keine Testdateien", tier="warn")
    proc = subprocess.run(
        [str(_py(root)), "-m", "pytest", *paths, "-q", "--tb=no"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    ok = proc.returncode == 0
    return _section(
        "core_tests",
        label_de="Kern-Tests (pytest)",
        ok=ok,
        detail_de=tail or f"rc={proc.returncode}",
        data={"rc": proc.returncode, "files": len(paths)},
        tier="warn",
    )


def run_system_audit(
    root: Path,
    *,
    persist: bool = True,
    live_stack: bool = False,
    run_tests: bool = False,
) -> Dict[str, Any]:
    """Umfassendes Audit — kritisch fail-closed, Warnungen und Info getrennt."""
    root = Path(root)
    sections: List[Dict[str, Any]] = [
        _audit_safety(root),
        _audit_governance(root),
        _audit_stack(root, live=live_stack),
        _audit_growth(root),
        _audit_series(root),
        _audit_runtime(root),
        _audit_linux(root),
        _audit_king_verify(root),
        _audit_launch_scope(root),
    ]
    if run_tests:
        sections.append(_run_core_tests(root))

    critical = [s for s in sections if s.get("tier") == "critical"]
    warnings = [s for s in sections if s.get("tier") == "warn"]
    crit_ok = sum(1 for s in critical if s.get("ok"))
    crit_total = len(critical) or 1
    warn_open = [s for s in warnings if not s.get("ok")]
    blockers = [s["label_de"] for s in critical if not s.get("ok")]

    audit_ok = crit_ok == crit_total
    if audit_ok and not warn_open:
        headline = f"Systemaudit PASS — {crit_ok}/{crit_total} kritisch"
    elif audit_ok:
        headline = f"Systemaudit PASS mit Warnungen — {', '.join(s['label_de'] for s in warn_open[:2])}"
    else:
        headline = f"Systemaudit FAIL — {', '.join(blockers[:2])}"

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "audit_ok": audit_ok,
        "critical_ok": crit_ok,
        "critical_total": crit_total,
        "warnings_open": len(warn_open),
        "sections": sections,
        "blockers_de": blockers,
        "warnings_de": [s["label_de"] for s in warn_open],
        "headline_de": headline,
        "next_de": (
            f"Beheben: {blockers[0]} — bash tools/king_ops.sh series-ready --repair"
            if blockers
            else (
                f"Optional: {warn_open[0]['label_de']}"
                if warn_open
                else "Betrieb unter http://127.0.0.1:17890/r3"
            )
        ),
        "operator_commands_de": [
            "bash tools/king_ops.sh system-audit",
            "bash tools/king_ops.sh system-audit --tests",
            "bash tools/king_ops.sh series-ready --repair",
        ],
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
