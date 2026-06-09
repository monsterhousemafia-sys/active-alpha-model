"""Watch H1 backtest — evaluate when complete, log status."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


def run_h1_watch(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

    status = h1_backtest_status(root)
    st = str(status.get("status") or "MISSING")
    out: Dict[str, Any] = {"status": st, "h1_backtest": status, "sealed": is_h1_backtest_sealed(root)}

    try:
        from ui.live_trading_dashboard.activity_log import log_dashboard_activity

        if st == "COMPLETE" and not out["sealed"]:
            from analytics.h1_unified_connect import connect_h1_pipeline, unified_h1_status

            out["unified"] = unified_h1_status(root)
            bench = out["unified"].get("benchmark") or {}
            out["benchmark"] = bench
            if not bench.get("exists"):
                out["benchmark_action"] = connect_h1_pipeline(root, auto_execute=True)
                out["sealed"] = is_h1_backtest_sealed(root)
            else:
                py = root / ".venv/bin/python3"
                if not py.is_file():
                    py = Path(sys.executable)
                proc = subprocess.run(
                    [str(py), "tools/run_daily_alpha_h1_pipeline.py", "--evaluate-only"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                out["evaluate_rc"] = proc.returncode
                try:
                    out["evaluation"] = json.loads(proc.stdout.strip().split("\n")[-1]) if proc.stdout else {}
                except json.JSONDecodeError:
                    out["evaluation_tail"] = (proc.stdout or "")[-500:]
                out["sealed"] = is_h1_backtest_sealed(root)
            try:
                import subprocess

                for script in ("tools/setup_nvme_storage.sh", "tools/cleanup_nvme_ballast.sh"):
                    subprocess.run(
                        ["bash", script],
                        cwd=str(root),
                        timeout=600,
                        check=False,
                    )
            except Exception:
                pass
            log_dashboard_activity(
                root,
                category="Active Alpha",
                action="H1 Evaluate",
                result=f"COMPLETE — sealed={out['sealed']}",
                status="ERFOLGREICH" if out["sealed"] else "INFO",
                source="AUTO",
            )
        elif st == "RUNNING":
            try:
                from execution.h1_cpu_priority import renice_running_h1_backtest

                out["cpu_priority"] = renice_running_h1_backtest(root)
            except Exception:
                pass
            log_dashboard_activity(
                root,
                category="Active Alpha",
                action="H1 Watch",
                result=f"läuft — {status.get('run_dir', '—')}",
                status="INFO",
                source="AUTO",
            )
        elif st in ("FAILED", "ZOMBIE", "MISSING"):
            try:
                from analytics.h1_migration_guard import ensure_h1_migration_healthy

                out["recovery"] = ensure_h1_migration_healthy(root, auto_fix=True)
                status = h1_backtest_status(root)
                st = str(status.get("status") or st)
                out["status"] = st
                out["h1_backtest"] = status
            except Exception as exc:
                out["recovery_error"] = str(exc)[:200]
            log_dashboard_activity(
                root,
                category="Evolution",
                action="H1 Watch",
                result=str(status.get("detail_de") or st)[:200],
                status="FEHLGESCHLAGEN" if st not in ("MISSING", "RUNNING") else "INFO",
                source="AUTO",
            )
    except Exception:
        pass

    from analytics.linux_operator_scope import log_operator_action

    log_operator_action(root, level="B", action="h1_watch", result=st)
    try:
        from analytics.h1_governance_status import sync_h1_governance_status

        out["governance"] = sync_h1_governance_status(root)
    except Exception:
        pass
    return out
