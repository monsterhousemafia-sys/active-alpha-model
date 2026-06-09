"""Federation Legion — Ränge, Rangliste, Join-Willkommen für Volunteer-Compute."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/FEDERATION_LEGION.json")
_STATS_REL = Path("evidence/federation_legion_stats.json")

_DEFAULT_RANKS: List[Dict[str, Any]] = [
    {"id": "evocatus", "name_de": "Evocatus", "min_cpu_seconds": 180000},
    {"id": "centurio", "name_de": "Centurio", "min_cpu_seconds": 36000},
    {"id": "optio", "name_de": "Optio", "min_cpu_seconds": 7200},
    {"id": "legionarius", "name_de": "Legionär", "min_cpu_seconds": 1800},
    {"id": "miles", "name_de": "Miles", "min_cpu_seconds": 300},
    {"id": "auxilia", "name_de": "Auxilia", "min_cpu_seconds": 60},
    {"id": "tiro", "name_de": "Tiro", "min_cpu_seconds": 0},
]


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


def load_legion_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = _load_json(root / _CONFIG_REL)
    if not cfg:
        cfg = {"schema_version": 1, "enabled": True, "ranks": _DEFAULT_RANKS}
    cfg.setdefault("enabled", True)
    cfg.setdefault("ranks", _DEFAULT_RANKS)
    cfg.setdefault("campaign_goal_cpu_hours", 10000)
    return cfg


def load_legion_stats(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _STATS_REL)
    if not doc:
        doc = {"schema_version": 1, "workers": {}, "updated_at_utc": _utc_now()}
    doc.setdefault("workers", {})
    return doc


def save_legion_stats(root: Path, doc: Dict[str, Any]) -> Path:
    root = Path(root)
    path = root / _STATS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = dict(doc)
    doc["schema_version"] = 1
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(path, doc)
    return path


def rank_for_cpu_seconds(root: Path, cpu_seconds: float) -> Dict[str, Any]:
    cfg = load_legion_config(root)
    ranks = sorted(cfg.get("ranks") or _DEFAULT_RANKS, key=lambda r: -int(r.get("min_cpu_seconds") or 0))
    cpu_seconds = max(0.0, float(cpu_seconds))
    for rank in ranks:
        if cpu_seconds >= float(rank.get("min_cpu_seconds") or 0):
            nxt = None
            for r in reversed(ranks):
                if int(r.get("min_cpu_seconds") or 0) > int(rank.get("min_cpu_seconds") or 0):
                    nxt = r
                    break
            next_at = float(nxt["min_cpu_seconds"]) if nxt else None
            return {
                "id": str(rank.get("id") or "tiro"),
                "name_de": str(rank.get("name_de") or "Tiro"),
                "cpu_seconds": round(cpu_seconds, 2),
                "next_rank_de": str(nxt.get("name_de") or "") if nxt else None,
                "next_rank_at_cpu_seconds": next_at,
            }
    return {"id": "tiro", "name_de": "Tiro", "cpu_seconds": round(cpu_seconds, 2)}


def record_legion_contribution(
    root: Path,
    *,
    worker_id: str,
    ok: bool,
    kind: str,
    cpu_seconds: float = 0.0,
) -> Dict[str, Any]:
    root = Path(root)
    wid = str(worker_id or "").strip()
    if not wid:
        return {}
    doc = load_legion_stats(root)
    workers: Dict[str, Any] = dict(doc.get("workers") or {})
    prior = dict(workers.get(wid) or {})
    cpu_seconds = max(0.0, float(cpu_seconds))
    entry = {
        **prior,
        "worker_id": wid,
        "cpu_seconds": round(float(prior.get("cpu_seconds") or 0) + cpu_seconds, 2),
        "tasks_ok": int(prior.get("tasks_ok") or 0) + (1 if ok else 0),
        "tasks_failed": int(prior.get("tasks_failed") or 0) + (0 if ok else 1),
        "last_job_kind": kind,
        "last_job_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
    }
    workers[wid] = entry
    doc["workers"] = workers
    save_legion_stats(root, doc)
    return entry


def _compute_workers(root: Path) -> List[Dict[str, Any]]:
    from analytics.preview_federation import load_federation_state, prune_stale_workers

    try:
        prune_stale_workers(root)
    except Exception:
        pass
    state = load_federation_state(root)
    workers = [
        dict(w)
        for w in (state.get("workers") or {}).values()
        if str(w.get("role") or "").lower() == "compute"
    ]
    return workers


def _legion_numbers(workers: List[Dict[str, Any]]) -> Dict[str, int]:
    ordered = sorted(
        workers,
        key=lambda w: str(w.get("first_seen_utc") or w.get("updated_at_utc") or w.get("last_seen_utc") or ""),
    )
    return {str(w.get("worker_id") or ""): i + 1 for i, w in enumerate(ordered) if w.get("worker_id")}


def _merge_legionnaire(
    root: Path,
    worker: Dict[str, Any],
    stats: Dict[str, Any],
    legion_no: Optional[int],
) -> Dict[str, Any]:
    wid = str(worker.get("worker_id") or "")
    wstats = dict(stats.get(wid) or {})
    cpu_s = float(wstats.get("cpu_seconds") or 0)
    rank = rank_for_cpu_seconds(root, cpu_s)
    hostname = str(worker.get("hostname") or wid[:24])
    bundle = str(worker.get("bundle_kind") or "lite")
    return {
        "worker_id": wid,
        "legion_number": legion_no,
        "hostname": hostname,
        "cpus": int(worker.get("cpus") or 0),
        "bundle_kind": bundle,
        "rank": rank,
        "cpu_seconds": cpu_s,
        "tasks_ok": int(wstats.get("tasks_ok") or 0),
        "tasks_failed": int(wstats.get("tasks_failed") or 0),
        "last_job_kind": wstats.get("last_job_kind"),
        "last_seen_utc": worker.get("last_seen_utc"),
        "headline_de": format_legionnaire_headline(root, legion_no, rank, int(worker.get("cpus") or 0)),
    }


def format_legionnaire_headline(
    root: Path,
    legion_no: Optional[int],
    rank: Dict[str, Any],
    cpus: int,
) -> str:
    no = f"#{legion_no}" if legion_no else "—"
    return f"Legion {no} · Rang {rank.get('name_de')} · {cpus} Kerne"


def legion_welcome_for_worker(root: Path, worker_id: str) -> Dict[str, Any]:
    root = Path(root)
    workers = _compute_workers(root)
    numbers = _legion_numbers(workers)
    stats_doc = load_legion_stats(root)
    worker = next((w for w in workers if str(w.get("worker_id")) == worker_id), None)
    if not worker:
        return {"welcome_de": "Willkommen in der Legion — Rechenleistung wird gemessen."}
    legion_no = numbers.get(worker_id)
    entry = _merge_legionnaire(root, worker, stats_doc.get("workers") or {}, legion_no)
    no_txt = f"#{legion_no}" if legion_no else "—"
    cfg = load_legion_config(root)
    goal_h = float(cfg.get("campaign_goal_cpu_hours") or 10000)
    total_cpu_s = sum(
        float((stats_doc.get("workers") or {}).get(wid, {}).get("cpu_seconds") or 0)
        for wid in (stats_doc.get("workers") or {})
    )
    campaign_pct = min(100, int(100 * (total_cpu_s / 3600.0) / max(1.0, goal_h)))
    entlohnung_de = (
        f"Entlohnung: Rang {entry['rank']['name_de']} · "
        f"{entry['cpu_seconds']:.0f} CPU-Sekunden · {entry['tasks_ok']} Jobs"
    )
    return {
        **entry,
        "entlohnung_de": entlohnung_de,
        "welcome_de": (
            f"Du bist Legionär {no_txt} — Rang {entry['rank']['name_de']} · "
            f"{entry['cpus']} Kerne bereit. Deine CPU-Sekunden zählen."
        ),
        "campaign_goal_cpu_hours": goal_h,
        "campaign_cpu_hours": round(total_cpu_s / 3600.0, 2),
        "campaign_pct": campaign_pct,
    }


def build_legion_leaderboard(root: Path, *, limit: int = 50) -> List[Dict[str, Any]]:
    root = Path(root)
    workers = _compute_workers(root)
    numbers = _legion_numbers(workers)
    stats = load_legion_stats(root).get("workers") or {}
    rows = [_merge_legionnaire(root, w, stats, numbers.get(str(w.get("worker_id") or ""))) for w in workers]
    rows.sort(key=lambda r: (-float(r.get("cpu_seconds") or 0), int(r.get("legion_number") or 9999)))
    return rows[: max(1, int(limit))]


def build_legion_summary(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_legion_config(root)
    if not bool(cfg.get("enabled")):
        return {"enabled": False, "headline_de": "Legion deaktiviert"}

    from analytics.federation_compute import build_utilization_summary

    util = build_utilization_summary(root)
    stats_doc = load_legion_stats(root)
    workers_stats = stats_doc.get("workers") or {}
    leaderboard = build_legion_leaderboard(root)
    total_cpu_s = sum(float(v.get("cpu_seconds") or 0) for v in workers_stats.values())
    total_tasks = sum(int(v.get("tasks_ok") or 0) for v in workers_stats.values())
    goal_h = float(cfg.get("campaign_goal_cpu_hours") or 10000)
    campaign_h = total_cpu_s / 3600.0
    legionnaires = len(leaderboard)

    return {
        "schema_version": 1,
        "enabled": True,
        "updated_at_utc": _utc_now(),
        "legionnaires": legionnaires,
        "total_cpu_seconds": round(total_cpu_s, 2),
        "total_cpu_hours": round(campaign_h, 2),
        "total_tasks_ok": total_tasks,
        "campaign_goal_cpu_hours": goal_h,
        "campaign_pct": min(100, int(100 * campaign_h / max(1.0, goal_h))),
        "utilization": util,
        "leaderboard": leaderboard,
        "headline_de": (
            f"Legion: {legionnaires} Krieger · {campaign_h:.1f}h CPU geliefert · "
            f"{total_tasks} Jobs · Feldzug {min(100, int(100 * campaign_h / max(1, goal_h)))}%"
            if legionnaires
            else "Legion wartet auf Freiwillige — ZIP teilen und CPUs spenden"
        ),
    }


def render_legion_html(root: Path, *, hub_base: str) -> str:
    summary = build_legion_summary(root)
    rows = summary.get("leaderboard") or []
    goal = float(summary.get("campaign_goal_cpu_hours") or 10000)
    camp_h = float(summary.get("total_cpu_hours") or 0)
    camp_pct = int(summary.get("campaign_pct") or 0)

    def _row_html(r: Dict[str, Any]) -> str:
        rank = r.get("rank") or {}
        return (
            f"<tr><td>{r.get('legion_number') or '—'}</td>"
            f"<td><strong>{rank.get('name_de')}</strong></td>"
            f"<td>{r.get('hostname')}</td>"
            f"<td>{r.get('cpus')}</td>"
            f"<td>{float(r.get('cpu_seconds') or 0):.0f}</td>"
            f"<td>{r.get('tasks_ok') or 0}</td>"
            f"<td>{r.get('last_job_kind') or '—'}</td></tr>"
        )

    table_body = "\n".join(_row_html(r) for r in rows) or (
        "<tr><td colspan='7'>Noch keine Legionäre — <a href='/join'>beitreten</a></td></tr>"
    )

    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>Active Alpha Legion</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#1d1d1f}}
h1{{font-size:28px}} .bar{{background:#e5e5ea;border-radius:8px;height:12px;overflow:hidden;margin:8px 0 20px}}
.fill{{background:linear-gradient(90deg,#8b4513,#d4a574);height:100%;width:{camp_pct}%}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{border:1px solid #e5e5ea;padding:10px;text-align:left}}
th{{background:#f5f5f7}} .meta{{color:#6e6e73;line-height:1.5}}
a.btn{{display:inline-block;margin-top:16px;padding:12px 18px;background:#8b4513;color:#fff;text-decoration:none;border-radius:12px;font-weight:600}}
</style></head><body>
<h1>⚔️ Legion — Volunteer Compute</h1>
<p class="meta">{summary.get('headline_de')}</p>
<p class="meta">Feldzug-Ziel: <strong>{goal:.0f} CPU-Stunden</strong> für Preview &amp; Validierung (H1 läuft auf König).</p>
<div class="bar"><div class="fill"></div></div>
<p class="meta">{camp_h:.1f}h von {goal:.0f}h ({camp_pct}%)</p>
<table>
<tr><th>#</th><th>Rang</th><th>Host</th><th>CPUs</th><th>CPU-Sek.</th><th>Jobs</th><th>Letzter Job</th></tr>
{table_body}
</table>
<p class="meta"><strong>Entlohnung:</strong> Jeder Job bringt CPU-Sekunden + Legion-Rang (sichtbar hier). Kein Echtgeld — faire Gutschrift nach Leistung. Neubeitritt: Willkommens-Stipendium.</p>
<p class="meta">Ränge: Tiro → Auxilia → Miles → Legionär → Optio → Centurio → Evocatus</p>
<a class="btn" href="/join">Der Legion beitreten</a>
<a class="btn" href="/" style="background:#0071e3;margin-left:8px">Command Center</a>
</body></html>"""
