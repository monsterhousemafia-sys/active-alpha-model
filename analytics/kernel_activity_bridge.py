"""Bridge ai_kernel (R3 KI lokal) actions into the shared activity log for the dashboard."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def log_kernel_command(
    root: Path,
    *,
    command: str,
    result: str,
    status: str = "ERFOLGREICH",
) -> None:
    try:
        from analytics.active_alpha_identity import load_unified_config
        from analytics.secret_redaction import redact_text
        from ui.live_trading_dashboard.activity_log import log_dashboard_activity

        cfg = load_unified_config(root)
        chat = (cfg.get("surfaces") or {}).get("r3_ki") or {}
        label = str(chat.get("label_de") or "R3 KI (lokal)")
        safe_result = redact_text(str(result or ""))[:240]
        log_dashboard_activity(
            root,
            category="Active Alpha",
            action=f"{label}: ai_kernel {command}",
            result=safe_result,
            status=status,
            source="CURSOR",
        )
    except Exception:
        pass


def log_kernel_startup(root: Path) -> None:
    try:
        from analytics.active_alpha_identity import status_line_de

        log_kernel_command(
            root,
            command="status",
            result=status_line_de(root, surface="r3_ki"),
            status="INFO",
        )
    except Exception:
        pass
