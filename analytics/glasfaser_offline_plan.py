"""Glasfaser-Umzug — Community-Ausbreitung offline-sicher (3 Phasen)."""
from __future__ import annotations

import json
import shutil
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_PLAN_REL = Path("control/GLASFASER_OFFLINE_PLAN.json")
_STATE_REL = Path("control/glasfaser_offline_state.json")
_EVIDENCE_REL = Path("evidence/glasfaser_offline_latest.json")
_BACKUP_DIR_REL = Path("evidence/glasfaser_offline")
_BACKUP_ZIP_NAME = "worker_LITE_backup.zip"


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


def load_glasfaser_plan(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _PLAN_REL)


def load_glasfaser_state(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _STATE_REL)
    if doc:
        return doc
    return {
        "schema_version": 1,
        "active_phase_id": "before_offline",
        "status": "pending",
        "offline_ack_at_utc": None,
        "comeback_ack_at_utc": None,
        "initiated_at_utc": None,
    }


def _save_state(root: Path, state: Dict[str, Any]) -> None:
    state["updated_at_utc"] = _utc_now()
    atomic_write_json(Path(root) / _STATE_REL, state)


def _save_plan_phases(root: Path, phases: List[Dict[str, Any]]) -> None:
    plan = load_glasfaser_plan(root)
    plan["phases"] = phases
    plan["updated_at_utc"] = _utc_now()
    atomic_write_json(Path(root) / _PLAN_REL, plan)


def _gate_tunnel_token_set(root: Path) -> Tuple[bool, str]:
    from analytics.remote_hub_access import load_tunnel_state, remote_access_status

    remote = remote_access_status(root)
    if remote.get("tunnel_token_set"):
        return True, "Cloudflare-Tunnel-Token gesetzt (stabile URL)"
    if remote.get("stable"):
        return True, "Stabiler Remote-Zugang (Tailscale o.ä.)"
    tunnel = load_tunnel_state(root)
    if (
        remote.get("tunnel_pid_alive")
        and tunnel.get("ok")
        and remote.get("remote_ready")
        and str(remote.get("public_base_url") or tunnel.get("public_url") or "").startswith("https://")
    ):
        url = str(remote.get("public_base_url") or tunnel.get("public_url") or "")
        return (
            True,
            f"Notfall-Cutover — Quick-Tunnel LIVE ({url[:52]}) · Token nach Online",
        )
    return (
        False,
        "Tunnel-Token fehlt — bash tools/setup_cloudflare_tunnel_token.sh",
    )


def _gate_session_autostart(root: Path) -> Tuple[bool, str]:
    try:
        from analytics.r3_community_stealth import session_autostart_path

        path = session_autostart_path(root)
    except Exception:
        path = Path.home() / ".config/autostart/r3-os-session.desktop"
    if path.is_file():
        return True, str(path)
    return False, "Autostart fehlt — bash tools/king_ops.sh r3-stealth"


def _gate_worker_export_ready(root: Path) -> Tuple[bool, str]:
    from analytics.community_spread_plan import evaluate_gate

    g = evaluate_gate(root, "worker_export_ready")
    return bool(g.get("ok")), str(g.get("detail_de") or "")


def _gate_zip_backup(root: Path) -> Tuple[bool, str]:
    backup = Path(root) / _BACKUP_DIR_REL / _BACKUP_ZIP_NAME
    if backup.is_file() and backup.stat().st_size > 1024:
        return True, str(backup)
    state = load_glasfaser_state(root)
    ext = str(state.get("external_backup_de") or "").strip()
    if ext:
        return True, f"Extern: {ext[:80]}"
    return False, f"Backup fehlt — Repair legt {_BACKUP_DIR_REL / _BACKUP_ZIP_NAME} an"


def _gate_community_spread_ready(root: Path) -> Tuple[bool, str]:
    from analytics.community_spread_plan import scan_community_spread

    scan = scan_community_spread(root)
    ok = bool(scan.get("ok"))
    detail = f"{scan.get('gates_ok')}/{scan.get('gates_total')} Gates"
    if not ok and scan.get("blockers_de"):
        detail += " — " + "; ".join(scan["blockers_de"][:2])
    return ok, detail


def _gate_remote_systemd(root: Path) -> Tuple[bool, str]:
    unit = Path.home() / ".config/systemd/user/active-alpha-preview-hub.service"
    if unit.is_file():
        return True, str(unit)
    legacy = Path.home() / ".config/systemd/user/active-alpha-hub.service"
    if legacy.is_file():
        return True, str(legacy)
    return False, "systemd Hub fehlt — bash tools/install_remote_systemd.sh"


def _gate_offline_ack(root: Path) -> Tuple[bool, str]:
    state = load_glasfaser_state(root)
    if state.get("offline_ack_at_utc"):
        return True, f"Offline bestätigt {state['offline_ack_at_utc']}"
    if state.get("active_phase_id") == "during_offline":
        return False, "bash tools/king_ops.sh glasfaser --go-offline bestätigen"
    return False, "Noch in Vorbereitung — Phase before_offline abschließen"


def _gate_hub_healthy(root: Path) -> Tuple[bool, str]:
    from analytics.community_spread_plan import evaluate_gate

    g = evaluate_gate(root, "hub_healthy")
    return bool(g.get("ok")), str(g.get("detail_de") or "")


def _probe_health(url: str, *, timeout: float = 8.0) -> Tuple[bool, str]:
    base = str(url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        return False, "share_url fehlt"
    health = f"{base}/api/health"
    try:
        req = urllib.request.Request(health, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = 200 <= int(resp.status) < 300
            return ok, f"HTTP {resp.status} {health[:64]}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} {health[:64]}"
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        return False, str(exc)[:100]


def _gate_remote_health_ok(root: Path) -> Tuple[bool, str]:
    from analytics.community_spread_plan import _community_share_url

    url = _community_share_url(root)
    return _probe_health(url)


def _gate_forum_draft_synced(root: Path) -> Tuple[bool, str]:
    from analytics.community_spread_plan import evaluate_gate

    g = evaluate_gate(root, "forum_draft_synced")
    return bool(g.get("ok")), str(g.get("detail_de") or "")


def _gate_comeback_ack(root: Path) -> Tuple[bool, str]:
    state = load_glasfaser_state(root)
    if state.get("comeback_ack_at_utc"):
        return True, f"Comeback {state['comeback_ack_at_utc']}"
    if state.get("active_phase_id") == "after_online":
        return False, "bash tools/king_ops.sh glasfaser --comeback bestätigen"
    return False, "Comeback noch nicht eingeleitet"


_GATE_FNS = {
    "tunnel_token_set": _gate_tunnel_token_set,
    "session_autostart": _gate_session_autostart,
    "worker_export_ready": _gate_worker_export_ready,
    "zip_backup": _gate_zip_backup,
    "community_spread_ready": _gate_community_spread_ready,
    "remote_systemd": _gate_remote_systemd,
    "offline_ack": _gate_offline_ack,
    "hub_healthy": _gate_hub_healthy,
    "remote_health_ok": _gate_remote_health_ok,
    "forum_draft_synced": _gate_forum_draft_synced,
    "comeback_ack": _gate_comeback_ack,
}


def evaluate_gate(root: Path, gate_id: str) -> Dict[str, Any]:
    fn = _GATE_FNS.get(gate_id)
    if fn is None:
        return {"id": gate_id, "ok": False, "detail_de": "unbekanntes Gate"}
    ok, detail = fn(root)
    return {"id": gate_id, "ok": bool(ok), "detail_de": detail}


def _phase_by_id(plan: Dict[str, Any], phase_id: str) -> Optional[Dict[str, Any]]:
    for ph in plan.get("phases") or []:
        if str(ph.get("id") or "") == phase_id:
            return ph
    return None


def evaluate_phase(root: Path, phase: Dict[str, Any]) -> Dict[str, Any]:
    gates = [evaluate_gate(root, str(g)) for g in (phase.get("gates") or [])]
    done = all(g["ok"] for g in gates) if gates else False
    return {
        "id": phase.get("id"),
        "label_de": phase.get("label_de"),
        "status": phase.get("status"),
        "done": done,
        "gates": gates,
        "actions_de": list(phase.get("actions_de") or []),
        "operator_note_de": phase.get("operator_note_de"),
    }


def _backup_worker_zip(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.worker_export_sync import load_export_marker

    marker = load_export_marker(root)
    src = Path(str(marker.get("lite_zip") or root.parent / "active_alpha_worker_LITE.zip"))
    if not src.is_file():
        src = root.parent / "active_alpha_worker_LITE.zip"
    dest_dir = root / _BACKUP_DIR_REL
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _BACKUP_ZIP_NAME
    if not src.is_file():
        return {"ok": False, "error_de": f"Lite-ZIP fehlt: {src}"}
    shutil.copy2(src, dest)
    return {"ok": True, "source": str(src), "backup": str(dest), "bytes": dest.stat().st_size}


def _repair_before_offline(root: Path) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []

    def _step(sid: str, label: str, fn) -> None:
        try:
            out = fn()
            ok = bool(out.get("ok", True)) if isinstance(out, dict) else bool(out)
            steps.append({"id": sid, "label_de": label, "ok": ok, "detail": out})
        except Exception as exc:
            steps.append({"id": sid, "label_de": label, "ok": False, "error_de": str(exc)[:120]})

    _step(
        "community_stealth",
        "Autostart (Stealth)",
        lambda: __import__(
            "analytics.r3_community_stealth", fromlist=["install_community_stealth"]
        ).install_community_stealth(root, persist=True),
    )
    _step(
        "community_spread",
        "Community-Spread synchronisieren",
        lambda: __import__(
            "analytics.community_spread_plan", fromlist=["ensure_community_spread"]
        ).ensure_community_spread(root, repair=True, persist=True),
    )
    _step("zip_backup", "Worker-ZIP Backup", lambda: _backup_worker_zip(root))
    _step(
        "remote_systemd",
        "Remote systemd",
        lambda: {
            "ok": True,
            "skipped": not (root / "tools/install_remote_systemd.sh").is_file(),
            "hint_de": "bash tools/install_remote_systemd.sh",
        },
    )
    return steps


def _repair_after_online(root: Path) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []

    def _step(sid: str, label: str, fn) -> None:
        try:
            out = fn()
            ok = bool(out.get("ok", True)) if isinstance(out, dict) else bool(out)
            steps.append({"id": sid, "label_de": label, "ok": ok, "detail": out})
        except Exception as exc:
            steps.append({"id": sid, "label_de": label, "ok": False, "error_de": str(exc)[:120]})

    _step(
        "hub",
        "Hub sicherstellen",
        lambda: {
            "ok": True,
            "port": __import__("analytics.hub_runtime", fromlist=["ensure_running"]).ensure_running(root),
        },
    )
    _step(
        "community_spread",
        "Community-Spread Repair",
        lambda: __import__(
            "analytics.community_spread_plan", fromlist=["ensure_community_spread"]
        ).ensure_community_spread(root, repair=True, persist=True),
    )
    def _health_step() -> Dict[str, Any]:
        ok, detail = _gate_remote_health_ok(root)
        return {"ok": ok, "detail_de": detail}

    _step("health", "Remote Health-Check", _health_step)
    return steps


def initiate_glasfaser_plan(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Phase einleiten — startet bei before_offline."""
    root = Path(root)
    plan = load_glasfaser_plan(root)
    state = load_glasfaser_state(root)
    now = _utc_now()
    state.update(
        {
            "active_phase_id": "before_offline",
            "status": "ACTIVE",
            "initiated_at_utc": state.get("initiated_at_utc") or now,
        }
    )
    phases = list(plan.get("phases") or [])
    for ph in phases:
        pid = str(ph.get("id") or "")
        if pid == "before_offline":
            ph["status"] = "active"
        elif pid in ("during_offline", "after_online"):
            ph["status"] = "pending"
    _save_state(root, state)
    _save_plan_phases(root, phases)
    scan = scan_glasfaser_offline(root, persist=False)
    doc = {
        "ok": True,
        "initiated": True,
        "active_phase_id": "before_offline",
        "headline_de": "Glasfaser-Umzug eingeleitet — Phase 1 aktiv",
        "message_de": "Nächster Schritt: bash tools/king_ops.sh glasfaser --repair",
        "scan": scan,
        "updated_at_utc": now,
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def set_glasfaser_phase(
    root: Path,
    *,
    phase_id: str,
    ack: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    plan = load_glasfaser_plan(root)
    state = load_glasfaser_state(root)
    now = _utc_now()
    if phase_id == "during_offline" and ack:
        state["offline_ack_at_utc"] = now
    if phase_id == "after_online" and ack:
        state["comeback_ack_at_utc"] = now
    state["active_phase_id"] = phase_id
    state["status"] = "ACTIVE"
    order = ["before_offline", "during_offline", "after_online"]
    phase_idx = order.index(phase_id) if phase_id in order else 0
    phases = list(plan.get("phases") or [])
    for ph in phases:
        pid = str(ph.get("id") or "")
        idx = order.index(pid) if pid in order else 99
        if idx < phase_idx:
            ph["status"] = "done"
        elif idx == phase_idx:
            ph["status"] = "active"
        else:
            ph["status"] = "pending"
    _save_state(root, state)
    _save_plan_phases(root, phases)
    scan = scan_glasfaser_offline(root, persist=persist)
    return scan


def scan_glasfaser_offline(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    plan = load_glasfaser_plan(root)
    state = load_glasfaser_state(root)
    active_id = str(state.get("active_phase_id") or "before_offline")
    evaluated = [evaluate_phase(root, ph) for ph in (plan.get("phases") or []) if isinstance(ph, dict)]
    active_ev = next((e for e in evaluated if e.get("id") == active_id), evaluated[0] if evaluated else {})
    blockers = [g for g in (active_ev.get("gates") or []) if not g.get("ok")]
    all_before = next((e for e in evaluated if e.get("id") == "before_offline"), {})
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "active_phase_id": active_id,
        "active_phase": active_ev,
        "phases": evaluated,
        "initiated_at_utc": state.get("initiated_at_utc"),
        "offline_ack_at_utc": state.get("offline_ack_at_utc"),
        "comeback_ack_at_utc": state.get("comeback_ack_at_utc"),
        "blockers_de": [f"{g['id']}: {g['detail_de']}" for g in blockers],
        "before_offline_ready": bool(all_before.get("done")),
        "headline_de": (
            f"Glasfaser Phase {active_id} — {len(blockers)} Blocker"
            if blockers
            else f"Glasfaser Phase {active_id} — bereit"
        ),
        "next_de": _next_operator_step(root, active_id, blockers, all_before),
        "ok": not blockers,
        "policy_ref": str(_PLAN_REL).replace("\\", "/"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _next_operator_step(
    root: Path,
    active_id: str,
    blockers: List[Dict[str, Any]],
    all_before: Dict[str, Any],
) -> str:
    if blockers:
        return f"Blocker: {blockers[0].get('id')} — {blockers[0].get('detail_de')}"
    if active_id == "before_offline":
        return "bash tools/king_ops.sh glasfaser --go-offline (wenn Glasfaser-Cutover startet)"
    if active_id == "during_offline":
        return "Warten — nach Online: bash tools/king_ops.sh glasfaser --comeback --repair"
    if active_id == "after_online":
        return "Forum posten: evidence/community_spread_forum_de.txt"
    return "bash tools/king_ops.sh glasfaser --repair"


def apply_glasfaser_cutover_now(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Notfall Glasfaser-Cutover — alles was ohne Token geht, sofort."""
    root = Path(root)
    if not load_glasfaser_state(root).get("initiated_at_utc"):
        initiate_glasfaser_plan(root, persist=False)

    steps: List[Dict[str, Any]] = []

    def _step(sid: str, label: str, fn) -> None:
        try:
            out = fn()
            ok = bool(out.get("ok", True)) if isinstance(out, dict) else bool(out)
            steps.append({"id": sid, "label_de": label, "ok": ok, "detail": out})
        except Exception as exc:
            steps.append({"id": sid, "label_de": label, "ok": False, "error_de": str(exc)[:120]})

    _step(
        "hub",
        "Hub online",
        lambda: {
            "ok": True,
            "port": __import__("analytics.hub_runtime", fromlist=["ensure_running"]).ensure_running(root),
        },
    )
    _step(
        "tunnel",
        "Quick-Tunnel sicherstellen",
        lambda: __import__(
            "analytics.remote_hub_access", fromlist=["ensure_remote_hub_url"]
        ).ensure_remote_hub_url(root, mode="auto"),
    )
    repair = apply_glasfaser_repair(root, persist=False)
    steps.extend(repair.get("steps") or [])

    backup = _backup_worker_zip(root)
    home_copy = Path.home() / "glasfaser_NOTFALL_worker_LITE.zip"
    try:
        if backup.get("ok") and Path(str(backup.get("backup"))).is_file():
            shutil.copy2(backup["backup"], home_copy)
            backup["home_copy"] = str(home_copy)
    except OSError as exc:
        backup["home_copy_error"] = str(exc)[:80]
    steps.append({"id": "home_zip", "label_de": "ZIP nach ~/", "ok": home_copy.is_file(), "detail": backup})

    _step(
        "systemd",
        "systemd Remote-Runtime",
        lambda: {
            "ok": True,
            "installed": __import__(
                "analytics.remote_hub_access", fromlist=["install_remote_systemd_services"]
            ).install_remote_systemd_services(root),
        },
    )

    from analytics.community_spread_plan import _community_share_url, _write_forum_draft
    from analytics.remote_hub_access import remote_access_status

    _write_forum_draft(root)
    remote = remote_access_status(root)
    url = _community_share_url(root)
    health_ok = False
    health_detail = ""
    if url:
        try:
            import urllib.request

            req = urllib.request.Request(f"{url.rstrip('/')}/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                health_ok = 200 <= int(resp.status) < 300
                health_detail = f"HTTP {resp.status}"
        except Exception as exc:
            health_detail = str(exc)[:100]

    scan = scan_glasfaser_offline(root, persist=persist)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "cutover": True,
        "ok": bool(scan.get("ok")),
        "before_offline_ready": bool(scan.get("before_offline_ready")),
        "steps": steps,
        "scan": scan,
        "public_base_url": url,
        "join_url": f"{url.rstrip('/')}/join" if url else None,
        "health_ok": health_ok,
        "health_detail_de": health_detail,
        "tunnel_mode_de": "Quick-Tunnel LIVE — Token nach Glasfaser-Online",
        "home_zip": str(home_copy) if home_copy.is_file() else None,
        "project_zip": str(root / _BACKUP_DIR_REL / _BACKUP_ZIP_NAME),
        "headline_de": (
            "NOTFALL-CUTOVER BEREIT — PC kann offline"
            if scan.get("ok")
            else scan.get("headline_de")
        ),
        "next_de": (
            "bash tools/king_ops.sh glasfaser --go-offline — Bagger/Offline jetzt"
            if scan.get("ok")
            else scan.get("next_de")
        ),
        "after_online_de": [
            "bash tools/setup_cloudflare_tunnel_token.sh",
            "bash tools/king_ops.sh glasfaser --comeback --repair",
        ],
    }
    if persist:
        atomic_write_json(root / Path("evidence/glasfaser_cutover_now_latest.json"), doc)
    return doc


def apply_glasfaser_repair(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    state = load_glasfaser_state(root)
    phase_id = str(state.get("active_phase_id") or "before_offline")
    if not state.get("initiated_at_utc"):
        initiate_glasfaser_plan(root, persist=False)
    steps: List[Dict[str, Any]] = []
    if phase_id == "before_offline":
        steps = _repair_before_offline(root)
    elif phase_id == "after_online":
        steps = _repair_after_online(root)
    scan = scan_glasfaser_offline(root, persist=persist)
    ok_steps = sum(1 for s in steps if s.get("ok"))
    return {
        "ok": bool(scan.get("ok")) or ok_steps > 0,
        "phase_id": phase_id,
        "steps": steps,
        "steps_ok": ok_steps,
        "steps_total": len(steps),
        "scan": scan,
        "headline_de": scan.get("headline_de"),
        "next_de": scan.get("next_de"),
    }
