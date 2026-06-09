#!/usr/bin/env python3
"""Single entry: bootstrap + preflight + Live-Trading Invest UI (legacy module name)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent


def bootstrap_live_trading_runtime(root: Path) -> Path:
    root = Path(root)
    if sys.platform.startswith("linux"):
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(root)
    os.environ["AA_PROJECT_ROOT"] = str(root)
    os.environ.setdefault("AA_INTERACTIVE_COCKPIT", "1")
    os.environ["AA_MINIMAL_INVEST_APP"] = "1"
    os.environ.setdefault("AA_RUN_MODE", "signal")
    os.environ.setdefault("AA_SIGNAL_REFRESH_ON_STALE_DATA", "1")

    from aa_frozen import is_frozen_exe

    if is_frozen_exe():
        from aa_exe_direct_startup import configure_direct_exe_startup

        root = Path(configure_direct_exe_startup())
    else:
        from aa_exe_direct_startup import apply_marktanalyse_os_profile

        apply_marktanalyse_os_profile()

    from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout

    root = ensure_marktanalyse_runtime_layout(Path(root))

    from integrations.trading212.t212_env_file_loader import load_trading212_env_file
    from integrations.trading212.t212_startup_bootstrap import bootstrap_trading212_credentials

    load_trading212_env_file(root)
    bootstrap_trading212_credentials(root)

    from execution.confirmed_live.p17_review_mode_preferences import apply_saved_review_mode_to_environment
    from execution.confirmed_live.trading_mode_policy import apply_saved_trading_mode

    apply_saved_review_mode_to_environment(root)
    apply_saved_trading_mode(root)

    try:
        from aa_config_env import load_aa_env
        from aa_live_daily_sync import ensure_between_trading_day_daily_refresh
        from analytics.prediction_operations import maybe_run_eod_prediction_switch

        maybe_run_eod_prediction_switch(root, force=False)
        ensure_between_trading_day_daily_refresh(root, load_aa_env(root), log_print=False)
    except Exception:
        pass

    from execution.confirmed_live.recovery_state_machine import record_startup

    record_startup(root, build_id="LIVE_TRADING_INVEST")

    try:
        from analytics.kernel_bootstrap import run_kernel_bootstrap

        run_kernel_bootstrap(root, write_evidence=True)
    except Exception:
        pass

    from analytics.champion_runtime_guard import (
        enforce_champion_runtime_hard,
        write_guard_evidence,
    )

    guard_status = enforce_champion_runtime_hard(root)
    write_guard_evidence(root, guard_status)

    from execution.confirmed_live.live_trading_enablement import ensure_live_trading_enabled

    try:
        ensure_live_trading_enabled(root, changed_by="live_trading_launch")
    except Exception:
        pass

    try:
        from execution.linux_native_bootstrap import reapply_native_order_environment

        if sys.platform.startswith("linux"):
            reapply_native_order_environment(root)
    except Exception:
        pass

    try:
        from aa_adaptive_runtime import refresh_price_feed_state

        refresh_price_feed_state(root, write=True)
    except Exception:
        pass
    return root


def run_preflight(root: Path) -> Dict[str, Any]:
    from analytics.champion_runtime_guard import verify_champion_runtime, write_guard_evidence
    from tools.verify_minimal_t212_flow import run_minimal_flow

    guard = verify_champion_runtime(root)
    write_guard_evidence(root, guard)
    report = run_minimal_flow(root, dry_run_order=True)
    report["champion_guard"] = guard.as_dict()
    if guard.hard_block:
        report["live_trading_ready"] = False
        report["pilot_core_ready"] = False
        report["overall_pass"] = False
        blockers = list(report.get("blockers") or [])
        for b in guard.blockers:
            if b not in blockers:
                blockers.append(f"champion_guard:{b}")
        report["blockers"] = blockers
    elif not guard.signals_ok:
        report["champion_signal_stale"] = True
    try:
        from analytics.pilot_trading_day_warnings import collect_trading_day_warnings

        day_warn = collect_trading_day_warnings(root, snap={})
        report["day_warnings"] = day_warn
        if day_warn.get("must_resolve_before_trading"):
            report["trading_day_warning_blockers"] = [
                w.get("code") for w in (day_warn.get("warnings") or []) if w.get("severity") == "critical"
            ]
    except Exception as exc:
        report["day_warnings_error"] = str(exc)[:200]
    return report


def launch_ui(root: Path) -> int:
    if os.environ.get("AA_LEGACY_FULL_COCKPIT", "").strip() == "1":
        from ui.interactive_cockpit.main_window import launch_interactive_cockpit

        return launch_interactive_cockpit(root)

    import sys

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ui.live_trading_dashboard.window import LiveTradingDashboardWindow

    app = QApplication.instance() or QApplication(sys.argv)
    from ui.interactive_cockpit.accessibility_helpers import (
        apply_window_accessibility,
        tag_interactive_widgets,
    )
    from ui.invest_layout import apply_invest_typography

    apply_invest_typography(app)

    from analytics.active_alpha_identity import product_name

    full_function_test = os.environ.get("AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST", "").strip() == "1"
    if not full_function_test:
        from aa_single_instance import acquire_single_instance

        pname = product_name(root)
        if acquire_single_instance(root, window_title=pname) is None:
            QMessageBox.information(
                None,
                pname,
                f"{pname} läuft bereits — bestehendes Fenster wurde aktiviert.",
            )
            return 0

    try:
        from ui.live_trading_dashboard.activity_log import log_dashboard_activity

        from analytics.active_alpha_identity import status_line_de

        log_dashboard_activity(
            root,
            category=product_name(root),
            action="Dashboard gestartet",
            result=status_line_de(root, surface="marktanalyse_app"),
            source="AUTO",
        )
        from analytics.monday_ops_checklist import is_trading_prep_day, write_monday_checklist_to_activity_log

        if is_trading_prep_day():
            write_monday_checklist_to_activity_log(root, source="AUTO")
    except Exception:
        pass

    win = LiveTradingDashboardWindow(root)
    apply_window_accessibility(win)
    tag_interactive_widgets(win)
    win.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Alpha Model — Invest Cockpit")
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--legacy-full-cockpit", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    args = p.parse_args(argv)

    root = bootstrap_live_trading_runtime(ROOT)
    if args.legacy_full_cockpit:
        os.environ["AA_LEGACY_FULL_COCKPIT"] = "1"

    if not args.skip_preflight:
        report = run_preflight(root)
        if getattr(sys, "frozen", False) and not report.get("live_trading_ready", report.get("pilot_core_ready")):
            from aa_exe_direct_startup import direct_exe_ready_message, direct_exe_requirements

            setup_hint = direct_exe_ready_message(direct_exe_requirements(root))
            if setup_hint:
                report.setdefault("blockers", []).append("direct_exe_setup")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if args.preflight_only:
            ready = report.get("live_trading_ready", report.get("pilot_core_ready"))
            return 0 if ready else 1
        if not report.get("live_trading_ready", report.get("pilot_core_ready")):
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            guard = report.get("champion_guard") or {}
            msg = guard.get("status_de") or "Preflight fehlgeschlagen."
            blockers = report.get("blockers") or []
            if blockers:
                msg = f"{msg}\n\nBlocker: {', '.join(blockers)}"
            QMessageBox.critical(None, "Live-Trading — Preflight", msg)
            return 1

    try:
        from analytics.kernel_bootstrap import format_critical_dialog_de, run_kernel_bootstrap

        kb = run_kernel_bootstrap(root, write_evidence=True)
        if not kb.get("safety", {}).get("ok"):
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            blockers = kb.get("safety", {}).get("blockers") or []
            QMessageBox.critical(
                None,
                "AI Kernel — Sicherheit",
                "Kernel-Sicherheitsprüfung fehlgeschlagen.\n\nBlocker: " + ", ".join(blockers),
            )
            return 1
        dw = kb.get("day_warnings") or {}
        if int(dw.get("critical_count") or 0) > 0:
            from PySide6.QtWidgets import QApplication, QMessageBox

            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.warning(
                None,
                "Vor dem Handelstag — kritische Punkte",
                (
                    "Diese Punkte haben den letzten schlechten Tag verursacht. "
                    "Bitte vor US-Eröffnung beheben:\n\n"
                    + format_critical_dialog_de(kb)
                ),
            )
    except Exception:
        pass

    return launch_ui(root)


# Back-compat aliases (do not use "pilot" in new code)
launch_live_trading_ui = launch_ui
launch_default_live_trading_ui = launch_ui
launch_default_pilot_ui = launch_ui
bootstrap_pilot_runtime = bootstrap_live_trading_runtime


if __name__ == "__main__":
    raise SystemExit(main())
