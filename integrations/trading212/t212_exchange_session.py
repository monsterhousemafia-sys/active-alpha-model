"""US equity session — NASDAQ/NYSE regular hours (America/New_York)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Optional
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
_SESSION_START = time(9, 30)
_SESSION_END = time(16, 0)


def us_equity_regular_session_open_now() -> Dict[str, object]:
    """
    Approximate NASDAQ/NYSE regular session (Mon–Fri 09:30–16:00 America/New_York).
    Extended/overnight not covered — pilot uses regular hours for first live fill.
    """
    now_ny = datetime.now(timezone.utc).astimezone(_NY)
    if now_ny.weekday() >= 5:
        return {
            "open": False,
            "reason_de": "US-Börse am Wochenende geschlossen — Order erst Mo–Fr (US-Regular).",
            "now_ny": now_ny.isoformat(),
            "phase": "CLOSED",
        }
    t = now_ny.time()
    if _SESSION_START <= t < _SESSION_END:
        return {"open": True, "reason_de": "", "now_ny": now_ny.isoformat(), "phase": "OPEN"}
    phase = "PREOPEN" if t < _SESSION_START else "CLOSED"
    return {
        "open": False,
        "reason_de": (
            "US-Regular-Session geschlossen (Mo–Fr 09:30–16:00 New York). "
            "Orders können für die Eröffnung vorgemerkt werden."
        ),
        "now_ny": now_ny.isoformat(),
        "phase": phase,
    }


def _next_business_day(d: date) -> date:
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt


def next_us_regular_session_open_utc(*, now: Optional[datetime] = None) -> datetime:
    """Next Mon–Fri 09:30 America/New_York as UTC-aware datetime."""
    ref = (now or datetime.now(timezone.utc)).astimezone(_NY)
    d = ref.date()
    if ref.weekday() >= 5:
        d = _next_business_day(d)
        open_local = datetime.combine(d, _SESSION_START, tzinfo=_NY)
        return open_local.astimezone(timezone.utc)
    t = ref.time()
    if t < _SESSION_START:
        open_local = datetime.combine(d, _SESSION_START, tzinfo=_NY)
        return open_local.astimezone(timezone.utc)
    if t < _SESSION_END:
        return ref.astimezone(timezone.utc)
    d = _next_business_day(d)
    open_local = datetime.combine(d, _SESSION_START, tzinfo=_NY)
    return open_local.astimezone(timezone.utc)


def current_us_session_end_utc(*, now: Optional[datetime] = None) -> datetime:
    ref = (now or datetime.now(timezone.utc)).astimezone(_NY)
    d = ref.date()
    if ref.weekday() >= 5 or ref.time() >= _SESSION_END:
        open_utc = next_us_regular_session_open_utc(now=ref.astimezone(timezone.utc))
        end_local = open_utc.astimezone(_NY).replace(
            hour=_SESSION_END.hour, minute=_SESSION_END.minute, second=0, microsecond=0
        )
        return end_local.astimezone(timezone.utc)
    end_local = datetime.combine(d, _SESSION_END, tzinfo=_NY)
    return end_local.astimezone(timezone.utc)


def is_within_us_open_execution_window(
    *,
    now: Optional[datetime] = None,
    minutes_after_open: int = 45,
) -> bool:
    """True during regular session and within first N minutes after open (auto-release window)."""
    sess = us_equity_regular_session_open_now() if now is None else _session_at(now)
    if not sess.get("open"):
        return False
    ref = (now or datetime.now(timezone.utc)).astimezone(_NY)
    open_today = datetime.combine(ref.date(), _SESSION_START, tzinfo=_NY).time()
    elapsed = (ref.time().hour * 60 + ref.time().minute) - (open_today.hour * 60 + open_today.minute)
    return 0 <= elapsed <= int(minutes_after_open)


def _session_at(now: datetime) -> Dict[str, object]:
    now_ny = now.astimezone(_NY)
    if now_ny.weekday() >= 5:
        return {"open": False, "phase": "CLOSED", "now_ny": now_ny.isoformat()}
    t = now_ny.time()
    if _SESSION_START <= t < _SESSION_END:
        return {"open": True, "phase": "OPEN", "now_ny": now_ny.isoformat()}
    return {
        "open": False,
        "phase": "PREOPEN" if t < _SESSION_START else "CLOSED",
        "now_ny": now_ny.isoformat(),
    }


def format_next_open_de(*, now: Optional[datetime] = None) -> str:
    open_utc = next_us_regular_session_open_utc(now=now)
    local = open_utc.astimezone(_NY)
    return local.strftime("%a %d.%m.%Y %H:%M") + " New York"
