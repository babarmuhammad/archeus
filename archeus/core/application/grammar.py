"""The deterministic control grammar (ADR-0006, plan §11 step 1; P7).

A control verb is recognised and resolved without a model: `pause <mission>`,
`resume <mission>`, `stop <mission>` / `cancel <mission>`, `status [<project>]`,
`why <id>`, `remember [that] <text>`, and `approve`, `reject`,
`reprioritise` (recognised, and answered that their phase has not arrived:
approvals are P9's, priorities P10's). A reference is an id, or the exact title
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
VERBS = {'pause': 'pause', 'resume': 'resume', 'stop': 'cancel', 'cancel': 'cancel',
         'status': 'status', 'why': 'why', 'remember': 'remember', 'approve': 'approve',
         'reject': 'reject', 'reprioritise': 'reprioritise', 'reprioritize': 'reprioritise'}
#: verbs recognised before their phase: answered, never acted on
NOT_YET = {'approve': 'P9 (approvals)', 'reject': 'P9 (approvals)',
           'reprioritise': 'P10 (priorities)'}
MISSION_VERBS = ('pause', 'resume', 'cancel')

Parsed = namedtuple('Parsed', 'verb arg')
#: `target` is a {kind, id} ref (or None for a bare `status` or a NOT_YET verb)
Control = namedtuple('Control', 'verb target arg')

_WORDS = re.compile(r'([A-Za-z]+)(?:\s+(.*))?\s*$', re.S)


def key(text):
    return ' '.join(text.casefold().split())


def parse(text):
    """Parsed(verb, arg) when *text* begins with a control verb, else None."""
    m = _WORDS.match(' '.join((text or '').split()))
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


def resolve(conn, text):
    """The Control *text* is, resolved against the rows, or None (the brain's)."""
    p = parse(text)
    if p is None:
        return None
    if p.verb in NOT_YET:
        return Control(p.verb, None, p.arg)
    if p.verb == 'remember':
        return Control('remember', None, p.arg)
    if p.verb in MISSION_VERBS:
        m = _mission(conn, p.arg) if p.arg else None
        return None if m is None else Control(p.verb, {'kind': 'mission', 'id': m.id}, p.arg)
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
