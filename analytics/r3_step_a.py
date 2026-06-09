"""Schritt A — Fortschritt und Meilenstein-Prüfung (Ubuntu unsichtbar)."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

from analytics.r3_desktop_fusion import load_fusion_config


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _milestone(
    mid: str,
    label_de: str,
    *,
    done: bool,
    detail_de: str = "",
) -> Dict[str, Any]:
    return {
        "id": mid,
        "label_de": label_de,
        "done": done,
        "detail_de": detail_de,
    }


def evaluate_step_a(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_fusion_config(root)

    fusion_ok = (root / "analytics/r3_desktop_fusion.py").is_file()
    power_ok = len(cfg.get("power_actions") or []) >= 4
    updates_ok = bool(cfg.get("updates"))

    native_ok = (root / "analytics/r3_native_apps.py").is_file()
    try:
        from analytics.r3_native_apps import native_apps_ready

        native_ok = native_apps_ready(root)
    except Exception:
        native_ok = False

    build_ok = False
    build_detail = "—"
    try:
        from analytics.r3_build_kernel import load_kernel_config

        kcfg = load_kernel_config(root)
        ev = _load_json(root / "evidence/r3_build_kernel_latest.json")
        src = (root / "analytics/r3_build_kernel.py").read_text(encoding="utf-8", errors="ignore")
        bug_free = "resolve_ollama_role(root, task," not in src
        build_ok = bool(kcfg.get("tools")) and bug_free
        build_detail = str(ev.get("headline_de") or ev.get("reply_de") or "Bereit")[:120]
    except Exception as exc:
        build_detail = str(exc)[:80]

    h1 = _load_json(root / "control/h1_governance_status.json")
    h1_sealed = bool(h1.get("sealed"))
    h1_pct = h1.get("progress_pct") or h1.get("percent")
    h1_status = str(h1.get("status") or "MISSING")
    try:
        from analytics.r3_step_b import h1_migration_status, is_step_b_released

        step_b_released = is_step_b_released(root)
        h1_mig = h1_migration_status(root)
    except Exception:
        step_b_released = False
        h1_mig = {}
    pilot = _load_json(root / "evidence/r3_pilot_central_latest.json")
    pilot_live = int((pilot.get("counts") or {}).get("live") or 0) > 0
    launch = _load_json(root / "evidence/launch_progress_latest.json")
    launch_ready = bool(launch.get("public_launch_ready"))

    if h1_sealed:
        h1_detail = f"H1 sealed · Pilot live {pilot_live}"
    elif step_b_released:
        h1_detail = (
            f"H1 migriert parallel — {h1_pct or '?'}% · {h1_status}"
            + (" · Monitor läuft" if h1_mig.get("h1_monitor_running") else "")
        )
    else:
        h1_detail = f"H1 läuft {h1_pct or '?'}% · Pilot live {pilot_live}"

    milestones = [
        _milestone(
            "fusion_ui",
            "Control Center + Spotlight + Dock",
            done=fusion_ok,
            detail_de="Apple × Microsoft Fusion im Cockpit",
        ),
        _milestone(
            "power",
            "Power-Aktionen",
            done=power_ok,
            detail_de="Sperren · Abmelden · Neustart · Ausschalten",
        ),
        _milestone(
            "updates",
            "Update-Status",
            done=updates_ok,
            detail_de="Ersatz für update-notifier",
        ),
        _milestone(
            "native_apps",
            "Eigene Kern-Apps",
            done=native_ok,
            detail_de="Dateien · Terminal · Einstellungen in R3",
        ),
        _milestone(
            "build_kernel",
            "Bau-Werkstatt",
            done=build_ok,
            detail_de=build_detail,
        ),
        _milestone(
            "h1_pilot",
            "H1 + Pilot live",
            done=(
                (h1_sealed and (pilot_live or launch_ready))
                or (
                    step_b_released
                    and bool(h1_mig.get("h1_monitor_running"))
                    and int(h1_pct or 0) >= 80
                )
            ),
            detail_de=h1_detail,
        ),
    ]
    done_n = sum(1 for m in milestones if m.get("done"))
    total = len(milestones)
    pct = int(round(100 * done_n / total)) if total else 0
    code_done = sum(1 for m in milestones[:5] if m.get("done"))
    code_total = 5

    return {
        "phase": "A",
        "step_a_percent": pct,
        "step_a_code_percent": int(round(100 * code_done / code_total)) if code_total else 0,
        "step_a_done": done_n,
        "step_a_total": total,
        "step_a_code_complete": code_done >= code_total,
        "step_a_ready_for_b": code_done >= code_total and (h1_sealed or step_b_released),
        "step_b_released": step_b_released,
        "h1_migration": h1_mig,
        "milestones": milestones,
    }


def render_step_a_progress(root: Path, doc: Dict[str, Any] | None = None) -> str:
    from analytics.r3_icons import icon_span

    root = Path(root)
    data = doc or evaluate_step_a(root)
    pct = int(data.get("step_a_percent") or 0)
    code_pct = int(data.get("step_a_code_percent") or 0)
    rows = []
    for m in data.get("milestones") or []:
        if not isinstance(m, dict):
            continue
        mark = icon_span("check", cls="r3-ico r3-ico--sm") if m.get("done") else icon_span("circle", cls="r3-ico r3-ico--sm")
        cls = "done" if m.get("done") else "open"
        rows.append(
            f'<li class="r3-stepa-item {cls}"><span class="r3-stepa-mark">{mark}</span>'
            f'<span class="r3-stepa-label">{html.escape(str(m.get("label_de") or ""))}</span>'
            f'<span class="r3-stepa-detail">{html.escape(str(m.get("detail_de") or ""))}</span></li>'
        )
    if data.get("step_a_ready_for_b") and data.get("step_b_released"):
        mig = (data.get("h1_migration") or {}).get("phase_de") or "H1 parallel"
        b_note = f"Schritt B aktiv — {mig}"
    elif data.get("step_a_ready_for_b"):
        b_note = "Schritt B freigeschaltet (H1 sealed)"
    else:
        b_note = f"Code {code_pct}% — Schritt B oder H1-Seal"
    try:
        from analytics.r3_quality_scores import evaluate_quality_scores

        qs = evaluate_quality_scores(root)
        avg = qs.get("average_10")
        if avg is not None:
            b_note += f" · Qualität Ø {avg}/10"
    except Exception:
        pass
    return f"""
<div class="r3-stepa" id="r3-step-a-progress" aria-label="Schritt A Fortschritt">
  <div class="r3-stepa-head">
    <strong>Schritt A</strong>
    <span>{pct}% · {data.get('step_a_done')}/{data.get('step_a_total')}</span>
  </div>
  <div class="r3-stepa-bar" role="progressbar" aria-valuenow="{pct}" aria-valuemin="0" aria-valuemax="100">
    <div class="r3-stepa-fill" style="width:{pct}%"></div>
  </div>
  <ul class="r3-stepa-list">{''.join(rows)}</ul>
  <p class="r3-stepa-foot">{html.escape(b_note)}</p>
</div>"""


from analytics.r3_icons import R3_ICON_CSS as _STEPA_ICON_CSS  # noqa: E402

STEP_A_CSS = _STEPA_ICON_CSS + """
.r3-stepa {
  margin: 0 22px 14px; padding: 14px 16px; border-radius: 14px;
  background: #fff; border: 1px solid rgba(0,0,0,.08);
}
.r3-stepa-head { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 8px; }
.r3-stepa-bar { height: 8px; border-radius: 999px; background: #ececec; overflow: hidden; }
.r3-stepa-fill { height: 100%; background: #E95420; border-radius: 999px; transition: width .3s; }
.r3-stepa-list { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 6px; }
.r3-stepa-item { display: grid; grid-template-columns: 20px 1fr; gap: 8px; font-size: 12px; align-items: start; }
.r3-stepa-item.open .r3-stepa-label { color: #6e6e6e; }
.r3-stepa-detail { grid-column: 2; color: #8a8a8a; font-size: 11px; }
.r3-stepa-foot { margin: 10px 0 0; font-size: 11px; color: #8a8a8a; }
"""
