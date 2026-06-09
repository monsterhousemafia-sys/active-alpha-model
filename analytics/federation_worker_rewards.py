"""Worker-Entlohnung — fair, messbar, ohne Echtgeld (Legion + CPU-Sekunden)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/FEDERATION_WORKER_REWARDS.json")
_EVIDENCE_REL = Path("evidence/federation_worker_rewards_latest.json")


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


def load_rewards_policy(root: Path) -> Dict[str, Any]:
    cfg = _load_json(Path(root) / _CONFIG_REL)
    if not cfg:
        return {
            "schema_version": 1,
            "enabled": True,
            "join_stipend_cpu_seconds": 60,
            "heartbeat_stipend_cpu_seconds": 3,
            "heartbeat_stipend_min_interval_s": 3600,
            "min_cpu_seconds_per_task": {
                "compute_pulse": 20,
                "backend_preview": 25,
                "snapshot_refresh": 15,
                "hub_verify": 1,
            },
            "pulse_tasks_per_worker": 3,
            "fair_pull_one_active_per_worker": True,
        }
    cfg.setdefault("enabled", True)
    return cfg


def apply_task_reward_credit(
    root: Path,
    *,
    kind: str,
    cpu_seconds: float,
    ok: bool,
) -> float:
    """Mindest-Gutschrift pro erledigtem Job — niemand geht leer aus."""
    if not ok:
        return max(0.0, float(cpu_seconds))
    pol = load_rewards_policy(root)
    if not pol.get("enabled", True):
        return max(0.0, float(cpu_seconds))
    mins = dict(pol.get("min_cpu_seconds_per_task") or {})
    floor = float(mins.get(str(kind or "")) or 1.0)
    return max(float(cpu_seconds), floor)


def grant_join_stipend(root: Path, *, worker_id: str, is_new: bool) -> Dict[str, Any]:
    if not is_new or not worker_id:
        return {"granted": False, "reason_de": "kein Neubeitritt"}
    pol = load_rewards_policy(root)
    if not pol.get("enabled", True):
        return {"granted": False, "reason_de": "Entlohnung deaktiviert"}
    stipend = float(pol.get("join_stipend_cpu_seconds") or 0)
    if stipend <= 0:
        return {"granted": False, "reason_de": "kein Join-Stipendium"}
    from analytics.federation_legion import record_legion_contribution

    entry = record_legion_contribution(
        root,
        worker_id=worker_id,
        ok=True,
        kind="join_stipend",
        cpu_seconds=stipend,
    )
    return {
        "granted": True,
        "cpu_seconds": stipend,
        "kind": "join_stipend",
        "detail_de": f"Willkommens-Gutschrift: {stipend:.0f} CPU-Sekunden",
        "legion_entry": entry,
    }


def grant_heartbeat_stipend(root: Path, *, worker_id: str) -> Dict[str, Any]:
    pol = load_rewards_policy(root)
    if not pol.get("enabled", True) or not worker_id:
        return {"granted": False}
    stipend = float(pol.get("heartbeat_stipend_cpu_seconds") or 0)
    interval = int(pol.get("heartbeat_stipend_min_interval_s") or 3600)
    if stipend <= 0:
        return {"granted": False}

    from analytics.federation_legion import load_legion_stats, record_legion_contribution, save_legion_stats

    doc = load_legion_stats(root)
    workers = dict(doc.get("workers") or {})
    prior = dict(workers.get(worker_id) or {})
    last_raw = str(prior.get("last_heartbeat_stipend_utc") or "")
    now = datetime.now(timezone.utc)
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
            if (now - last).total_seconds() < interval:
                return {"granted": False, "reason_de": "Heartbeat-Intervall"}
        except ValueError:
            pass

    entry = record_legion_contribution(
        root,
        worker_id=worker_id,
        ok=True,
        kind="heartbeat",
        cpu_seconds=stipend,
    )
    entry["last_heartbeat_stipend_utc"] = _utc_now()
    workers[worker_id] = entry
    doc["workers"] = workers
    save_legion_stats(root, doc)
    return {"granted": True, "cpu_seconds": stipend, "kind": "heartbeat"}


def worker_has_active_task(active: Dict[str, Any], worker_id: str) -> bool:
    wid = str(worker_id or "")
    return any(str(v.get("worker_id") or "") == wid for v in active.values())


def worker_fairness_score(root: Path, worker_id: str) -> float:
    """Niedriger = unterversorgt → bei gleicher Priorität bevorzugen."""
    from analytics.federation_legion import load_legion_stats

    stats = load_legion_stats(root).get("workers") or {}
    w = dict(stats.get(worker_id) or {})
    cpu_s = float(w.get("cpu_seconds") or 0)
    tasks = int(w.get("tasks_ok") or 0)
    return cpu_s + tasks * 5.0


def build_rewards_summary(root: Path) -> Dict[str, Any]:
    root = Path(root)
    pol = load_rewards_policy(root)
    from analytics.federation_legion import build_legion_leaderboard, build_legion_summary

    legion = build_legion_summary(root)
    board = build_legion_leaderboard(root)
    rows: List[Dict[str, Any]] = []
    for r in board:
        rank = r.get("rank") or {}
        rows.append(
            {
                "worker_id": r.get("worker_id"),
                "hostname": r.get("hostname"),
                "legion_number": r.get("legion_number"),
                "rank_de": rank.get("name_de"),
                "cpu_seconds": r.get("cpu_seconds"),
                "tasks_ok": r.get("tasks_ok"),
                "entlohnung_de": (
                    f"Rang {rank.get('name_de')} · {float(r.get('cpu_seconds') or 0):.0f} CPU-Sek. · "
                    f"{int(r.get('tasks_ok') or 0)} Jobs"
                ),
            }
        )
    under_served = sorted(rows, key=lambda x: float(x.get("cpu_seconds") or 0))[:3]
    doc = {
        "schema_version": 1,
        "ok": True,
        "enabled": bool(pol.get("enabled", True)),
        "policy_de": pol.get("policy_de") or pol.get("entlohnung_summary_de"),
        "legionnaires": len(rows),
        "workers": rows,
        "under_served_de": [w.get("entlohnung_de") for w in under_served if w.get("hostname")],
        "headline_de": (
            f"Entlohnung aktiv — {len(rows)} Worker · Legion-Rang + CPU-Sekunden (kein Echtgeld)"
            if rows
            else "Entlohnung bereit — wartet auf Worker"
        ),
        "legion": legion,
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def entlohnung_for_worker(root: Path, worker_id: str) -> str:
    from analytics.federation_legion import legion_welcome_for_worker

    welcome = legion_welcome_for_worker(root, worker_id)
    rank = (welcome.get("rank") or {}).get("name_de") or "Tiro"
    cpu_s = float(welcome.get("cpu_seconds") or 0)
    next_rank = (welcome.get("rank") or {}).get("next_rank_de")
    base = f"Entlohnung: Rang {rank} · {cpu_s:.0f} CPU-Sekunden gutgeschrieben"
    if next_rank:
        need = (welcome.get("rank") or {}).get("next_rank_at_cpu_seconds")
        if need is not None:
            base += f" · Nächster Rang {next_rank} ab {float(need):.0f}s"
    return base
