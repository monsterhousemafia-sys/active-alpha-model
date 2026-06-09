"""Linux host roles: WSL compute (default) vs native desktop app."""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict

POLICY_REL = "control/linux_host_security.json"
_KERNEL_REL = Path("control/AI_KERNEL.json")
_COMPUTE_ENV_KEYS = (
    "AA_LINUX_COMPUTE_HOST",
    "AA_EXECUTION_DRY_RUN",
    "AA_NO_LIVE_ORDER_SUBMISSION",
    "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION",
)


def is_linux_host() -> bool:
    return sys.platform.startswith("linux")


def is_wsl() -> bool:
    if not is_linux_host():
        return False
    try:
        with open("/proc/version", encoding="utf-8", errors="ignore") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return bool(os.environ.get("WSL_DISTRO_NAME"))


def is_native_execution_host() -> bool:
    """True when Linux runs the full Marktanalyse app (not headless compute)."""
    return os.environ.get("AA_LINUX_NATIVE_APP", "").strip() == "1"


def live_order_submission_blocked() -> bool:
    """True when live T212 POST must be refused (default on Linux compute)."""
    if not is_linux_host():
        return False
    if is_native_execution_host():
        return False
    if os.environ.get("AA_LINUX_ALLOW_LIVE_ORDERS", "").strip() == "1":
        return False
    return True


def apply_linux_compute_env(*, overwrite: bool = False) -> Dict[str, str]:
    """Default fail-closed env for headless Linux/WSL compute."""
    if not is_linux_host() or is_native_execution_host():
        return {}
    defaults = {
        "AA_EXECUTION_DRY_RUN": "1",
        "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION": "1",
        "AA_NO_LIVE_ORDER_SUBMISSION": "1",
        "AA_LINUX_COMPUTE_HOST": "1",
        "AA_SKIP_CHAMPION_RUNTIME_GUARD": os.environ.get("AA_SKIP_CHAMPION_RUNTIME_GUARD", ""),
    }
    # Never inherit skip-guard from empty default
    if not defaults["AA_SKIP_CHAMPION_RUNTIME_GUARD"]:
        defaults.pop("AA_SKIP_CHAMPION_RUNTIME_GUARD")
    applied: Dict[str, str] = {}
    for key, val in defaults.items():
        if overwrite or not os.environ.get(key):
            os.environ[key] = val
            applied[key] = val
    return applied


def assert_live_submission_host_allowed() -> None:
    from integrations.trading212.t212_confirmed_execution_client import T212ExecutionBlockedError

    if live_order_submission_blocked():
        host = "WSL" if is_wsl() else "Linux"
        raise T212ExecutionBlockedError(
            f"{host}_COMPUTE_HOST_LIVE_ORDERS_FORBIDDEN — "
            "Use run_marktanalyse_linux.sh (native) or Windows GUI for orders."
        )


def host_role_summary() -> Dict[str, Any]:
    return {
        "platform": sys.platform,
        "is_linux": is_linux_host(),
        "is_wsl": is_wsl(),
        "native_execution_host": is_native_execution_host(),
        "compute_only": live_order_submission_blocked(),
        "live_orders_allowed": not live_order_submission_blocked(),
        "policy_ref": POLICY_REL,
    }


def apply_native_app_env(root: Path) -> None:
    """Native Linux app — mirrors Windows ``active_alpha_marktanalyse_os.bat`` env."""
    if not is_linux_host():
        return
    root = Path(root).resolve()
    os.environ["AA_PROJECT_ROOT"] = str(root)
    os.environ["AA_LINUX_NATIVE_APP"] = "1"
    # Only strip headless-compute flags — not user order prefs (P17 / NO_LIVE).
    for key in ("AA_LINUX_COMPUTE_HOST", "AA_EXECUTION_DRY_RUN"):
        os.environ.pop(key, None)
    try:
        from execution.linux_nvme_storage import apply_nvme_storage_env

        apply_nvme_storage_env(root)
    except Exception:
        pass


def load_kernel_doc(root: Path) -> Dict[str, Any]:
    path = Path(root) / _KERNEL_REL
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def go_live_allows_live_sync(root: Path) -> bool:
    go_live = str(load_kernel_doc(root).get("learning", {}).get("go_live_date") or "")
    if not go_live:
        return False
    return date.today() >= date.fromisoformat(go_live)
