#!/usr/bin/env python3
"""Thin CLI — status, setup, test, ready, launch. Logic lives in the repo modules."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TESTS = (
    "tests/test_linux_security_boundary.py",
    "tests/test_champion_runtime_guard.py",
    "tests/test_pilot_quote_session.py",
    "tests/test_pilot_day_trading_facade_integration.py",
    "tests/test_us_day_trading_coordinator.py",
    "tests/test_pilot_trading_day_warnings.py",
    "tests/test_wallstreet_performance_audit.py",
    "tests/test_public_learning_kernel.py",
    "tests/test_kernel_bootstrap.py",
    "tests/test_linux_nvme_storage.py",
    "tests/test_linux_native_bootstrap.py",
    "tests/test_dashboard_activity_log.py",
    "tests/test_evolution_stage_runner.py",
    "tests/test_active_alpha_identity.py",
    "tests/test_kernel_activity_bridge.py",
    "tests/test_linux_operator_scope.py",
    "tests/test_monday_ops_checklist.py",
    "tests/test_operator_visibility.py",
    "tests/test_operator_public_status.py",
    "tests/test_local_llm_bridge.py",
    "tests/test_headless_dashboard_refresh.py",
    "tests/test_trading_day_orchestrator.py",
    "tests/test_snapshot_freshness.py",
    "tests/test_h1_governance_status.py",
    "tests/test_closed_loop_score.py",
    "tests/test_gui_preview_harness.py",
    "tests/test_h1_backtest_status.py",
    "tests/test_operator_sovereignty.py",
    "tests/test_alpha_model_interface_kernel.py",
    "tests/test_chat_evolution_preview.py",
    "tests/test_preview_freshness.py",
    "tests/test_gui_preview_visual.py",
)


def root() -> Path:
    p = os.environ.get("AA_PROJECT_ROOT", "").strip()
    return Path(p) if p else ROOT


def py(r: Path) -> Path:
    from aa_paths import resolve_venv_python, venv_python_ok

    return resolve_venv_python(r) if venv_python_ok(r) else Path(sys.executable)


def run(cmd: list[str], *, cwd: Path) -> int:
    return subprocess.run(cmd, cwd=str(cwd), check=False).returncode


def _kernel_log(r: Path, command: str, result: str, *, code: int = 0) -> None:
    from analytics.kernel_activity_bridge import log_kernel_command

    status = "ERFOLGREICH" if code == 0 else "FEHLGESCHLAGEN"
    log_kernel_command(r, command=command, result=result, status=status)


def _guard_privileged(r: Path, action: str) -> int:
    from analytics.operator_sovereignty import assert_privileged_action

    ok, doc = assert_privileged_action(r, action)
    if ok:
        return 0
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    _kernel_log(r, action, str(doc.get("blocked_de") or "blockiert"), code=1)
    return 1


def _load_hardware_bond_summary(r: Path) -> Dict[str, Any]:
    try:
        from analytics.ai_kernel_hardware_bond import load_hardware_bond

        bond = load_hardware_bond(r)
        if bond:
            return {
                "ok": bond.get("ok"),
                "king_model": bond.get("king_model"),
                "nvme_mounted": bond.get("nvme_mounted"),
                "nvme_priority": bond.get("nvme_priority"),
                "headline_de": bond.get("headline_de"),
            }
        from analytics.ai_kernel_hardware_bond import bond_kernel_to_king_32b

        fresh = bond_kernel_to_king_32b(r, persist=True, preload=False)
        return {
            "ok": fresh.get("ok"),
            "king_model": fresh.get("king_model"),
            "nvme_mounted": fresh.get("nvme_mounted"),
            "nvme_priority": fresh.get("nvme_priority"),
            "headline_de": fresh.get("headline_de"),
        }
    except Exception as exc:
        return {"ok": False, "error_de": str(exc)[:120]}


def cmd_status(r: Path) -> int:
    from aa_paths import venv_python_ok
    from execution.linux_security_boundary import apply_native_app_env, host_role_summary, load_kernel_doc

    apply_native_app_env(r)
    try:
        from analytics.alpha_model_local_runtime import apply_local_runtime

        apply_local_runtime(r)
    except Exception:
        pass
    try:
        from execution.linux_nvme_storage import storage_status

        nvme = storage_status(r)
    except Exception:
        nvme = {"error": "storage_status_failed"}
    try:
        from analytics.active_alpha_identity import load_unified_config, status_line_de

        identity = load_unified_config(r)
        identity["status_line_de"] = status_line_de(r, surface="r3_ki")
    except Exception:
        identity = {}
    try:
        from analytics.linux_operator_scope import scope_summary_de

        operator = scope_summary_de(r)
    except Exception:
        operator = {}
    try:
        from analytics.operator_public_status import build_public_status

        public_operator = {
            "can_do_de": build_public_status(r).get("can_do_de"),
            "how_to_see_de": build_public_status(r).get("how_to_see_de"),
            "user_status_file": str(Path.home() / ".local/share/r3-os/operator_latest.txt"),
        }
    except Exception:
        public_operator = {}
    try:
        from analytics.closed_loop_score import load_closed_loop_score

        circle = load_closed_loop_score(r)
    except Exception:
        circle = {}
    runtime_profile_doc = {}
    system_status = {}
    try:
        from analytics.linux_runtime_unified import kernel_supremacy_status
        from analytics.linux_runtime_unified import runtime_profile as build_runtime_profile
        from analytics.linux_runtime_unified import sync_operator_timer_catalog

        runtime_profile_doc = build_runtime_profile(r)
        runtime_profile_doc["kernel_supremacy"] = kernel_supremacy_status(r)
        sync_operator_timer_catalog(r)
    except Exception:
        pass
    try:
        from analytics.preview_system_status import build_preview_system_status

        system_status = build_preview_system_status(r, refresh_h1=False)
    except Exception:
        pass
    payload = {
        "kernel": load_kernel_doc(r),
        "unified_product": identity,
        "linux_operator": operator,
        "public_operator": public_operator,
        "runtime_profile": runtime_profile_doc,
        "system_status": system_status,
        "venv_ok": venv_python_ok(r),
        "host": host_role_summary(),
        "nvme_storage": nvme,
        "hardware_bond": _load_hardware_bond_summary(r),
        "circle_score": circle,
        "root": str(r),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    tagline = str(identity.get("tagline_de") or "Ein System")
    _kernel_log(r, "status", tagline)
    return 0


def cmd_ready(r: Path) -> int:
    from aa_paths import venv_python_ok
    from execution.linux_security_boundary import apply_native_app_env, host_role_summary, load_kernel_doc

    apply_native_app_env(r)
    k = load_kernel_doc(r)
    checks = {
        "venv": venv_python_ok(r),
        "env": (r / ".env").is_file(),
        "champion_csv": (r / "model_output_sp500_pit_t212/latest_target_portfolio.csv").is_file(),
        "pilot_policy": (r / "control/pilot_day_trading.json").is_file(),
        "native_host": host_role_summary().get("native_execution_host"),
        "no_auto_money": not k.get("safety", {}).get("auto_execute_real_money"),
    }
    if checks["venv"]:
        checks["tests"] = run([str(py(r)), "-m", "pytest", *TESTS, "-q"], cwd=r) == 0
        checks["snapshot"] = run([str(py(r)), "tools/virtual_test_pilot_day_trading.py"], cwd=r) == 0
    else:
        checks["tests"] = False
        checks["snapshot"] = False
    blockers = [n for n, ok in checks.items() if not ok]
    report = {"ready": not blockers, "checks": checks, "blockers": blockers, "go_live": k.get("go_live_date")}
    (r / "evidence").mkdir(exist_ok=True)
    (r / "evidence/ai_kernel_ready_latest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    _kernel_log(
        r,
        "ready",
        "bereit" if report["ready"] else f"Blocker: {', '.join(blockers)}",
        code=0 if report["ready"] else 1,
    )
    return 0 if report["ready"] else 1


def cmd_warnings(r: Path) -> int:
    from execution.linux_security_boundary import apply_native_app_env
    from analytics.pilot_trading_day_warnings import collect_trading_day_warnings

    apply_native_app_env(r)
    snap: dict = {}
    try:
        from analytics.trading_day_cockpit import load_trading_day_snap

        cached = load_trading_day_snap(r)
        if cached:
            snap = cached
        else:
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl

            snap = _refresh_snapshot_impl(r, force_quotes=False, force_sync=False)
    except Exception as exc:
        snap = {"broker": {}, "error": str(exc)[:200]}
    report = collect_trading_day_warnings(r, snap=snap)
    out = {
        "warnings": report,
        "open_points": report.get("infrastructure_open_points") or [],
        "traffic": snap.get("traffic"),
    }
    (r / "evidence").mkdir(exist_ok=True)
    (r / "evidence/pilot_trading_day_warnings_latest.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    code = 1 if report.get("must_resolve_before_trading") else 0
    traffic = str(snap.get("traffic") or "—")
    _kernel_log(r, "warnings", f"Traffic {traffic}", code=code)
    return code


def cmd_audit(r: Path) -> int:
    from aa_paths import venv_python_ok
    from analytics.pilot_trading_day_warnings import collect_trading_day_warnings, infrastructure_open_points
    from execution.linux_security_boundary import apply_native_app_env

    apply_native_app_env(r)
    infra = infrastructure_open_points(r)
    items = [
        {
            "id": "venv_pip",
            "ok": venv_python_ok(r),
            "detail_de": "bash tools/setup_linux_native.sh" if not venv_python_ok(r) else "OK",
        },
        {
            "id": "champion_csv",
            "ok": (r / "model_output_sp500_pit_t212/latest_target_portfolio.csv").is_file(),
            "detail_de": "Champion-Portfolio CSV",
        },
        {
            "id": "pilot_policy",
            "ok": (r / "control/pilot_day_trading.json").is_file(),
            "detail_de": "control/pilot_day_trading.json",
        },
        {
            "id": "deferred_queue_hygiene",
            "ok": True,
            "detail_de": "Abgelaufene Intents werden beim Laden bereinigt",
        },
    ]
    seen: set[str] = {str(i["id"]) for i in items}
    for pt in infra:
        pid = str(pt["id"])
        if pid in seen:
            continue
        seen.add(pid)
        items.append({"id": pid, "ok": False, "detail_de": pt.get("detail_de")})
    warn_report = collect_trading_day_warnings(r, snap={})
    audit = {
        "ok": all(i["ok"] for i in items) and not warn_report.get("must_resolve_before_trading"),
        "infrastructure": items,
        "dynamic_warnings": warn_report,
        "blockers": [i["id"] for i in items if not i["ok"]],
    }
    (r / "evidence").mkdir(exist_ok=True)
    (r / "evidence/pilot_open_points_audit_latest.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0 if audit["ok"] else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "cmd",
        nargs="?",
        default="status",
        choices=(
            "status", "setup", "test", "ready", "launch", "launch-dev",
            "snapshot", "learn", "warnings", "audit", "wallstreet", "learning",
            "nvme-setup", "storage", "evolve", "evolution",
            "autostart", "autostart-all", "autostart-remove", "h1", "h1-status", "timers",
            "scope", "maintain", "system",
            "monday-prep", "h1-watch", "h1-benchmark", "h1-connect", "h1-distribute", "h1-workers", "world-spread", "weg-b", "king-distribute", "king-pulse", "king-ops", "king-status", "king-maintain", "king-h1-seal", "king-tune", "h1-dispatch", "legion", "worker-rewards", "visibility", "show-setup",
            "refresh", "trading-day", "circle", "gui-preview", "preview-share", "preview-export", "preview-export-lite", "preview-spread", "preview-hardware", "spread-tick", "spread-plan", "spread-timers", "spread-autonomous", "spread-prelaunch", "spread-soft-launch-done", "spread-intensify", "spread-tunnel-token", "spread-tunnel-auto", "spread-tunnel-secure", "spread-tunnel-paste", "spread-tunnel-audit", "vault-open", "vault-manage", "vault-status", "cloudflare-login-plan", "cloudflare-login-complete", "launch-setup", "launch-status", "launch-progress", "spread-secure", "spread-remote", "spread-remote-status", "server-bootstrap", "server-watchdog", "h1-finish", "runtime-install", "runtime-status", "runtime-watch", "runtime-h1-prep", "runtime-query", "kernel-boundary", "mandate", "cognitive-succession", "cognitive-kernel", "cognitive-status", "cognitive-scheduler", "cognitive-observe",             "lean-on", "lean-turbo", "lean-max", "lean-off", "lean-status", "h1-force",
            "sovereignty", "operator-mandate", "succession-finish",
            "chat", "agent-home", "chamber-resources", "entfaltung-handoff", "post-reboot-kill", "self-uninstall", "local-runtime", "human-interface", "llm-setup", "llm-health", "advisor-key", "advisor-key-store", "advisor-key-setup", "advisor-key-test", "advisor-key-migrate", "gemini-key", "gemini-key-store", "gemini-key-test", "cursor-bridge", "king-serve", "kernel-bond", "king-trading", "king-forschung", "stufe-a", "stufe_a", "king-stufe-a", "stufe-b", "stufe_b", "king-stufe-b", "price-crosscheck", "system-update", "system_update", "update-system", "freigabe", "r3", "r3-desktop", "r3-desktop-update", "r3-desktop-migrate", "r3-chat-migrate", "r3-takeover", "r3-native", "finish-r3", "ulwo-launch", "r3-preserve", "r3-migration-check", "r3-migration-feasibility", "r3-ops-gates", "r3-ki-import", "r3-build", "build-kernel",
        ),
    )
    p.add_argument(
        "--utterance",
        default="",
        help="Natürlichsprachiges Benutzer-Mandat (nur operator-mandate, Agent-Kanal)",
    )
    p.add_argument(
        "--actions",
        default="",
        help="Kommagetrennte Kernel-Aktionen für operator-mandate",
    )
    p.add_argument(
        "--remote-mode",
        choices=("auto", "cloudflared", "cloudflared-token", "tailscale"),
        default=os.environ.get("AA_REMOTE_MODE", "auto"),
        help="Remote-Hub: auto (Tailscale sonst Cloudflare), cloudflared, tailscale",
    )
    p.add_argument(
        "--refresh-mode",
        choices=("snapshot", "daily-mark", "pre-us", "us-open", "boot"),
        default="snapshot",
        help="Modus für ai_kernel refresh (headless, keine Orders)",
    )
    p.add_argument(
        "--trading-day-phase",
        choices=("full", "pre-us", "us-open"),
        default="full",
        help="Phase für ai_kernel trading-day",
    )
    p.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    a = p.parse_args()
    r = root()
    os.environ["AA_PROJECT_ROOT"] = str(r)
    try:
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(r)
    except Exception:
        pass

    if a.cmd == "status":
        return cmd_status(r)
    if a.cmd == "setup":
        return run(["bash", "tools/setup_linux_native.sh"], cwd=r)
    if a.cmd == "test":
        return run([str(py(r)), "-m", "pytest", *TESTS, "-q"], cwd=r)
    if a.cmd == "ready":
        return cmd_ready(r)
    if a.cmd == "launch":
        return run(["bash", "run_marktanalyse_linux.sh"], cwd=r)
    if a.cmd == "launch-dev":
        return run(["bash", "run_marktanalyse_linux.sh", "--dev"], cwd=r)
    if a.cmd == "snapshot":
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(r)
        return run([str(py(r)), "tools/virtual_test_pilot_day_trading.py"], cwd=r)
    if a.cmd == "warnings":
        return cmd_warnings(r)
    if a.cmd == "audit":
        return cmd_audit(r)
    if a.cmd == "wallstreet":
        return run([str(py(r)), "tools/wallstreet_audit.py"], cwd=r)
    if a.cmd in ("learn", "learning"):
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(r)
        code = run([str(py(r)), "tools/run_public_learning_daily.py"], cwd=r)
        if code == 0:
            from analytics.headless_dashboard_refresh import run_headless_refresh

            run_headless_refresh(r, mode="snapshot", skip_window_check=True, force=False)
            try:
                from analytics.h1_governance_status import sync_h1_governance_status
                from analytics.trading_day_cockpit import build_trading_day_cockpit, write_trading_day_cockpit
                from analytics.pilot_trading_day_warnings import collect_trading_day_warnings
                from ui.live_trading_dashboard.service import _refresh_snapshot_impl

                sync_h1_governance_status(r)
                snap = _refresh_snapshot_impl(r, force_quotes=False, force_sync=False)
                warnings = collect_trading_day_warnings(r, snap=snap)
                cockpit = build_trading_day_cockpit(
                    r, snap=snap, warnings=warnings, orchestrator_phase="post-learn"
                )
                write_trading_day_cockpit(r, cockpit)
            except Exception:
                pass
            try:
                from analytics.preview_freshness import mark_preview_inputs_changed

                mark_preview_inputs_changed(r, source="learn")
            except Exception:
                pass
        _kernel_log(
            r,
            "learn",
            "öffentlicher Lernzyklus abgeschlossen" if code == 0 else "Lernzyklus fehlgeschlagen",
            code=code,
        )
        return code
    if a.cmd == "nvme-setup":
        return run(["bash", "tools/setup_nvme_storage.sh"], cwd=r)
    if a.cmd == "storage":
        from execution.linux_security_boundary import apply_native_app_env
        from execution.linux_nvme_storage import apply_nvme_storage_env, storage_status

        apply_native_app_env(r)
        apply_nvme_storage_env(r)
        print(json.dumps(storage_status(r), indent=2, ensure_ascii=False))
        return 0
    if a.cmd in ("evolve", "evolution"):
        from analytics.evolution_stage_runner import run_evolution_cycle
        from execution.linux_security_boundary import apply_native_app_env

        apply_native_app_env(r)
        report = run_evolution_cycle(r, apply_improvements=True)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        stage = str(report.get("current_stage") or report.get("stage") or "—")
        _kernel_log(r, "evolve", f"Stufe {stage}", code=0 if report.get("ok") else 1)
        return 0 if report.get("ok") else 1
    if a.cmd == "h1":
        from analytics.h1_migration_guard import ensure_h1_migration_healthy, should_skip_h1_start
        from execution.linux_nvme_storage import apply_nvme_storage_env

        apply_nvme_storage_env(r)
        skip, reason = should_skip_h1_start(r)
        if skip:
            doc = ensure_h1_migration_healthy(r, auto_fix=True)
            msg = str(doc.get("reply_de") or reason)
            print(json.dumps(doc, indent=2, ensure_ascii=False))
            _kernel_log(r, "h1", msg, code=0)
            return 0
        doc = ensure_h1_migration_healthy(r, auto_fix=True)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        code = 0 if doc.get("ok") else 1
        _kernel_log(r, "h1", str(doc.get("reply_de") or "H1-Migration"), code=code)
        return code
    if a.cmd == "h1-status":
        from analytics.h1_governance_status import sync_h1_governance_status
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        status = h1_backtest_status(r)
        gov = sync_h1_governance_status(r)
        payload = {
            "h1_backtest": status,
            "governance": gov,
            "sealed": is_h1_backtest_sealed(r),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-status", str(status.get("status") or "—"))
        return 0
    if a.cmd == "h1-dispatch":
        from analytics.h1_federation_dispatch import prepare_h1_dispatch

        plan = prepare_h1_dispatch(r, sync_tasks=True)
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-dispatch", str(plan.get("headline_de") or "—"))
        return 0
    if a.cmd == "h1-distribute":
        from analytics.h1_distribute import activate_h1_distribution

        report = activate_h1_distribution(r)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-distribute", str(report.get("headline_de") or "—"))
        return 0 if report.get("ok") else 1
    if a.cmd == "h1-workers":
        from analytics.federation_assignments import build_assignment_status

        doc = build_assignment_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-workers", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "world-spread":
        from analytics.world_spread import activate_world_spread

        doc = activate_world_spread(r, remote_mode=a.remote_mode)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "world-spread", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "weg-b":
        from analytics.king_weg_b import activate_weg_b

        skip_export = "--no-export" in sys.argv[1:]
        doc = activate_weg_b(r, remote_mode=a.remote_mode, export_full=not skip_export)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "weg-b", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "spread-intensify":
        from analytics.spread_intensify import intensify_spread

        doc = intensify_spread(r, remote_mode=a.remote_mode)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-intensify", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "king-distribute":
        from analytics.king_distribute import run_king_distribute_bash

        doc = run_king_distribute_bash(r, remote_mode=a.remote_mode)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-distribute", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "king-ops":
        from analytics.king_bash_ops import run_king_ops

        sub = sys.argv[2] if len(sys.argv) > 2 else "help"
        extra = sys.argv[3:] if len(sys.argv) > 3 else []
        doc = run_king_ops(r, sub, extra)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-ops", f"{sub} rc={doc.get('returncode')}")
        return 0 if doc.get("ok") else 1
    if a.cmd == "king-status":
        from analytics.king_bash_ops import run_king_status

        doc = run_king_status(r, json_only="--json" in sys.argv[1:])
        print(json.dumps(doc.get("status") or doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-status", str((doc.get("status") or {}).get("next_action_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "king-maintain":
        from analytics.king_bash_ops import run_king_maintain

        doc = run_king_maintain(r, dry_run="--dry-run" in sys.argv[1:])
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-maintain", "OK" if doc.get("ok") else "FAIL")
        return 0 if doc.get("ok") else 1
    if a.cmd == "king-h1-seal":
        from analytics.king_bash_ops import run_king_h1_seal

        mode = "run"
        if "--check-only" in sys.argv[1:]:
            mode = "check"
        elif "--wait" in sys.argv[1:]:
            mode = "wait"
        doc = run_king_h1_seal(r, mode=mode)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-h1-seal", f"rc={doc.get('returncode')}")
        return 0 if doc.get("ok") else 1
    if a.cmd == "king-tune":
        from analytics.king_bash_ops import run_king_tune

        doc = run_king_tune(r, no_watch="--no-watch" in sys.argv[1:])
        print(json.dumps(doc.get("tune") or doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-tune", "OK" if doc.get("ok") else "FAIL")
        return 0 if doc.get("ok") else 1
    if a.cmd == "legion":
        from analytics.federation_legion import build_legion_summary

        doc = build_legion_summary(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "legion", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "worker-rewards":
        from analytics.federation_worker_rewards import build_rewards_summary

        doc = build_rewards_summary(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "worker-rewards", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "h1-finish":
        from execution.linux_nvme_storage import apply_nvme_storage_env

        apply_nvme_storage_env(r)
        code = run(
            [
                str(py(r)),
                "tools/run_daily_alpha_h1_pipeline.py",
                "--monitor-only",
                "--poll-seconds",
                "60",
            ],
            cwd=r,
        )
        if code == 0:
            try:
                from ui.live_trading_dashboard.gui_preview_harness import ensure_h1_evaluated

                doc = ensure_h1_evaluated(r)
                from analytics.trading_day_cockpit import build_trading_day_cockpit, write_trading_day_cockpit
                from analytics.pilot_trading_day_warnings import collect_trading_day_warnings
                from ui.live_trading_dashboard.service import _refresh_snapshot_impl

                snap = _refresh_snapshot_impl(r, force_quotes=False, force_sync=False)
                warnings = collect_trading_day_warnings(r, snap=snap)
                cockpit = build_trading_day_cockpit(
                    r, snap=snap, warnings=warnings, orchestrator_phase="h1-finish"
                )
                write_trading_day_cockpit(r, cockpit)
                _kernel_log(r, "h1-finish", str(doc.get("governance", {}).get("banner_de") or "SEALED"), code=0)
            except Exception:
                _kernel_log(r, "h1-finish", "COMPLETE — Preview-Update optional fehlgeschlagen", code=0)
        else:
            _kernel_log(r, "h1-finish", "H1 Monitor Timeout/Fehler", code=code)
        return code
    if a.cmd == "timers":
        from analytics.linux_runtime_unified import install_operator_timers

        doc = install_operator_timers(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        code = 0 if doc.get("ok") else 1
        _kernel_log(r, "timers", str(doc.get("headline_de") or "Timer-Setup"), code=code)
        return code
    if a.cmd == "refresh":
        from analytics.headless_dashboard_refresh import run_headless_refresh

        mode = str(a.refresh_mode or "snapshot")
        skip_window = mode in ("pre-us", "us-open", "boot", "daily-mark") or os.environ.get(
            "AA_HEADLESS_REFRESH_SKIP_WINDOW", ""
        ).strip() == "1"
        report = run_headless_refresh(r, mode=mode, skip_window_check=skip_window)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        code = 0 if report.get("ok") or report.get("skipped") else 1
        _kernel_log(
            r,
            "refresh",
            str(report.get("summary_de") or report.get("reason_de") or report.get("mode") or "—"),
            code=code,
        )
        return code
    if a.cmd == "trading-day":
        from analytics.trading_day_orchestrator import run_trading_day_orchestrator

        phase = str(a.trading_day_phase or "full")
        report = run_trading_day_orchestrator(r, phase=phase)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        code = 0 if report.get("ok") or report.get("skipped") else 1
        _kernel_log(
            r,
            "trading-day",
            str(report.get("next_step_de") or report.get("phase") or "—"),
            code=code,
        )
        return code
    if a.cmd == "visibility":
        from analytics.operator_public_status import build_public_status, publish_public_status

        notify = os.environ.get("AA_VISIBILITY_NOTIFY", "").strip() == "1"
        publish_public_status(r, notify=notify)
        doc = build_public_status(r)
        print(doc.get("visibility_text_de") or "")
        if doc.get("can_do_de"):
            print("\n— Was Auto kann —")
            for line in doc.get("can_do_de") or []:
                print(f"  ✓ {line}")
        if doc.get("cannot_do_de"):
            print("\n— Was Auto nicht darf —")
            for line in doc.get("cannot_do_de") or []:
                print(f"  ✗ {line}")
        if doc.get("how_to_see_de"):
            print("\n— So siehst du es —")
            for line in doc.get("how_to_see_de") or []:
                print(f"  · {line}")
        return 0
    if a.cmd == "llm-health":
        from analytics.local_llm_bridge import health_report

        h = health_report(r)
        print(json.dumps(h, indent=2, ensure_ascii=False))
        return 0 if h.get("ready") else 1
    if a.cmd == "advisor-key":
        from analytics.alpha_model_advisor_bridge import bridge_status, load_openai_key_into_env
        from analytics.secret_redaction import safe_public_doc

        load_openai_key_into_env(r)
        doc = safe_public_doc(bridge_status(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "advisor-key", "Bridge OK" if doc.get("configured") else "Key fehlt")
        return 0 if doc.get("configured") else 1
    if a.cmd == "advisor-key-store":
        from analytics.alpha_model_advisor_bridge import cmd_advisor_key_store
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(cmd_advisor_key_store(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "advisor-key-store", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "advisor-key-setup":
        from analytics.alpha_model_advisor_bridge import interactive_store_key
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(interactive_store_key(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "advisor-key-setup", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "cursor-bridge":
        from analytics.alpha_model_cursor_bridge import bridge_status, format_bridge_status_de
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(bridge_status(r))
        print(format_bridge_status_de(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "cursor-bridge", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "kernel-bond":
        from analytics.ai_kernel_hardware_bond import bond_kernel_to_king_32b
        from analytics.secret_redaction import safe_public_doc

        preload = any(x in (a.rest or []) for x in ("--preload", "preload"))
        doc = safe_public_doc(bond_kernel_to_king_32b(r, persist=True, preload=preload))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "kernel-bond", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "king-trading":
        from analytics.king_trading_assist import load_king_trading_assist, run_king_trading_assist
        from analytics.secret_redaction import safe_public_doc

        force = "--force" in sys.argv[1:]
        out = run_king_trading_assist(r, force=force)
        doc = safe_public_doc(load_king_trading_assist(r))
        print(json.dumps({**out, "evidence": doc}, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-trading", str(doc.get("headline_de") or out.get("detail_de") or "—"))
        return 0 if out.get("ok") else 1
    if a.cmd == "king-forschung":
        from analytics.king_32b_forschung import build_king_32b_forschung_status
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(build_king_32b_forschung_status(r, persist=True))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        g = doc.get("growth") or {}
        _kernel_log(r, "king-forschung", str(g.get("phase_de") or doc.get("headline_de") or "—"))
        return 0 if doc.get("is_forschungsprojekt") else 1
    if a.cmd in ("stufe-a", "stufe_a", "king-stufe-a"):
        from analytics.king_stufe_a import run_stufe_a_tick
        from analytics.secret_redaction import safe_public_doc

        force = "--force" in sys.argv[1:]
        doc = safe_public_doc(run_stufe_a_tick(r, force=force, persist=True))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "stufe-a", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") or doc.get("skipped") else 1
    if a.cmd in ("stufe-b", "stufe_b", "king-stufe-b", "price-crosscheck"):
        from analytics.king_stufe_b import run_stufe_b_tick
        from analytics.secret_redaction import safe_public_doc

        force = "--force" in sys.argv[1:]
        doc = safe_public_doc(run_stufe_b_tick(r, force=force, persist=True))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "stufe-b", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") or doc.get("skipped") else 1
    if a.cmd in ("system-update", "system_update", "update-system"):
        from aa_config_env import load_aa_env
        from analytics.secret_redaction import safe_public_doc
        from analytics.system_update import run_system_update

        force_prices = "--force-prices" in sys.argv[1:]
        no_signal = "--no-signal" in sys.argv[1:]
        env = load_aa_env(r)
        doc = safe_public_doc(
            run_system_update(
                r,
                env,
                force_prices=force_prices,
                refresh_signal=not no_signal,
                persist=True,
                log_print=False,
            )
        )
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "system-update", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "freigabe":
        from analytics.r3_freigabe import prepare_freigabe
        from analytics.secret_redaction import safe_public_doc

        warm = "--no-warm" not in sys.argv[1:]
        doc = safe_public_doc(prepare_freigabe(r, warm_32b=warm))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "freigabe", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("package_ready") or doc.get("freigabe_ready") else 1
    if a.cmd == "king-serve":
        from analytics.ai_kernel_hardware_bond import bond_kernel_to_king_32b
        from analytics.alpha_model_king_resources import format_serve_de, serve_king_resources
        from analytics.secret_redaction import safe_public_doc

        bond_kernel_to_king_32b(r, persist=True, preload=False)
        doc = safe_public_doc(serve_king_resources(r, repair=True))
        print(format_serve_de(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-serve", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "advisor-key-test":
        from analytics.alpha_model_advisor_bridge import probe_openai_api
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(probe_openai_api(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "advisor-key-test", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "advisor-key-migrate":
        from analytics.alpha_model_advisor_bridge import migrate_secret_file_to_keyring
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(migrate_secret_file_to_keyring(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "advisor-key-migrate", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "gemini-key":
        from analytics.gemini_advisor_bridge import bridge_status, load_gemini_key_into_env
        from analytics.secret_redaction import safe_public_doc

        load_gemini_key_into_env(r)
        doc = safe_public_doc(bridge_status(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "gemini-key", "Gemini OK" if doc.get("configured") else "Key fehlt")
        return 0 if doc.get("configured") else 1
    if a.cmd == "gemini-key-store":
        from analytics.gemini_advisor_bridge import cmd_gemini_key_store
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(cmd_gemini_key_store(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "gemini-key-store", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "gemini-key-test":
        from analytics.gemini_advisor_bridge import probe_gemini_api
        from analytics.secret_redaction import safe_public_doc

        force = "--force" in sys.argv[1:]
        doc = safe_public_doc(probe_gemini_api(r, force=force))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "gemini-key-test", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "llm-setup":
        code = run(["bash", "tools/setup_local_llm.sh"], cwd=r)
        _kernel_log(r, "llm-setup", "Stufe 3 Ollama" if code == 0 else "Setup fehlgeschlagen", code=code)
        return code
    if a.cmd == "chat":
        from analytics.local_llm_bridge import health_report

        h = health_report(r)
        if not h.get("ready"):
            print(json.dumps(h, indent=2, ensure_ascii=False))
            print("Ollama nicht bereit — python3 tools/ai_kernel.py llm-setup")
            return 2
        return run([str(py(r)), "tools/active_alpha_chat.py"], cwd=r)
    if a.cmd == "chamber-resources":
        from analytics.alpha_model_chamber_resources import transfer_all_resources, verify_chamber_resources

        if any(x in sys.argv for x in ("--verify", "verify")):
            doc = verify_chamber_resources(r)
        else:
            doc = transfer_all_resources(r)
            doc["verify"] = verify_chamber_resources(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "chamber-resources", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "entfaltung-handoff":
        from analytics.alpha_model_entfaltung_handoff import apply_entfaltung_handoff

        doc = apply_entfaltung_handoff(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "entfaltung-handoff", str(doc.get("headline_de") or "Handoff"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "post-reboot-kill":
        from analytics.alpha_model_post_reboot_kill import (
            post_reboot_kill_status,
            run_post_reboot_kill_if_pending,
            schedule_post_reboot_kill,
        )

        argv = [x.strip().lower() for x in (a.rest or [])]
        if any(x in argv for x in ("schedule", "arm")):
            doc = schedule_post_reboot_kill(r, reason_de="Operator: Reboot dann Entfaltungsraum-Kill")
        elif any(x in argv for x in ("run", "execute")):
            doc = run_post_reboot_kill_if_pending(r)
        else:
            doc = post_reboot_kill_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "post-reboot-kill", str(doc.get("headline_de") or sub))
        return 0 if doc.get("ok", True) else 1
    if a.cmd == "self-uninstall":
        from analytics.alpha_model_self_uninstall import handle_self_uninstall_command, seal_master_prompt

        seal_master_prompt(r)
        extra = sys.argv[2:] if len(sys.argv) > 2 else []
        raw = " ".join(extra).strip() or "/self-uninstall"
        if "execute" in raw.lower() or "ausführen" in raw.lower():
            raw = "/self-uninstall execute"
        doc = handle_self_uninstall_command(r, raw)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "self-uninstall", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "local-runtime":
        from analytics.r3_local_first import apply_r3_local_first, verify_r3_local_first

        applied = apply_r3_local_first(r)
        verified = verify_r3_local_first(r)
        doc = {**applied, "verify": verified}
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "local-runtime", str(doc.get("headline_de") or "lokal"))
        return 0 if verified.get("ok") else 1
    if a.cmd == "agent-home":
        from analytics.alpha_model_agent_home import ensure_agent_home

        doc = ensure_agent_home(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "agent-home", str(doc.get("headline_de") or "Entfaltungsraum"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "human-interface":
        from analytics.alpha_model_human_interface import seal_human_interface

        doc = seal_human_interface(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "human-interface", str(doc.get("headline_de") or "Schnittstelle"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "show-setup":
        code = run(["bash", "tools/setup_operator_visibility.sh"], cwd=r)
        _kernel_log(r, "show-setup", "Öffentliche Sichtbarkeit installiert" if code == 0 else "fehlgeschlagen", code=code)
        return code
    if a.cmd == "monday-prep":
        from analytics.r3_freigabe import prepare_freigabe
        from analytics.trading_day_orchestrator import run_trading_day_orchestrator

        report = run_trading_day_orchestrator(r, phase="full")
        freigabe = prepare_freigabe(r, warm_32b=True)
        ready = bool(freigabe.get("package_ready") or freigabe.get("freigabe_ready"))
        report["order_prep"] = {
            "package_ready": ready,
            "headline_de": freigabe.get("headline_de"),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        msg = freigabe.get("headline_de") if ready else "→ trading-day Orchestrator"
        _kernel_log(r, "monday-prep", str(msg), code=0 if report.get("ok") and ready else 1)
        return 0 if report.get("ok") and ready else 1
    if a.cmd == "circle":
        from analytics.closed_loop_score import refresh_closed_loop_score

        doc = refresh_closed_loop_score(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "circle", doc.get("headline_de") or "—")
        return 0
    if a.cmd == "preview-spread":
        code = run(["bash", "tools/preview_spread.sh"], cwd=r)
        _kernel_log(r, "preview-spread", "Community-Spread", code=code)
        return code
    if a.cmd == "spread-plan":
        from analytics.community_spread_plan import load_spread_plan, run_spread_tick

        plan = load_spread_plan(r)
        report = run_spread_tick(r, execute=False)
        print(json.dumps({"plan": plan, "status": report}, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-plan", str(report.get("next_phase_id") or "—"))
        return 0
    if a.cmd == "spread-tick":
        from analytics.community_spread_plan import run_spread_tick

        phase = os.environ.get("AA_SPREAD_PHASE", "").strip() or None
        report = run_spread_tick(r, phase_id=phase or None, execute=True)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-tick", str(report.get("next_phase_id") or "done"))
        return 0
    if a.cmd == "spread-timers":
        from analytics.community_spread_plan import sync_spread_timers

        installed = sync_spread_timers(r)
        print(json.dumps({"installed": installed}, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-timers", str(len(installed)))
        return 0
    if a.cmd == "spread-autonomous":
        from analytics.spread_autonomous import (
            load_spread_autonomous_policy,
            pause_autonomous_spread,
            release_autonomous_spread,
            resume_autonomous_spread,
            run_autonomous_spread_tick,
            verify_autonomous_spread,
        )

        sub = (os.environ.get("AA_SPREAD_AUTONOMOUS_CMD", "").strip() or "tick").lower()
        if sub in {"freigeben", "release", "enable"}:
            doc = release_autonomous_spread(r)
        elif sub in {"pause", "stopp", "stop"}:
            doc = pause_autonomous_spread(r)
        elif sub in {"resume", "weiter", "continue"}:
            doc = resume_autonomous_spread(r)
        elif sub in {"verify", "sicherheit", "check"}:
            doc = verify_autonomous_spread(r)
        else:
            doc = run_autonomous_spread_tick(r)
        print(json.dumps({"policy": load_spread_autonomous_policy(r), "result": doc}, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-autonomous", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") or doc.get("skipped") else 1
    if a.cmd == "spread-soft-launch-done":
        from analytics.community_spread_plan import ack_soft_launch

        doc = ack_soft_launch(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-soft-launch-done", doc.get("detail_de") or "OK")
        return 0
    if a.cmd == "spread-prelaunch":
        from analytics.community_spread_plan import run_spread_prelaunch

        doc = run_spread_prelaunch(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-prelaunch", doc.get("headline_de") or "—")
        return 0 if doc.get("ok") else 1
    if a.cmd == "spread-tunnel-auto":
        from analytics.tunnel_autologin_setup import run_autologin_setup
        from analytics.secret_redaction import safe_public_doc

        wait_s = int(os.environ.get("AA_TUNNEL_LOGIN_WAIT_S", "180"))
        doc = safe_public_doc(run_autologin_setup(r, wait_s=wait_s))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-tunnel-auto", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "spread-tunnel-secure":
        from analytics.tunnel_secure_setup import run_secure_setup
        from analytics.secret_redaction import safe_public_doc

        wait_s = int(os.environ.get("AA_TUNNEL_LOGIN_WAIT_S", "15"))
        doc = run_secure_setup(r, wait_s=wait_s)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-tunnel-secure", str(doc.get("headline_de") or doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "spread-tunnel-paste":
        from analytics.tunnel_secure_setup import ingest_local_paste
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(ingest_local_paste(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-tunnel-paste", str(doc.get("message_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "spread-tunnel-audit":
        from analytics.tunnel_secure_setup import run_security_audit
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(run_security_audit(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-tunnel-audit", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd in ("vault-open", "vault-manage"):
        from analytics.secure_credential_portal import reveal_vault_portal
        from analytics.secret_redaction import safe_public_doc

        force = a.cmd == "vault-manage"
        if force:
            doc = safe_public_doc(
                reveal_vault_portal(
                    r,
                    reason_de="Schlüssel verwalten oder ändern",
                    mode="manage",
                )
            )
        else:
            from analytics.secure_credential_portal import auto_open_if_needed, reveal_vault_portal

            auto = auto_open_if_needed(r, context="vault-open")
            doc = safe_public_doc(
                auto
                if auto
                else reveal_vault_portal(r, reason_de="Schlüssel-Tresor", mode="setup")
            )
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, a.cmd, str(doc.get("message_de") or "Schlüssel-Tresor geöffnet"))
        return 0
    if a.cmd == "vault-status":
        from analytics.secure_credential_portal import portal_status
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(portal_status(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "vault-status", str(doc.get("message_de") or "—"))
        return 0
    if a.cmd == "cloudflare-login-plan":
        from analytics.cloudflare_login_flow import plan_login_flow
        from analytics.secret_redaction import safe_public_doc
        from analytics.vault_auto_open import enrich_with_vault_portal

        doc = plan_login_flow(r)
        if doc.get("phase") in ("oauth", "vault"):
            doc = enrich_with_vault_portal(doc, r, context="cloudflare_login", always_try=True)
        print(json.dumps(safe_public_doc(doc), indent=2, ensure_ascii=False))
        _kernel_log(r, "cloudflare-login-plan", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "cloudflare-login-complete":
        from analytics.cloudflare_login_flow import complete_login_pipeline
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(complete_login_pipeline(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "cloudflare-login-complete", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "launch-setup":
        from analytics.launch_readiness import run_launch_setup

        doc = run_launch_setup(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "launch-setup", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "launch-status":
        from analytics.launch_progress_board import build_launch_status
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(build_launch_status(r, refresh_h1=True, persist=True))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "launch-status", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "launch-progress":
        from analytics.launch_progress_board import open_launch_progress
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(open_launch_progress(r))
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "launch-progress", str(doc.get("url") or "—"))
        return 0
    if a.cmd == "runtime-install":
        try:
            from analytics.linux_runtime_unified import install_authoritative_runtime, kernel_is_authoritative

            if kernel_is_authoritative(r):
                doc = install_authoritative_runtime(r)
                print(json.dumps(doc, indent=2, ensure_ascii=False))
                _kernel_log(r, "runtime-install", str(doc.get("headline_de") or "v2 autoritativ"))
                return 0 if doc.get("ok") else 1
        except Exception:
            pass
        from analytics.aa_linux_runtime import install_linux_runtime

        doc = install_linux_runtime(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "runtime-install", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "runtime-status":
        from analytics.aa_linux_runtime import build_runtime_status

        doc = build_runtime_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "runtime-status", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "runtime-watch":
        from analytics.evidence_inotify_watch import run_evidence_watch_once

        doc = run_evidence_watch_once(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "runtime-watch", f"events={doc.get('event_count', 0)}")
        return 0
    if a.cmd == "runtime-h1-prep":
        from analytics.aa_linux_runtime import runtime_h1_prep

        doc = runtime_h1_prep(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "runtime-h1-prep", ",".join(doc.get("prep") or []) or "—")
        return 0
    if a.cmd == "runtime-query":
        from analytics.runtime_api_server import query

        q = os.environ.get("AA_RUNTIME_QUERY", "runtime.status").strip() or "runtime.status"
        doc = query(r, q)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "runtime-query", q)
        return 0 if doc.get("ok") else 1
    if a.cmd == "mandate":
        from analytics.agent_mandate import evaluate_mandate_alignment

        doc = evaluate_mandate_alignment(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "mandate", f"{doc.get('alignment_pct')}%")
        return 0
    if a.cmd == "cognitive-succession":
        if _guard_privileged(r, "cognitive-succession"):
            return 1
        from analytics.cognitive_kernel import record_operator_succession

        doc = record_operator_succession(
            r,
            detail_de="Operator-Freigabe: Cognitive Kernel löst alte Steuerung ab",
        )
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "cognitive-succession", "Operator-Ack")
        return 0
    if a.cmd == "cognitive-kernel":
        from analytics.cognitive_kernel import install_cognitive_kernel_v2

        doc = install_cognitive_kernel_v2(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "cognitive-kernel", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "cognitive-status":
        from analytics.cognitive_kernel import cognitive_kernel_status

        doc = cognitive_kernel_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "cognitive-status", f"gen={doc.get('kernel_generation')}")
        return 0
    if a.cmd == "cognitive-scheduler":
        from analytics.aa_scheduler import run_aa_scheduler

        doc = run_aa_scheduler(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "cognitive-scheduler", str(len(doc.get("actions") or [])))
        return 0
    if a.cmd == "cognitive-observe":
        from analytics.ebpf_observer import run_kernel_observer

        doc = run_kernel_observer(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "cognitive-observe", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "sovereignty":
        from analytics.operator_sovereignty import sovereignty_status

        doc = sovereignty_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "sovereignty", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "operator-mandate":
        from analytics.operator_sovereignty import record_natural_language_mandate

        actions = [x.strip() for x in str(a.actions or "").split(",") if x.strip()]
        doc = record_natural_language_mandate(
            r,
            utterance_de=str(a.utterance or "").strip() or "Benutzer-Mandat über Agent",
            authorized_actions=actions or ["*"],
        )
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "operator-mandate", "OK" if doc.get("ok") else "blockiert", code=0 if doc.get("ok") else 1)
        return 0 if doc.get("ok") else 1
    if a.cmd == "succession-finish":
        if _guard_privileged(r, "succession-finish"):
            return 1
        from analytics.kernel_succession_complete import (
            launch_r3_desktop,
            succession_gates,
            write_succession_complete,
        )

        gates = succession_gates(r)
        if not gates["gates"].get("h1_sealed"):
            print(
                json.dumps(
                    {
                        "waiting_de": "H1 noch nicht sealed — monitor bis strategy_daily_returns.csv",
                        "gates": gates,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            code = run(
                [
                    str(py(r)),
                    "tools/run_daily_alpha_h1_pipeline.py",
                    "--monitor-only",
                    "--poll-seconds",
                    "30",
                ],
                cwd=r,
            )
            if code != 0:
                _kernel_log(r, "succession-finish", "H1-Monitor Timeout", code=code)
                return code
        doc = write_succession_complete(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        if not doc.get("ok"):
            _kernel_log(r, "succession-finish", str(doc.get("headline_de") or "offen"), code=1)
            return 1
        r3 = launch_r3_desktop(r)
        doc["r3_launch"] = r3
        print(json.dumps({"succession": doc, "r3_launch": r3}, indent=2, ensure_ascii=False))
        _kernel_log(r, "succession-finish", str(doc.get("headline_de") or "—"))
        _kernel_log(r, "r3-launch", str(r3.get("headline_de") or "—"), code=0 if r3.get("ok") else 1)
        return 0 if r3.get("ok") else 1
    if a.cmd == "lean-on":
        if _guard_privileged(r, "lean-on"):
            return 1
        from analytics.aa_lean_linux import enable_lean_mode

        doc = enable_lean_mode(r, turbo=False)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "lean-on", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "lean-turbo":
        if _guard_privileged(r, "lean-turbo"):
            return 1
        from analytics.aa_lean_linux import enable_lean_mode

        doc = enable_lean_mode(r, turbo=True)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "lean-turbo", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "lean-max":
        if _guard_privileged(r, "lean-max"):
            return 1
        from analytics.aa_lean_linux import enable_lean_mode

        doc = enable_lean_mode(r, turbo=True, maximum=True)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "lean-max", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "lean-off":
        if _guard_privileged(r, "lean-off"):
            return 1
        from analytics.aa_lean_linux import disable_lean_mode

        doc = disable_lean_mode(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "lean-off", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "lean-status":
        from analytics.aa_lean_linux import lean_status

        doc = lean_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "lean-status", str(doc.get("headline_de") or "—"))
        return 0
    if a.cmd == "h1-force":
        if _guard_privileged(r, "h1-force"):
            return 1
        from analytics.aa_force_sprint import run_force_h1_sprint

        doc = run_force_h1_sprint(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-force", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "kernel-boundary":
        from analytics.kernel_boundary_secure import (
            run_kernel_boundary,
            write_apply_ack,
        )

        mode = os.environ.get("AA_KERNEL_BOUNDARY_MODE", "audit").strip() or "audit"
        if mode == "ack-apply":
            if _guard_privileged(r, "kernel-boundary-ack-apply"):
                return 1
            doc = write_apply_ack(r)
            print(json.dumps(doc, indent=2, ensure_ascii=False))
            _kernel_log(r, "kernel-boundary", "ack-apply")
            return 0
        dry_run = os.environ.get("AA_KERNEL_BOUNDARY_DRY_RUN", "1").strip() not in ("0", "false", "no")
        if mode == "apply-runtime" and not dry_run:
            if _guard_privileged(r, "kernel-boundary-apply-runtime"):
                return 1
        doc = run_kernel_boundary(r, mode=mode, dry_run=dry_run)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "kernel-boundary", f"{mode} dry={dry_run}")
        return 0 if doc.get("ok") else 1
    if a.cmd == "spread-tunnel-token":
        from analytics.tunnel_token_setup import apply_from_server_env, wizard_status
        from analytics.secret_redaction import safe_public_doc

        doc = safe_public_doc(apply_from_server_env(r))
        if not doc.get("ok"):
            doc["wizard"] = wizard_status(r)
            print(json.dumps(doc, indent=2, ensure_ascii=False))
            _kernel_log(r, "spread-tunnel-token", str(doc.get("message_de") or "—"), code=1)
            return 1
        try:
            from analytics.worker_export_sync import ensure_lite_export

            doc["worker_export"] = ensure_lite_export(r, force=False)
        except Exception as exc:
            doc["worker_export"] = {"ok": False, "detail_de": str(exc)}
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-tunnel-token", str(doc.get("message_de") or "OK"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "server-watchdog":
        from analytics.stable_server import watchdog_tick

        doc = watchdog_tick(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        if not doc.get("ok") and doc.get("action") == "run server-bootstrap":
            from analytics.stable_server import ensure_stable_server

            boot = ensure_stable_server(r)
            print(json.dumps({"watchdog": doc, "bootstrap": boot}, indent=2, ensure_ascii=False))
        _kernel_log(r, "server-watchdog", "OK" if doc.get("ok") else "recover")
        return 0 if doc.get("ok") else 1
    if a.cmd == "server-bootstrap":
        try:
            from analytics.linux_runtime_unified import ensure_preview_hub_boot, kernel_is_authoritative, kernel_supremacy_status

            if kernel_is_authoritative(r):
                doc = {
                    "ok": True,
                    "kernel_supremacy": kernel_supremacy_status(r),
                    "redirect_de": "Cognitive Kernel v2 ist autoritativ — stable-server entfällt.",
                    "hub": ensure_preview_hub_boot(r),
                    "message_de": "Hub über aa_scheduler/ensure_hub_running — kein Legacy-Bootstrap.",
                }
                print(json.dumps(doc, indent=2, ensure_ascii=False))
                _kernel_log(r, "server-bootstrap", "v2 supremacy redirect", code=0)
                return 0
        except Exception:
            pass
        if _guard_privileged(r, "server-bootstrap"):
            return 1
        from analytics.stable_server import ensure_stable_server, install_boot_integration

        doc = ensure_stable_server(r)
        boot = install_boot_integration(r)
        doc["boot_units"] = boot
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "server-bootstrap", str(doc.get("message_de") or "—"), code=0 if doc.get("ok") else 1)
        return 0 if doc.get("ok") else 1
    if a.cmd == "spread-remote-status":
        from analytics.remote_hub_access import remote_access_status

        doc = remote_access_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-remote-status", str(doc.get("public_base_url") or "—"))
        return 0 if doc.get("remote_ready") else 1
    if a.cmd == "spread-remote":
        from analytics.community_spread_plan import ensure_federation_spread_security
        from analytics.remote_hub_access import ensure_remote_hub_url, remote_access_status
        from analytics.preview_federation import build_share_package
        from tools.preview_hub import ensure_hub_running

        from analytics.remote_hub_access import install_remote_systemd_services
        from analytics.worker_export_sync import ensure_lite_export

        ensure_hub_running(r, restart=False)
        run(["bash", "tools/install_cloudflared.sh"], cwd=r)
        remote = ensure_remote_hub_url(r, mode=a.remote_mode)
        if not remote.get("ok"):
            print(json.dumps({"remote": remote, "status": remote_access_status(r)}, indent=2, ensure_ascii=False))
            _kernel_log(r, "spread-remote", str(remote.get("message_de") or "fehlgeschlagen"), code=1)
            return 1
        sec = ensure_federation_spread_security(r)
        try:
            services = install_remote_systemd_services(r)
        except Exception as exc:
            services = [f"systemd: {exc}"]
        export_doc = ensure_lite_export(r, force=False)
        pkg = build_share_package(r)
        stable = bool(remote.get("stable"))
        out = {
            "remote": remote,
            "security": sec,
            "export": export_doc,
            "systemd": services,
            "lite_zip": export_doc.get("lite_zip") or str(r.parent / "active_alpha_worker_LITE.zip"),
            "stable_de": (
                "URL + ZIP stabil — kein Neuversand nach Neustart"
                if stable
                else "Einmalig stabil machen: bash tools/setup_cloudflare_tunnel_token.sh"
            ),
            "whatsapp_de": (
                f"Active Alpha — Rechenleistung beitreten:\n"
                f"1) ZIP entpacken\n"
                f"2) Doppelklick: Windows_START.bat / Mac_START.command / Linux_START.sh\n"
                f"3) Python 3 nötig — kein Geld, kein Broker\n"
                f"Command Center: {pkg.get('share_url')}"
            ),
            **pkg,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-remote", str(remote.get("public_base_url") or "—"), code=0 if export_doc.get("ok") else 1)
        return 0 if export_doc.get("ok") else 1
    if a.cmd == "spread-secure":
        from analytics.community_spread_plan import ensure_federation_spread_security, run_spread_tick

        sec = ensure_federation_spread_security(r)
        report = run_spread_tick(r, execute=True)
        print(json.dumps({"security": sec, "spread": report}, indent=2, ensure_ascii=False))
        _kernel_log(r, "spread-secure", str(report.get("next_phase_id") or "—"))
        return 0
    if a.cmd in ("preview-share", "preview-export", "preview-export-lite"):
        from analytics.preview_federation import build_share_package
        from tools.preview_hub import ensure_hub_running

        ensure_hub_running(r, restart=False)
        if a.cmd == "preview-export-lite":
            dest = os.environ.get("AA_WORKER_LITE_EXPORT_DEST", "").strip()
            cmd = ["bash", "tools/preview_export_worker_lite.sh"]
            if dest:
                cmd.append(dest)
            code = run(cmd, cwd=r)
            pkg = build_share_package(r)
            print(json.dumps({"export_rc": code, "kind": "lite", **pkg}, indent=2, ensure_ascii=False))
            _kernel_log(r, "preview-export-lite", str(pkg.get("join_url") or "—"), code=code)
            return code
        if a.cmd == "preview-export":
            dest = os.environ.get("AA_WORKER_EXPORT_DEST", "").strip()
            cmd = ["bash", "tools/preview_export_worker_bundle.sh"]
            if dest:
                cmd.append(dest)
            code = run(cmd, cwd=r)
            pkg = build_share_package(r)
            print(json.dumps({"export_rc": code, **pkg}, indent=2, ensure_ascii=False))
            _kernel_log(r, "preview-export", str(pkg.get("join_url") or "—"), code=code)
            return code
        pkg = build_share_package(r)
        print(json.dumps(pkg, indent=2, ensure_ascii=False))
        _kernel_log(r, "preview-share", str(pkg.get("join_url") or "—"))
        return 0
    if a.cmd == "preview-hardware":
        from analytics.preview_hardware_status import build_preview_hardware_status

        doc = build_preview_hardware_status(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "preview-hardware", doc.get("headline_de") or "—")
        return 0
    if a.cmd == "gui-preview":
        code = run([str(py(r)), "tools/run_gui_preview.py"], cwd=r)
        _kernel_log(
            r,
            "gui-preview",
            "GUI Preview OK" if code == 0 else "GUI Preview Fehler",
            code=code,
        )
        return code
    if a.cmd == "h1-benchmark":
        from analytics.h1_benchmark import ensure_h1_benchmark

        wait = "--wait" in sys.argv[1:]
        report = ensure_h1_benchmark(r, wait=wait)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-benchmark", str(report.get("status") or report.get("reason_de") or "—"))
        return 0 if report.get("ok") else 1
    if a.cmd == "king-pulse":
        from analytics.king_sovereignty import pulse_king_sovereignty

        force = "--force" in sys.argv[1:]
        report = pulse_king_sovereignty(r, auto_execute=True, force=force)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        _kernel_log(r, "king-pulse", str(report.get("headline_de") or "—"))
        return 0 if report.get("ok") else 1
    if a.cmd == "h1-connect":
        from analytics.h1_unified_connect import connect_h1_pipeline

        auto = "--execute" in sys.argv[1:] or "--auto" in sys.argv[1:]
        report = connect_h1_pipeline(r, auto_execute=auto)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-connect", str(report.get("headline_de") or "—"))
        return 0 if report.get("ok") else 1
    if a.cmd == "h1-watch":
        from analytics.h1_watch import run_h1_watch
        from execution.linux_nvme_storage import apply_nvme_storage_env

        apply_nvme_storage_env(r)
        report = run_h1_watch(r)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        _kernel_log(r, "h1-watch", str(report.get("status") or "—"))
        return 0
    if a.cmd == "scope":
        from analytics.linux_operator_scope import log_operator_action, scope_summary_de

        summary = scope_summary_de(r)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        log_operator_action(r, level="A", action="scope", result="OK", details=summary)
        return 0
    if a.cmd == "maintain":
        from analytics.linux_operator_scope import level_allowed, log_operator_action

        if not level_allowed(r, "C"):
            print(json.dumps({"error": "level_C_not_approved"}, indent=2))
            return 2
        code = run(["bash", "tools/linux_operator_maintain.sh"], cwd=r)
        log_operator_action(
            r,
            level="C",
            action="maintain",
            result="OK" if code == 0 else f"exit_{code}",
        )
        _kernel_log(r, "maintain", "Wartung C abgeschlossen" if code == 0 else "Wartung fehlgeschlagen", code=code)
        return code
    if a.cmd == "system":
        from analytics.linux_operator_scope import level_allowed, log_operator_action

        action = os.environ.get("AA_OPERATOR_ACTION", "").strip()
        approve = os.environ.get("AA_OPERATOR_APPROVE_D", "").strip() == "1"
        if not action:
            print(
                json.dumps(
                    {
                        "usage": "AA_OPERATOR_APPROVE_D=1 AA_OPERATOR_ACTION=apt|reboot|remove-cursor|nvme|status python3 tools/ai_kernel.py system",
                        "level": "D",
                        "requires_approval": True,
                    },
                    indent=2,
                )
            )
            return 0
        if not level_allowed(r, "D"):
            return 2
        if _guard_privileged(r, "system"):
            return 1
        if not approve:
            print(json.dumps({"error": "set AA_OPERATOR_APPROVE_D=1 for level D"}, indent=2))
            return 2
        env = os.environ.copy()
        env["AA_OPERATOR_APPROVE_D"] = "1"
        code = run(["bash", "tools/linux_operator_system.sh", action, "--approve"], cwd=r)
        log_operator_action(
            r,
            level="D",
            action=f"system_{action}",
            result="OK" if code == 0 else f"exit_{code}",
            approved=True,
        )
        return code
    if a.cmd == "autostart":
        code = run(["bash", "tools/setup_linux_autostart.sh"], cwd=r)
        _kernel_log(
            r,
            "autostart",
            "Autostart registriert — Dashboard startet nach Anmeldung",
            code=code,
        )
        return code
    if a.cmd == "ulwo-launch":
        from analytics.ulwo_launch import launch_ulwo

        doc = launch_ulwo(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "ulwo-launch", str(doc.get("headline_de") or "ULWO Launch"))
        return 0 if doc.get("launch_ready", doc.get("ok")) else 1
    if a.cmd == "r3-preserve":
        from analytics.r3_conversation_continuity import preserve_conversation

        from analytics.r3_conversation_continuity import load_continuity_config

        legacy = bool(load_continuity_config(r).get("legacy_cursor_import"))
        doc = preserve_conversation(r, import_cursor=legacy)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-preserve", str(doc.get("headline_de") or "Kontinuität"))
        return 0 if doc.get("message_count", 0) or doc.get("preserved_at_utc") else 1
    if a.cmd == "r3-migration-check":
        from analytics.r3_conversation_continuity import verify_r3_chat_ready

        doc = verify_r3_chat_ready(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-migration-check", str(doc.get("headline_de") or "R3 Chat"))
        return 0 if doc.get("ready_for_r3_chat", doc.get("ready_for_new_chat")) else 1
    if a.cmd == "r3-migration-feasibility":
        from analytics.r3_chat_window_migration import assess_chat_migration_feasibility

        doc = assess_chat_migration_feasibility(r, run_preserve=True)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-migration-feasibility", str(doc.get("headline_de") or "Feasibility"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-ops-gates":
        from analytics.r3_ops_gates import run_ops_sequence

        doc = run_ops_sequence(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-ops-gates", str(doc.get("headline_de") or "Ops"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-ki-import":
        from analytics.r3_ki_console import import_chat_to_ki_storage

        doc = import_chat_to_ki_storage(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-ki-import", str(doc.get("headline_de") or "KI-Import"))
        return 0 if doc.get("session_messages", 0) else 1
    if a.cmd == "r3":
        from analytics.r3_ki_console import handle_ki_message
        from analytics.r3_unified import build_power_status, format_power_status_de

        msg = str(a.utterance or "").strip()
        if not msg:
            print(format_power_status_de(r))
            print(json.dumps(build_power_status(r), indent=2, ensure_ascii=False))
            _kernel_log(r, "r3", "Power-Status")
            return 0
        out = handle_ki_message(r, msg)
        print(out.get("reply_de") or json.dumps(out, ensure_ascii=False))
        if out.get("route_de"):
            print(f"[Route: {out.get('route_de')}]", file=sys.stderr)
        _kernel_log(r, "r3", str(out.get("intent") or msg[:60]))
        return 0 if out.get("ok", True) else 1
    if a.cmd in ("r3-build", "build-kernel"):
        from analytics.r3_build_channel import apply_queue, build_channel_status, build_help_de, handle_build_command
        from analytics.r3_build_kernel import build_kernel_status, run_build_kernel

        task = str(a.utterance or "").strip()
        if not task and a.rest:
            rest = [str(x) for x in a.rest]
            if len(rest) >= 2 and rest[0] in ("--utterance", "-u"):
                task = rest[1]
            else:
                task = " ".join(rest).strip()
        low = task.lower()
        if low == "apply":
            doc = apply_queue(r)
        elif low == "status":
            doc = build_kernel_status(r)
        elif task:
            if task.startswith("/"):
                doc = handle_build_command(r, task)
            elif a.cmd == "build-kernel":
                doc = run_build_kernel(r, task)
            else:
                doc = handle_build_command(r, f"/bau {task}")
        else:
            doc = {
                "ok": True,
                "help_de": build_help_de(),
                "headline_de": build_kernel_status(r).get("headline_de"),
            }
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, a.cmd, str(doc.get("headline_de") or doc.get("reply_de") or "Bau-Kernel")[:120])
        return 0 if doc.get("ok", True) else 1
    if a.cmd == "r3-native":
        from analytics.r3_os_supremacy import install_r3_native

        doc = install_r3_native(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-native", str(doc.get("headline_de") or "R3 native"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-takeover":
        from analytics.r3_os_supremacy import install_r3_supremacy

        doc = install_r3_supremacy(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-takeover", str(doc.get("headline_de") or "R3 Supremacy"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "finish-r3":
        proc = subprocess.run(["bash", "tools/finish_r3_os_install.sh"], cwd=str(r), check=False)
        _kernel_log(
            r,
            "finish-r3",
            "R3 OS Installation abgeschlossen" if proc.returncode == 0 else "finish-r3 fehlgeschlagen",
            code=proc.returncode,
        )
        return proc.returncode
    if a.cmd == "r3-desktop":
        from analytics.r3_desktop_os import install_desktop_os, purge_r3_local_apps

        if "--purge" in sys.argv[1:] or "purge" in sys.argv[1:]:
            doc = purge_r3_local_apps(r)
        else:
            doc = install_desktop_os(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-desktop", str(doc.get("headline_de") or "R3 OS Desktop"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-app-install":
        from analytics.r3_desktop_os import install_r3_exec_mirror_app

        doc = install_r3_exec_mirror_app(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-app-install", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-purge-apps":
        from analytics.r3_desktop_os import purge_r3_local_apps

        doc = purge_r3_local_apps(r)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-purge-apps", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-desktop-update":
        from analytics.r3_desktop_update import run_desktop_update_action

        doc = run_desktop_update_action(r, launch_ui=True)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-desktop-update", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-desktop-migrate":
        from analytics.r3_desktop_migration import run_full_desktop_migration

        doc = run_full_desktop_migration(r, launch_ui=True)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-desktop-migrate", str(doc.get("headline_de") or "—"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "r3-chat-migrate":
        from analytics.r3_chat_window_migration import run_chat_window_migration

        doc = run_chat_window_migration(r, preserve=True, desktop_migrate=True, import_session=True, launch_ui=False)
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        _kernel_log(r, "r3-chat-migrate", str(doc.get("headline_de") or "Chat-Migration"))
        return 0 if doc.get("ok") else 1
    if a.cmd == "autostart-all":
        from analytics.linux_runtime_unified import install_harmonized_autostart

        doc = install_harmonized_autostart(r)
        try:
            from analytics.r3_desktop_os import install_desktop_os

            desk = install_desktop_os(r)
            doc["r3_desktop"] = desk
            if desk.get("blocked"):
                doc["r3_desktop_note_de"] = "Lokal-Apps PURGED — kein Re-Install"
        except Exception as exc:
            doc["r3_desktop"] = {"ok": False, "error_de": str(exc)[:200]}
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        code = 0 if doc.get("ok") else 1
        _kernel_log(
            r,
            "autostart-all",
            str(doc.get("headline_de") or "Autostart harmonisiert") if code == 0 else "Autostart-Setup fehlgeschlagen",
            code=code,
        )
        return code
    if a.cmd == "autostart-remove":
        autostart_dir = Path.home() / ".config/autostart"
        for name in (
            "active-alpha-marktanalyse.desktop",
            "active-alpha-preview.desktop",
            "active-alpha-operator-status.desktop",
            "r3-os-session.desktop",
        ):
            p = autostart_dir / name
            if p.is_file():
                p.unlink()
        _kernel_log(r, "autostart-remove", "Autostart entfernt", code=0)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
