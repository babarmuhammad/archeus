"""What an automation reacts to and what it asks for (p14-design-gate §7, §10).

Pure: no I/O, no clock, no database — only its arguments — so the same event
and the same automation give the same answer and the same rationale in any
order, on any machine (E04), and the simulation can run it over the log
without writing anything.

    validate_trigger / validate_template   refuse a rule when it is written
    matches                                does this event fire this trigger, and why
    render                                 the mission a template asks for
    should_suspend                         the loop guard's suspension rule
"""

import fnmatch
import re

#: the only keys a template may have: a mission's title, objective and success
#: criteria. No model, harness, account, profile, plan, approval or verdict
#: (§12, E11, E14): an automation asks for work, it never decides how.
TEMPLATE_KEYS = ('title', 'objective', 'success_criteria')
#: P14's own bookkeeping can never be a trigger (D10)
FORBIDDEN_PREFIXES = ('automation.', 'automation_run.')
#: a value substituted from an event is data: one line, this long at most
MAX_VALUE = 200
#: three escalations or three rate-limited runs in the window suspend (§10)
SUSPEND_AFTER = 3
WINDOW_S = 3600

_PLACEHOLDER = re.compile(r'\{([^{}]*)\}')
_ALLOWED = re.compile(r'(event\.type|event\.seq|subject\.kind|subject\.id|payload\.\w+)')
_CONTROL = re.compile(r'[\x00-\x1f\x7f]+')
_SCALARS = (str, int, float, bool, type(None))


class Invalid(ValueError):
    """A trigger or template that cannot be written."""


def validate_trigger(trigger, types):
    """The trigger as stored, or Invalid. *types* is the set of registered
    event types (the caller's registry: this module imports nothing)."""
    if not isinstance(trigger, dict) or trigger.get('kind', 'event') != 'event':
        raise Invalid("a trigger is {kind: 'event', type, where} (schedule and condition "
                      "triggers are not built: p14-design-gate D14)")
    extra = set(trigger) - {'kind', 'type', 'where'}
    if extra:
        raise Invalid('a trigger has no %s' % sorted(extra))
    t = trigger.get('type')
    if t not in types:
        raise Invalid('%r is not a registered event type' % (t,))
    if t.startswith(FORBIDDEN_PREFIXES):
        raise Invalid("an automation cannot react to automation events (%s): that is a loop "
                      "by construction" % t)
    where = trigger.get('where') or {}
    if not isinstance(where, dict):
        raise Invalid('where maps payload keys to values')
    for k, v in where.items():
        if not (isinstance(k, str) and re.fullmatch(r'\w+', k)):
            raise Invalid('where names a top-level payload key: %r' % (k,))
        if isinstance(v, dict):
            if len(v) != 1 or next(iter(v)) not in ('glob', 'not_glob') \
                    or not isinstance(next(iter(v.values())), str):
                raise Invalid("a where test is a value, {glob: p} or {not_glob: p}: %r" % (v,))
        elif not isinstance(v, _SCALARS):
            raise Invalid('a where value is a string, number, boolean or null: %r' % (v,))
    return {'kind': 'event', 'type': t, 'where': dict(where)}


def validate_template(template):
    """The template as stored, or Invalid."""
    if not isinstance(template, dict):
        raise Invalid('a template is {title, objective, success_criteria?}')
    extra = set(template) - set(TEMPLATE_KEYS)
    if extra:
        raise Invalid('a template asks for a mission and nothing else; it cannot carry %s'
                      % sorted(extra))
    for k in ('title', 'objective'):
        v = template.get(k)
        if not (isinstance(v, str) and v.strip()):
            raise Invalid('a template needs a %s' % k)
        for name in _PLACEHOLDER.findall(v):
            if not _ALLOWED.fullmatch(name):
                raise Invalid('{%s} is not a placeholder (event.type, event.seq, subject.kind, '
                              'subject.id, payload.<key>)' % name)
    crit = template.get('success_criteria') or []
    if not (isinstance(crit, list) and all(isinstance(c, dict) for c in crit)):
        raise Invalid('success_criteria is a list of {text, check}')
    return {'title': template['title'], 'objective': template['objective'],
            'success_criteria': [dict(c) for c in crit]}


def _test(want, got):
    if isinstance(want, dict):
        (op, pattern), = want.items()
        hit = isinstance(got, str) and fnmatch.fnmatchcase(got, pattern)
        return hit if op == 'glob' else not hit
    return type(want) is type(got) and want == got


def matches(trigger, event_type, payload):
    """(fired, rationale): the rationale names each test and the value it saw."""
    if event_type != trigger['type']:
        return False, None
    seen = {}
    for k, want in sorted(trigger['where'].items()):
        got = payload.get(k)
        if not _test(want, got):
            return False, None
        seen[k] = {'test': want, 'value': got}
    return True, {'type': event_type, 'where': seen}


def _value(v):
    return _CONTROL.sub(' ', '' if v is None else str(v)).strip()[:MAX_VALUE]


def render(template, event_type, seq, subject, payload):
    """The mission's title, objective and criteria for one event. A payload
    key the event does not carry renders empty."""
    values = {'event.type': event_type, 'event.seq': seq, 'subject.kind': subject[0],
              'subject.id': subject[1]}

    def sub(text):
        return _PLACEHOLDER.sub(lambda m: _value(
            payload.get(m.group(1)[8:]) if m.group(1).startswith('payload.')
            else values[m.group(1)]), text)
    return {'title': sub(template['title'])[:MAX_VALUE], 'objective': sub(template['objective']),
            'success_criteria': [dict(c) for c in template.get('success_criteria') or ()]}


def should_suspend(recent):
    """*recent* is the automation's runs in the window as (state, reason_code)."""
    return (sum(s == 'ESCALATED' for s, _ in recent) >= SUSPEND_AFTER
            or sum(c == 'rate_limited' for _, c in recent) >= SUSPEND_AFTER)
