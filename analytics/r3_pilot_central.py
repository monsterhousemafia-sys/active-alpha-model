"""Pilot-Zentrale — Chat, Bau-Anzeige, Umsetzung+Test, König-Freigabe."""
from __future__ import annotations

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_pilot_central.json")
_EVIDENCE_REL = Path("evidence/r3_pilot_central_latest.json")


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


def load_pilot_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {"title_de": "Pilot-Zentrale"}


def pilot_share_dir() -> Path:
    return Path.home() / ".local/share/r3-os/pilot"


def _board_path(cfg: Dict[str, Any]) -> Path:
    name = str(cfg.get("board_file") or "central_board.json")
    return pilot_share_dir() / name


def load_board(root: Path) -> Dict[str, Any]:
    cfg = load_pilot_config(root)
    doc = _load_json(_board_path(cfg))
    if not doc:
        doc = {"schema_version": 1, "items": [], "current_id": None}
    doc.setdefault("items", [])
    return doc


def save_board(root: Path, doc: Dict[str, Any]) -> None:
    cfg = load_pilot_config(root)
    dest = pilot_share_dir()
    dest.mkdir(parents=True, exist_ok=True)
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(_board_path(cfg), doc)
    atomic_write_json(Path(root) / _EVIDENCE_REL, build_pilot_board(root))


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def is_king(root: Path) -> bool:
    try:
        from analytics.r3_local_surface import is_king_cockpit_local

        return is_king_cockpit_local(root)
    except Exception:
        return True


def submit_contribution(
    root: Path,
    mandate_de: str,
    *,
    author_de: str = "du",
    author_id: str = "local",
    branch: Optional[str] = None,
) -> Dict[str, Any]:
    root = Path(root)
    mandate = str(mandate_de or "").strip()
    if not mandate:
        return {"ok": False, "reply_de": "Beitrag leer — z.B. /beitrag Tile für Handel heute"}

    from analytics.r3_forschungszweig import (
        classify_mandate_branch,
        load_forschungszweig_config,
        strip_branch_prefix,
    )

    cfg = load_forschungszweig_config(root)
    branch_id = branch or classify_mandate_branch(mandate, cfg)
    mandate = strip_branch_prefix(mandate)

    board = load_board(root)
    item = {
        "id": _new_id(),
        "branch": branch_id,
        "branch_label_de": (
            cfg.get("title_de") if branch_id == cfg.get("branch_id") else "R3-OS Pilot"
        ),
        "mandate_de": mandate[:600],
        "author_de": author_de[:80],
        "author_id": author_id[:40],
        "status": "eingereicht",
        "submitted_at_utc": _utc_now(),
        "preview_de": mandate[:220],
        "test_de": None,
        "implement_de": None,
    }
    items: List[Dict[str, Any]] = list(board.get("items") or [])
    items.insert(0, item)
    board["items"] = items[:40]
    board["current_id"] = item["id"]
    save_board(root, board)
    branch_note = (
        "Forschungszweig (Finanzierung)"
        if branch_id == cfg.get("branch_id")
        else "R3-OS"
    )
    return {
        "ok": True,
        "item": item,
        "reply_de": f"Beitrag #{item['id']} · {branch_note} — wird umgesetzt …",
    }


def _run_default_test(root: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    cmd = str(cfg.get("default_test_cmd") or "python3 -m pytest tests/ -q --tb=no")
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output_de": out.strip()[:3000],
        "cmd": cmd,
    }


def implement_and_test_contribution(root: Path, item_id: Optional[str] = None) -> Dict[str, Any]:
    """Umsetzen (Bau-Kernel) + Test — dann wartet_freigabe."""
    root = Path(root)
    cfg = load_pilot_config(root)
    board = load_board(root)
    iid = item_id or board.get("current_id")
    items = list(board.get("items") or [])
    item = next((x for x in items if x.get("id") == iid), None)
    if not item:
        return {"ok": False, "reply_de": "Kein Beitrag auf dem Board."}

    item["status"] = "wird_umgesetzt"
    item["implement_started_utc"] = _utc_now()
    save_board(root, board)

    mandate = str(item.get("mandate_de") or "")
    branch = str(item.get("branch") or "r3_os")
    if branch == "forschungszweig_finanzierung":
        impl_prompt = (
            f"Forschungszweig Finanzierung — tägliche Aktienprognose / Marktanalyse:\n{mandate}\n"
            "Nur Module: prediction, trading_day, pilot_day_trading, live_trading_dashboard, "
            "aa_live_daily_sync, run_tomorrow_prediction. "
            "Kein R3-OS-Cockpit-Layout. Am Ende finish mit summary_de."
        )
    else:
        impl_prompt = (
            f"Pilot-Zentrale R3-OS — grafisch/UI im Cockpit umsetzen:\n{mandate}\n"
            "Schreibe nur nötige Dateien unter analytics/, tools/, control/, tests/. "
            "Keine Trading-Prognose-Logik. Am Ende finish mit summary_de."
        )
    from analytics.r3_build_kernel import run_build_kernel

    kernel_doc = run_build_kernel(root, impl_prompt)
    item["implement_de"] = str(kernel_doc.get("summary_de") or kernel_doc.get("headline_de") or "")[:400]
    item["implement_trace_steps"] = kernel_doc.get("steps")
    item["kernel_ok"] = bool(kernel_doc.get("ok"))

    item["status"] = "getestet"
    test = _run_default_test(root, cfg)
    item["test_de"] = test.get("output_de", "")[:500]
    item["test_ok"] = bool(test.get("ok"))
    item["tested_at_utc"] = _utc_now()

    if item.get("kernel_ok") and item.get("test_ok"):
        item["status"] = "wartet_freigabe"
        item["preview_de"] = (
            f"{item.get('implement_de') or mandate}\n[Test OK]"
        )[:400]
        reply = (
            f"Beitrag #{item['id']} umgesetzt und getestet.\n"
            f"König: /freigeben zum Live-Schalten.\n{item.get('preview_de', '')[:800]}"
        )
        ok = True
    else:
        item["status"] = "fehler"
        reply = (
            f"Beitrag #{item['id']} — Fehler bei Umsetzung oder Test.\n"
            f"Kernel: {item.get('kernel_ok')} · Test: {item.get('test_ok')}\n"
            f"{(item.get('test_de') or '')[:600]}"
        )
        ok = False

    for i, x in enumerate(items):
        if x.get("id") == item["id"]:
            items[i] = item
            break
    board["items"] = items
    board["current_id"] = item["id"]
    save_board(root, board)
    return {"ok": ok, "item": item, "reply_de": reply, "kernel": kernel_doc, "test": test}


def king_approve(root: Path, item_id: Optional[str] = None) -> Dict[str, Any]:
    root = Path(root)
    if not is_king(root):
        return {"ok": False, "reply_de": "Nur der König kann freigeben."}

    board = load_board(root)
    iid = item_id or board.get("current_id")
    items = list(board.get("items") or [])
    item = next((x for x in items if x.get("id") == iid), None)
    if not item:
        return {"ok": False, "reply_de": "Nichts zum Freigeben."}
    if item.get("status") not in ("wartet_freigabe", "getestet"):
        return {
            "ok": False,
            "reply_de": f"Status {item.get('status')} — nicht freigabefähig.",
        }

    item["status"] = "live"
    item["approved_at_utc"] = _utc_now()
    item["approved_by_de"] = "König"

    for i, x in enumerate(items):
        if x.get("id") == item["id"]:
            items[i] = item
            break
    board["items"] = items
    board["current_id"] = None
    save_board(root, board)

    try:
        from analytics.r3_dev_trail import record_dev_change, set_next_changes

        record_dev_change(
            root,
            title_de=f"Live: {item.get('mandate_de', '')[:80]}",
            detail_de=str(item.get("implement_de") or item.get("preview_de") or "")[:300],
            status="done",
        )
        set_next_changes(root, [f"Nächster Beitrag über /beitrag — {item.get('author_de', 'Mitwirkende')}"])
    except Exception:
        pass

    return {
        "ok": True,
        "item": item,
        "reply_de": f"Freigegeben · #{item['id']} ist jetzt live im R3.\n{item.get('mandate_de', '')[:200]}",
    }


def king_reject(root: Path, item_id: Optional[str] = None) -> Dict[str, Any]:
    root = Path(root)
    if not is_king(root):
        return {"ok": False, "reply_de": "Nur der König kann ablehnen."}

    board = load_board(root)
    iid = item_id or board.get("current_id")
    items = list(board.get("items") or [])
    item = next((x for x in items if x.get("id") == iid), None)
    if not item:
        return {"ok": False, "reply_de": "Kein Beitrag zum Ablehnen."}

    item["status"] = "abgelehnt"
    item["rejected_at_utc"] = _utc_now()
    for i, x in enumerate(items):
        if x.get("id") == item["id"]:
            items[i] = item
            break
    board["items"] = items
    if board.get("current_id") == item["id"]:
        board["current_id"] = None
    save_board(root, board)
    return {"ok": True, "reply_de": f"Beitrag #{item['id']} abgelehnt."}


def build_pilot_board(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_pilot_config(root)
    board = load_board(root)
    items = list(board.get("items") or [])
    os_items = [x for x in items if x.get("branch", "r3_os") != "forschungszweig_finanzierung"]
    current_id = board.get("current_id")
    current = next((x for x in os_items if x.get("id") == current_id), None)
    if not current:
        current = next((x for x in os_items if x.get("status") not in ("live", "abgelehnt")), None)
    awaiting = [x for x in os_items if x.get("status") == "wartet_freigabe"]
    queue = [x for x in os_items if x.get("status") not in ("live", "abgelehnt")][:8]
    live_recent = [x for x in items if x.get("status") == "live"][:5]

    return {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "title_de": cfg.get("title_de"),
        "tagline_de": cfg.get("tagline_de"),
        "is_king": is_king(root),
        "current": current,
        "current_id": current_id,
        "awaiting_king": awaiting,
        "queue": queue,
        "live_recent": live_recent,
        "counts": {
            "total": len(items),
            "wartet_freigabe": len(awaiting),
            "live": len([x for x in items if x.get("status") == "live"]),
        },
        "chat_commands_de": cfg.get("chat_commands_de"),
        "headline_de": (
            f"Du baust: {current.get('mandate_de', '')[:80]}"
            if current
            else "Pilot-Zentrale — /beitrag <was du bauen willst>"
        ),
    }


def pilot_help_de() -> str:
    return (
        "Pilot-Zentrale — ein Chat für alles.\n"
        "/beitrag <was> — R3-OS einreichen\n"
        "/beitrag forschung <was> — Forschungszweig (Prognose/Finanzierung)\n"
        "/prognose <was> — Kurzform Forschungszweig\n"
        "/freigeben — König: live schalten\n"
        "/ablehnen — König: verwerfen\n"
        "/board — Anzeige\n"
        "Mitwirkende nutzen dieselbe Schnittstelle (/join · Hub)."
    )


def handle_pilot_command(root: Path, text: str, *, author_de: str = "du") -> Dict[str, Any]:
    root = Path(root)
    raw = str(text or "").strip()
    low = raw.lower()

    if low in ("/pilot", "/zentrale", "/board"):
        doc = build_pilot_board(root)
        cur = doc.get("current") or {}
        lines = [doc.get("headline_de") or "—"]
        if cur:
            lines.append(f"Status: {cur.get('status')} · #{cur.get('id')}")
            if cur.get("preview_de"):
                lines.append(str(cur["preview_de"])[:400])
        if doc.get("awaiting_king"):
            lines.append(f"Wartet Freigabe: {len(doc['awaiting_king'])}")
        return {"ok": True, "reply_de": "\n".join(lines), "board": doc}

    if (
        low.startswith("/beitrag ")
        or low.startswith("/contribute ")
        or low.startswith("/forschung ")
        or low.startswith("/prognose ")
    ):
        task = raw.split(maxsplit=1)[1] if " " in raw else ""
        branch = None
        if low.startswith("/forschung ") or low.startswith("/prognose "):
            branch = "forschungszweig_finanzierung"
            task = f"forschung {task}"
        sub = submit_contribution(root, task, author_de=author_de, branch=branch)
        if not sub.get("ok"):
            return sub
        done = implement_and_test_contribution(root, sub["item"]["id"])
        return {**done, "submitted": True}

    if low.startswith("/freigeben") or low.startswith("/approve"):
        parts = raw.split()
        iid = parts[1] if len(parts) > 1 else None
        return king_approve(root, iid)

    if low.startswith("/ablehnen") or low.startswith("/reject"):
        parts = raw.split()
        iid = parts[1] if len(parts) > 1 else None
        return king_reject(root, iid)

    if low.startswith("/bau ") or low.startswith("/build "):
        task = raw.split(maxsplit=1)[1] if " " in raw else ""
        sub = submit_contribution(root, task, author_de=author_de)
        if not sub.get("ok"):
            return sub
        return implement_and_test_contribution(root, sub["item"]["id"])

    return {"ok": False, "unknown": True}


def render_pilot_central_section(board: Dict[str, Any]) -> str:
    import html

    esc = lambda t: html.escape(str(t or ""), quote=True)
    if not board:
        return ""
    current = board.get("current") or {}
    cur_status = esc(current.get("status") or "—")
    cur_mandate = esc(current.get("mandate_de") or "Noch nichts — /beitrag im Chat")
    cur_author = esc(current.get("author_de") or "")
    cur_id = esc(current.get("id") or "")
    cur_preview = esc(current.get("preview_de") or "")
    test_ok = current.get("test_ok")
    test_badge = "getestet OK" if test_ok else ("Test offen" if current else "")
    king = bool(board.get("is_king"))
    approve_btn = ""
    if king and current.get("status") == "wartet_freigabe":
        approve_btn = f"""
    <div class="pz-king-actions">
      <button type="button" class="pz-approve" data-pilot-action="approve" data-id="{cur_id}">Freigeben</button>
      <button type="button" class="pz-reject" data-pilot-action="reject" data-id="{cur_id}">Ablehnen</button>
    </div>"""

    queue_html = ""
    for item in board.get("queue") or []:
        if item.get("id") == current.get("id"):
            continue
        queue_html += (
            f'<li><span class="pz-q-status">{esc(item.get("status"))}</span> '
            f'<span class="pz-q-author">{esc(item.get("author_de"))}</span> '
            f'{esc((item.get("mandate_de") or "")[:100])}</li>'
        )

    live_html = ""
    for item in board.get("live_recent") or []:
        live_html += f'<li>{esc((item.get("mandate_de") or "")[:90])}</li>'

    return f"""
<section class="pilot-central" id="pilot-central" aria-label="Pilot-Zentrale">
  <div class="pz-head">
    <div class="pz-eyebrow">Pilot · Zentrale Schnittstelle</div>
    <h2 class="pz-title">{esc(board.get('title_de'))}</h2>
    <p class="pz-tagline">{esc(board.get('tagline_de'))}</p>
  </div>
  <div class="pz-current" id="pz-current">
    <div class="pz-current-label">Du baust gerade</div>
    <p class="pz-mandate" id="pz-mandate">{cur_mandate}</p>
    <p class="pz-meta" id="pz-meta">{cur_author} · <span id="pz-status">{cur_status}</span> · {test_badge}</p>
    <p class="pz-preview" id="pz-preview">{cur_preview}</p>
    {approve_btn}
  </div>
  <div class="pz-cols">
    <div class="pz-col">
      <h3>Warteschlange</h3>
      <ul class="pz-queue" id="pz-queue">{queue_html or '<li class="pz-empty">—</li>'}</ul>
    </div>
    <div class="pz-col">
      <h3>Live (freigegeben)</h3>
      <ul class="pz-live" id="pz-live">{live_html or '<li class="pz-empty">—</li>'}</ul>
    </div>
  </div>
  <p class="pz-chat-hint">Chat: <code>/beitrag &lt;was&gt;</code> · König: <code>/freigeben</code></p>
</section>"""
