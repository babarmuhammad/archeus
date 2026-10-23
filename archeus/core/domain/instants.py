"""Provider resets and breaker times, read once where they are read (T-106).

The router is import-free (router.py, boundary B1): the snapshot builder parses
a provider's free-text reset with `ahead` and hands the router two strings for
it: `at`, the instant as written (the text a decision carries, offset kept), and
`key`, the same instant in UTC (ms, Z). The router sorts and compares by `key`
only, so readings in different zones order by instant. P11 parses a stored limit
with `instant`. Naive values are UTC, never local time (T-106 r4), and nothing goes
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


def _ms(at):
    """*at* with its microseconds cut to milliseconds: the instant as written (T-106 r5)."""
    return at.replace(microsecond=at.microsecond // 1000 * 1000)


def _written(at):
    """{'at', 'key'} for an aware instant in milliseconds, or None when its UTC form is
    outside the platform's range (a provider's value at year 9999 with an offset)."""
    try:
        key = at.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    except (OverflowError, ValueError):
        return None
    return {'at': at.isoformat(timespec='milliseconds').replace('+00:00', 'Z'), 'key': key}


def written(iso):
    """The written instant of a readable reset, past or not (`ahead` adds the check),
    else None."""
    at = instant(iso)
    return None if at is None else _written(_ms(at))


def ahead(iso, now):
    """The written instant of a readable reset after *now* (an aware datetime), else
    None. The check and the written text use the same instant (T-106 r5)."""
    at = instant(iso)
    if at is None:
        return None
    at = _ms(at)
    return None if at <= now else _written(at)
