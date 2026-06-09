"""H1-Seal-Policy — zentral: ist Seal für operative Gates erforderlich?"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_POLICY_REL = Path("control/h1_seal_policy.json")


def load_h1_seal_policy(root: Path) -> Dict[str, Any]:
    path = Path(root) / _POLICY_REL
    if not path.is_file():
        return {"seal_required": True, "benchmark_required_for_operations": True}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"seal_required": True}
    except (json.JSONDecodeError, OSError):
        return {"seal_required": True}


def is_h1_seal_required(root: Path) -> bool:
    return load_h1_seal_policy(root).get("seal_required", True) is not False


def is_h1_benchmark_required(root: Path) -> bool:
    pol = load_h1_seal_policy(root)
    if pol.get("benchmark_required_for_operations") is False:
        return False
    return is_h1_seal_required(root)


def seal_policy_banner_de(root: Path) -> str:
    pol = load_h1_seal_policy(root)
    if pol.get("seal_required") is False:
        return str(pol.get("headline_de") or "H1-Seal optional")
    return "H1-Seal erforderlich (pass_full_seal)"
