"""Abhängigkeits-Risiko — zu wenige Menschen/Hosts, ehrlich messen."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/federation_dependency_latest.json")
_STATEMENT_REL = Path("evidence/spread_dependency_statement_de.txt")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def classify_compute_workers(workers: List[Dict[str, Any]]) -> Dict[str, Any]:
    king_hosts = {
        str(w.get("hostname") or "").strip().lower()
        for w in workers
        if str(w.get("role") or "").lower() == "king" and w.get("hostname")
    }
    compute = [w for w in workers if str(w.get("role") or "").lower() == "compute"]
    remote_compute = [
        w
        for w in compute
        if str(w.get("hostname") or "").strip().lower() not in king_hosts
        or bool(w.get("remote_join"))
    ]
    local_only = [w for w in compute if w not in remote_compute]
    unique_hosts = {str(w.get("hostname") or "").strip().lower() for w in compute if w.get("hostname")}
    return {
        "compute_total": len(compute),
        "remote_compute": len(remote_compute),
        "local_only_compute": len(local_only),
        "unique_compute_hosts": len(unique_hosts),
        "remote_compute_workers": remote_compute,
        "local_only_workers": local_only,
    }


def assess_federation_dependency(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.preview_federation import build_federation_summary, prune_stale_workers

    try:
        prune_stale_workers(root)
    except Exception:
        pass
    summary = build_federation_summary(root)
    workers = list(summary.get("workers") or [])
    cls = classify_compute_workers(workers)
    remote_n = int(cls.get("remote_compute") or 0)
    local_n = int(cls.get("local_only_compute") or 0)
    total_n = int(cls.get("compute_total") or 0)

    if remote_n >= 2:
        risk = "low"
        ok = True
        headline = f"Föderation divers — {remote_n} externe Compute-Hosts"
    elif remote_n == 1:
        risk = "medium"
        ok = False
        headline = "Ein externer Worker — noch zu wenig Menschen für echte Unabhängigkeit"
    elif local_n >= 1:
        risk = "high"
        ok = False
        headline = "Nur lokaler Compute — Abhängigkeit von zu wenigen (gleicher PC)"
    else:
        risk = "critical"
        ok = False
        headline = "Kein Compute-Worker — System hängt am König allein"

    adoption_pct = 0
    if remote_n >= 2:
        adoption_pct = 100
    elif remote_n == 1:
        adoption_pct = 60
    elif local_n >= 1:
        adoption_pct = 25
    elif total_n > 0:
        adoption_pct = 15

    doc = {
        "schema_version": 1,
        "ok": ok,
        "risk_level": risk,
        "headline_de": headline,
        "dependency_de": (
            "Freundlich nur Rechenleistung — jeder freiwillige PC-Worker auf eigenem Host "
            "macht das Netz robuster (ehrlich: noch kein externer Host)."
            if remote_n < 1
            else "Freiwillige Compute-Worker auf eigenen PCs — so war es vorgesehen."
        ),
        "compute_total": total_n,
        "remote_compute": remote_n,
        "local_only_compute": local_n,
        "adoption_pct_honest": adoption_pct,
        "adoption_done": remote_n >= 1,
        "next_action_de": (
            "Welt-ZIP + Link an Menschen mit eigenem PC — nicht nur König-Host"
            if remote_n < 1
            else "Weitere Worker gewinnen — Bus-Faktor senken"
        ),
        "updated_at_utc": _utc_now(),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def dependency_statement_de() -> str:
    return """=== Active Alpha — Worker nur Rechenleistung (so vorgesehen) ===

Freundlich und ehrlich: Wir fangen nur freiwillige CPU an — kein Broker, kein Echtgeld,
kein Hintergrund-Install, kein Browser-only-Klick.

Was ein Worker ist:
- ~100 KB ZIP, Python 3, START (Win/Mac/Linux)
- Meldet Kerne/RAM, nimmt Jobs wenn idle
- Jederzeit stoppen (Dienst aus / Ordner löschen)

Was noch fehlt (nicht erzwingbar):
- Externer PC: jemand muss ZIP auf eigenem Rechner starten (Adoption 25%, 0 remote Hosts)
- Stabile URL: Quick-Tunnel bis tunnel-stable setup (Cloudflare-Token)
- Reichweite: Forum/Reddit noch offen (Öffentlich 86%)

Was bewusst nicht eingefangen wird:
- Gefakte Remote-Worker, Echtgeld, beliebige Rollen ohne Bundle

Nächster Schritt: Welt-ZIP + Link an Menschen mit eigenem PC — freundlich fragen, nicht drängen.
"""


def write_dependency_statement(root: Path) -> Path:
    root = Path(root)
    path = root / _STATEMENT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dependency_statement_de(), encoding="utf-8")
    return path
