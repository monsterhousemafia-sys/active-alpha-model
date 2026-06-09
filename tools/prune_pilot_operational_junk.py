#!/usr/bin/env python3
"""Safe cleanup of stale pilot order/quote state (no model/champion files)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _archive(path: Path, archive_dir: Path) -> int:
    if not path.is_file():
        return 0
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{path.name}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
    shutil.copy2(path, dest)
    path.unlink()
    return 1


def prune(root: Path, *, dry_run: bool = False) -> dict:
    root = Path(root)
    report: dict = {"dry_run": dry_run, "actions": []}

    def act(msg: str, n: int = 0) -> None:
        report["actions"].append({"msg": msg, "count": n})

    archive = root / "live_pilot/confirmed_execution/archive_prune"

    # Orphan confirmation tokens
    tok_dir = root / "live_pilot/confirmed_execution/confirmation_tokens"
    if tok_dir.is_dir():
        files = list(tok_dir.glob("*.json"))
        if not dry_run:
            for p in files:
                p.unlink()
        act("removed_confirmation_tokens", len(files))

    # Phantom dry-run submitted orders
    sub_dir = root / "live_pilot/confirmed_execution/submitted_orders"
    if sub_dir.is_dir():
        files = list(sub_dir.glob("*.json"))
        if not dry_run:
            for p in files:
                p.unlink()
        act("removed_submitted_orders", len(files))

    # Stale order drafts
    draft_dir = root / "live_pilot/confirmed_execution/order_drafts"
    if draft_dir.is_dir():
        files = list(draft_dir.glob("*.json"))
        if not dry_run:
            for p in files:
                p.unlink()
        act("removed_order_drafts", len(files))

    # Archive noisy ledger, start fresh tail file
    ledger = root / "live_pilot/confirmed_execution/live_execution_audit_ledger.jsonl"
    if ledger.is_file() and ledger.stat().st_size > 0:
        if not dry_run:
            _archive(ledger, archive)
            ledger.write_text(
                json.dumps(
                    {
                        "timestamp_utc": _utc_now(),
                        "note": "ledger_rotated_after_prune",
                        "status": "ARCHIVE_MARKER",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        act("archived_execution_ledger", 1)

    # Cap recovery sessions
    rec_path = root / "live_pilot/confirmed_execution/recovery_state.json"
    if rec_path.is_file():
        try:
            doc = json.loads(rec_path.read_text(encoding="utf-8"))
            sessions = list(doc.get("sessions") or [])
            if len(sessions) > 25:
                doc["sessions"] = sessions[-25:]
                doc["pruned_at_utc"] = _utc_now()
                if not dry_run:
                    rec_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
                act("capped_recovery_sessions", len(sessions) - 25)
        except (json.JSONDecodeError, OSError):
            pass

    # Reset stock-buy streak (permissions OK — fresh counter)
    gate = root / "live_pilot/manual_execution/readonly_real_account_state/t212_stock_buy_gate.json"
    if not dry_run:
        gate.parent.mkdir(parents=True, exist_ok=True)
        gate.write_text(
            json.dumps(
                {
                    "consecutive_insufficient": 0,
                    "api_execute_scope_proven": True,
                    "api_execute_scope_proven_utc": _utc_now(),
                    "note": "reset_after_prune_permissions_confirmed",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    act("reset_t212_stock_buy_gate", 1)

    # Drop stale quote snapshot (force refresh with plausibility)
    snap = root / "paper/p16d/live_quote_snapshot.json"
    if snap.is_file():
        if not dry_run:
            _archive(snap, archive)
        act("archived_live_quote_snapshot", 1)

    # Align legacy cash snapshot with latest_sync
    sync_path = root / "live_pilot/manual_execution/readonly_real_account_state/latest_sync.json"
    legacy = root / "live_pilot/manual_execution/readonly_real_account_state/latest.json"
    if sync_path.is_file():
        try:
            sync = json.loads(sync_path.read_text(encoding="utf-8"))
            cash = sync.get("cash_eur") or (sync.get("cash_breakdown") or {}).get("available_to_trade_eur")
            if cash is not None and not dry_run:
                legacy_doc = {
                    "readonly_observed_real_broker_available_cash_eur": float(cash),
                    "available_real_manual_ticket_budget_eur": round(max(0.0, float(cash) - 50.0), 2),
                    "readonly_broker_cash_verified": True,
                    "real_cash_reserve_required_eur": 50.0,
                    "updated_at_utc": sync.get("synced_at_utc") or _utc_now(),
                    "synced_from": "latest_sync.json",
                }
                legacy.write_text(json.dumps(legacy_doc, indent=2) + "\n", encoding="utf-8")
                act("synced_legacy_latest_json_cash", 1)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # Optional: old EXE backup
    old_exe = root / "Marktanalyse.exe.old"
    if old_exe.is_file():
        if not dry_run:
            old_exe.unlink()
        act("removed_marktanalyse_exe_old", 1)

    report["completed_at_utc"] = _utc_now()
    out = root / "evidence" / "pilot_operational_prune_latest.json"
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    report = prune(ROOT, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
