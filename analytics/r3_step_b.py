"""Phase B — OS-Stack, Meilensteine, H1-Migration parallel."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from analytics.r3_desktop_fusion import load_fusion_config

_CONFIG_REL = Path("control/r3_step_b.json")
_EVIDENCE_REL = Path("evidence/r3_step_b_latest.json")
_MASTER_PROMPT_REL = Path("control/r3_phase_b_master_prompt_de.md")


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


def load_step_b_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL)


def is_step_b_released(root: Path) -> bool:
    return bool(load_step_b_config(root).get("released"))


def is_phase_b_active(root: Path) -> bool:
    cfg = load_fusion_config(root)
    bcfg = load_step_b_config(root)
    return (
        str(cfg.get("phase") or "A").upper() == "B"
        and bool(bcfg.get("released"))
        and bool(bcfg.get("phase_active", True))
    )


def _milestone(mid: str, label_de: str, *, done: bool, detail_de: str = "") -> Dict[str, Any]:
    return {
        "id": mid,
        "label_de": label_de,
        "done": done,
        "detail_de": detail_de,
    }


def _eval_phase_b_milestones(root: Path, h1m: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = Path(root)
    session_ok = False
    session_detail = "Session-Panel in System Plane"
    try:
        from analytics.r3_system_plane import session_panel

        doc = session_panel(root)
        session_ok = bool(doc.get("ok"))
        session_detail = str(doc.get("headline_de") or session_detail)[:120]
    except Exception:
        pass

    login_ok = (root / "control/r3_login_shell.json").is_file()
    login_detail = "Login-Screen — Phase B Meilenstein 1" if not login_ok else "R3 Login konfiguriert"

    native_ok = False
    native_detail = "—"
    try:
        from analytics.r3_native_apps import native_apps_ready

        native_ok = native_apps_ready(root)
        native_detail = "Dateien · Terminal · Einstellungen · Plane"
    except Exception:
        native_detail = "Native-Apps prüfen"

    wm_src = (root / "analytics/r3_native_apps.py").read_text(encoding="utf-8", errors="ignore")
    wm_snap = "snapped-left" in wm_src and "r3NativeShell" in wm_src
    wm_spaces = "r3Spaces" in wm_src or "spaces" in wm_src.lower() and "mission" in wm_src.lower()
    wm_done = wm_snap and wm_spaces
    wm_detail = (
        "Snap · Drag · Resize · Multi-Fenster"
        if wm_snap and not wm_spaces
        else ("Snap + Spaces aktiv" if wm_done else "WM ausstehend")
    )

    packages_ok = False
    packages_detail = "APT-Panel · Schritt B"
    try:
        src = wm_src
        packages_ok = "updates_panel" in src and "apt" in src.lower()
        if packages_ok:
            packages_detail = "R3 Updates-Panel · apt list"
    except Exception:
        pass

    cfg = load_step_b_config(root)
    h1_done = bool(h1m.get("h1_sealed"))
    h1_partial = bool(h1m.get("h1_migration_stable")) and not h1_done
    h1_detail = (
        str(h1m.get("phase_de") or "H1")
        if not h1_done
        else "H1 sealed — in R3 integriert"
    )
    if not h1_done and cfg.get("migration_sufficient_pre_seal"):
        seal_when = str(cfg.get("seal_deferred_until") or "Montag")
        h1_detail = f"Migration genug — Seal {seal_when} (Trading) · {h1_detail}"[:160]

    return [
        _milestone(
            "login_session",
            "Login + Session-Manager",
            done=login_ok and session_ok,
            detail_de=f"{login_detail} · {session_detail}"[:140],
        ),
        _milestone(
            "native_suite",
            "Native App-Suite",
            done=native_ok,
            detail_de=native_detail,
        ),
        _milestone(
            "wm_spaces",
            "Fenster-Management",
            done=wm_done,
            detail_de=wm_detail,
        ),
        _milestone(
            "r3_packages",
            "Paket- und Update-Schicht",
            done=packages_ok,
            detail_de=packages_detail,
        ),
        _milestone(
            "h1_integrated",
            "H1 parallel integriert",
            done=h1_done,
            detail_de=h1_detail + (" · stabil" if h1_partial else ""),
        ),
    ]


def _h1_monitor_running(root: Path) -> bool:
    try:
        from analytics.h1_migration_guard import h1_process_inventory

        return int(h1_process_inventory(Path(root)).get("monitor_count") or 0) > 0
    except Exception:
        return False


def _h1_backtest_running(root: Path) -> bool:
    try:
        from analytics.h1_migration_guard import h1_process_inventory

        return int(h1_process_inventory(Path(root)).get("backtest_count") or 0) > 0
    except Exception:
        return False


def h1_migration_status(root: Path) -> Dict[str, Any]:
    """H1 darf parallel zu Phase B laufen und beim Seal einhaken."""
    root = Path(root)
    cfg = load_step_b_config(root)
    parallel = bool(cfg.get("h1_migration_parallel"))
    try:
        from analytics.h1_governance_status import sync_h1_governance_status

        h1 = sync_h1_governance_status(root, write_readiness=False)
    except Exception:
        h1 = _load_json(root / "control/h1_governance_status.json")

    sealed = bool(h1.get("sealed"))
    status = str(h1.get("status") or "MISSING")
    pct = int(h1.get("progress_pct") or 0)
    monitor = _h1_monitor_running(root)
    backtest = _h1_backtest_running(root)

    if sealed:
        phase_de = "H1 sealed — in R3 integriert"
        migrates = True
    elif parallel and is_step_b_released(root):
        phase_de = f"H1 migriert parallel ({pct}% · {status})"
        migrates = True
    else:
        phase_de = f"H1 {status} ({pct}%)"
        migrates = False

    on_seal_de = (
        "Automatisch: governance sync, Evaluate, Aktien-Gate, Launch-Readiness"
        if parallel
        else "Manuell: ai_kernel h1-finish"
    )

    health: Dict[str, Any] = {}
    stable = False
    try:
        from analytics.h1_migration_guard import h1_process_inventory

        inv = h1_process_inventory(root)
        health = {
            "monitor_count": inv.get("monitor_count"),
            "backtest_count": inv.get("backtest_count"),
            "duplicate_risk": inv.get("duplicate_risk"),
        }
        stable = (
            status in ("RUNNING", "COMPLETE")
            and backtest
            and int(inv.get("monitor_count") or 0) == 1
            and int(inv.get("starter_count") or 0) == 0
        ) or sealed
    except Exception:
        pass

    return {
        "parallel_with_step_b": parallel and is_step_b_released(root) and not sealed,
        "migrates_on_seal": migrates or sealed,
        "h1_sealed": sealed,
        "h1_status": status,
        "h1_progress_pct": pct,
        "h1_monitor_running": monitor,
        "h1_backtest_running": backtest,
        "h1_migration_stable": stable,
        "h1_process_health": health,
        "phase_de": phase_de if stable or sealed else f"{phase_de} · Stabilisierung",
        "on_seal_de": on_seal_de,
        "note_de": str(cfg.get("h1_migration_note_de") or ""),
    }


def load_phase_b_master_prompt_template(root: Path) -> str:
    """Statischer Phase-B-Masterprompt für Ollama."""
    path = Path(root) / _MASTER_PROMPT_REL
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return ""


def build_phase_b_ollama_prompt(root: Path) -> str:
    """Masterprompt + Live-Stand für Ollama system message."""
    root = Path(root)
    base = load_phase_b_master_prompt_template(root)
    if not base:
        return ""
    if not is_phase_b_active(root):
        return ""
    doc = evaluate_step_b(root, persist=False)
    lines = [
        base,
        "",
        "## Live-Stand (Evidence)",
        f"- {doc.get('headline_de')}",
        f"- Fortschritt: {doc.get('step_b_done')}/{doc.get('step_b_total')} Meilensteine ({doc.get('step_b_percent')}%)",
        f"- Nächster Fokus: {doc.get('step_b_next_de')}",
    ]
    h1 = doc.get("h1_migration") or {}
    lines.append(f"- H1: {h1.get('phase_de')} · sealed={h1.get('h1_sealed')} · stabil={h1.get('h1_migration_stable')}")
    lines.append("- Meilensteine:")
    for m in doc.get("milestones") or []:
        if not isinstance(m, dict):
            continue
        mark = "✓" if m.get("done") else "○"
        lines.append(f"  {mark} {m.get('label_de')} — {m.get('detail_de', '')}"[:120])
    lines.append("")
    lines.append("Einleitung: Bei Start oder „Phase B“ — Status oben nennen, dann nächsten Meilenstein angehen.")
    return "\n".join(lines)


def evaluate_step_b(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_step_b_config(root)
    fusion = load_fusion_config(root)
    released = bool(cfg.get("released"))
    phase_active = is_phase_b_active(root)
    h1m = h1_migration_status(root)
    milestones = _eval_phase_b_milestones(root, h1m)
    done_n = sum(1 for m in milestones if m.get("done"))
    total = len(milestones)
    pct = int(round(100 * done_n / total)) if total else 0

    try:
        from analytics.r3_step_a import evaluate_step_a

        step_a = evaluate_step_a(root)
    except Exception:
        step_a = {}

    next_open = next((m for m in milestones if not m.get("done")), None)
    next_de = str(next_open.get("label_de") or "—") if next_open else "Phase B Meilensteine vollständig"

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "phase": "B",
        "phase_active": phase_active,
        "released": released,
        "released_by_de": cfg.get("released_by_de"),
        "released_at_utc": cfg.get("released_at_utc"),
        "phase_started_at_utc": cfg.get("phase_started_at_utc"),
        "phase_title_de": cfg.get("phase_title_de") or fusion.get("phase_b_title_de") or "Phase B",
        "step_b_active": released and bool(step_a.get("step_a_ready_for_b")),
        "step_b_percent": pct,
        "step_b_done": done_n,
        "step_b_total": total,
        "step_b_next_de": next_de,
        "step_a_ready_for_b": bool(step_a.get("step_a_ready_for_b")),
        "step_a_percent": step_a.get("step_a_percent"),
        "h1_migration": h1m,
        "milestones": milestones,
        "milestones_de": [str(m) for m in (cfg.get("milestones_de") or []) if m],
        "headline_de": (
            f"Phase B · {pct}% — {next_de}"
            if phase_active
            else (
                f"Schritt B aktiv · {h1m.get('phase_de')}"
                if released
                else "Schritt B wartet auf Freigabe"
            )
        ),
        "updated_at_utc": _utc_now(),
    }

    if persist:
        path = root / _EVIDENCE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return doc


def render_step_b_progress(root: Path, doc: Dict[str, Any] | None = None) -> str:
    from analytics.r3_icons import icon_span

    root = Path(root)
    data = doc or evaluate_step_b(root, persist=False)
    pct = int(data.get("step_b_percent") or 0)
    rows = []
    for m in data.get("milestones") or []:
        if not isinstance(m, dict):
            continue
        mark = (
            icon_span("check", cls="r3-ico r3-ico--sm")
            if m.get("done")
            else icon_span("circle", cls="r3-ico r3-ico--sm")
        )
        cls = "done" if m.get("done") else "open"
        rows.append(
            f'<li class="r3-stepb-item {cls}"><span class="r3-stepb-mark">{mark}</span>'
            f'<span class="r3-stepb-label">{html.escape(str(m.get("label_de") or ""))}</span>'
            f'<span class="r3-stepb-detail">{html.escape(str(m.get("detail_de") or ""))}</span></li>'
        )
    h1m = data.get("h1_migration") or {}
    foot = f"Nächster Meilenstein: {data.get('step_b_next_de') or '—'}"
    if h1m.get("phase_de"):
        foot += f" · {h1m.get('phase_de')}"
    sa = data.get("step_a_percent")
    if sa is not None:
        foot += f" · Schritt A {sa}% abgeschlossen"

    return f"""
<div class="r3-stepb" id="r3-step-b-progress" aria-label="Phase B Fortschritt">
  <div class="r3-stepb-head">
    <strong>Phase B</strong>
    <span>{pct}% · {data.get('step_b_done')}/{data.get('step_b_total')}</span>
  </div>
  <div class="r3-stepb-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100">
    <div class="r3-stepb-fill" style="width:{pct}%"></div>
  </div>
  <p class="r3-stepb-sub">{html.escape(str(data.get('phase_title_de') or ''))}</p>
  <ul class="r3-stepb-list">{''.join(rows)}</ul>
  <p class="r3-stepb-foot">{html.escape(foot)}</p>
</div>"""


from analytics.r3_icons import R3_ICON_CSS as _STEPB_ICON_CSS  # noqa: E402

STEP_B_CSS = _STEPB_ICON_CSS + """
.r3-stepb {
  margin: 0 22px 14px; padding: 14px 16px; border-radius: 14px;
  background: linear-gradient(180deg, #fff9f6, #fff);
  border: 1px solid rgba(233,84,32,.22);
}
.r3-stepb-head { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 8px; }
.r3-stepb-sub { margin: 0 0 10px; font-size: 11px; color: #8a8a8a; }
.r3-stepb-bar { height: 8px; border-radius: 999px; background: #ececec; overflow: hidden; }
.r3-stepb-fill { height: 100%; background: #E95420; border-radius: 999px; transition: width .3s; }
.r3-stepb-list { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 6px; }
.r3-stepb-item { display: grid; grid-template-columns: 20px 1fr; gap: 8px; font-size: 12px; align-items: start; }
.r3-stepb-item.open .r3-stepb-label { color: #6e6e6e; }
.r3-stepb-detail { grid-column: 2; color: #8a8a8a; font-size: 11px; }
.r3-stepb-foot { margin: 10px 0 0; font-size: 11px; color: #8a8a8a; }
"""
