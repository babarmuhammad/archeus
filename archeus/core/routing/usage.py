"""Usage feeds (resource-router §4; p10-design-gate §7): what the provider says
an account's windows are at, read without blocking.

A feed's `read(account)` returns `{windows: {5h: pct, ...}, resets_at: {...},
observed_at: epoch seconds, source}` or None when nothing is known — never a
0% it did not observe (the reason `quota.worst_window` is not used). A read
is an in-memory lookup: the router runs inside the writer's transaction, so a
feed never waits on the network there. The legacy poller refreshes its cache
on its own thread; the scripted feed is set by a test.
"""

import os
import time

#: the legacy poller's labels -> V1 windows (account-wide windows only;
#: per-model weekly limits are not an account's ceiling)
LEGACY_WINDOWS = {'session': '5h', 'weekly': '7d'}


class FakeUsageFeed:
    """Scripted usage (testing-strategy §1.1 FakeUsageFeed): every account
    reads `default_pct` on its 5-hour window, observed now, until `set` says
    otherwise. A fake provider's window starts empty — which is a reading,
    not an unknown."""
    source = 'scripted'

    def __init__(self, default_pct=0.0, clock=time.time):
        self.default_pct, self.clock = default_pct, clock
        self._set = {}

    def set(self, account_id, window, pct, resets_at=None):
        self._set.setdefault(account_id, {})[window] = (float(pct), resets_at, self.clock())

    def read(self, account):
        got = self._set.get(account['id'])
        if got is None:
            if self.default_pct is None:
                return None
            got = {'5h': (float(self.default_pct), None, self.clock())}
        return {'windows': {w: v[0] for w, v in got.items()},
                'resets_at': {w: v[1] for w, v in got.items() if v[1]},
                'observed_at': max(v[2] for v in got.values()), 'source': self.source}


class NoUsageFeed:
    """Nothing is known about any account."""
    source = 'usage_api'

    def read(self, account):
        return None


class LegacyUsageFeed:
    """Claude Code accounts through the current product's usage poller (the P10
    preparation seam `usage.windows_snapshot`); every other harness reports no
    window here, so its accounts are governed by budgets (§4)."""
    source = 'usage_api'

    def read(self, account):
        if account['harness_id'] != 'claude_code' or not account.get('home_ref'):
            return None
        from claude_sessions import usage
        windows, observed_at, status = usage.windows_snapshot(
            os.path.expanduser(account['home_ref']), poll=True)
        got = {LEGACY_WINDOWS[label]: (pct, reset) for label, pct, reset in windows
               if label in LEGACY_WINDOWS}
        if status != 'ok' or not got or observed_at is None:
            return None
        return {'windows': {w: v[0] for w, v in got.items()},
                'resets_at': {w: v[1] for w, v in got.items() if v[1]},
                'observed_at': observed_at, 'source': self.source}
