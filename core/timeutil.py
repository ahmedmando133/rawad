"""
Libya (Africa/Tripoli) time helpers.

Libya uses Eastern European Time (UTC+2) year-round with **no daylight saving**,
so a fixed offset is exact and avoids depending on the IANA tz database (which
is not bundled with Python on Windows).

Used by the Layer-2 zero-token router (to answer "are you open now?") and by the
Layer-3 system prompt (to give the model an accurate sense of "now").
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Fixed UTC+2 (EET) — exact for Libya, which has no DST.
LIBYA_TZ = timezone(timedelta(hours=2), name="EET")

_WEEKDAY_AR = {
    0: "الاثنين",
    1: "الثلاثاء",
    2: "الأربعاء",
    3: "الخميس",
    4: "الجمعة",
    5: "السبت",
    6: "الأحد",
}

# English key used in knowledge/doctor_profile.yaml -> working_hours.<key>
_WEEKDAY_KEY = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


def libya_now() -> datetime:
    """Current time in Tripoli, Libya (UTC+2)."""
    return datetime.now(LIBYA_TZ)


def weekday_ar(dt: datetime) -> str:
    """Arabic name of the day (الأحد، الاثنين، ...) for `dt`."""
    return _WEEKDAY_AR[dt.weekday()]


def weekday_ar_index(index: int) -> str:
    """Arabic day name from a `datetime.weekday()` index (0 = Monday .. 6 = Sunday)."""
    return _WEEKDAY_AR[index]


def weekday_key(dt: datetime) -> str:
    """Profile key of the day (sunday, monday, ...) for `dt`."""
    return _WEEKDAY_KEY[dt.weekday()]


def ordered_weekday_keys() -> list[str]:
    """All weekday keys, Monday-first (index-aligned with `datetime.weekday()`)."""
    return [_WEEKDAY_KEY[i] for i in range(7)]


def is_closed_value(value: str | None) -> bool:
    """True if a working_hours value means the clinic is closed that day."""
    if not value:
        return True
    return ("مغلق" in value) or ("غير متواجد" in value)
