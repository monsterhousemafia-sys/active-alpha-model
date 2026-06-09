"""Qt widgets for read-only Decision Cockpit (V4R2 / V4R3)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from aa_authorization_policy import format_authorization_tab_lines
from aa_decision_cockpit_viewmodel import load_decision_cockpit


def _fmt_eligibility(display: str) -> str:
    return display


def build_cockpit_tab_labels(data: Dict[str, Any]) -> Dict[str, str]:
    exec_ov = data.get("executive_overview") or {}
    safety = data.get("safety_automation") or {}
    controller = data.get("controller_state") or {}
    cost = data.get("cost_stress_robustness") or {}
    mon = data.get("monitoring") or {}
    exp = data.get("experiment_registry") or {}
    audit = data.get("audit_review_chain") or {}
    auth = data.get("authorization_status") or {}
    why = data.get("why_not_promoted") or {}
    gov = data.get("champion_governance_de") or {}
    op = data.get("operator_transparency_de") or {}
    drift = op.get("h4_pointer_drift") or {}

    overview_lines = [f"=== {b} ===" for b in (data.get("banners") or [])]
    champ_line = f"Active Champion: {exec_ov.get('active_champion')}"
    overview_lines.append(champ_line)
    if exec_ov.get("champion_blocked_for_safety"):
        overview_lines.append("CHAMPION STATUS MISSING OR CONFLICTING")
        overview_lines.append("BLOCKED FOR SAFETY")
    if drift.get("drift_detected"):
        overview_lines.append("*** POINTER-DRIFT FAILSAFE — Challenger ≠ Locked Champion ***")
        overview_lines.extend(drift.get("lines_de") or [])
    if op.get("h3_rebalance_precheck", {}).get("quote_coverage_label_de"):
        overview_lines.append(
            f"Rebalance-Quote (Vorcheck): {op['h3_rebalance_precheck']['quote_coverage_label_de']}"
        )
    if op.get("last_signal_date"):
        overview_lines.append(f"Letztes Signal: {op['last_signal_date']}")
    if gov.get("lines_de"):
        overview_lines.append("--- Champion-Governance ---")
        overview_lines.extend(gov["lines_de"])
    overview_lines += [
        f"Candidate: {exec_ov.get('candidate')}",
        f"Control Reference: {exec_ov.get('control_reference')}",
    ]
    if exec_ov.get("manifest_blocked_for_safety"):
        overview_lines.append(str(exec_ov.get("manifest_status") or "EXPERIMENT MANIFEST MISSING OR CONFLICTING"))
        overview_lines.append("BLOCKED FOR SAFETY")
    overview_lines += [
        f"Evidence Stage: {exec_ov.get('evidence_stage')}",
        exec_ov.get("evidence_stage_summary") or "",
        f"Source Classification: {exec_ov.get('source_classification')}",
        f"Promotion Eligible: {_fmt_eligibility(exec_ov.get('promotion_eligible_display', 'UNKNOWN'))}",
        f"Paper Eligible: {_fmt_eligibility(exec_ov.get('paper_eligible_display', 'UNKNOWN'))}",
        f"Real Money Eligible: {_fmt_eligibility(exec_ov.get('real_money_eligible_display', 'UNKNOWN'))}",
    ]
    if controller.get("blocked_for_safety"):
        overview_lines.append("Controller State: UNKNOWN — BLOCKED FOR SAFETY")
    else:
        if controller.get("lifecycle_message"):
            overview_lines.extend(str(controller["lifecycle_message"]).split("\n"))
        overview_lines += [
            f"Current Executed Phase: {controller.get('current_executed_phase')}",
            f"Execution Status: {controller.get('execution_status')}",
            f"Expected Next Phase: {controller.get('expected_next_phase')}",
            f"Next Phase Authorized: {controller.get('next_phase_authorized_display')}",
        ]

    auth_lines = format_authorization_tab_lines(auth)

    safety_lines = []
    if safety.get("safety_banner"):
        safety_lines.append(str(safety["safety_banner"]))
    for warning in safety.get("safety_warnings") or []:
        safety_lines.append(warning)
    for key in ("AUTO_RESEARCH", "AUTO_PROMOTE_PAPER", "AUTO_PROMOTE_SIGNAL", "AUTO_EXECUTE_REAL_MONEY"):
        safety_lines.append(f"{key}: {safety.get(key, 'UNKNOWN')}")
    hooks_status = safety.get("hooks_status", "UNKNOWN")
    if hooks_status == "UNKNOWN":
        safety_lines.append("Hooks: UNKNOWN — BLOCKED FOR SAFETY")
    else:
        safety_lines.append(f"Hooks: {hooks_status}")
    safety_lines.append(f"System Health: {safety.get('system_health', 'UNKNOWN')}")
    safety_lines.append(f"LKG Available: {safety.get('last_known_good_available')}")

    ladder_lines = [(data.get("evidence_ladder") or {}).get("summary", "")]
    for step in (data.get("evidence_ladder") or {}).get("stages") or []:
        marker = " <- CURRENT" if step.get("status") == "CURRENT" else ""
        blocker = f" ({step.get('blocker')})" if step.get("blocker") else ""
        ladder_lines.append(f"{step.get('stage')}: {step.get('status')}{marker}{blocker}")

    why_lines = ["Promotion blocked because (explanatory):"]
    why_lines += [f"- {r}" for r in why.get("explanatory_reasons") or []]
    why_lines.append("")
    why_lines.append("Current active blockers:")
    why_lines += [f"- {b}" for b in why.get("current_active_blockers") or []]
    why_lines.append("")
    why_lines.append("Source conflicts:")
    if why.get("source_conflicts"):
        why_lines += [f"- {c}" for c in why["source_conflicts"]]
    else:
        why_lines.append("- (none detected)")

    cost_lines = [
        f"Cost Stress: {cost.get('cost_stress_status')} (pass={cost.get('cost_stress_pass')})",
        f"Blocker: {cost.get('cost_stress_blocker')}",
        f"Proxy analyses: {cost.get('proxy_label')}",
        f"DSR probability: {cost.get('dsr_probability')} (required: {cost.get('dsr_required_probability')})",
        f"DSR status: {cost.get('dsr_status')}",
        f"PBO: {cost.get('pbo_status')}",
        f"Subperiod screen: {cost.get('subperiod_screen_pass')}",
        f"Robustness: {cost.get('robustness_status')} (pass={cost.get('robustness_pass')})",
    ]

    shadow = mon.get("shadow") or {}
    paper = mon.get("paper") or {}
    forward = mon.get("forward") or {}
    mon_lines = [f"Forward Monitoring: {forward.get('display', forward.get('status', 'UNKNOWN'))}"]
    if shadow.get("evidence_missing"):
        mon_lines.append("Shadow Observation: UNKNOWN — BLOCKED FOR SAFETY")
        mon_lines.append("Evidence for activation state is missing.")
    else:
        mon_lines.append(f"Shadow Observation: {shadow.get('display')} — not activated")
        scs = shadow.get("shadow_collection_started")
        mon_lines.append(f"shadow_collection_started = {scs if scs is not None else 'UNKNOWN'}")
    if paper.get("evidence_missing"):
        mon_lines.append("Paper Simulation: UNKNOWN — BLOCKED FOR SAFETY")
        mon_lines.append("Evidence for activation state is missing.")
    else:
        mon_lines.append(f"Paper Simulation: {paper.get('display')} — not activated")
        pss = paper.get("paper_simulation_started")
        mon_lines.append(f"paper_simulation_started = {pss if pss is not None else 'UNKNOWN'}")

    if exp.get("blocked_for_safety"):
        exp_lines = [
            "Experiment: UNKNOWN — BLOCKED FOR SAFETY",
            str(exp.get("status_message") or "EXPERIMENT MANIFEST MISSING OR CONFLICTING"),
        ]
    else:
        exp_lines = [
            f"Experiment: {exp.get('experiment_id')}",
            f"Candidate: {exp.get('candidate')}",
            f"Champion Reference: {exp.get('champion_reference')}",
            f"Control Reference: {exp.get('control_reference')}",
            f"Status: {exp.get('status')}",
            f"Evidence Stage: {exp.get('evidence_stage')}",
        ]

    audit_lines = [f"Chain: {audit.get('chain')}"]
    if controller.get("blocked_for_safety"):
        audit_lines.append("Controller State: UNKNOWN — BLOCKED FOR SAFETY")
    else:
        if controller.get("lifecycle_message"):
            audit_lines.extend(str(controller["lifecycle_message"]).split("\n"))
        audit_lines += [
            f"Current Executed Phase: {controller.get('current_executed_phase')}",
            f"Execution Status: {controller.get('execution_status')}",
            f"Expected Next Phase: {controller.get('expected_next_phase')}",
            f"Next Phase Authorized: {controller.get('next_phase_authorized_display')}",
        ]
    for r in audit.get("reviews") or []:
        sealed = "SEALED" if r.get("external_sealed") else "PENDING"
        audit_lines.append(
            f"{r.get('phase_id')}: {sealed} zip={r.get('review_zip')} hash={r.get('review_zip_sha256')}"
        )

    gov_lines = list(gov.get("lines_de") or [])
    if gov.get("charter_ref"):
        gov_lines.extend(["", f"Charter: {gov['charter_ref']}", f"Criteria: {gov.get('criteria_ref', '')}"])

    h1_lines = list((op.get("h1_model_comparison") or {}).get("lines_de") or [])
    h2_lines = list((op.get("h2_champion_status") or {}).get("lines_de") or [])
    h3_lines = list((op.get("h3_rebalance_precheck") or {}).get("lines_de") or [])
    h4_lines = list(drift.get("lines_de") or [])

    safety_with_drift = list(safety_lines)
    if drift.get("failsafe_banner_de"):
        safety_with_drift.insert(0, str(drift["failsafe_banner_de"]))

    return {
        "Overview": "\n".join(overview_lines),
        "Modell-Vergleich (Research)": "\n".join(h1_lines) if h1_lines else "Canonical Comparison nicht geladen.",
        "Champion-Status": "\n".join(h2_lines) if h2_lines else "Champion-Status nicht verfügbar.",
        "Rebalance-Vorcheck": "\n".join(h3_lines) if h3_lines else "Rebalance-Vorcheck nicht verfügbar.",
        "Pointer-Drift": "\n".join(h4_lines) if h4_lines else "Pointer-Drift-Check nicht verfügbar.",
        "Champion-Governance": "\n".join(gov_lines) if gov_lines else "Governance-Daten nicht verfügbar.",
        "Authorization": "\n".join(auth_lines),
        "Safety": "\n".join(safety_with_drift),
        "Evidence Ladder": "\n".join(ladder_lines),
        "Why Not Promoted": "\n".join(why_lines),
        "Cost & Robustness": "\n".join(cost_lines),
        "Monitoring": "\n".join(mon_lines),
        "Experiment": "\n".join(exp_lines),
        "Audit Chain": "\n".join(audit_lines),
    }


def build_portfolio_signal_lines(root: Path) -> str:
    """Live portfolio + backtest metrics for V5R cockpit (read-only)."""
    from aa_config_env import resolve_launcher_env
    from aa_dashboard_result import (
        exemplar_stock_portfolio,
        load_result_context,
        load_target_portfolio,
        scale_portfolio_rows,
    )
    from aa_live_daily_sync import read_sync_manifest
    from aa_r3_daily_diagnosis import format_r3_diagnosis_block, read_r3_diagnosis_manifest
    from aa_adaptive_runtime import format_adaptive_status_block

    root = Path(root)
    env = resolve_launcher_env(root, frozen=False)
    out_name = str(env.get("AA_BACKTEST_OUT_DIR") or "model_output_sp500_pit_t212")
    out_dir = root / out_name
    lines = [f"Output: {out_dir}", ""]

    if not out_dir.is_dir():
        lines.append("Modell-Output nicht gefunden — Backtest noch nicht ausgeführt.")
        return "\n".join(lines)

    try:
        ctx = load_result_context(out_dir, metrics={})
        metrics = ctx.get("metrics") or {}
        lines.append(f"Signal-Datum: {ctx.get('signal_date', 'n/a')}")
        lines.append(f"Kontext: {ctx.get('context_line', '')}")
        lines.append("")
        lines.append("Kennzahlen (Backtest):")
        for key in ("cagr", "sharpe_0rf", "max_drawdown", "information_ratio", "total_return"):
            val = metrics.get(key)
            if val is not None:
                lines.append(f"  {key}: {val}")
        lines.append("")
        portfolio, source_label = load_target_portfolio(out_dir)
        capital = float(env.get("AA_EXEMPLAR_PORTFOLIO_CAPITAL") or 10_000.0)
        stock_pf = exemplar_stock_portfolio(portfolio)
        rows, invested, _cash = scale_portfolio_rows(stock_pf, capital)
        lines.append(f"Quelle: {source_label}")
        lines.append(f"Exemplarisches Aktienportfolio (volle Allokation, ohne Cash/SPY-Filler):")
        lines.append(f"  Kapital: {capital:,.0f} USD | Positionen: {len(rows)}")
        lines.append(f"  Investiert: {invested:,.2f} USD (100 % Aktien)")
        sync_doc = read_sync_manifest(out_dir)
        if sync_doc.get("synced_at_utc"):
            lines.append(f"  Live-Tagesdaten: {sync_doc.get('price_latest', 'n/a')} (Sync {sync_doc.get('synced_at_utc')})")
            n_quotes = len(sync_doc.get("live_quotes") or {})
            if n_quotes:
                lines.append(f"  Live-Kurse (Portfolio): {n_quotes} Ticker")
            if sync_doc.get("r3_regime_match") is False:
                lines.append("  R3-Diagnose: Regime-Drift — Signal-Refresh empfohlen")
            elif sync_doc.get("r3_regime_match") is True:
                lines.append("  R3-Diagnose: Regime mit Tagesdaten bestätigt")
        r3_block = format_r3_diagnosis_block(read_r3_diagnosis_manifest(out_dir))
        if r3_block:
            lines.append("")
            lines.append(r3_block)
        adaptive_block = format_adaptive_status_block(root)
        if adaptive_block:
            lines.append("")
            lines.append(adaptive_block)
        for row in rows[:15]:
            lines.append(
                f"  {row.get('ticker', '?')}: {float(row.get('weight_pct', 0)):.2f}% "
                f"-> {float(row.get('amount', 0)):,.2f} USD"
            )
        if len(rows) > 15:
            lines.append(f"  … +{len(rows) - 15} weitere")
    except Exception as exc:
        lines.append(f"Portfolio/Signal konnte nicht geladen werden: {exc}")
    return "\n".join(lines)


def build_cockpit_tab_labels_with_live(root: Path, data: Dict[str, Any]) -> Dict[str, str]:
    tabs = build_cockpit_tab_labels(data)
    tabs["Portfolio & Signal"] = build_portfolio_signal_lines(root)
    return tabs


OPERATIVE_BUTTON_LABELS = (
    "promote",
    "promotion",
    "real money",
    "echtgeld",
    "shadow activate",
    "paper activate",
    "start pipeline",
    "build exe",
    "broker",
)


def cockpit_widget_has_operative_actions(widget) -> bool:
    from PySide6.QtWidgets import QPushButton

    for btn in widget.findChildren(QPushButton):
        text = (btn.text() or "").lower()
        if any(k in text for k in OPERATIVE_BUTTON_LABELS):
            return True
    return False


def create_decision_cockpit_widget(root: Path, parent=None):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    root = Path(root)
    data = load_decision_cockpit(root)
    return create_decision_cockpit_widget_from_data(data, parent=parent, root=root)


def create_decision_cockpit_widget_from_data(
    data: Dict[str, Any],
    parent=None,
    root: Path | None = None,
    *,
    include_portfolio_tab: bool = False,
    include_p16f_desktop: bool = False,
):
    from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

    QApplication.instance() or QApplication([])
    if include_portfolio_tab and root is not None:
        tabs = build_cockpit_tab_labels_with_live(root, data)
    else:
        tabs = build_cockpit_tab_labels(data)

    if include_p16f_desktop and root is not None:
        from aa_decision_cockpit_p16f_desktop import build_p16f_desktop_tabs

        tabs.update(build_p16f_desktop_tabs(root))

    container = QWidget(parent)
    layout = QVBoxLayout(container)
    tab_widget = QTabWidget(container)
    for title, text in tabs.items():
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text)
        tab_widget.addTab(editor, title)
    layout.addWidget(tab_widget)
    container.setProperty("decision_cockpit_read_only", True)
    if root is not None:
        container.setProperty("decision_cockpit_root", str(root))
    return container
