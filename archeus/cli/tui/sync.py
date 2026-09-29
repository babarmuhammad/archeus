"""The TUI's connection, freshness, commands and invalidation (p17-design-gate
A2, §7, §8): the Python side of the SPA's `data/connection.ts`,
`data/commands.ts` and `data/invalidation.ts`, function for function. Derived
from what the stream and the reads report, never from a guess about Core. The
shared cases in `clients/app/test/fixtures/parity.json` run against both sides.
"""

import re
import uuid

from ._tables import RULES

# ── the connection (one machine) and each view's freshness ──────────────────

_SIGNED_OUT = ('unauthenticated', 'revoked')


def initial(now):
    return {'conn': 'connecting', 'gen': 0, 'since': now}


def next_state(s, sig, now):
    """The next connection state. A signed-out client stays signed out."""
    if s['conn'] in _SIGNED_OUT:
        return s
    cur = s['conn']

    def to(conn, bump=False):
        if conn == cur and not bump:
            return s
        return {'conn': conn, 'gen': s['gen'] + (1 if bump else 0), 'since': now}
    if sig == 'unauthorized':
        return to('unauthenticated')
    if sig == 'self_revoked':
        return to('revoked')
    if sig == 'offline':
        return to('offline')
    if sig == 'online':
        return to('reconnecting') if cur == 'offline' else s
    if sig == 'stream_lost':
        return s if cur == 'offline' else to('reconnecting')
    if sig == 'resync':
        # a resync before anything was shown is only a fresh start
        return to('connecting', True) if cur == 'connecting' else to('resynced', True)
    if sig == 'stream_open':
        # coming back from a drop is a resync: what was read before may be old
        if cur in ('reconnecting', 'offline'):
            return to('resynced', True)
        return to('live') if cur == 'connecting' else s
    if sig == 'frame':
        return to('live') if cur == 'connecting' else s
    if sig == 'settled':
        return to('live') if cur == 'resynced' else s
    raise ValueError('unknown signal %r' % (sig,))


def can_command(conn):
    """Commands are sent only on a live connection."""
    return conn in ('live', 'resynced')


def freshness(c, entry):
    """A view's freshness from the connection and the generation it was read in."""
    has = entry['hasData']
    if entry.get('error') and not has:
        return 'unavailable'
    if c['conn'] in ('reconnecting', 'connecting'):
        return 'reconnecting' if has else 'unavailable'
    if c['conn'] not in ('live', 'resynced'):
        return 'stale' if has else 'unavailable'
    if entry['gen'] < c['gen'] or entry.get('pending') or entry.get('error'):
        return 'stale'
    return 'current'


BANNER = {
    'connecting': 'Connecting…',
    'live': None,
    'reconnecting': 'Reconnecting — what you see may be out of date. Nothing is sent until '
                    'the connection is back.',
    'resynced': 'Back — everything on screen was read again.',
    'offline': 'Offline — nothing you do here is sent. Work on the computer running Archeus '
               'continues.',
    'unauthenticated': 'This client is signed out: its access was revoked or has expired. Open '
                       'Archeus from the computer running it, or pair this client again.',
    'revoked': 'This client’s access was revoked. It cannot act any more; pair it again to '
               'use it.',
}

# ── commands: one key per user action, Core's refusal in words ──────────────


def new_key():
    return str(uuid.uuid4())


def decide_body(a, decision, key, extra=None):
    """An approval decision echoes the action_hash the card displayed (P9 X02)."""
    return dict({'decision': decision, 'action_hash': a['action_hash'],
                 'expected_version': a['version'], 'idempotency_key': key}, **(extra or {}))


def key_after(prev, outcome, fresh=new_key):
    """After a network failure nobody knows whether Core applied the action, so
    trying again reuses the key; after any answer it is new."""
    return prev if outcome == 'network' else fresh()


def retryable(r):
    """Retry once, with the same key, only when Core asked for it."""
    return r['code'] in ('busy', 'core_starting')


def _s(v):
    return '' if v is None else str(v)


def explain(r):
    """Core's refusal in words, from its own code and detail."""
    d = r.get('detail') or {}
    code = r['code']
    if code == 'scope_required':
        return 'This client does not hold the “%s” scope.' % _s(d.get('scope'))
    if code == 'not_permitted':
        return 'Not permitted: %s' % _s(d.get('why'))
    if code == 'version_conflict':
        return 'This changed since you opened it. It has been read again — act on what is there now.'
    if code == 'guard_failed':
        why = next((v for v in (d.get('reason'), d.get('guard')) if v is not None),
                   'a guard refused')
        return 'Refused: %s' % _s(why)
    if code == 'invalid_transition':
        return 'Not possible from %s%s.' % (_s(d.get('from')),
                                            ' (%s)' % d['trigger'] if d.get('trigger') else '')
    if code == 'policy_denied':
        return 'The policy denies it: %s' % _s(d.get('reason'))
    if code == 'approval_not_eligible':
        return 'This approval cannot be decided now: %s' % _s(d.get('why'))
    if code == 'queued_intent_refused':
        return 'Archeus refused a command that was sent late. Nothing was changed.'
    if code == 'host_not_allowed':
        return 'Only from the computer running Archeus.'
    if code == 'core_starting':
        return 'Archeus is starting. Try again in a moment.'
    if code == 'busy':
        return 'Archeus is busy. It will be retried once.'
    if code == 'unauthenticated':
        return 'This client is signed out.'
    if code == 'invalid_request':
        return 'Invalid: %s%s' % ('%s ' % d['field'] if d.get('field') else '', _s(d.get('why')))
    if code == 'not_found':
        return 'It no longer exists.'
    if code == 'refused':
        return 'Refused: %s' % _s(d.get('why'))
    if code == 'network':
        return 'Archeus could not be reached. Nothing was sent.'
    return '%s %s' % (r['status'], code)


# ── invalidation: which reads a stream frame makes stale ────────────────────

def _compile(pattern, sid):
    rest, tail = pattern, r'(\?.*)?'
    if rest.endswith('**'):
        rest, tail = rest[:-2], '.*'
    body = re.escape(sid).join('[^/?]+'.join(re.escape(p) for p in part.split('*'))
                               for part in rest.split('{id}'))
    return re.compile('^' + body + tail + r'\Z')


def stale_by(frame):
    """A predicate over read paths for one frame. Frames carry identities only:
    a frame never changes what is on screen, it says which reads to repeat, and
    a subject kind with no rule makes nothing stale."""
    subject = (frame.get('data') or {}).get('subject') or {}
    kind = subject.get('kind')
    rx = [_compile(p, subject.get('id') or '') for p in RULES.get(kind, [])] if kind else []
    return lambda path: any(r.match(path) for r in rx)
