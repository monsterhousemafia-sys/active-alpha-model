"""User scenario planning — editable amounts, no order execution."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

DEFAULT_CAPITAL = 500.0
DEFAULT_RESERVE = 50.0
FEE_RATE = 0.002


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _store_path(root: Path) -> Path:
    p = root / "live_pilot/planning/user_scenarios.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _parse_amount(text: str) -> Optional[float]:
    if not text or not str(text).strip():
        return None
    s = str(text).strip().replace(",", ".")
    try:
        v = float(s)
        return v if v >= 0 else None
    except ValueError:
        return None


def load_scenarios(root: Path) -> List[Dict[str, Any]]:
    path = _store_path(root)
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return list(doc.get("scenarios") or [])
    except json.JSONDecodeError:
        return []


def save_scenarios(root: Path, scenarios: List[Dict[str, Any]]) -> None:
    atomic_write_json(_store_path(root), {"scenarios": scenarios, "updated_at_utc": _utc_now()})


def create_scenario(
    root: Path,
    *,
    name: str,
    capital_eur: float = DEFAULT_CAPITAL,
    reserve_eur: float = DEFAULT_RESERVE,
    items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    scenario = {
        "id": str(uuid.uuid4()),
        "name": name or "Neues Szenario",
        "comment": "",
        "capital_eur": capital_eur,
        "reserve_eur": reserve_eur,
        "items": items or [],
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
    }
    scenarios = load_scenarios(root)
    scenarios.append(scenario)
    save_scenarios(root, scenarios)
    return scenario


def duplicate_scenario(root: Path, scenario_id: str) -> Optional[Dict[str, Any]]:
    scenarios = load_scenarios(root)
    for s in scenarios:
        if s.get("id") == scenario_id:
            copy = {**s, "id": str(uuid.uuid4()), "name": f"{s.get('name', 'Szenario')} (Kopie)", "created_at_utc": _utc_now()}
            scenarios.append(copy)
            save_scenarios(root, scenarios)
            return copy
    return None


def delete_scenario(root: Path, scenario_id: str) -> bool:
    scenarios = load_scenarios(root)
    new_list = [s for s in scenarios if s.get("id") != scenario_id]
    if len(new_list) == len(scenarios):
        return False
    save_scenarios(root, new_list)
    return True


def calculate_scenario(
    scenario: Dict[str, Any],
    *,
    authorized_capital: float = 500.0,
    live_prices: Dict[str, float] | None = None,
    price_freshness: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    capital = float(scenario.get("capital_eur") or DEFAULT_CAPITAL)
    reserve = float(scenario.get("reserve_eur") or DEFAULT_RESERVE)
    items = list(scenario.get("items") or [])

    if price_freshness is not None and not price_freshness.get("calculation_allowed", True):
        return {
            "total_notional_eur": 0.0,
            "total_costs_eur": 0.0,
            "total_deploy_eur": 0.0,
            "cash_reserve_eur": reserve,
            "rest_cash_eur": round(max(0, capital - reserve), 2),
            "max_deployable_eur": round(min(authorized_capital, capital) - reserve, 2),
            "budget_gate": "FAIL",
            "weights_pct": {},
            "planning_status": f"BLOCKIERT — {price_freshness.get('reason', 'Live-Preise nicht aktuell')}",
            "automatic_execution": False,
            "items": items,
            "live_price_gate": "FAIL_STALE_OR_MISSING",
        }

    total_notional = sum(float(i.get("amount_eur") or 0) for i in items)
    total_costs = round(total_notional * FEE_RATE, 4)
    total_deploy = round(total_notional + total_costs, 4)
    max_deploy = min(authorized_capital, capital) - reserve
    budget_ok = total_deploy <= max_deploy
    over_frame = total_deploy > max_deploy

    weights = {}
    live_detail: Dict[str, Any] = {}
    if total_notional > 0:
        for i in items:
            sym = i.get("symbol", "?")
            weights[sym] = round(100.0 * float(i.get("amount_eur") or 0) / total_notional, 2)
            if live_prices and sym in live_prices:
                px = float(live_prices[sym])
                amt = float(i.get("amount_eur") or 0)
                if px > 0:
                    live_detail[sym] = {
                        "live_price_eur": round(px, 4),
                        "estimated_shares": round(amt / px, 4),
                        "notional_eur": round(amt, 2),
                    }

    status = "PLANUNG OK — NICHT AUSGEFÜHRT"
    if over_frame:
        status = "PLANUNG ÜBER AKTUELLEM RAHMEN — NICHT HANDLUNGSBEREIT"
    elif live_prices and items:
        missing = [i.get("symbol") for i in items if str(i.get("symbol", "")).upper() not in live_prices]
        if missing:
            status = f"PLANUNG OK — LIVE-PREIS FEHLT FÜR {', '.join(missing)}"

    return {
        "total_notional_eur": round(total_notional, 2),
        "total_costs_eur": total_costs,
        "total_deploy_eur": total_deploy,
        "cash_reserve_eur": reserve,
        "rest_cash_eur": round(max(0, capital - total_deploy - reserve), 2),
        "max_deployable_eur": round(max_deploy, 2),
        "budget_gate": "PASS" if budget_ok else "FAIL",
        "weights_pct": weights,
        "planning_status": status,
        "automatic_execution": False,
        "items": items,
        "live_price_detail": live_detail,
        "live_price_gate": "PASS" if price_freshness is None or price_freshness.get("calculation_allowed") else "FAIL",
    }


def parse_amount_input(text: str) -> tuple[Optional[float], Optional[str]]:
    v = _parse_amount(text)
    if v is None:
        return None, "Ungültiger Betrag — bitte positive Zahl eingeben (Punkt oder Komma)."
    return v, None
