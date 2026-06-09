"""GUI preview harness — backend + offscreen Qt smoke for Live-Dashboard."""
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_EVIDENCE_JSON = Path("evidence/gui_preview_latest.json")
_EVIDENCE_TXT = Path("evidence/gui_preview_latest.txt")
_SCREENSHOT = Path("evidence/gui_preview_screenshot.png")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(step_id: str, label_de: str, ok: bool, *, detail_de: str = "", **extra: Any) -> Dict[str, Any]:
    return {
        "id": step_id,
        "label_de": label_de,
        "pass": ok,
        "detail_de": (detail_de or ("OK" if ok else "Fehler"))[:400],
        **extra,
    }


def _run_step(steps: List[Dict[str, Any]], step_id: str, label_de: str, fn: Callable[[], str]) -> None:
    try:
        detail = fn() or "OK"
        steps.append(_step(step_id, label_de, True, detail_de=detail))
    except Exception as exc:
        steps.append(
            _step(
                step_id,
                label_de,
                False,
                detail_de=str(exc)[:300],
                error_type=type(exc).__name__,
                traceback=traceback.format_exc()[-600:],
            )
        )


def _run_step_partial(
    steps: List[Dict[str, Any]],
    step_id: str,
    label_de: str,
    fn: Callable[[], tuple[bool, str]],
) -> None:
    try:
        ok, detail = fn()
        steps.append(_step(step_id, label_de, ok, detail_de=detail or "—", partial=not ok))
    except Exception as exc:
        steps.append(
            _step(
                step_id,
                label_de,
                False,
                detail_de=str(exc)[:300],
                error_type=type(exc).__name__,
                traceback=traceback.format_exc()[-600:],
            )
        )


def ensure_h1_evaluated(root: Path) -> Dict[str, Any]:
    """On COMPLETE: evaluate + seal; sync governance for Preview/Dashboard."""
    root = Path(root)
    from analytics.h1_governance_status import sync_h1_governance_status
    from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

    bt = h1_backtest_status(root)
    st = str(bt.get("status") or "MISSING")
    out: Dict[str, Any] = {
        "status": st,
        "run_dir": bt.get("run_dir"),
        "detail_de": bt.get("detail_de"),
        "sealed": is_h1_backtest_sealed(root),
    }
    ev_path = root / "evidence/daily_alpha_h1_evaluation_latest.json"
    if st == "COMPLETE":
        if not ev_path.is_file() or not out["sealed"]:
            from tools.run_daily_alpha_h1_pipeline import _evaluate

            out["evaluation"] = _evaluate(root, seal=True)
            out["sealed"] = is_h1_backtest_sealed(root)
        else:
            try:
                out["evaluation"] = json.loads(ev_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                out["evaluation"] = {}
    elif ev_path.is_file():
        try:
            out["evaluation"] = json.loads(ev_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            out["evaluation"] = {}
    out["governance"] = sync_h1_governance_status(root)
    try:
        from analytics.closed_loop_score import refresh_closed_loop_score

        refresh_closed_loop_score(root)
    except Exception:
        pass
    return out


def run_backend_preview(
    root: Path,
    *,
    snap: Optional[Dict[str, Any]] = None,
    allow_snapshot_refresh: bool = True,
) -> List[Dict[str, Any]]:
    """Data-layer checks — no Qt window required."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []

    def circle() -> str:
        from analytics.closed_loop_score import load_closed_loop_score

        doc = load_closed_loop_score(root)
        assert doc.get("headline_de"), "headline fehlt"
        assert len(doc.get("stages") or []) == 6
        return f"{doc['headline_de']} · {doc.get('bottleneck_de') or '—'}"

    _run_step(steps, "circle_score", "Kreis-Score (Superprogramm)", circle)

    def cockpit() -> tuple[bool, str]:
        from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

        doc = load_trading_day_cockpit_doc(root)
        if not doc and (root / "evidence/trading_day_latest.txt").is_file():
            lines = [
                ln for ln in (root / "evidence/trading_day_latest.txt").read_text(encoding="utf-8").splitlines() if ln.strip()
            ]
            if lines:
                return True, f"{len(lines)} Zeilen (TXT)"
        lines = (doc.get("cockpit_lines_de") or []) if doc else []
        if lines:
            return True, f"{doc.get('next_step_de') or '—'} · {len(lines)} Zeilen"
        return False, "fehlt — einmal: ai_kernel trading-day"

    _run_step_partial(steps, "trading_day_cockpit", "Tages-Cockpit Evidence", cockpit)

    def operator() -> str:
        from analytics.operator_visibility import build_visibility_snapshot

        vis = build_visibility_snapshot(root)
        assert vis.get("headline_de")
        circle_hl = vis.get("circle_headline_de") or ""
        return f"{vis['headline_de'][:120]} · Timer: {len(vis.get('scheduled_timers') or [])}"

    _run_step(steps, "operator_visibility", "Auto-Operator Sichtbarkeit", operator)

    def public_status() -> str:
        from analytics.operator_public_status import build_public_status

        doc = build_public_status(root)
        assert doc.get("can_do_de")
        circle = doc.get("circle_score") or {}
        return f"Kann {len(doc['can_do_de'])} · Kreis: {circle.get('headline_de') or '—'}"

    _run_step(steps, "public_operator", "Öffentlicher Operator-Status", public_status)

    def learning() -> tuple[bool, str]:
        path = root / "evidence/public_learning_report_latest.json"
        if not path.is_file():
            return False, "fehlt — einmal: ai_kernel learn (Timer 22:20)"
        doc = json.loads(path.read_text(encoding="utf-8"))
        q = doc.get("quality_score") or {}
        evo = doc.get("evolution") or {}
        return True, f"Note {q.get('grade') or '—'} · {evo.get('stage_id') or '—'} → {evo.get('next_stage_id') or '—'}"

    _run_step_partial(steps, "learning_report", "Lernreport", learning)

    def h1_backtest() -> tuple[bool, str]:
        from analytics.h1_governance_status import estimate_h1_progress_pct, sync_h1_governance_status
        from analytics.live_profile_governance import h1_backtest_status

        raw = h1_backtest_status(root)
        st = str(raw.get("status") or "MISSING")
        if st == "COMPLETE":
            ensure_h1_evaluated(root)
        gov = sync_h1_governance_status(root)
        pct = int(gov.get("progress_pct") or estimate_h1_progress_pct(root, raw))
        detail = str(gov.get("banner_de") or f"{st} ~{pct}%")
        if raw.get("detail_de") and st == "RUNNING":
            detail = f"{detail} · {raw['detail_de']}"
        if st in ("FAILED", "ZOMBIE", "MISSING"):
            return False, detail
        if gov.get("sealed"):
            return True, detail
        return st in ("COMPLETE", "RUNNING"), detail

    _run_step_partial(steps, "h1_backtest", "H1 Backtest + Governance", h1_backtest)

    def h1_evaluation() -> tuple[bool, str]:
        h1_doc = ensure_h1_evaluated(root)
        st = str(h1_doc.get("status") or "MISSING")
        sealed = bool(h1_doc.get("sealed"))
        ev = h1_doc.get("evaluation") or {}
        if sealed:
            msg = str(ev.get("message_de") or "SEALED")
            ms = ev.get("metrics_strategy") or {}
            return True, f"SEALED · Sharpe {ms.get('sharpe_0rf', '—')} · {msg[:180]}"
        if st == "RUNNING":
            pct = int((h1_doc.get("governance") or {}).get("progress_pct") or 0)
            try:
                from analytics.r3_step_b import h1_migration_status, is_step_b_released

                if is_step_b_released(root) and h1_migration_status(root).get("parallel_with_step_b"):
                    return True, f"migriert parallel ~{pct}% — Evaluate nach COMPLETE"
            except Exception:
                pass
            return False, f"läuft ~{pct}% — Evaluate nach COMPLETE"
        if st == "COMPLETE":
            msg = str(ev.get("message_de") or "Evaluate ausstehend")
            passed = bool(ev.get("pass_full_seal"))
            return passed, msg[:240]
        return False, f"H1 {st} — ai_kernel h1-status"

    _run_step_partial(steps, "h1_evaluation", "H1 Evaluate/Seal", h1_evaluation)

    def snapshot_step() -> str:
        nonlocal snap
        if snap is None and allow_snapshot_refresh:
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl

            snap = _refresh_snapshot_impl(root, force_quotes=False, force_sync=False)
        elif snap is None:
            snap = {}
        assert isinstance(snap, dict)
        broker = snap.get("broker") or {}
        traffic = snap.get("traffic") or "—"
        cash = broker.get("cash_eur")
        pick = (snap.get("today_pick") or {}).get("symbol") or "—"
        if broker.get("error") and cash is None:
            return f"Ampel {traffic} · Konto-Fehler (Preview trotzdem nutzbar)"
        return f"Ampel {traffic} · Konto {cash if cash is not None else '—'} € · Pick {pick}"

    _run_step(steps, "dashboard_snapshot", "Dashboard-Snapshot", snapshot_step)

    def warnings() -> str:
        from analytics.pilot_trading_day_warnings import collect_trading_day_warnings

        w = collect_trading_day_warnings(root, snap=snap or {})
        crit = int(w.get("critical_count") or 0)
        return f"{crit}× kritisch · {w.get('headline_de') or '—'}"

    _run_step(steps, "trading_warnings", "Handels-Warnungen", warnings)

    def headless() -> str:
        from analytics.snapshot_freshness import snapshot_age_seconds

        stamp_path = root / "evidence/snapshot_stamp.json"
        at = "—"
        if stamp_path.is_file():
            try:
                at = json.loads(stamp_path.read_text(encoding="utf-8")).get("at_utc") or "—"
            except (json.JSONDecodeError, OSError):
                pass
        age = snapshot_age_seconds(root)
        return f"Letzter Snap {at} · Alter {int(age) if age is not None else '—'}s"

    _run_step(steps, "snapshot_freshness", "Snapshot-Frische", headless)

    return steps


def run_chat_preview_steps(
    root: Path,
    *,
    skip_chat: bool = False,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Stufe 3: Ollama-Chat treibt Evolution im Preview voran."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []
    chat_doc: Dict[str, Any] = {}

    def llm_health() -> tuple[bool, str]:
        from analytics.local_llm_bridge import health_report, warmup_ollama

        warmup_ollama(root)
        h = health_report(root)
        if h.get("ready"):
            return True, f"{h.get('resolved_model')} @ {h.get('base_url')}"
        return False, f"Ollama offline — evolve-only · {h.get('base_url')}"

    _run_step_partial(steps, "llm_chat_health", "Lokaler Chat (Ollama)", llm_health)

    def chat_evolution() -> tuple[bool, str]:
        nonlocal chat_doc
        from analytics.local_llm_bridge import health_report

        ollama_ok = bool(health_report(root).get("ready"))
        if skip_chat or not ollama_ok:
            from analytics.chat_evolution_preview import run_chat_evolution_drive

            chat_doc = run_chat_evolution_drive(root, apply_evolve=True, ask_llm=False)
            nxt = str(chat_doc.get("next_step_de") or (chat_doc.get("evolve") or {}).get("message_de") or "evolve OK")
            tag = "evolve-only" if not ollama_ok else "ohne KI-Chat"
            return bool(chat_doc.get("ok", True)), f"{nxt[:200]} ({tag})"[:240]

        from analytics.chat_evolution_preview import run_chat_evolution_drive

        chat_doc = run_chat_evolution_drive(root, apply_evolve=True, ask_llm=True, chat_timeout_s=75)
        reply = str(chat_doc.get("chat_reply_de") or "")[:120]
        nxt = str(chat_doc.get("next_step_de") or chat_doc.get("reason_de") or "—")[:200]
        detail = f"{nxt}" + (f" · KI: {reply}…" if reply and reply != "(Chat übersprungen)" else "")
        ok = bool(chat_doc.get("ok")) or bool((chat_doc.get("evolve") or {}).get("ok", True))
        return ok, detail

    _run_step_partial(steps, "chat_evolution_drive", "KI Evolution (Chat + evolve)", chat_evolution)
    return steps, chat_doc


def _load_snap_for_gui(
    root: Path,
    snap: Optional[Dict[str, Any]],
    *,
    allow_refresh: bool = True,
) -> Dict[str, Any]:
    if snap:
        return snap
    if not allow_refresh:
        from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

        doc = load_trading_day_cockpit_doc(root)
        embedded = doc.get("snap")
        if isinstance(embedded, dict) and embedded:
            return embedded
        return {
            "traffic": "GELB",
            "broker": {"cash_eur": 0.0},
            "plan": {"allocations": []},
            "rebalance_status": {"summary_de": "Preview ohne Refresh"},
            "trading_readiness": {"ready": False, "checks": []},
            "public_learning": {},
            "today_action_de": doc.get("next_step_de") or "GUI Preview",
            "n_positions": 0,
            "live_enabled": True,
            "venv_ok": True,
            "model_script_ok": True,
            "portfolio_orders": {"has_orders": False, "n_buys": 0},
            "quote_coverage": {},
            "prediction_gate": {"ok": True},
            "sector_status": {},
            "policy": {"order_execution_type": "limit"},
            "deferred": {"status_de": "—", "policy": {"user_armed": False}},
            "guard": {"signals_ok": True},
        }
    from ui.live_trading_dashboard.service import _refresh_snapshot_impl

    return _refresh_snapshot_impl(root, force_quotes=False, force_sync=False)


def run_gui_preview(
    root: Path,
    snap: Dict[str, Any],
    *,
    screenshot: bool = False,
) -> tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    """Offscreen Qt: instantiate dashboard, apply snapshot, probe widgets."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []
    probes: Dict[str, Any] = {}
    screenshot_path: Optional[str] = None

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["AA_GUI_PREVIEW"] = "1"
    os.environ["AA_ALLOW_MULTI_INSTANCE"] = "1"

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    def window_create() -> str:
        from ui.live_trading_dashboard.window import LiveTradingDashboardWindow

        win = LiveTradingDashboardWindow(root)
        win._eod_timer.stop()
        win._auto_refresh_timer.stop()
        run_gui_preview._window = win  # type: ignore[attr-defined]
        return f"Fenster {win.windowTitle()[:80]}"

    _run_step(steps, "gui_window", "GUI-Fenster erstellen", window_create)
    win = getattr(run_gui_preview, "_window", None)
    if win is None:
        return steps, probes, screenshot_path

    def apply_snap() -> str:
        snap["_refresh_source"] = "GUI_PREVIEW"
        win._apply_snapshot(snap)
        win._auto_refresh_timer.stop()
        win._eod_timer.stop()
        app.processEvents()
        return f"Ampel {snap.get('traffic')} · Positionen {snap.get('n_positions', 0)}"

    _run_step(steps, "gui_apply_snapshot", "Snapshot in GUI malen", apply_snap)

    def status_banner() -> str:
        text = win._status_banner.text().strip()
        assert text and text != "—", "Status-Banner leer"
        probes["status_banner"] = text[:200]
        return text[:120]

    _run_step(steps, "gui_status_banner", "Ampel / Status-Banner", status_banner)

    def activity_cockpit() -> str:
        text = win._activity_next.text().strip()
        assert text, "Activity/Cockpit leer"
        probes["activity_next"] = text[:300]
        has_circle = "Kreis" in text or "Kreis-Score" in text
        has_cockpit = "Tages-Cockpit" in text or "Phase:" in text or "├──" in text
        assert has_circle or has_cockpit, "Kreis oder Cockpit-Zeilen fehlen"
        return text.split("\n", 1)[0][:120]

    _run_step(steps, "gui_activity_cockpit", "Tages-Cockpit + Kreis im Panel", activity_cockpit)

    def auto_operator() -> str:
        text = win._auto_operator._headline.text().strip()
        assert text and text != "Lädt …", "Auto-Operator-Panel leer"
        probes["auto_operator_headline"] = text[:200]
        return text[:120]

    _run_step(steps, "gui_auto_operator", "Auto-Operator-Panel", auto_operator)

    def learning_panel() -> str:
        text = win._learning_metric.text().strip()
        assert text, "Lernpanel leer"
        probes["learning_metric"] = text[:200]
        return text[:120]

    _run_step(steps, "gui_learning", "Evolution / Lernqualität", learning_panel)

    def portfolio() -> str:
        title = win._portfolio_metric.text().strip()
        rows = win._portfolio_table.rowCount()
        assert title, "Portfolio-Banner leer"
        probes["portfolio_metric"] = title[:200]
        probes["portfolio_rows"] = rows
        return f"{title[:80]} · {rows} Zeilen"

    _run_step(steps, "gui_portfolio", "Champion-Portfolio Tabelle", portfolio)

    def visual_ops() -> str:
        assert hasattr(win, "_visual_ops")
        win._visual_ops.update_from_snap(root, snap)
        app.processEvents()
        return "Visual-Ops aktualisiert"

    _run_step(steps, "gui_visual_ops", "Visual-Ops Panel", visual_ops)

    def controls() -> str:
        win._ensure_controls_operable()
        app.processEvents()
        assert win._btn_refresh.isEnabled(), "Aktualisieren gesperrt"
        probes["refresh_enabled"] = win._btn_refresh.isEnabled()
        probes["portfolio_orders_enabled"] = win._btn_portfolio_orders.isEnabled()
        return (
            f"Aktualisieren ✓ · Portfolio-Orders "
            f"{'frei' if win._btn_portfolio_orders.isEnabled() else 'gesperrt (erwartbar)'}"
        )

    _run_step(steps, "gui_controls", "Bedienbarkeit (Buttons)", controls)

    if screenshot:
        try:
            out = root / _SCREENSHOT
            out.parent.mkdir(parents=True, exist_ok=True)
            pix = win.grab()
            if pix.save(str(out)):
                screenshot_path = str(out)
                steps.append(_step("gui_screenshot", "Screenshot", True, detail_de=str(out)))
            else:
                steps.append(_step("gui_screenshot", "Screenshot", False, detail_de="Speichern fehlgeschlagen"))
        except Exception as exc:
            steps.append(_step("gui_screenshot", "Screenshot", False, detail_de=str(exc)[:200]))

    win.close()
    app.processEvents()
    return steps, probes, screenshot_path


def format_preview_report_de(report: Dict[str, Any]) -> str:
    lines = [
        f"=== GUI Preview — {report.get('product', 'Active Alpha')} ===",
        f"Zeit: {report.get('generated_at_utc')}",
        f"Gesamt: {report.get('passed')}/{report.get('total')} OK"
        + (f" · {report.get('failed')} Fehler" if report.get("failed") else ""),
        "",
    ]
    for section, key in (
        ("Backend (Daten & Evidence)", "backend_steps"),
        ("KI Chat — Evolution (Stufe 3)", "chat_steps"),
        ("GUI (Offscreen Qt)", "gui_steps"),
    ):
        steps = report.get(key) or []
        if not steps:
            continue
        lines.append(f"— {section} —")
        for s in steps:
            icon = "✓" if s.get("pass") else ("~" if s.get("partial") else "✗")
            lines.append(f"  {icon} {s.get('label_de')}: {s.get('detail_de')}")
        lines.append("")
    chat = report.get("chat_evolution") or {}
    if chat.get("chat_reply_de"):
        lines.append("— KI-Empfehlung (active-alpha-chat) —")
        for ln in str(chat["chat_reply_de"]).splitlines()[:8]:
            if ln.strip():
                lines.append(f"  {ln.strip()[:200]}")
        if chat.get("next_step_de"):
            lines.append(f"  → {chat['next_step_de']}")
        lines.append("")
    if report.get("widget_probes"):
        lines.append("— Widget-Vorschau —")
        for k, v in (report.get("widget_probes") or {}).items():
            lines.append(f"  · {k}: {str(v)[:160]}")
        lines.append("")
    if report.get("screenshot"):
        lines.append(f"Screenshot: {report['screenshot']}")
    partials = [
        s for s in (report.get("backend_steps") or []) + (report.get("chat_steps") or []) + (report.get("gui_steps") or [])
        if s.get("partial") and not s.get("pass")
    ]
    if partials:
        lines.append("Hinweis (gelb, kein Blocker): " + ", ".join(s.get("id") or "?" for s in partials))
    if report.get("blockers"):
        lines.append("Blocker: " + ", ".join(report["blockers"]))
    return "\n".join(lines)


def run_full_gui_preview(
    root: Path,
    *,
    backend_only: bool = False,
    refresh_snap: bool = False,
    screenshot: bool = False,
    skip_chat: bool = False,
    mode: str = "stable",
    snap: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    from execution.linux_security_boundary import apply_native_app_env
    from execution.linux_nvme_storage import apply_nvme_storage_env

    apply_native_app_env(root)
    apply_nvme_storage_env(root)

    if refresh_snap and snap is None:
        try:
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl

            snap = _refresh_snapshot_impl(root, force_quotes=False, force_sync=False)
        except Exception:
            snap = snap or {}

    backend_steps = run_backend_preview(
        root, snap=snap, allow_snapshot_refresh=refresh_snap
    )
    chat_steps: List[Dict[str, Any]] = []
    chat_doc: Dict[str, Any] = {}
    if not backend_only:
        try:
            chat_steps, chat_doc = run_chat_preview_steps(root, skip_chat=skip_chat)
        except Exception as exc:
            chat_steps.append(
                _step(
                    "chat_fatal",
                    "KI Chat Preview",
                    False,
                    detail_de=str(exc)[:300],
                    traceback=traceback.format_exc()[-600:],
                )
            )
    gui_steps: List[Dict[str, Any]] = []
    probes: Dict[str, Any] = {}
    screenshot_path: Optional[str] = None

    if not backend_only:
        try:
            gui_snap = _load_snap_for_gui(root, snap, allow_refresh=refresh_snap)
            gui_steps, probes, screenshot_path = run_gui_preview(
                root, gui_snap, screenshot=screenshot
            )
        except Exception as exc:
            gui_steps.append(
                _step(
                    "gui_fatal",
                    "GUI-Preview",
                    False,
                    detail_de=str(exc)[:300],
                    traceback=traceback.format_exc()[-800:],
                )
            )

    all_steps = backend_steps + chat_steps + gui_steps
    failed = [s for s in all_steps if not s.get("pass") and not s.get("partial")]
    cockpit_snap = snap
    if cockpit_snap is None and not backend_only:
        try:
            cockpit_snap = _load_snap_for_gui(root, snap, allow_refresh=refresh_snap)
        except Exception:
            cockpit_snap = {}
    try:
        from analytics.preview_cockpit import build_preview_cockpit

        cockpit_doc = build_preview_cockpit(root, snap=cockpit_snap or {})
    except Exception:
        cockpit_doc = {}
    system_status_doc: Dict[str, Any] = {}
    try:
        from analytics.preview_system_status import build_preview_system_status

        system_status_doc = build_preview_system_status(root, refresh_h1=False)
    except Exception:
        pass

    report: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "product": "R3 Cockpit",
        "mode": "backend_only" if backend_only else str(mode or "stable"),
        "passed": sum(1 for s in all_steps if s.get("pass")),
        "failed": len(failed),
        "total": len(all_steps),
        "overall_pass": len(failed) == 0,
        "blockers": [s["id"] for s in failed],
        "backend_steps": backend_steps,
        "chat_steps": chat_steps,
        "chat_evolution": chat_doc,
        "gui_steps": gui_steps,
        "widget_probes": probes,
        "screenshot": screenshot_path,
        "snap_traffic": (snap or cockpit_snap or {}).get("traffic"),
        "cockpit": cockpit_doc,
        "system_status": system_status_doc,
        "note_de": "Command Center: Operator-Aktionen im Hub — Orders nur Order-Desk.",
    }
    text = format_preview_report_de(report)
    report["report_de"] = text

    try:
        from analytics.preview_federation import merge_federation_into_report, sync_king_contribution

        sync_king_contribution(root, preview_report=report)
        report = merge_federation_into_report(root, report)
    except Exception:
        pass

    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / _EVIDENCE_JSON).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (root / _EVIDENCE_TXT).write_text(text + "\n", encoding="utf-8")
    try:
        from analytics.gui_preview_visual import write_gui_preview_html
        from analytics.preview_manifest import load_preview_manifest

        report["manifest"] = load_preview_manifest(root)
        report["visual_paths"] = write_gui_preview_html(root, report)
    except Exception:
        report["visual_paths"] = {}
    return report
