"""Orders nur über R3 — Active Alpha Model liefert Pläne, keine Broker-Orders."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_POLICY_REL = Path("control/r3_order_execution_policy.json")
_DEFAULT_ALLOWED = (
    "ORDER_WORKFLOW_DIALOG",
    "LIVE_DASHBOARD_PORTFOLIO",
    "LIVE_DASHBOARD_REBALANCE",
    "USER_CLICK",
    "R3_ORDER_DESK",
    "R3_COCKPIT",
    "R3_DESKTOP",
)
_DEFAULT_FORBIDDEN = (
    "LIVE_BAT_REBALANCE",
    "LIVE_BAT_REBALANCE_FORCE",
    "LIVE_AUTO_REBALANCE",
    "LIVE_FORCED_REBALANCE",
    "LIVE_REBALANCE",
    "LIVE_REBALANCE_ENQUEUE",
    "DEFERRED_INTENT",
    "WALKFORWARD_REBALANCE",
    "WALKFORWARD_REBALANCE_AUTO",
    "alpha_engine",
    "background",
    "scheduler",
    "session",
    "aa_scheduler",
    "sync_r3_flow",
    "headless",
)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_order_execution_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc.get("allowed_order_sources"):
        doc["allowed_order_sources"] = list(_DEFAULT_ALLOWED)
    if not doc.get("forbidden_order_sources"):
        doc["forbidden_order_sources"] = list(_DEFAULT_FORBIDDEN)
    return doc


def _test_bypass() -> bool:
    flag = os.environ.get("AA_ORDER_EXECUTION_TEST_BYPASS", "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return False
    import sys

    return "pytest" in sys.modules


def is_r3_order_source(source: str, policy: Optional[Dict[str, Any]] = None) -> bool:
    src = str(source or "").strip()
    if not src:
        return False
    pol = policy or {}
    allowed = {str(s) for s in (pol.get("allowed_order_sources") or [])}
    forbidden = {str(s) for s in (pol.get("forbidden_order_sources") or [])}
    if src in forbidden:
        return False
    return src in allowed


def check_order_execution_allowed(
    root: Path,
    *,
    source: str,
    operation: str = "order",
) -> Dict[str, Any]:
    """Fail-closed: Live-Orders nur von R3-Oberflächen."""
    root = Path(root)
    if _test_bypass():
        return {"allowed": True, "source": source, "operation": operation, "bypass": "test"}

    policy = load_order_execution_policy(root)
    src = str(source or "").strip() or "UNKNOWN"
    if is_r3_order_source(src, policy):
        try:
            from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

            trust = assess_t212_trust_from_root(root, persist=False)
            if not trust.get("orders_allowed", True):
                return {
                    "allowed": False,
                    "source": src,
                    "operation": operation,
                    "error": "T212_UNTRUSTED",
                    "message_de": trust.get("message_de")
                    or "T212 nicht vertrauenswürdig — Orders blockiert (fail-closed).",
                    "t212_trust": trust,
                    "policy_ref": str(_POLICY_REL).replace("\\", "/"),
                }
        except Exception as exc:
            return {
                "allowed": False,
                "source": src,
                "operation": operation,
                "error": "T212_TRUST_GATE_ERROR",
                "message_de": f"T212 Trust Gate — {str(exc)[:80]}",
                "policy_ref": str(_POLICY_REL).replace("\\", "/"),
            }
        return {
            "allowed": True,
            "source": src,
            "operation": operation,
            "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        }
    return {
        "allowed": False,
        "source": src,
        "operation": operation,
        "error": "R3_ORDER_SURFACE_REQUIRED",
        "message_de": (
            "Orders nur über R3 (Order-Desk / Cockpit mit Bestätigung). "
            f"Active Alpha Model liefert nur Pläne — Quelle «{src}» ist nicht erlaubt."
        ),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }


def check_gui_lease_source_allowed(root: Path, lease_source: str) -> Dict[str, Any]:
    return check_order_execution_allowed(
        root,
        source=lease_source,
        operation="gui_confirmation_lease",
    )
