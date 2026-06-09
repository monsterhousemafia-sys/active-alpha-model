"""Erhaltungsprogramm — Wartung + Konsolidierung Bash-Weltverbreitung."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_PLAN_REL = Path("control/ERHALTUNGSPROGRAMM.json")
_STATE_REL = Path("control/erhaltungsprogramm_state.json")
_EVIDENCE_REL = Path("evidence/erhaltungsprogramm_latest.json")
_CONSOLIDATION_REL = Path("evidence/bash_weltweit_consolidation_latest.json")

_KING_OPS_COMMANDS = (
    "verify",
    "status",
    "maintain",
    "pipeline",
    "distribute",
    "community-spread",
    "glasfaser",
    "series-ready",
    "r3-stealth",
    "pulse",
    "h1-seal",
    "workers",
    "connect",
)


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


def load_erhaltungsprogramm_plan(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _PLAN_REL)


def load_erhaltungs_state(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _STATE_REL)
    if doc:
        return doc
    return {"schema_version": 1, "status": "pending", "started_at_utc": None}


def _bash_script_count(root: Path) -> int:
    tools = Path(root) / "tools"
    if not tools.is_dir():
        return 0
    return sum(1 for p in tools.glob("*.sh") if p.is_file())


def _worker_platforms(root: Path) -> List[Dict[str, Any]]:
    from analytics.worker_export_sync import load_export_marker

    marker = load_export_marker(root)
    lite_dest = Path(str(marker.get("lite_dest") or root.parent / "active_alpha_worker_LITE"))
    platforms = [
        ("linux", "Linux_START.sh"),
        ("windows", "Windows_START.bat"),
        ("macos", "Mac_START.command"),
    ]
    out: List[Dict[str, Any]] = []
    for os_id, script in platforms:
        path = lite_dest / script
        out.append(
            {
                "os": os_id,
                "script": script,
                "present": path.is_file(),
                "path": str(path) if path.is_file() else None,
            }
        )
    return out


def consolidate_bash_weltweit(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Konsolidiert wie Bash sich weltweit ausgebreitet hat — Schichten + Evidence."""
    root = Path(root)
    plan = load_erhaltungsprogramm_plan(root)
    orch = _load_json(root / "control/h1_orchestrator_model.json")
    world = _load_json(root / "evidence/world_spread_latest.json")
    community = _load_json(root / "evidence/community_spread_sustain_latest.json")
    glasfaser = _load_json(root / "evidence/glasfaser_offline_latest.json")
    distribute = _load_json(root / "evidence/king_distribute_latest.json")
    federation = _load_json(root / "evidence/preview_federation.json")
    remote = _load_json(root / "evidence/remote_hub_tunnel.json")

    workers = federation.get("workers") if isinstance(federation.get("workers"), dict) else {}
    worker_rows = [
        {
            "worker_id": wid,
            "role": str((w or {}).get("role") or ""),
            "host": str((w or {}).get("hostname") or (w or {}).get("host") or "")[:64],
            "remote_join": bool((w or {}).get("remote_join")),
        }
        for wid, w in (workers or {}).items()
        if isinstance(w, dict)
    ]

    platforms = _worker_platforms(root)
    script_n = _bash_script_count(root)
    public_url = str(
        world.get("public_base_url")
        or community.get("share_url")
        or remote.get("public_url")
        or ""
    ).rstrip("/")

    layers: List[Dict[str, Any]] = [
        {
            "id": "koenig",
            "label_de": "König-Host (Orchestrator)",
            "entry_de": "bash tools/king_ops.sh",
            "role_de": str(orch.get("bash_role_de") or "Ein Bash-Einstieg — 30+ Befehle"),
            "scripts_in_tools": script_n,
            "primary_commands_de": list(_KING_OPS_COMMANDS),
        },
        {
            "id": "verteilen",
            "label_de": "König verteilt",
            "entry_de": "bash tools/king_distribute.sh",
            "chains_de": [
                "world-spread → Tunnel + Lite-ZIP",
                "spread-intensify → Forum + Timer",
                "h1-distribute → Worker-Queue",
            ],
            "last_headline_de": distribute.get("headline_de"),
        },
        {
            "id": "worker_weltweit",
            "label_de": "Worker weltweit (ZIP)",
            "entry_de": "Doppelklick START-Skript — kein König-Bash nötig",
            "platforms": platforms,
            "lite_zip": str(
                world.get("lite_zip") or distribute.get("lite_zip") or root.parent / "active_alpha_worker_LITE.zip"
            ),
            "join_url": world.get("join_url") or community.get("join_url"),
        },
        {
            "id": "community_linux",
            "label_de": "Linux-Community",
            "entry_de": "bash tools/king_ops.sh community-spread",
            "forum_ref": "evidence/community_spread_forum_de.txt",
            "gates_ok": community.get("gates_ok"),
            "share_url": community.get("share_url") or public_url,
        },
        {
            "id": "glasfaser",
            "label_de": "Glasfaser-Umzug",
            "entry_de": "bash tools/king_ops.sh glasfaser",
            "active_phase": glasfaser.get("active_phase_id"),
            "blockers_de": glasfaser.get("blockers_de") or [],
        },
    ]

    isolation_de = (
        "Worker-Bash läuft isoliert — Rechenleistung nur mit gültiger Join-URL + Token. "
        "mom_1-Seal und Orders bleiben beim König."
    )

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "doctrine_de": plan.get("doctrine_de") or orch.get("orchestrator_de"),
        "headline_de": (
            f"Bash weltweit — {script_n} König-Skripte · "
            f"{sum(1 for p in platforms if p.get('present'))}/3 Worker-Plattformen · "
            f"{len(worker_rows)} Federation-Knoten"
        ),
        "public_base_url": public_url or None,
        "tunnel_stable": bool(world.get("tunnel_stable") or remote.get("stable")),
        "tunnel_token_set": bool(
            (world.get("remote_status") or {}).get("tunnel_token_set")
        ),
        "layers": layers,
        "federation_workers": worker_rows,
        "federation_worker_count": len(worker_rows),
        "world_spread_ok": bool(world.get("ok")),
        "community_spread_ok": bool(community.get("ok")),
        "isolation_de": isolation_de,
        "spread_map_de": [
            "König: king_ops.sh → verify/maintain/distribute/pulse",
            "Welt: king_distribute.sh → ai_kernel world-spread",
            "Community: community-spread → Forum + Timer",
            "Worker: Lite-ZIP → Linux/Win/Mac START (Python 3)",
            "H1-Welt: Full-Worker → Prep-Chunks zurück zum König",
        ],
        "evidence_refs": [
            "evidence/world_spread_latest.json",
            "evidence/community_spread_sustain_latest.json",
            "evidence/king_distribute_latest.json",
            "evidence/glasfaser_offline_latest.json",
            "control/h1_orchestrator_model.json",
        ],
        "next_de": (
            "Tunnel-Token stabilisieren — bash tools/setup_cloudflare_tunnel_token.sh"
            if not bool((world.get("remote_status") or {}).get("tunnel_token_set"))
            else "bash tools/king_ops.sh distribute — ZIP weltweit teilen"
        ),
    }
    if persist:
        atomic_write_json(root / _CONSOLIDATION_REL, doc)
    return doc


def _run_bash_step(root: Path, script: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
    root = Path(root)
    path = root / script
    if not path.is_file():
        return {"ok": False, "error_de": f"fehlt: {script}"}
    proc = subprocess.run(
        ["bash", str(path), *(args or [])],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "script": script,
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-800:],
    }


def start_erhaltungsprogramm(root: Path, *, repair: bool = True, persist: bool = True) -> Dict[str, Any]:
    """Erhaltungsprogramm starten — Wartung + Bash-Welt-Konsolidierung."""
    root = Path(root)
    state = load_erhaltungs_state(root)
    now = _utc_now()
    if not state.get("started_at_utc"):
        state["started_at_utc"] = now
    state["status"] = "ACTIVE"
    state["last_run_at_utc"] = now
    atomic_write_json(root / _STATE_REL, state)

    steps: List[Dict[str, Any]] = []

    def _record(sid: str, label: str, fn) -> None:
        try:
            out = fn()
            ok = bool(out.get("ok", True)) if isinstance(out, dict) else bool(out)
            steps.append({"id": sid, "label_de": label, "ok": ok, "detail": out})
        except Exception as exc:
            steps.append({"id": sid, "label_de": label, "ok": False, "error_de": str(exc)[:120]})

    if repair:
        _record("verify", "Safety verify", lambda: _run_bash_step(root, "tools/king_verify.sh"))
        _record("maintain", "Maintain (clean)", lambda: _run_bash_step(root, "tools/king_clean.sh"))
        _record(
            "community_spread",
            "Community-Spread Scan",
            lambda: __import__(
                "analytics.community_spread_plan", fromlist=["scan_community_spread"]
            ).scan_community_spread(root),
        )
        _record(
            "glasfaser",
            "Glasfaser Scan",
            lambda: __import__(
                "analytics.glasfaser_offline_plan", fromlist=["scan_glasfaser_offline"]
            ).scan_glasfaser_offline(root, persist=True),
        )
        _record(
            "series_ready",
            "Serienreife Scan",
            lambda: __import__(
                "analytics.series_readiness", fromlist=["scan_series_readiness"]
            ).scan_series_readiness(root, persist=True, force=True, fast=True),
        )

    consolidation = consolidate_bash_weltweit(root, persist=True)
    steps.append(
        {
            "id": "bash_consolidation",
            "label_de": "Bash weltweit konsolidieren",
            "ok": True,
            "detail": {"headline_de": consolidation.get("headline_de")},
        }
    )

    ok_n = sum(1 for s in steps if s.get("ok"))
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": now,
        "status": "ACTIVE",
        "started_at_utc": state.get("started_at_utc"),
        "ok": ok_n == len(steps),
        "steps": steps,
        "steps_ok": ok_n,
        "steps_total": len(steps),
        "consolidation": consolidation,
        "consolidation_ref": str(_CONSOLIDATION_REL),
        "headline_de": consolidation.get("headline_de"),
        "doctrine_de": consolidation.get("doctrine_de"),
        "next_de": consolidation.get("next_de"),
        "message_de": (
            "Erhaltungsprogramm aktiv — Bash-Welt konsolidiert in evidence/bash_weltweit_consolidation_latest.json"
        ),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
