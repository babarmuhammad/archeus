"""The automation worker (P14, p14-design-gate §5, §11, §16): an outbox
consumer (`consumers.deliver`, at-least-once, in seq order) that runs ONE
writer command — `automations.react` — per event an automation cares about.

An event nothing matches costs one read and no write. A matching event's
runs, missions and suspensions commit together, so a re-delivery (a crash
before the effect row, a second worker, a replay) finds its runs and writes
nothing.

A reaction that RAISES is a fault, not an outcome (every expected outcome —
stale, escalated, rate-limited, denied — is a recorded run). The event is held
(`consumers.Hold`: the cursor stays, nothing after it overtakes it) and retried
after RETRY_S, doubling; after MAX_ATTEMPTS it is quarantined: its effect row
says `quarantined: <error>`, the cursor moves on, and `GET /v1/automations`
lists it. Attempts are counted per process (D11): a failed attempt committed
nothing, so a restart's fresh budget can repeat nothing.
"""

import logging
import time

from ...infra.db.writer import WriterClosed
from ...infra.eventlog import consumers, outbox
from ..application import automations as A

log = logging.getLogger('archeus.core')

CONSUMER = 'automation'
MAX_ATTEMPTS = 3
RETRY_S = 1.0


class Automations:
    def __init__(self, db, *, actor, clock=time.monotonic, retry_s=RETRY_S):
        self.db, self.actor, self.clock, self.retry_s = db, actor, clock, retry_s
        self.on_wake = None
        self.stopping = lambda: False
        #: event seq -> (attempts, not before): what is held, and until when
        self.retrying = {}

    def pending(self):
        with self.db.read() as conn:
            n = outbox.head(conn) - consumers.cursor(conn, CONSUMER)
        if n and self.on_wake is not None:
            self.on_wake()
        return n

    def detail(self):
        """What the thread's status adds (§16): held events and quarantines."""
        with self.db.read() as conn:
            q = len(A.quarantined(conn))
        return {'retrying': {s: a for s, (a, _) in self.retrying.items()}, 'quarantined': q}

    def sweep(self):
        return []

    def pass_once(self):
        return {'changed': consumers.deliver(self.db, CONSUMER, self._handle) > 0}

    def _relevant(self, e):
        if A.settles(e):
            return True
        with self.db.read() as conn:
            if not A.enabled(conn):
                return False
            return bool(A.candidates(conn, e))

    def _handle(self, e):
        held = self.retrying.get(e.seq)
        if held and self.clock() < held[1]:
            raise consumers.Hold
        try:
            if not self._relevant(e):
                return ''
            out = self.db.writer.execute(A.react, {'actor': self.actor, 'seq': e.seq})
        except WriterClosed:
            raise                           # Core is stopping: not this event's fault
        except Exception as x:
            attempts = (held[0] if held else 0) + 1
            if attempts >= MAX_ATTEMPTS:
                self.retrying.pop(e.seq, None)
                log.exception('automation: event %d quarantined after %d attempts', e.seq,
                              attempts)
                return 'quarantined: %s: %s' % (type(x).__name__, x)
            self.retrying[e.seq] = (attempts, self.clock() + self.retry_s * 2 ** (attempts - 1))
            log.warning('automation: event %d failed (attempt %d), held: %s', e.seq, attempts, x)
            raise consumers.Hold
        self.retrying.pop(e.seq, None)
        return ' '.join(out['runs'] + ([out['settled']] if out['settled'] else []))
