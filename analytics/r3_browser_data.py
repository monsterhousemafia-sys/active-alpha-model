"""R3 als lokaler Browser — Prognose-Daten direkt aus dem Internet."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_browser_data_policy.json")
_EVIDENCE_REL = Path("evidence/r3_browser_ingest_latest.json")


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


def load_browser_data_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "internet_first": True,
            "price_source": "internet",
            "mode_de": "Lokaler Browser — Daten aus Internet",
            "session_autostart_ingest": True,
            "fast_ingest_on_hub_open": True,
        }
    return doc


def load_ingest_status(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)


def _internet_env(root: Path, policy: Mapping[str, Any]) -> Dict[str, str]:
    from aa_config_env import load_aa_env

    env = dict(load_aa_env(root))
    src = str(policy.get("price_source") or "internet").strip().lower()
    env["AA_PRICE_DATA_SOURCE"] = src
    for key, val in (policy.get("session_env") or {}).items():
        env[str(key)] = str(val)
    return env


def ingest_prognosis_data_from_internet(
    root: Path,
    *,
    force: bool = False,
    fast: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """R3 zieht Prognose-Rohdaten live aus dem Internet (yfinance, Quotes, optional Sektoren)."""
    root = Path(root)
    policy = load_browser_data_policy(root)
    steps: List[Dict[str, Any]] = []

    try:
        from aa_adaptive_runtime import probe_internet_prices, refresh_price_feed_state

        internet_ok = probe_internet_prices()
    except Exception as exc:
        internet_ok = False
        steps.append({"step": "internet_probe", "ok": False, "error_de": str(exc)[:120]})

    if not internet_ok:
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": False,
            "internet_ok": False,
            "mode_de": str(policy.get("mode_de") or ""),
            "message_de": "Kein Internet — R3 kann Prognose-Daten nicht aktualisieren.",
            "ingest_steps": steps,
        }
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    env = _internet_env(root, policy)
    old_env = {k: os.environ.get(k) for k in env}
    try:
        os.environ.update({str(k): str(v) for k, v in env.items()})

        feed = refresh_price_feed_state(root, env, write=True)
        steps.append(
            {
                "step": "price_feed",
                "ok": True,
                "price_source": feed.get("price_source"),
                "reason": feed.get("price_source_reason"),
            }
        )

        try:
            from market.live_quote_engine import refresh_live_quotes

            quotes = refresh_live_quotes(
                root, force=bool(force and not fast), owner="r3_browser_ingest"
            )
            steps.append(
                {
                    "step": "live_quotes",
                    "ok": True,
                    "provider": quotes.get("provider"),
                    "skipped": bool(quotes.get("refresh_skipped")),
                }
            )
        except Exception as exc:
            steps.append({"step": "live_quotes", "ok": False, "error_de": str(exc)[:120]})

        price_latest: Optional[str] = None
        price_refreshed = False
        try:
            from aa_data_freshness import assess_daily_data
            from aa_live_daily_sync import refresh_prediction_prices, resolve_prediction_tickers

            report = assess_daily_data(root, env)
            need = bool(force) or not bool(report.price_current)
            if need or not fast:
                tickers, _ = resolve_prediction_tickers(root, env)
                price_refreshed, price_latest, _msgs = refresh_prediction_prices(
                    root, env, tickers=tickers, force=bool(force)
                )
            else:
                price_latest = (
                    report.price_latest.isoformat() if report.price_latest is not None else None
                )
            steps.append(
                {
                    "step": "ohlcv",
                    "ok": True,
                    "refreshed": price_refreshed,
                    "price_latest": price_latest,
                    "fast": bool(fast and not force),
                }
            )
        except Exception as exc:
            steps.append({"step": "ohlcv", "ok": False, "error_de": str(exc)[:120]})

        if not fast and bool(policy.get("internet_first", True)):
            try:
                from aa_sector_reference import ensure_sector_reference_fresh

                sec = ensure_sector_reference_fresh(root, env)
                steps.append({"step": "sectors", "ok": bool(sec.get("ok", True))})
            except Exception as exc:
                steps.append({"step": "sectors", "ok": False, "error_de": str(exc)[:120]})

        from aa_data_freshness import assess_daily_data

        final_report = assess_daily_data(root, env)
        price_latest = (
            final_report.price_latest.isoformat()
            if final_report.price_latest is not None
            else price_latest
        )
        ok = bool(final_report.price_current) or bool(
            str(feed.get("price_source") or "") == "internet"
        )

        doc: Dict[str, Any] = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "ok": ok,
            "internet_ok": True,
            "mode_de": str(policy.get("mode_de") or "Lokaler Browser"),
            "price_source": "internet",
            "price_latest": price_latest,
            "price_current": bool(final_report.price_current),
            "signal_date": (
                final_report.signal_date.isoformat()
                if getattr(final_report, "signal_date", None) is not None
                else None
            ),
            "providers_de": ["yfinance", "live_quote_engine"],
            "sources_de": list(policy.get("sources_de") or []),
            "ingest_steps": steps,
            "message_de": (
                f"R3 Browser: Prognose-Daten aus Internet"
                + (f" · Preise {price_latest}" if price_latest else "")
            ),
        }
    finally:
        for key, prior in old_env.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def maybe_fast_ingest_for_hub(root: Path) -> Dict[str, Any]:
    """Beim Hub-Öffnen: Quote-Keepalive wenn Policy es verlangt."""
    try:
        from analytics.r3_quote_keepalive import (
            assess_quote_freshness,
            load_quote_keepalive_policy,
            tick_quote_keepalive,
        )

        kpol = load_quote_keepalive_policy(root)
        if kpol.get("refresh_on_hub_open", True):
            if assess_quote_freshness(root).get("needs_refresh"):
                return tick_quote_keepalive(root, force=False, owner="hub_open", persist=True)
            prior = load_ingest_status(root)
            if prior:
                return prior
    except Exception:
        pass
    policy = load_browser_data_policy(root)
    if not bool(policy.get("fast_ingest_on_hub_open", True)):
        return load_ingest_status(root)
    prior = load_ingest_status(root)
    if prior.get("ok") and prior.get("price_current") and prior.get("internet_ok") is not False:
        return prior
    return ingest_prognosis_data_from_internet(root, fast=True, force=False, persist=True)


def apply_session_browser_env(policy: Optional[Mapping[str, Any]] = None) -> Dict[str, str]:
    """Setzt Session-Umgebung: R3 = lokaler Browser, Preise aus Internet."""
    policy = dict(policy or {})
    patch = dict(policy.get("session_env") or {})
    if bool(policy.get("internet_first", True)):
        patch.setdefault("AA_PRICE_DATA_SOURCE", str(policy.get("price_source") or "internet"))
    for key, val in patch.items():
        os.environ[str(key)] = str(val)
    return {str(k): str(v) for k, v in patch.items()}


def render_browser_data_strip(root: Path, ingest: Optional[Dict[str, Any]] = None) -> str:
    import html

    doc = ingest or load_ingest_status(root)
    if not doc:
        return ""
    ok = bool(doc.get("ok"))
    cls = "ok" if ok else "fail"
    src = html.escape(str(doc.get("price_source") or "internet"))
    latest = html.escape(str(doc.get("price_latest") or "—"))
    msg = html.escape(str(doc.get("message_de") or doc.get("mode_de") or ""))
    return (
        f'<p class="r3-browser-data {cls}" id="r3-browser-data">'
        f"<strong>Lokaler Browser</strong> · Datenquelle {src} · Preise {latest}"
        f"{f' · {msg}' if msg else ''}"
        f"</p>"
    )
