"""R3 Betriebs-Checkliste — maschinenlesbarer Scan (SSoT: control/r3_operational_checklist.json)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_operational_checklist.json")
_EVIDENCE_REL = Path("evidence/r3_operational_checklist_latest.json")


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


def load_checklist_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _get_path(doc: Dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in str(dotted or "").split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _fields_present(doc: Dict[str, Any], fields: Sequence[str]) -> bool:
    if not fields:
        return bool(doc)
    return all(_get_path(doc, f) is not None for f in fields)


def _result(
    *,
    status: str,
    detail_de: str,
    ok: Optional[bool] = None,
    tier: str = "critical",
) -> Dict[str, Any]:
    if ok is None:
        ok = status == "PASS"
    return {
        "status": status,
        "ok": bool(ok),
        "detail_de": str(detail_de or "—")[:160],
        "tier": tier,
    }


def _eval_item(root: Path, item: Dict[str, Any], *, section: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    iid = str(item.get("id") or "")
    tier = str(section.get("tier") or "critical")
    label = str(item.get("label_de") or iid)
    out: Dict[str, Any] = {
        "id": iid,
        "label_de": label,
        "tier": tier,
        "section_id": section.get("id"),
        "fail_closed": bool(item.get("fail_closed")),
    }

    try:
        if iid == "safety_flags_off":
            pg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text(encoding="utf-8")) or {}
            flags = {
                k: pg.get(k)
                for k in (
                    "auto_research_enabled",
                    "auto_promote_paper_enabled",
                    "auto_promote_signal_enabled",
                    "auto_execute_real_money_enabled",
                )
            }
            ok = all(v is False for v in flags.values())
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=str(flags), tier=tier))

        elif iid == "governance_locked":
            kv = _load_json(root / "evidence/king_verify_latest.json")
            ok = bool(kv.get("ok"))
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de="king_verify OK" if ok else "prüfen", tier=tier))

        elif iid == "orders_only_r3":
            pol = _load_json(root / "control/r3_order_execution_policy.json")
            ok = str(pol.get("status") or "").upper() == "AUTHORITATIVE"
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=pol.get("headline_de", ""), tier=tier))

        elif iid == "dry_run_guard":
            from analytics.r3_mirror_state import resolve_submission_mode

            sub = resolve_submission_mode(root)
            ok = not bool(sub.get("live_submit"))
            out.update(
                _result(
                    ok=ok,
                    status="PASS" if ok else "FAIL",
                    detail_de=f"live_submit={sub.get('live_submit')}",
                    tier=tier,
                )
            )

        elif iid in {"hub_local", "r3_surface", "stack_ok"}:
            stack = _load_json(root / "evidence/stack_integrity_latest.json")
            if iid == "hub_local":
                ok = bool(stack.get("hub_ok") or stack.get("stack_ok"))
                detail = "127.0.0.1:17890"
            elif iid == "r3_surface":
                r3 = stack.get("r3") or {}
                ok = bool(r3.get("surface_page_ok") or r3.get("mirror_api_ok") or stack.get("stack_ok"))
                detail = "/r3"
            else:
                ok = bool(stack.get("stack_ok"))
                detail = "OK" if ok else ", ".join((stack.get("failures_de") or [])[:2]) or "prüfen"
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=detail, tier=tier))

        elif iid == "autostart":
            detach = _load_json(root / "evidence/r3_operational_independence_latest.json")
            ok = bool(detach.get("operational_detach"))
            n = f"{detach.get('gates_ok')}/{detach.get('gates_total')}"
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=n, tier=tier))

        elif iid == "home_ownership":
            ho = _load_json(root / "evidence/r3_home_ownership_latest.json")
            ok = ho.get("ok") is not False if ho else True
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=ho.get("headline_de", "—"), tier=tier))

        elif iid in {
            "internet",
            "account",
            "ingest",
            "engine",
            "plan",
            "display",
            "orders",
            "orders_gate",
        }:
            cycle = _load_json(root / "evidence/r3_trading_cycle_latest.json")
            stage_id = "orders" if iid == "orders_gate" else iid
            stage = next((s for s in (cycle.get("stages") or []) if s.get("id") == stage_id), None)
            if stage:
                ok = bool(stage.get("ok"))
                out.update(
                    _result(
                        ok=ok,
                        status="PASS" if ok else "FAIL",
                        detail_de=str(stage.get("detail_de") or stage.get("value_de") or ""),
                        tier=tier,
                    )
                )
            elif iid in {"orders", "orders_gate"}:
                pol = _load_json(root / "control/r3_order_execution_policy.json")
                ok = str(pol.get("status") or "").upper() == "AUTHORITATIVE"
                out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=str(pol.get("status")), tier=tier))
            else:
                out.update(_result(status="FAIL", detail_de="Stufe fehlt im Kreislauf", tier=tier))

        elif iid == "metrics_traceable":
            from analytics.r3_mirror_state import build_exec_mirror_state

            state = build_exec_mirror_state(root)
            metrics = state.get("system_metrics") or []
            op = _load_json(root / "evidence/r3_operator_readiness_latest.json")
            if not op.get("operational_pct"):
                try:
                    from analytics.r3_operator_readiness import sync_r3_operator_readiness

                    op = sync_r3_operator_readiness(root, persist=True)
                except Exception:
                    pass
            ok = (
                bool(metrics)
                and all(m.get("evidence_ref") for m in metrics)
                and bool(op.get("evidence_ref"))
                and op.get("operational_pct") is not None
            )
            out.update(
                _result(
                    ok=ok,
                    status="PASS" if ok else "FAIL",
                    detail_de=f"{len(metrics)} API-Metriken · Operator {op.get('operational_pct') or '—'}%",
                    tier=tier,
                )
            )

        elif iid == "plan_panel":
            plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
            ok = plan.get("investable_eur") is not None
            out.update(
                _result(
                    ok=ok,
                    status="PASS" if ok else "FAIL",
                    detail_de=f"investable={plan.get('investable_eur')}",
                    tier=tier,
                )
            )

        elif iid == "t212_panel":
            orders = _load_json(root / "evidence/r3_stock_orders_latest.json")
            pkg = (orders.get("initial_package") or {})
            state = {}
            try:
                from analytics.r3_mirror_state import build_exec_mirror_state

                state = build_exec_mirror_state(root)
            except Exception:
                pass
            exec_pkg = state.get("execution_package") or {}
            has_sell_block = "sell_lines" in exec_pkg
            has_buy = bool(orders.get("buy_count", 0) > 0 or pkg.get("active"))
            ok = has_sell_block and has_buy
            detail = f"Verkauf+Kauf UI · sell={orders.get('sell_count', 0)} buy={orders.get('buy_count', 0)}"
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=detail, tier=tier))

        elif iid == "status_compact":
            from analytics.r3_mirror_state import build_exec_mirror_state

            state = build_exec_mirror_state(root)
            ok = bool(state.get("display_headline_de") or state.get("system_metrics"))
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de="Mirror-State OK", tier=tier))

        elif iid == "poll_refresh":
            view_path = root / "analytics/r3_mirror_view.py"
            if not view_path.is_file():
                view_path = Path(__file__).resolve().parent / "r3_mirror_view.py"
            view = view_path.read_text(encoding="utf-8") if view_path.is_file() else ""
            ok = "r3PollMirror" in view and "r3PatchMirrorDisplays" in view
            prof = _load_json(root / "control/r3_runtime_profile.json")
            detail = f"poll={prof.get('mirror_poll_ms')}ms soft={prof.get('mirror_soft_update')}"
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=detail, tier=tier))

        elif iid == "upgrade_confirm":
            prof = _load_json(root / "control/r3_runtime_profile.json")
            ok = str(prof.get("status") or "").upper() == "AUTHORITATIVE"
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=prof.get("label_de", ""), tier=tier))

        elif iid == "buy_single":
            orders = _load_json(root / "evidence/r3_stock_orders_latest.json")
            n = int(orders.get("buy_count") or 0)
            ok = n > 0
            out.update(_result(ok=ok, status="PASS" if ok else "PARTIAL", detail_de=f"{n} BUY-Zeilen", tier=tier))

        elif iid == "sell_single":
            orders = _load_json(root / "evidence/r3_stock_orders_latest.json")
            n = int(orders.get("sell_count") or 0)
            view_path = root / "analytics/r3_mirror_view.py"
            if not view_path.is_file():
                view_path = Path(__file__).resolve().parent / "r3_mirror_view.py"
            view = view_path.read_text(encoding="utf-8") if view_path.is_file() else ""
            impl = 'r3-exec-sell' in view and '_block("Verkauf"' in view
            if n > 0:
                out.update(_result(ok=True, status="PASS", detail_de=f"{n} SELL-Zeilen", tier=tier))
            elif impl:
                out.update(
                    _result(
                        ok=True,
                        status="PARTIAL",
                        detail_de="UI+Merge OK — 0 SELL (kein Reeval-Verkauf)",
                        tier=tier,
                    )
                )
            else:
                out.update(_result(status="FAIL", detail_de="Verkauf-Block fehlt", tier=tier))

        elif iid == "initial_package":
            fr = _load_json(root / "evidence/r3_freigabe_latest.json")
            ok = bool(fr.get("package_ready"))
            out.update(_result(ok=ok, status="PASS" if ok else "PARTIAL", detail_de=fr.get("headline_de", ""), tier=tier))

        elif iid == "sell_notice":
            tf = _load_json(root / "evidence/r3_trading_functions_latest.json")
            fn = next((f for f in (tf.get("functions") or []) if f.get("id") == "sell_notice"), None)
            ok = bool(fn)
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=(fn or {}).get("headline_de", ""), tier=tier))

        elif iid == "min_trade":
            pol = _load_json(root / "control/r3_trading_functions_policy.json")
            ok = pol.get("min_trade_eur") is not None
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=f"min={pol.get('min_trade_eur')}", tier=tier))

        elif iid == "no_background_orders":
            pol = _load_json(root / "control/r3_order_execution_policy.json")
            forbidden = pol.get("forbidden_order_sources") or []
            ok = bool(forbidden) and str(pol.get("status") or "").upper() == "AUTHORITATIVE"
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=f"{len(forbidden)} blockiert", tier=tier))

        elif iid == "signal_plan":
            plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
            ok = plan.get("investable_eur") is not None
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=f"investable={plan.get('investable_eur')}", tier=tier))

        elif iid == "reeval_actions":
            reev = _load_json(root / "evidence/pilot_portfolio_reevaluation_latest.json")
            actions = reev.get("recommended_actions") or []
            ok = isinstance(actions, list)
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=f"{len(actions)} Aktionen", tier=tier))

        elif iid == "closed_loop":
            loop = _load_json(root / "evidence/r3_closed_loop_latest.json")
            ok = bool(loop.get("loop_ok"))
            out.update(_result(ok=ok, status="PASS" if ok else "PARTIAL", detail_de=loop.get("headline_de", ""), tier=tier))

        elif iid == "prediction_gate":
            pr = _load_json(root / "control/prediction_readiness.json")
            ok = bool(pr.get("order_gate_ok"))
            out.update(_result(ok=ok, status="PASS" if ok else "PARTIAL", detail_de=str(pr.get("order_gate_ok")), tier=tier))

        elif iid == "h1_separate":
            out.update(_result(ok=True, status="PASS", detail_de="H1 König-Territorium — kein R3-Blocker", tier=tier))

        elif iid == "king_ops":
            kv = _load_json(root / "evidence/king_verify_latest.json")
            ok = bool(kv.get("ok"))
            out.update(_result(ok=ok, status="PASS" if ok else "PARTIAL", detail_de="verify", tier=tier))

        elif iid == "king_agent":
            from analytics.local_llm_bridge import load_llm_config, ollama_available

            cfg = load_llm_config(root)
            base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
            ok = ollama_available(base, timeout_s=2.0)
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=base, tier=tier))

        elif iid == "r3_bau":
            pol = _load_json(root / "control/king_32b_autonomous_build.json")
            ok = bool(pol.get("autonomous_build_enabled"))
            out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=pol.get("headline_de", ""), tier=tier))

        elif iid == "series_ready":
            sr = _load_json(root / "evidence/series_readiness_latest.json")
            ok = bool(sr.get("series_ready"))
            out.update(
                _result(
                    ok=ok,
                    status="PASS" if ok else "FAIL",
                    detail_de=str(sr.get("headline_de") or sr.get("readiness_pct")),
                    tier=tier,
                )
            )

        else:
            ref = item.get("evidence_ref")
            if ref:
                doc = _load_json(root / str(ref))
                fields = list(item.get("fields_de") or [])
                ok = _fields_present(doc, fields) if fields else bool(doc)
                out.update(_result(ok=ok, status="PASS" if ok else "FAIL", detail_de=str(ref), tier=tier))
            else:
                out.update(_result(status="PARTIAL", detail_de="kein Scanner — manuell", tier=tier))

    except Exception as exc:
        out.update(_result(status="FAIL", detail_de=str(exc)[:120], tier=tier))

    return out


def scan_operational_checklist(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Alle Checklisten-Punkte scannen — PASS / PARTIAL / FAIL."""
    root = Path(root)
    policy = load_checklist_policy(root)
    sections_out: List[Dict[str, Any]] = []
    all_items: List[Dict[str, Any]] = []

    for section in policy.get("sections") or []:
        if not isinstance(section, dict):
            continue
        items_out: List[Dict[str, Any]] = []
        for item in section.get("items") or []:
            if not isinstance(item, dict):
                continue
            evaluated = _eval_item(root, item, section=section)
            items_out.append(evaluated)
            all_items.append(evaluated)
        sections_out.append(
            {
                "id": section.get("id"),
                "title_de": section.get("title_de"),
                "tier": section.get("tier"),
                "items": items_out,
                "items_ok": sum(1 for i in items_out if i.get("ok")),
                "items_total": len(items_out),
            }
        )

    critical = [i for i in all_items if i.get("tier") == "critical"]
    warnings = [i for i in all_items if i.get("tier") == "warn"]
    crit_fail = [i for i in critical if not i.get("ok")]
    partial = [i for i in all_items if i.get("status") == "PARTIAL"]
    checklist_ok = not crit_fail

    if checklist_ok and not partial:
        headline = f"R3 Checkliste OK — {sum(1 for i in all_items if i.get('ok'))}/{len(all_items)}"
    elif checklist_ok:
        headline = f"R3 Checkliste OK — {len(partial)} Hinweis(e)"
    else:
        headline = f"R3 Checkliste — Blocker: {crit_fail[0].get('label_de')}"

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "checklist_ok": checklist_ok,
        "items_ok": sum(1 for i in all_items if i.get("ok")),
        "items_total": len(all_items),
        "critical_fail": len(crit_fail),
        "partial_count": len(partial),
        "blockers_de": [i.get("label_de") for i in crit_fail],
        "partial_de": [i.get("label_de") for i in partial],
        "sections": sections_out,
        "headline_de": headline,
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "verify_all_de": policy.get("verify_all_de"),
        "test_suites_de": policy.get("test_suites_de"),
        "next_de": (
            "Betrieb OK — http://127.0.0.1:17890/r3"
            if checklist_ok
            else f"Beheben: {crit_fail[0].get('id')} — bash tools/king_ops.sh r3-checklist --repair"
        ),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
