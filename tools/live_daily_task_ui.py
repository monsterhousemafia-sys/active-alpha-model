"""User-facing console formatting for live daily automation."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _icon(ok: bool) -> str:
    return "[OK]" if ok else "[--]"


def format_preflight_report(report: Mapping[str, Any], *, width: int = 60) -> str:
    """Plain-text report for CMD / Task Scheduler logs."""
    lines: List[str] = []
    bar = "=" * width
    lines.append(bar)
    lines.append("  Active Alpha - Automatisierung - Systemcheck")
    lines.append(bar)
    lines.append("")

    ok = bool(report.get("ok"))
    status = "BEREIT" if ok else "BLOCKIERT"
    lines.append(f"  Ergebnis:  {status}")
    lines.append(f"  {report.get('message_de', '')}")
    lines.append("")

    required = [i for i in (report.get("items") or []) if i.get("required")]
    optional = [i for i in (report.get("items") or []) if not i.get("required")]
    req_ok = sum(1 for i in required if i.get("ok"))
    lines.append(f"  Pflichtpunkte: {req_ok}/{len(required)}")
    lines.append("  " + "-" * (width - 2))
    for item in required:
        mark = _icon(bool(item.get("ok")))
        label = str(item.get("label") or item.get("id") or "")
        lines.append(f"  {mark} {label}")
        if not item.get("ok"):
            detail = str(item.get("detail_de") or "")[:width]
            lines.append(f"       -> {detail}")

    if optional:
        lines.append("")
        lines.append("  Optional:")
        lines.append("  " + "-" * (width - 2))
        for item in optional:
            mark = _icon(bool(item.get("ok")))
            label = str(item.get("label") or item.get("id") or "")
            lines.append(f"  {mark} {label}")

    blockers = report.get("blockers") or []
    if blockers:
        lines.append("")
        lines.append("  Was zu tun ist:")
        lines.append("  " + "-" * (width - 2))
        for b in blockers[:6]:
            lines.append(f"  * {str(b)[:width - 4]}")

    lines.append("")
    lines.append(bar)
    return "\n".join(lines)


def format_setup_banner() -> str:
    bar = "=" * 60
    return "\n".join(
        [
            bar,
            "  Active Alpha - Automatisierung einrichten",
            bar,
            "",
            "  Was passiert automatisch?",
            "  * Mo-Fr 15:25  Konto sync, Mark zaehlen, Orders vormerken",
            "  * Kein blindes Senden an Trading 212",
            "  * Ausfuehrung erst bei US-Eroeffnung (Dashboard) oder manuell",
            "",
        ]
    )


def format_task_registered(task_name: str, schedule: str, next_hint: str) -> str:
    bar = "-" * 60
    return "\n".join(
        [
            "",
            bar,
            "  Aufgabe registriert",
            bar,
            f"  Name:     {task_name}",
            f"  Plan:     {schedule}",
            f"  Nächster: {next_hint}",
            "",
            "  Status prüfen:  check_live_daily_setup.bat",
            "  Testlauf:       run_live_daily_mark_scheduled.bat",
            bar,
            "",
        ]
    )
