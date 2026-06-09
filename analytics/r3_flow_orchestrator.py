"""R3 Flow-Orchestrator — Hardware + Software fließen visuell in R3 zusammen."""
from __future__ import annotations

import html
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_flow_orchestrator_policy.json")
_EVIDENCE_REL = Path("evidence/r3_flow_latest.json")


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


def load_flow_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _channel(
    *,
    cid: str,
    label_de: str,
    ok: bool,
    detail_de: str,
    warn: bool = False,
) -> Dict[str, Any]:
    state = "ok" if ok else ("warn" if warn else "fail")
    return {
        "id": cid,
        "label_de": label_de,
        "ok": bool(ok),
        "warn": bool(warn) and not ok,
        "state": state,
        "detail_de": detail_de[:120],
    }


def _hardware_channel(root: Path, hardware: Dict[str, Any], pulse: Dict[str, Any]) -> Dict[str, Any]:
    gpu_on = bool((hardware.get("gpu_returns") or {}).get("enabled"))
    mem = hardware.get("memory_available_gb")
    hung = bool((hardware.get("benchmark") or {}).get("benchmark_hung"))
    over_eta = bool((hardware.get("benchmark") or {}).get("benchmark_over_eta"))
    nvme = bool(hardware.get("nvme_mounted"))
    mem_ok = mem is None or float(mem) >= 8.0
    ok = mem_ok and not hung and nvme
    warn = over_eta or (mem is not None and float(mem) < 12.0)
    detail = (
        f"GPU {'ON' if gpu_on else 'OFF'}"
        + (f" · {float(mem):.0f} GB frei" if mem is not None else "")
        + (" · NVMe" if nvme else " · NVMe fehlt")
    )
    if hung:
        detail = "Benchmark hängt — Status prüfen"
    return _channel(cid="hardware", label_de="Hardware", ok=ok, detail_de=detail, warn=warn)


def _orchestrator_channel(pulse: Dict[str, Any]) -> Dict[str, Any]:
    phase = str(pulse.get("phase") or "sync")
    layer = str(pulse.get("active_layer") or "—")
    handoff = str(pulse.get("handoff_to") or "—")
    hung = bool(pulse.get("benchmark_hung"))
    ok = bool(pulse.get("ok", True)) and not hung
    detail = f"{phase} · {layer} → {handoff}"
    if pulse.get("beat"):
        detail = f"Takt {pulse.get('beat')} · {detail}"
    return _channel(cid="orchestrator", label_de="Takt", ok=ok, detail_de=detail, warn=hung)


def _hub_channel(root: Path) -> Dict[str, Any]:
    try:
        from analytics.hub_runtime import build_health_report

        rep = build_health_report(root)
        ok = bool(rep.get("online"))
        detail = f"HTTP :{rep.get('port', 17890)}" if ok else "Hub offline"
        return _channel(cid="hub", label_de="Hub", ok=ok, detail_de=detail, warn=not ok)
    except Exception as exc:
        return _channel(cid="hub", label_de="Hub", ok=False, detail_de=str(exc)[:80], warn=True)


def _r3_cockpit_channel(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_runtime import build_health_report

        rep = build_health_report(root)
        running = bool(rep.get("cockpit_running"))
        cache = _load_json(root / "evidence/desktop_shell_cache_meta.json")
        cache_ok = bool(cache.get("bytes", 0) >= 120)
        ok = running or cache_ok
        if running:
            detail = "Qt-Cockpit aktiv"
        elif cache_ok:
            detail = "Cache warm — Fenster geschlossen"
        else:
            detail = "R3 wartet"
        return _channel(
            cid="r3_cockpit",
            label_de="R3 Cockpit",
            ok=ok,
            detail_de=detail,
            warn=not running and cache_ok,
        )
    except Exception as exc:
        return _channel(
            cid="r3_cockpit",
            label_de="R3 Cockpit",
            ok=False,
            detail_de=str(exc)[:80],
            warn=True,
        )


def _kurse_channel(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_browser_data import load_ingest_status

        doc = load_ingest_status(root)
    except Exception:
        doc = {}
    if not doc:
        return _channel(
            cid="kurse",
            label_de="Kurse",
            ok=False,
            detail_de="Ingest ausstehend",
            warn=True,
        )
    ok = bool(doc.get("internet_ok")) and bool(doc.get("ok"))
    latest = str(doc.get("price_latest") or "—")
    return _channel(
        cid="kurse",
        label_de="Kurse",
        ok=ok,
        detail_de=f"Internet · {latest}",
        warn=bool(doc.get("internet_ok")) and not ok,
    )


def _modell_channel(root: Path) -> Dict[str, Any]:
    try:
        from analytics.alpha_model_background_engine import build_engine_status

        eng = build_engine_status(root)
        predict = eng.get("predict") or {}
        h1 = eng.get("h1_backtest") or {}
        signal = str(predict.get("signal_date") or eng.get("r3_display", {}).get("signal_date") or "—")
        h1s = str(h1.get("status") or "—")
        ok = bool(eng.get("ok")) or bool(predict.get("ok")) or bool(eng.get("r3_display", {}).get("ok"))
        detail = f"Hintergrund · {signal} · H1 {h1s}"
        return _channel(cid="modell", label_de="Modell", ok=ok, detail_de=detail, warn=not ok)
    except Exception:
        readiness = _load_json(root / "control/prediction_readiness.json")
        signal = str(readiness.get("signal_date") or "—")
        ok = bool(readiness.get("ok"))
        return _channel(cid="modell", label_de="Modell", ok=ok, detail_de=f"Hintergrund · {signal}", warn=not ok)


def _hub_channel_readonly(root: Path) -> Dict[str, Any]:
    try:
        from analytics.hub_runtime import build_health_report

        rep = build_health_report(root)
        ok = bool(rep.get("online"))
        detail = f"HTTP :{rep.get('port', 17890)}" if ok else "Hub offline"
        return _channel(cid="hub", label_de="Hub", ok=ok, detail_de=detail, warn=not ok)
    except Exception as exc:
        return _channel(cid="hub", label_de="Hub", ok=False, detail_de=str(exc)[:80], warn=True)


def _r3_cockpit_channel_readonly(root: Path) -> Dict[str, Any]:
    cache = _load_json(root / "evidence/desktop_shell_cache_meta.json")
    cache_ok = bool(cache.get("bytes", 0) >= 120)
    ok = cache_ok
    detail = "Cache warm" if cache_ok else "Cache ausstehend"
    return _channel(cid="r3_cockpit", label_de="R3 Cockpit", ok=ok, detail_de=detail, warn=not ok)


def _kurse_channel_readonly(root: Path) -> Dict[str, Any]:
    doc = _load_json(root / "evidence/r3_browser_ingest_latest.json")
    if not doc:
        return _channel(cid="kurse", label_de="Kurse", ok=False, detail_de="Ingest ausstehend", warn=True)
    ok = bool(doc.get("internet_ok")) and bool(doc.get("ok"))
    latest = str(doc.get("price_latest") or "—")
    return _channel(
        cid="kurse",
        label_de="Kurse",
        ok=ok,
        detail_de=f"Internet · {latest}",
        warn=bool(doc.get("internet_ok")) and not ok,
    )


def _modell_channel_readonly(root: Path) -> Dict[str, Any]:
    eng = _load_json(root / "evidence/alpha_model_background_engine_latest.json")
    if not eng:
        readiness = _load_json(root / "control/prediction_readiness.json")
        signal = str(readiness.get("signal_date") or "—")
        ok = bool(readiness.get("ok"))
        return _channel(cid="modell", label_de="Modell", ok=ok, detail_de=f"Hintergrund · {signal}", warn=not ok)
    predict = eng.get("predict") or {}
    h1 = eng.get("h1_backtest") or {}
    signal = str(predict.get("signal_date") or eng.get("r3_display", {}).get("signal_date") or "—")
    h1s = str(h1.get("status") or "—")
    ok = bool(eng.get("ok")) or bool((eng.get("r3_display") or {}).get("ok"))
    return _channel(cid="modell", label_de="Modell", ok=ok, detail_de=f"Hintergrund · {signal} · H1 {h1s}", warn=not ok)


def _fluidity_pct(channels: List[Dict[str, Any]], *, penalties: int = 0) -> int:
    if not channels:
        return 0
    score = sum(100 if c.get("ok") else (50 if c.get("warn") else 0) for c in channels)
    base = int(round(score / len(channels)))
    return max(0, min(100, base - penalties * 10))


def build_r3_flow_status(
    root: Path,
    *,
    pulse: Optional[Dict[str, Any]] = None,
    hardware: Optional[Dict[str, Any]] = None,
    persist: bool = False,
    read_only: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    policy = load_flow_policy(root)
    pulse = pulse if pulse is not None else _load_json(root / "evidence/king_network_pulse_latest.json")
    hardware = hardware if hardware is not None else _load_json(root / "evidence/king_hardware_latest.json")

    if read_only:
        channels = [
            _hardware_channel(root, hardware, pulse),
            _orchestrator_channel(pulse),
            _hub_channel_readonly(root),
            _r3_cockpit_channel_readonly(root),
            _kurse_channel_readonly(root),
            _modell_channel_readonly(root),
        ]
    else:
        channels = [
            _hardware_channel(root, hardware, pulse),
            _orchestrator_channel(pulse),
            _hub_channel(root),
            _r3_cockpit_channel(root),
            _kurse_channel(root),
            _modell_channel(root),
        ]
    penalties = 0
    if bool((hardware.get("benchmark") or {}).get("benchmark_hung")):
        penalties += 1
    if bool(pulse.get("benchmark_hung")):
        penalties += 1
    fluidity = _fluidity_pct(channels, penalties=penalties)
    stable_min = int(policy.get("fluidity_stable_min_pct") or 75)
    ok_n = sum(1 for c in channels if c.get("ok"))
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": str(policy.get("headline_de") or "R3 Flow"),
        "fluidity_pct": fluidity,
        "stable": fluidity >= stable_min,
        "stable_min_pct": stable_min,
        "channels_ok": ok_n,
        "channels_total": len(channels),
        "channels": channels,
        "merge_de": "R3",
        "pulse_ref": "evidence/king_network_pulse_latest.json",
        "hardware_ref": "evidence/king_hardware_latest.json",
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "message_de": (
            f"{'Stabil' if fluidity >= stable_min else 'Aufbau'} · "
            f"{fluidity}% flüssig · {ok_n}/{len(channels)} Kanäle"
        ),
        "next_de": "bash tools/king_ops.sh r3-flow",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def sync_r3_flow(
    root: Path,
    *,
    source_node: str = "r3",
    warm_cache: bool = False,
    persist: bool = True,
) -> Dict[str, Any]:
    """Hard/Soft synchronisieren — Prognose-Pipeline hält R3-Cache."""
    root = Path(root)
    pulse: Dict[str, Any] = {}
    hardware: Dict[str, Any] = {}
    try:
        from analytics.king_network import sync_network_pulse

        pulse = sync_network_pulse(root, source_node=source_node)
        hardware = _load_json(root / "evidence/king_hardware_latest.json")
    except Exception:
        pulse = _load_json(root / "evidence/king_network_pulse_latest.json")
        hardware = _load_json(root / "evidence/king_hardware_latest.json")

    doc = build_r3_flow_status(root, pulse=pulse, hardware=hardware, persist=persist)

    if warm_cache:
        def _warm() -> None:
            try:
                from analytics.desktop_shell_cache import warm_desktop_cache

                warm_desktop_cache(root, fast=True, block=False)
            except Exception:
                pass

        threading.Thread(target=_warm, name="r3-flow-warm", daemon=True).start()

    return doc


R3_FLOW_CSS = """
.r3-flow {
  display: flex; align-items: center; justify-content: center; flex-wrap: wrap;
  gap: 6px; margin: 14px 0 6px; padding: 10px 12px; border-radius: 16px;
  border: 1px solid var(--line); background: rgba(127,127,127,.05);
}
.r3-flow-node {
  padding: 5px 11px; border-radius: 999px; font-size: 11px; font-weight: 600;
  border: 1px solid var(--line); background: rgba(127,127,127,.08); color: var(--muted);
  white-space: nowrap;
}
.r3-flow-node.ok { border-color: rgba(50,215,76,.45); color: var(--ok, #32d74b); }
.r3-flow-node.warn { border-color: rgba(255,214,10,.45); color: var(--warn, #ffd60a); }
.r3-flow-node.fail { border-color: rgba(255,69,58,.45); color: var(--fail, #ff453a); }
.r3-flow-arrow { font-size: 12px; color: var(--muted); opacity: .55; user-select: none; }
.r3-flow-merge {
  font-size: 13px; font-weight: 800; letter-spacing: .08em;
  color: var(--accent); padding: 5px 14px; border-radius: 999px;
  background: var(--accent-soft, rgba(94,92,230,.18));
  border: 1px solid rgba(94,92,230,.35);
}
.r3-flow-meta {
  text-align: center; margin: 0 0 12px; font-size: 11px; color: var(--muted);
}
"""


def render_r3_flow_strip(
    root: Path,
    flow: Optional[Dict[str, Any]] = None,
    *,
    compact: bool = False,
) -> str:
    if flow is None:
        doc = _load_json(root / _EVIDENCE_REL)
        if not doc:
            doc = build_r3_flow_status(root, persist=False, read_only=True)
    else:
        doc = flow
    nodes = []
    channels = list(doc.get("channels") or [])
    for i, ch in enumerate(channels):
        if i:
            nodes.append('<span class="r3-flow-arrow" aria-hidden="true">›</span>')
        state = str(ch.get("state") or ("ok" if ch.get("ok") else "fail"))
        label = html.escape(str(ch.get("label_de") or ""))
        detail = html.escape(str(ch.get("detail_de") or ""))
        nodes.append(
            f'<span class="r3-flow-node {state}" title="{detail}">{label}</span>'
        )
    nodes.append('<span class="r3-flow-arrow" aria-hidden="true">══►</span>')
    nodes.append(f'<span class="r3-flow-merge">{html.escape(str(doc.get("merge_de") or "R3"))}</span>')
    fluidity = int(doc.get("fluidity_pct") or 0)
    stable = "stabil" if doc.get("stable") else "aufbau"
    meta = html.escape(str(doc.get("message_de") or f"{fluidity}% · {stable}"))
    meta_html = (
        ""
        if compact
        else f'<p class="r3-flow-meta">{fluidity}% flüssig · {meta}</p>'
    )
    return f"""
<div class="r3-flow" id="r3-flow" aria-label="Hard/Soft Fluss in R3">
  {''.join(nodes)}
</div>{meta_html}"""
