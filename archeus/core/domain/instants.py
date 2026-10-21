"""Provider resets and breaker times, read once where they are read (T-106).

The router is import-free (router.py, boundary B1): the snapshot builder parses
a provider's free-text reset with `ahead` and hands the router the written
instant, which the router only compares. P11 parses a stored limit with
`instant`. Naive values are UTC, never local time (T-106 r4), and nothing goes
through timestamp() (OSError on Windows outside 1970-2038, T-106 r2).
"""

from datetime import datetime, timezone


def instant(iso):
    """The aware instant of a reset or breaker time, or None when it is not a time."""
    try:
        at = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except (AttributeError, TypeError, ValueError):
        return None
    return at if at.tzinfo is not None else at.replace(tzinfo=timezone.utc)


def ahead(iso, now):
    """The written instant of a readable reset after *now* (an aware datetime), else
    None. Milliseconds and Z, the form the router compares as text; the check and
    the text use the same instant (T-106 r5)."""
    at = instant(iso)
    if at is None:
        return None
    at = at.replace(microsecond=at.microsecond // 1000 * 1000)
    return None if at <= now else at.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
