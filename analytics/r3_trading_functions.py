"""R3 — drei Handelsfunktionen: Initial Bestellung, Umschichtung, Verkauf (nur Meldung + R3-Orders)."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_trading_functions_policy.json")
_EVIDENCE_REL = Path("evidence/r3_trading_functions_latest.json")
_REEVAL_REL = Path("evidence/pilot_portfolio_reevaluation_latest.json")
_SNAPSHOT_REL = Path("evidence/pilot_day_trading_snapshot_latest.json")
_PLAN_REL = Path("evidence/pilot_investment_plan_latest.json")
_READINESS_REL = Path("control/prediction_readiness.json")

_SELL_CODES = frozenset({"REDUZIEREN", "ABBAUEN", "VERKAUFEN"})
_BUY_CODES = frozenset({"NACHKAUF", "KAUFEN", "ERHÖHEN"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_functions_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "min_trade_eur": 12.0,
            "min_investable_eur_initial": 50.0,
            "min_drift_pct_rebalance": 4.0,
            "max_single_buy_pct": 0.12,
        }
    return doc


def _collect_context(root: Path) -> Dict[str, Any]:
    root = Path(root)
    reeval = _load_json(root / _REEVAL_REL)
    snap = _load_json(root / _SNAPSHOT_REL)
    plan = _load_json(root / _PLAN_REL)
    readiness = _load_json(root / _READINESS_REL)

    if not reeval and snap.get("reevaluation"):
        reeval = dict(snap.get("reevaluation") or {})

    rebalance = snap.get("rebalance_status") or snap.get("rebalance") or {}
    if not rebalance:
        try:
            from analytics.pilot_walkforward_mirror import rebalance_status

            rebalance = rebalance_status(root)
        except Exception:
            rebalance = {}

    broker = snap.get("broker") or {}
    human = reeval.get("human_snapshot") or {}
    exposure = reeval.get("exposure_check") or {}
    actions = list(reeval.get("recommended_actions") or [])

    positions_count = int(
        human.get("positions_count")
        or snap.get("n_positions")
        or len(broker.get("positions") or [])
        or 0
    )
    r3_investable = None
    t212_trusted = False
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        t212_trusted = bool(assess_t212_trust_from_root(root, persist=False).get("trusted"))
    except Exception:
        t212_trusted = False
    try:
        from analytics.r3_closed_loop import resolve_r3_investable_for_trading

        if t212_trusted:
            r3_investable = resolve_r3_investable_for_trading(root)
    except Exception:
        pass
    scaling = reeval.get("scaling") or {}
    live_cap: Dict[str, Any] = {}
    try:
        live_cap = _load_json(root / "evidence/r3_live_capital_latest.json")
    except Exception:
        live_cap = {}
    if t212_trusted and live_cap.get("ok"):
        if live_cap.get("investable_eur") is not None:
            r3_investable = float(live_cap["investable_eur"])
        if live_cap.get("planning_cash_eur") is not None:
            broker = {**broker, **(live_cap.get("broker") or {})}
            positions_count = int(live_cap.get("positions_count") or positions_count)

    if t212_trusted:
        investable = float(
            r3_investable
            or plan.get("investable_eur")
            or scaling.get("investable_eur")
            or reeval.get("deployable_eur")
            or broker.get("cash_eur")
            or 0
        )
    else:
        investable = 0.0
    cash_weight = float(exposure.get("cash_weight_pct") or human.get("cash_weight_pct") or 0)

    sells = [a for a in actions if str(a.get("action_code") or "").upper() in _SELL_CODES]
    buys = [a for a in actions if str(a.get("action_code") or "").upper() in _BUY_CODES]

    return {
        "reeval": reeval,
        "plan": plan,
        "readiness": readiness,
        "rebalance": rebalance,
        "actions": actions,
        "positions_count": positions_count,
        "investable_eur": investable,
        "cash_weight_pct": cash_weight,
        "under_invested": bool(exposure.get("under_invested")),
        "allocation_drift_pct": float(reeval.get("allocation_drift_l1_pct") or 0),
        "rebalance_due": bool(rebalance.get("is_due")),
        "order_gate_ok": bool(readiness.get("order_gate_ok")) and t212_trusted,
        "t212_trusted": t212_trusted,
        "prediction_ok": bool(readiness.get("ok")),
        "sells": sells,
        "buys": buys,
    }


def _sum_notional(rows: List[Dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        try:
            total += abs(float(row.get("gap_eur") or 0))
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def evaluate_initial_order(ctx: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    min_inv = float(policy.get("min_investable_eur_initial") or 50.0)
    min_trade = float(policy.get("min_trade_eur") or 12.0)
    flat = int(ctx.get("positions_count") or 0) == 0
    buys = [b for b in ctx.get("buys") or [] if abs(float(b.get("gap_eur") or 0)) >= min_trade]
    investable = float(ctx.get("investable_eur") or 0)
    active = (
        flat
        and investable >= min_inv
        and bool(buys)
        and bool(ctx.get("prediction_ok"))
        and bool(ctx.get("under_invested") or ctx.get("cash_weight_pct", 0) >= 85)
    )
    required = active and bool(ctx.get("order_gate_ok"))
    return {
        "id": "initial_order",
        "label_de": "Initial Bestellung",
        "active": active,
        "required": required,
        "order_count": len(buys),
        "notional_eur": _sum_notional(buys),
    }


def evaluate_sell_notice(ctx: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    min_trade = float(policy.get("min_trade_eur") or 12.0)
    sells = [s for s in ctx.get("sells") or [] if abs(float(s.get("gap_eur") or 0)) >= min_trade]
    active = len(sells) > 0
    required = active and bool(ctx.get("order_gate_ok"))
    return {
        "id": "sell_notice",
        "label_de": "Verkauf",
        "active": active,
        "required": required,
        "order_count": len(sells),
        "notional_eur": _sum_notional(sells),
    }


def evaluate_rebalance_notice(ctx: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    min_drift = float(policy.get("min_drift_pct_rebalance") or 4.0)
    min_trade = float(policy.get("min_trade_eur") or 12.0)
    flat = int(ctx.get("positions_count") or 0) == 0
    buys = [b for b in ctx.get("buys") or [] if abs(float(b.get("gap_eur") or 0)) >= min_trade]
    sells = [s for s in ctx.get("sells") or [] if abs(float(s.get("gap_eur") or 0)) >= min_trade]
    due = bool(ctx.get("rebalance_due"))
    drift = float(ctx.get("allocation_drift_pct") or 0)
    has_positions = not flat
    has_actions = bool(buys or sells)
    sell_rotation = bool(sells)
    active = has_positions and has_actions and (due or drift >= min_drift or sell_rotation)
    required = active and bool(ctx.get("order_gate_ok"))
    return {
        "id": "rebalance_notice",
        "label_de": "Umschichtung",
        "active": active,
        "required": required,
        "order_count": (len(buys) + len(sells)) if active else 0,
        "notional_eur": round(_sum_notional(buys) + _sum_notional(sells), 2) if active else 0.0,
        "rebalance_due": due,
        "drift_pct": drift,
    }


def build_r3_trading_functions(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Drei R3-Funktionen aus Evidence — keine Orders, nur Meldungen."""
    root = Path(root)
    policy = load_functions_policy(root)
    ctx = _collect_context(root)

    functions = [
        evaluate_initial_order(ctx, policy),
        evaluate_sell_notice(ctx, policy),
        evaluate_rebalance_notice(ctx, policy),
    ]
    active = [f for f in functions if f.get("active")]
    required = [f for f in functions if f.get("required")]
    primary_id = required[0]["id"] if required else (active[0]["id"] if active else None)

    stocks: List[Dict[str, Any]] = []
    stock_groups: Dict[str, Any] = {}
    initial_package: Dict[str, Any] = {}
    try:
        from analytics.r3_stock_orders import refresh_stock_order_evidence

        orders_doc = refresh_stock_order_evidence(root, persist=persist)
        try:
            from analytics.r3_mirror_capital import gate_orders_doc_for_display, resolve_mirror_account

            mirror_acct = resolve_mirror_account(root)
            orders_doc = gate_orders_doc_for_display(
                orders_doc,
                t212_trusted=bool(mirror_acct.get("t212_trusted")),
            )
        except Exception:
            pass
        stocks = list(orders_doc.get("stocks") or [])
        stock_groups = dict(orders_doc.get("stock_groups") or {})
        initial_package = dict(orders_doc.get("initial_package") or {})
    except Exception:
        pass

    doc: Dict[str, Any] = {
        "schema_version": 5,
        "updated_at_utc": _utc_now(),
        "functions": functions,
        "primary_function_id": primary_id,
        "functions_active": len(active),
        "functions_required": len(required),
        "orders_ref": "evidence/r3_stock_orders_latest.json",
        "stocks": stocks,
        "stock_groups": stock_groups,
        "initial_package": initial_package,
        "context": {
            "positions_count": ctx.get("positions_count"),
            "investable_eur": ctx.get("investable_eur"),
            "rebalance_due": ctx.get("rebalance_due"),
            "order_gate_ok": ctx.get("order_gate_ok"),
        },
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def load_r3_trading_functions(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)


def render_r3_trading_functions_html(
    root: Path,
    doc: Optional[Dict[str, Any]] = None,
    *,
    exec_only: bool = False,
) -> str:
    """Order-Oberfläche — auf /desktop nur Paket-Button (exec_only)."""
    data = doc or load_r3_trading_functions(root)
    if not data.get("functions"):
        data = build_r3_trading_functions(root, persist=False)

    try:
        from analytics.r3_stock_orders import load_stock_orders, refresh_stock_order_evidence
        from analytics.r3_mirror_capital import gate_orders_doc_for_display, resolve_mirror_account

        mirror_acct = resolve_mirror_account(root)
        orders = load_stock_orders(root)
        if not orders.get("stocks"):
            orders = refresh_stock_order_evidence(root, persist=False)
        orders = gate_orders_doc_for_display(
            orders,
            t212_trusted=bool(mirror_acct.get("t212_trusted")),
        )
        data = {
            **data,
            "stocks": orders.get("stocks") or data.get("stocks") or [],
            "stock_groups": orders.get("stock_groups") or data.get("stock_groups") or {},
            "initial_package": orders.get("initial_package") or data.get("initial_package") or {},
        }
    except Exception:
        pass

    from analytics.r3_freigabe import package_ready
    from analytics.r3_operator_surface_text import freigabe_blocked_de
    from analytics.r3_t212_operator_api import needs_operator_api_setup

    freigabe = package_ready(root, refresh_orders=False)
    pkg = data.get("initial_package") or freigabe.get("initial_package") or {}
    notional = float(freigabe.get("notional_eur") or pkg.get("notional_eur") or 0)
    ready = bool(freigabe.get("ready"))
    governance_hint = ""
    if ready:
        btn_label = f"Gewinn starten — {notional:.0f} € → T212"
        btn_class = "r3-freigabe-btn ready"
        btn_onclick = ' onclick="r3FreigabeSubmit()"'
        btn_disabled = ""
    else:
        trust_code = None
        try:
            from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

            trust_code = assess_t212_trust_from_root(root, persist=False).get("reason_code")
        except Exception:
            trust_code = None
        btn_label = freigabe_blocked_de(
            reason_code=str(trust_code or "") or None,
            needs_api=needs_operator_api_setup(root),
        )
        btn_class = "r3-freigabe-btn blocked"
        btn_onclick = ""
        btn_disabled = " disabled"

    freigabe_html = (
        f'<div class="r3-freigabe-row">'
        f'<button type="button" class="{btn_class}" id="r3-freigabe-btn"{btn_disabled}{btn_onclick}>'
        f"{html.escape(btn_label)}</button>"
        f"{governance_hint}</div>"
    )

    def _stock_btn(row: Dict[str, Any]) -> str:
        sym = html.escape(str(row.get("symbol") or ""))
        side = str(row.get("side") or "BUY").upper()
        side_de = html.escape(str(row.get("side_de") or ("Kauf" if side == "BUY" else "Verkauf")))
        notional = float(row.get("notional_eur") or 0)
        action_de = html.escape(str(row.get("action_de") or "")[:80])
        steer = str(row.get("steering_mode") or row.get("side_de") or "")
        if side == "BUY" and steer.upper().startswith("GAS"):
            side_de = html.escape(steer)
        css_side = "gas" if side == "BUY" else "sell"
        css_new = " r3-stock-new" if row.get("is_new_position") else ""
        return (
            f'<button type="button" class="r3-stock-btn r3-stock-{css_side}{css_new}" '
            f'data-symbol="{sym}" data-side="{side}" '
            f'onclick="r3OrderStock(\'{sym}\', \'{side}\', {notional:.2f})" '
            f'title="{action_de}">'
            f'<span class="r3-stock-sym">{sym}</span>'
            f'<span class="r3-stock-side">{side_de}</span>'
            f'<span class="r3-stock-eur">{notional:.0f} €</span>'
            f"</button>"
        )

    def _stock_section(title: str, rows: List[Dict[str, Any]], *, css: str = "", always: bool = False) -> str:
        label = html.escape(title)
        cls = f"r3-stocks-section {css}".strip()
        if not rows:
            if not always:
                return ""
            return (
                f'<div class="{cls}" data-side-block="{label.lower()}">'
                f'<div class="r3-stocks-heading">{label}</div>'
                f'<p class="r3-stocks-empty">—</p></div>'
            )
        btns = "".join(_stock_btn(r) for r in rows)
        return (
            f'<div class="{cls}" data-side-block="{label.lower()}">'
            f'<div class="r3-stocks-heading">{label}</div>'
            f'<div class="r3-stocks-grid">{btns}</div></div>'
        )

    groups = data.get("stock_groups") or {}
    all_stocks = list(data.get("stocks") or [])
    sells = list(groups.get("sells") or [])
    if not sells:
        sells = [r for r in all_stocks if str(r.get("side") or "").upper() == "SELL"]
    buys = [r for r in all_stocks if str(r.get("side") or "").upper() == "BUY"]
    if not buys:
        buys = list(groups.get("new_buys") or []) + list(groups.get("rebuy") or [])

    stocks_html = ""
    if not exec_only:
        sections = [
            _stock_section("Verkauf", sells, css="r3-stocks-sell", always=True),
            _stock_section("Kauf", buys, css="r3-stocks-buy", always=True),
        ]
        stocks_html = (
            '<div class="r3-einzel-wrap" id="r3-einzel-wrap">'
            f'{"".join(sections)}'
            "</div>"
        )

    toast = "" if exec_only else '<p class="r3-order-toast" id="r3-order-toast" aria-live="polite"></p>'
    return (
        f'<section class="r3-trading-functions" id="r3-trading-functions">'
        f"{freigabe_html}{stocks_html}{toast}"
        f"</section>"
    )


R3_TRADING_FUNCTIONS_CSS = """
.r3-trading-functions {
  flex-shrink: 0; margin: 0;
  padding: var(--r3-pad-lg) var(--r3-pad-x);
  background: var(--r3-surface);
  border-top: 1px solid var(--r3-border);
}
.r3-freigabe-row { text-align: center; margin: 0 0 var(--r3-gap); }
.r3-freigabe-btn {
  display: block; width: 100%; max-width: none;
  padding: var(--r3-pad-lg); border-radius: var(--r3-radius); border: none;
  font-size: 15px; font-weight: 800; letter-spacing: .02em;
  cursor: pointer; font-family: inherit;
}
.r3-freigabe-btn.ready {
  background: linear-gradient(145deg, var(--r3-orange-top) 0%, var(--r3-orange-bottom) 100%);
  color: #fff; box-shadow: 0 4px 14px rgba(233,84,32,.28);
}
.r3-freigabe-btn.ready:hover { filter: brightness(1.05); }
.r3-freigabe-btn.blocked {
  background: var(--r3-bg); color: var(--r3-muted);
  border: 1px solid var(--r3-border); cursor: not-allowed;
}
.r3-freigabe-btn:disabled { opacity: .55; cursor: wait; }
.r3-freigabe-hint {
  margin: var(--r3-gap) 0 0; font-size: 12px; color: var(--r3-muted); line-height: 1.4;
}
.r3-einzel-wrap { margin-top: var(--r3-gap); }
.r3-einzel-label {
  margin: 0 0 var(--r3-gap); text-align: center; font-size: 11px; font-weight: 700;
  color: var(--r3-muted); text-transform: uppercase; letter-spacing: .06em;
}
.r3-stocks-wrap { margin-top: var(--r3-gap); }
.r3-stocks-grouped { display: flex; flex-direction: column; gap: var(--r3-gap); }
.r3-stocks-section {
  border: 1px solid var(--r3-border); border-radius: var(--r3-radius);
  padding: var(--r3-pad); background: var(--r3-bg);
}
.r3-stocks-heading {
  font-size: 10px; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; margin: 0 0 6px; color: var(--r3-muted);
}
.r3-stocks-empty { margin: 0; padding: 8px 10px; font-size: 13px; color: var(--r3-muted); }
.r3-stocks-sell { border-color: rgba(255,59,48,.28); background: var(--r3-fail-bg); }
.r3-stocks-sell .r3-stocks-heading { color: var(--r3-fail); }
.r3-stocks-buy { border-color: rgba(36,138,61,.28); background: var(--r3-ok-bg); }
.r3-stocks-buy .r3-stocks-heading { color: var(--r3-ok); }
.r3-stocks-new { border-color: rgba(36,138,61,.28); background: var(--r3-ok-bg); }
.r3-stocks-rebuy { border-color: rgba(154,123,0,.28); background: var(--r3-warn-bg); }
.r3-stocks-buy .r3-stocks-heading { color: var(--r3-ok); }
.r3-stocks-meta {
  text-align: center; font-size: 11px; color: var(--r3-muted); margin: 0 0 var(--r3-gap);
}
.r3-stocks-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(108px, 1fr));
  gap: var(--r3-gap);
}
.r3-stock-btn {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: var(--r3-pad); border-radius: var(--r3-radius-sm);
  border: 1px solid var(--r3-border); background: var(--r3-surface);
  cursor: pointer; font-family: inherit; color: var(--r3-text);
}
.r3-stock-btn:disabled { opacity: .55; cursor: wait; }
.r3-stock-buy, .r3-stock-gas { border-color: rgba(36,138,61,.3); }
.r3-stock-sell { border-color: rgba(255,59,48,.3); }
.r3-stock-sym { font-size: 14px; font-weight: 800; }
.r3-stock-side { font-size: 9px; font-weight: 700; text-transform: uppercase; }
.r3-stock-buy .r3-stock-side, .r3-stock-gas .r3-stock-side { color: var(--r3-ok); }
.r3-stock-sell .r3-stock-side { color: var(--r3-fail); }
.r3-stock-eur { font-size: 11px; color: var(--r3-muted); }
.r3-order-toast {
  min-height: 1.2em; text-align: center; font-size: 12px; font-weight: 600;
  margin: var(--r3-gap) 0 0; color: var(--r3-muted);
}
.r3-order-toast.ok { color: var(--r3-ok); }
.r3-order-toast.fail { color: var(--r3-fail); }
"""

R3_TRADING_FUNCTIONS_JS = """
function r3OrderToast(msg, ok) {
  const el = document.getElementById('r3-order-toast');
  if (!el) return;
  el.className = 'r3-order-toast ' + (ok ? 'ok' : 'fail');
  el.textContent = msg || '';
}
function r3SetOrderBusy(busy) {
  document.querySelectorAll('.r3-stock-btn, .r3-freigabe-btn').forEach((b) => {
    b.disabled = !!busy;
  });
}
async function r3PostOrder(body) {
  r3SetOrderBusy(true);
  r3OrderToast('Sende…', true);
  try {
    const r = await fetch('/api/r3/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    r3OrderToast(j.message_de || j.error || (j.ok ? 'OK' : 'Fehler'), !!j.ok);
    if (j.ok) {
      if (typeof r3RefreshUiPreferSoft === 'function') setTimeout(() => r3RefreshUiPreferSoft(), 600);
      else setTimeout(() => location.reload(), 1200);
      return j;
    }
    return j;
  } catch (e) {
    r3OrderToast('Verbindung fehlgeschlagen', false);
    return { ok: false };
  } finally {
    r3SetOrderBusy(false);
  }
}
async function r3OrderStock(symbol, side, notional) {
  const sideDe = side === 'SELL' ? 'Verkauf' : 'Kauf';
  const ok = window.confirm(sideDe + ' ' + symbol + ' — ' + Number(notional).toFixed(0) + ' €?');
  if (!ok) return;
  return r3PostOrder({ mode: 'single', symbol: symbol, side: side, confirm: true });
}
async function r3FreigabeSubmit() {
  const ok = window.confirm('Zielportfolio jetzt an Trading212 senden? (einmalig bestätigen)');
  if (!ok) return;
  return r3PostOrder({ mode: 'initial_package', confirm: true });
}
async function r3RefreshOrderSurface() {
  try {
    await fetch('/api/r3/freigabe?prepare=1&auto=desktop', { cache: 'no-store' });
    const btn = document.getElementById('r3-freigabe-btn');
    if (btn && btn.classList.contains('blocked')) {
      if (typeof r3RefreshUiPreferSoft === 'function') r3RefreshUiPreferSoft();
      else location.reload();
    }
  } catch (e) { /* silent */ }
}
document.addEventListener('DOMContentLoaded', () => {
  if (window.R3_EXEC_ONLY) return;
  const btn = document.getElementById('r3-freigabe-btn');
  if (btn && btn.classList.contains('blocked')) {
    r3RefreshOrderSurface();
  }
});
"""
