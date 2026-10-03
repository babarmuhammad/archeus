"""The deterministic control grammar (ADR-0006, plan §11 step 1; P7).

A control verb is recognised and resolved without a model: `pause <mission>`,
`resume <mission>`, `stop <mission>` / `cancel <mission>`, `status [<project>]`,
`why <id>`, `remember [that] <text>`, `approve` / `reject` (bound to a card,
P19 S3), `pause all` / `resume all`, `reprioritise <mission> [to] <n>`, and
`emergency stop` (P19 B10), which only asks: its card confirms it, and
`use` / `don't use <account|harness> [for <mission>]` (P19 B10, a directive for
that mission or the thread's: ADR-0042 §3 decides what it does). `stop` on an
EXECUTING mission is `stop_running`, one card that pauses then cancels it
(C-33). A reference is an id, or the exact title
(case and spacing aside) of one open mission / one project. Anything that does
not match whole, or whose reference does not resolve to exactly one object, is
not a control verb, and goes to the brain — so a sentence that happens to
begin with "stop" is read, not obeyed.

`parse` is pure. `resolve` reads one snapshot and writes nothing.
"""

import re
from collections import namedtuple

from ...infra.db import rows
from ..domain import entities, ids, states

#: word -> verb
VERBS = {'pause': 'pause', 'resume': 'resume', 'stop': 'stop', 'cancel': 'cancel',
         'status': 'status', 'why': 'why', 'remember': 'remember', 'approve': 'approve',
         'reject': 'reject', 'reprioritise': 'reprioritise', 'reprioritize': 'reprioritise',
         'emergency': 'estop', 'use': 'use'}
MISSION_VERBS = ('pause', 'resume', 'cancel')
#: `pause all` / `resume all` (P19.5, ADR-0042 §1): the all-scope verb wins over a
#: mission titled "all", which stays reachable by its id
ALL_VERBS = {'pause': 'pause_all', 'resume': 'resume_all'}
#: `reprioritise <mission> [to] <integer>`: the mission, then its new priority
_PRIORITY = re.compile(r'^(.*?)\s+(?:to\s+)?([-+]?\d+)$', re.I)

Parsed = namedtuple('Parsed', 'verb arg')
#: `target` is a {kind, id} ref (or None for a bare `status`, `approve` or `reject`)
Control = namedtuple('Control', 'verb target arg')

_WORDS = re.compile(r'([A-Za-z]+)(?:\s+(.*))?\s*$', re.S)
#: `don't use` / `do not use` (P19 B10): the one verb that is not one word
_DONT = re.compile(r"(?:don['\u2019]?t|do not)\s+use\s+(.+)$", re.I | re.S)
#: `<resource> for <mission>`
_FOR = re.compile(r'^(.*?)\s+for\s+(.+)$', re.I)


def key(text):
    return ' '.join(text.casefold().split())


def parse(text):
    """Parsed(verb, arg) when *text* begins with a control verb, else None."""
    norm = ' '.join((text or '').split())
    d = _DONT.match(norm)
    if d is not None:
        return Parsed('dont_use', d.group(1).strip().rstrip('.!'))
    m = _WORDS.match(norm)
    if m is None or m.group(1).lower() not in VERBS:
        return None
    verb = VERBS[m.group(1).lower()]
    arg = (m.group(2) or '').strip().rstrip('.!')
    if verb == 'remember':
        arg = re.sub(r'^that\b', '', arg, flags=re.I).strip()
        return Parsed(verb, arg) if arg else None
    return Parsed(verb, arg)


def _one(matches):
    return matches[0] if len(matches) == 1 else None


def _mission(conn, arg):
    live = [r.entity for r in rows.where(conn, entities.Mission)
            if r.entity.state not in states.terminal('mission')]
    if ids.is_id(arg, 'mission'):
        return _one([m for m in live if m.id == arg] or
                    [r.entity for r in rows.where(conn, entities.Mission) if r.entity.id == arg])
    return _one([m for m in live if key(m.title) == key(arg)])


def _project(conn, arg):
    every = [r.entity for r in rows.where(conn, entities.Project)]
    if ids.is_id(arg, 'project'):
        return _one([p for p in every if p.id == arg])
    return _one([p for p in every if key(p.name) == key(arg)])


def resource(conn, name, kinds=('account', 'harness'), harnesses=()):
    """The one account (by label or id) or harness (by id, among the
    execution *harnesses* Core has) *name* names, as a `{kind, id}` ref, or
    None. "account X" / "harness X" says which."""
    n = key(name)
    for word in ('account', 'harness'):
        if n.startswith(word + ' ') and word in kinds:
            n, kinds = n[len(word) + 1:], (word,)
    got = []
    if 'account' in kinds:
        got += [{'kind': 'account', 'id': r.entity.id} for r in rows.where(conn, entities.Account)
                if n in (key(r.entity.id), key(r.entity.label))]
    if 'harness' in kinds:
        got += [{'kind': 'harness', 'id': h} for h in sorted(harnesses) if key(h) == n]
    return _one(got)


def resolve(conn, text, mission=None, harnesses=()):
    """The Control *text* is, resolved against the rows, or None (the brain's).
    In a mission's thread (*mission*, P19 S1) a mission verb with no object is
    about that mission."""
    p = parse(text)
    if p is None:
        return None
    if p.verb in ('approve', 'reject'):
        return Control(p.verb, None, p.arg)       # bound to a card, never to its words
    if p.verb == 'remember':
        return Control('remember', None, p.arg)
    if p.verb in ('use', 'dont_use'):
        # a directive for a named mission, or the thread's (ADR-0042 §1, P19 B10);
        # with no mission named its scope is ambiguous, read as the mission's
        got = _FOR.match(p.arg)
        name, named = (got.group(1), got.group(2)) if got else (p.arg, None)
        m = _mission(conn, named) if named else (
            rows.get(conn, entities.Mission, mission).entity if mission else None)
        r = resource(conn, name, harnesses=harnesses) if name else None
        if m is None or r is None:
            return None                     # what does not resolve is the brain's
        return Control(p.verb, {'kind': 'mission', 'id': m.id},
                       {'resource': r, 'scope': 'mission' if named else 'ambiguous'})
    if p.verb == 'estop':
        # `emergency stop` only asks: the card confirms it (P19 B10, ADR-0042 §1)
        return Control('estop', None, '') if key(p.arg) == 'stop' else None
    if p.verb in ALL_VERBS and key(p.arg) == 'all':
        return Control(ALL_VERBS[p.verb], None, '')
    if p.verb == 'reprioritise':
        got = _PRIORITY.match(p.arg)
        m = _mission(conn, got.group(1) if got else p.arg) if p.arg else None
        if m is None:
            return None                     # an object that does not resolve: the brain's
        return Control('reprioritise', {'kind': 'mission', 'id': m.id},
                       got.group(2) if got else '')
    if p.verb in MISSION_VERBS + ('stop',):
        m = _mission(conn, p.arg) if p.arg else None
        if m is None and mission and not p.arg:
            m = rows.get(conn, entities.Mission, mission).entity
        if m is None:
            return None
        verb = p.verb
        if verb == 'stop':
            # a running mission has no cancel edge: one card pauses, then cancels
            # it (C-33); any other mission is cancelled as before
            verb = 'stop_running' if m.state == 'EXECUTING' else 'cancel'
        return Control(verb, {'kind': 'mission', 'id': m.id}, p.arg)
    if p.verb == 'status':
        if not p.arg:
            return Control('status', None, '')
        proj = _project(conn, p.arg)
        return None if proj is None else Control('status', {'kind': 'project', 'id': proj.id},
                                                  p.arg)
    if p.verb == 'why':
        kind = ids.kind_of(p.arg) if p.arg else None
        return None if kind is None else Control('why', {'kind': kind, 'id': p.arg}, p.arg)
    return None
