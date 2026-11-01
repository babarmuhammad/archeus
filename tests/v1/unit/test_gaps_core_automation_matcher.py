"""T-312: the highest-risk uncovered branches of archeus/core/automation/matcher.py.

Fail-closed and denial paths first — a trigger that is not a mapping, a type that is
not a string, a `where` that is not a mapping, a glob test that is not exactly one
string, a value test that is type-strict, a template that is not a mission request —
then the boundary values (the 60 s and the 7-day schedule caps, the digit bound, the
MAX_VALUE cut, the two suspension counters, the forbidden-prefix edge), then the error
paths (a title or objective that is missing or not a string).

matcher.py is pure (no I/O, no clock, no OS), so every case below is a value in and a
value out and gives the same answer on Linux and on Windows: no disk, no process, no
environment, no skipif, no sleep. Style, `_trigger` and the parametrize tables follow
tests/v1/unit/test_automation_units.py, the closest existing test of this module.
"""

import pytest

from archeus.core.automation import matcher as M
from archeus.core.domain import events

TYPES = set(events.REGISTRY)
MODEL_ADDED = 'repository.model_added'          # a registered, non-forbidden type
ESCALATED = ('ESCALATED', 'depth_exceeded')
LIMITED = ('SKIPPED', 'rate_limited')


def _trigger(**where):
    """The stored form of an event trigger, as test_automation_units.py builds it."""
    return M.validate_trigger({'type': MODEL_ADDED, 'where': where}, TYPES)


def _sub(value, text='{payload.x}'):
    """What one payload value becomes in a mission title (the render seam)."""
    t = M.validate_template({'title': text, 'objective': 'o'})
    return M.render(t, 'e.type', 1, ('kind', 'id'), {'x': value})['title']


# ── 1. the write gate: a trigger that cannot be written at all (matcher.py:52-78) ──

@pytest.mark.parametrize('trigger', [None, MODEL_ADDED, 7, [], (MODEL_ADDED,), True],
                         ids=['none', 'string', 'int', 'list', 'tuple', 'bool'])
def test_a_trigger_that_is_not_a_mapping_is_refused(trigger):
    # matcher.py:54 `if not isinstance(trigger, dict) or trigger.get('kind', 'event')
    # != 'event'` — a non-mapping is refused as Invalid, it never reaches a .get()
    # and never raises AttributeError/TypeError out of the write path.
    with pytest.raises(M.Invalid, match='a trigger is'):
        M.validate_trigger(trigger, TYPES)


@pytest.mark.parametrize('bad_type', [123, 1.5, None, MODEL_ADDED.title(), [MODEL_ADDED],
                                      {MODEL_ADDED: 1}, True],
                         ids=['int', 'float', 'missing-none', 'title-cased', 'list',
                              'dict', 'bool'])
def test_a_trigger_type_that_is_not_a_string_is_refused(bad_type):
    # matcher.py:61 `if not isinstance(t, str) or t not in types` — the isinstance
    # half is what stops an unhashable type (list, dict) reaching `t not in types`
    # of a set, which would raise TypeError instead of refusing the rule.
    with pytest.raises(M.Invalid, match='not a registered event type'):
        M.validate_trigger({'type': bad_type}, TYPES)
    with pytest.raises(M.Invalid, match='not a registered event type'):
        M.validate_trigger({'kind': 'event', 'type': bad_type}, TYPES)


@pytest.mark.parametrize('t, why', [
    ('automation.created', 'loop by construction'),
    ('automation_run.state_changed', 'loop by construction'),
    ('automation.schedule_due', 'loop by construction'),
    ('automation.', 'loop by construction'),                  # the bare prefix itself
    ('automationx.created', None),                             # prefix must be dotted
    ('automation', None),
    ('automation_run', None),
    ('x.automation.created', None),                            # only a *leading* prefix
], ids=['created', 'run-state', 'schedule-due', 'bare-prefix', 'automationx',
        'automation', 'automation_run', 'prefixed'])
def test_only_a_leading_dotted_automation_prefix_is_refused(t, why):
    # matcher.py:63 `if t.startswith(FORBIDDEN_PREFIXES)` with FORBIDDEN_PREFIXES =
    # ('automation.', 'automation_run.'): dropping the dot (or matching a substring)
    # would refuse ordinary types, widening the rule past P14's own bookkeeping.
    types = TYPES | {t}
    if why:
        with pytest.raises(M.Invalid, match=why):
            M.validate_trigger({'type': t}, types)
    else:
        assert M.validate_trigger({'type': t}, types) == {'kind': 'event', 'type': t,
                                                          'where': {}}


@pytest.mark.parametrize('where', ['path=x', 5, [('a', 1)], {'a'}, object()],
                         ids=['string', 'int', 'pairs', 'set', 'object'])
def test_a_where_that_is_not_a_mapping_is_refused(where):
    # matcher.py:67 `if not isinstance(where, dict)` — a truthy non-mapping is
    # refused; falling through would reach .items() and crash the write path.
    with pytest.raises(M.Invalid, match='where maps payload keys'):
        M.validate_trigger({'type': MODEL_ADDED, 'where': where}, TYPES)


@pytest.mark.parametrize('empty', [None, {}, [], 0, '', False],
                         ids=['none', 'dict', 'list', 'zero', 'string', 'false'])
def test_an_empty_where_is_stored_as_no_test_and_fires_on_every_payload(empty):
    # matcher.py:66 `where = trigger.get('where') or {}` and the empty loop at
    # matcher.py:145: a falsy where means "no test", so the rule fires for every
    # event of its type — the widest-reaching rule the module can store, and the
    # one an accidental `where: 0` silently becomes.
    stored = M.validate_trigger({'type': MODEL_ADDED, 'where': empty}, TYPES)
    assert stored == {'kind': 'event', 'type': MODEL_ADDED, 'where': {}}
    assert M.matches(stored, MODEL_ADDED, {'anything': 1}) == (
        True, {'type': MODEL_ADDED, 'where': {}})


@pytest.mark.parametrize('test', [
    {},                                        # matcher.py:73 `len(v) != 1`
    {'glob': 'a*', 'not_glob': 'b*'},           # two tests in one dict
    {'regex': 'a*'},                            # op not in ('glob', 'not_glob')
    {'GLOB': 'a*'},                             # the op name is case-sensitive
    {1: 'a*'},                                  # a non-string op
    {'glob': 123},                              # matcher.py:74 pattern must be a str
    {'glob': None},
    {'not_glob': ['a*']},
    {'glob': {'pattern': 'a*'}},
], ids=['empty', 'two-ops', 'regex', 'upper-op', 'int-op', 'int-pattern',
        'none-pattern', 'list-pattern', 'dict-pattern'])
def test_a_glob_test_that_is_not_exactly_one_string_pattern_is_refused(test):
    with pytest.raises(M.Invalid, match='a where test is a value'):
        M.validate_trigger({'type': MODEL_ADDED, 'where': {'path': test}}, TYPES)


@pytest.mark.parametrize('key', ['a.b', 'a b', '', 'a-b', 'a\nb', 'payload.a', '\u00e9!x',
                                 1, None, ('a',)],
                         ids=['dotted', 'space', 'empty', 'dash', 'newline', 'payload-prefixed',
                              'punctuation', 'int', 'none', 'tuple'])
def test_a_where_key_that_is_not_one_word_is_refused(key):
    # matcher.py:70 `if not (isinstance(k, str) and re.fullmatch(r'\w+', k))` — a
    # dotted key would reach into a nested payload value the rule cannot name.
    with pytest.raises(M.Invalid, match='top-level payload key'):
        M.validate_trigger({'type': MODEL_ADDED, 'where': {key: 'v'}}, TYPES)


@pytest.mark.parametrize('key', ['_1', 'a1', 'PATH', 'caf\xe9'], ids=['underscore', 'digits',
                                                                      'upper', 'unicode-word'])
def test_a_where_key_of_word_characters_is_kept_exactly_as_written(key):
    # matcher.py:70/78 — \w+ is unicode-aware and case-faithful: a key is neither
    # folded nor lower-cased on the way to storage (the payload lookup is exact).
    assert M.validate_trigger({'type': MODEL_ADDED, 'where': {key: 'v'}}, TYPES) == {
        'kind': 'event', 'type': MODEL_ADDED, 'where': {key: 'v'}}


@pytest.mark.parametrize('value', [(1,), set(), frozenset(), b'bytes', [[1]], 1j, object()],
                         ids=['tuple', 'set', 'frozenset', 'bytes', 'nested-list',
                              'complex', 'object'])
def test_a_where_value_that_is_not_a_scalar_is_refused(value):
    # matcher.py:76 `elif not isinstance(v, _SCALARS)` — a container or an object
    # would be compared by identity and rendered as a repr into a rationale.
    with pytest.raises(M.Invalid, match='string, number, boolean or null'):
        M.validate_trigger({'type': MODEL_ADDED, 'where': {'a': value}}, TYPES)


@pytest.mark.parametrize('value', ['x', '', 1, 0, 1.5, True, False, None],
                         ids=['str', 'empty-str', 'int', 'zero', 'float', 'true', 'false',
                              'none'])
def test_a_scalar_where_value_is_stored_by_value_not_by_identity(value):
    # matcher.py:76-78 — every scalar passes and is copied out in a new dict.
    src = {'type': MODEL_ADDED, 'where': {'a': value}}
    stored = M.validate_trigger(src, TYPES)
    assert stored == {'kind': 'event', 'type': MODEL_ADDED, 'where': {'a': value}}
    stored['where']['a'] = 'mutated'
    assert src == {'type': MODEL_ADDED, 'where': {'a': value}}      # matcher.py:78 dict(where)


# ── 2. the write gate: a template that is not a mission request (matcher.py:109-129) ──

@pytest.mark.parametrize('template, why', [
    (None, 'a template is'),
    ('title', 'a template is'),
    (7, 'a template is'),
    ([], 'a template is'),
    ({'title': 't'}, 'needs a objective'),                        # matcher.py:119
    ({'objective': 'o'}, 'needs a title'),
    ({'title': 123, 'objective': 'o'}, 'needs a title'),           # not a str at all
    ({'title': [], 'objective': 'o'}, 'needs a title'),
    ({'title': 't', 'objective': '   '}, 'needs a objective'),     # whitespace only
    ({'title': 't', 'objective': 0}, 'needs a objective'),
    ({'title': 't', 'objective': 'o', 'success_criteria': 'abc'}, 'list of'),
    ({'title': 't', 'objective': 'o', 'success_criteria': 5}, 'list of'),
    ({'title': 't', 'objective': 'o', 'success_criteria': {'text': 'c'}}, 'list of'),
    ({'title': 't', 'objective': 'o', 'success_criteria': ({'text': 'c'},)}, 'list of'),
    ({'title': 't', 'objective': 'o', 'success_criteria': ['c']}, 'list of'),
    ({'title': 't', 'objective': 'o', 'success_criteria': [{'text': 'c'}, 'c']}, 'list of'),
    ({'title': 't', 'objective': 'o', 'model': 'cheap'}, 'cannot carry'),
    ({'title': 't', 'objective': 'o', 'success_criteria': [{'text': 'c'}]}, None),
], ids=['none', 'string', 'int', 'list', 'no-objective', 'no-title', 'int-title',
        'list-title', 'blank-objective', 'zero-objective', 'str-criteria', 'int-criteria',
        'dict-criteria', 'tuple-criteria', 'str-item', 'mixed-item', 'carries-model',
        'ok-criteria'])
def test_a_template_that_is_not_a_mission_request_is_refused(template, why):
    # matcher.py:111 / 119-120 / 126-127 — the three refusals of the template gate.
    if why is None:
        assert M.validate_template(template) == {'title': 't', 'objective': 'o',
                                                 'success_criteria': [{'text': 'c'}]}
    else:
        with pytest.raises(M.Invalid, match=why):
            M.validate_template(template)


@pytest.mark.parametrize('falsy', [None, [], '', 0, False],
                         ids=['none', 'list', 'string', 'zero', 'false'])
def test_a_falsy_success_criteria_is_stored_as_no_criteria(falsy):
    # matcher.py:125 `crit = template.get('success_criteria') or []` then
    # matcher.py:126 — a falsy value of any type is normalized to no criteria.
    assert M.validate_template({'title': 't', 'objective': 'o',
                               'success_criteria': falsy})['success_criteria'] == []


def test_the_criteria_a_template_carries_are_copies_of_the_ones_it_was_given():
    # matcher.py:129 `[dict(c) for c in crit]` — a stored template cannot be
    # rewritten through the dict its caller still holds, nor the other way round.
    crit = [{'text': 'c'}]
    src = {'title': 't', 'objective': 'o', 'success_criteria': crit}
    stored = M.validate_template(src)
    crit[0]['text'] = 'changed'
    crit.append({'text': 'late'})
    assert stored['success_criteria'] == [{'text': 'c'}]
    stored['success_criteria'][0]['text'] = 'mutated'
    assert src['success_criteria'] == [{'text': 'changed'}, {'text': 'late'}]


# ── 3. placeholders: the only way an event reaches a mission (matcher.py:121-124, 163-166) ──

@pytest.mark.parametrize('name', [
    '{}', '{ event.type}', '{event.type }', '{event}', '{subject}',
    '{payload}', '{payload.a.b}', '{payload.path.strip()}', '{payload["path"]}',
    '{Payload.path}', '{EVENT.TYPE}', '{event.typee}', '{payload1.x}',
], ids=['empty', 'leading-space', 'trailing-space', 'event-only',
        'subject-only', 'payload-only', 'dotted-payload', 'call-syntax', 'quote-syntax',
        'upper-name', 'upper-dotted', 'near-miss', 'near-miss-prefix'])
@pytest.mark.parametrize('field', ['title', 'objective'], ids=['title', 'objective'])
def test_a_placeholder_outside_the_allowed_set_is_refused_in_either_field(field, name):
    # matcher.py:121-124 `for name in _PLACEHOLDER.findall(v): if not
    # _ALLOWED.fullmatch(name)` — the check runs for BOTH fields; dropping the loop
    # or using .match() instead of .fullmatch() (which 'event.typee' and
    # '{payload.a.b}' defeat) would let a hostile name reach render's lookup.
    template = {'title': 't', 'objective': 'o'}
    template[field] = 'x %s y' % name
    with pytest.raises(M.Invalid, match='is not a placeholder'):
        M.validate_template(template)


@pytest.mark.parametrize('name, want', [
    ('{event.type}', MODEL_ADDED),
    ('{event.seq}', '7'),
    ('{subject.kind}', 'repository'),
    ('{subject.id}', 'rep_1'),
    ('{payload.path}', 'app/x.py'),
    ('{payload.__class__}', ''),                  # a dict lookup, not an attribute
    ('{{event.type}}', '{%s}' % MODEL_ADDED),     # the inner braces substitute
], ids=['event-type', 'event-seq', 'subject-kind', 'subject-id', 'payload-key',
        'dunder-key', 'doubled-braces'])
def test_each_allowed_placeholder_substitutes_its_own_source(name, want):
    # matcher.py:163-166 — `payload.get(...) if m.group(1).startswith('payload.')
    # else values[m.group(1)]`: the four event/subject sources are this `else`
    # branch, and a payload key is a dict key, never an attribute lookup.
    t = M.validate_template({'title': name, 'objective': 'o'})
    assert M.render(t, MODEL_ADDED, 7, ('repository', 'rep_1'),
                    {'path': 'app/x.py'})['title'] == want


def test_a_payload_cannot_forge_the_event_or_the_subject_it_is_matched_on():
    # matcher.py:164-166 — the payload branch is `payload.get(key)` and the event
    # branch reads `values`; a payload key spelled like a value source must not be
    # able to rewrite the mission's provenance.
    t = M.validate_template({'title': '{event.type}|{subject.id}|{payload.note}',
                             'objective': 'o'})
    out = M.render(t, MODEL_ADDED, 7, ('repository', 'rep_1'),
                   {'event.type': 'forged', 'subject.id': 'forged', 'note': 'n'})
    assert out['title'] == '%s|rep_1|n' % MODEL_ADDED


@pytest.mark.parametrize('missing', [None, 'missing'],
                         ids=['explicit-null', 'absent-key'])
def test_a_placeholder_whose_payload_key_is_absent_renders_empty(missing):
    # matcher.py:164 `payload.get(...)` with matcher.py:153-154 — a key the event
    # does not carry is empty data, never the text 'None' and never a KeyError.
    t = M.validate_template({'title': '[{payload.missing}]', 'objective': 'o'})
    payload = {} if missing == 'missing' else {'missing': None}
    assert M.render(t, MODEL_ADDED, 1, ('k', 'i'), payload)['title'] == '[]'


@pytest.mark.parametrize('value, expected', [
    (0, '0'), (False, 'False'), ({}, '{}'), ([], '[]'), ('', ''), (1, '1'),
], ids=['zero', 'false', 'empty-dict', 'empty-list', 'empty-str', 'one'])
def test_a_falsy_payload_value_renders_its_own_text_and_not_empty(value, expected):
    # matcher.py:154 `'' if v is None else str(v)` — only null is empty data; a
    # falsy 0 / False / {} is still data the mission has to be told about.
    assert _sub(value) == expected


def test_the_literal_text_around_a_substitution_is_kept_while_the_value_is_stripped():
    # matcher.py:154 vs matcher.py:163-166 — `_CONTROL.sub` and `strip()` act on
    # the substituted value alone: the brackets and spaces of the template itself
    # are the author's text and survive untouched.
    assert _sub('  a\x00b  ', '[ {payload.x} ]') == '[ a b ]'


def test_the_event_fields_render_empty_rather_than_none_when_they_are_missing():
    # matcher.py:154 `'' if v is None else str(v)` — a None seq or subject is
    # empty data in a mission title, not the literal text 'None'.
    t = M.validate_template({'title': '[{event.seq}][{subject.kind}][{subject.id}]',
                             'objective': 'o'})
    assert M.render(t, MODEL_ADDED, None, (None, None), {})['title'] == '[][][]'


@pytest.mark.parametrize('value, expected', [
    ('y' * M.MAX_VALUE, 'y' * M.MAX_VALUE),                       # kept whole
    ('y' * (M.MAX_VALUE + 1), 'y' * M.MAX_VALUE),                 # cut at MAX_VALUE
    ('a' * M.MAX_VALUE + ' ' * 50, 'a' * M.MAX_VALUE),            # stripped, then cut
    (' ' * 50 + 'a' * M.MAX_VALUE, 'a' * M.MAX_VALUE),
    ('a\x00\x1fb', 'a b'),                                         # controls -> one space
    ('\x00\x1f\x7f\x0b', ''),                                      # only controls
    ('  padded \n', 'padded'),
    ('line\nbreak', 'line break'),
    (True, 'True'), (1.5, '1.5'), (['a'], "['a']"),
], ids=['exact-cap', 'one-over-cap', 'trailing-padding', 'leading-padding', 'controls',
        'only-controls', 'padded', 'newline', 'bool', 'float', 'list'])
def test_a_substituted_value_is_one_short_line_cut_exactly_at_max_value(value, expected):
    # matcher.py:153-154 `_CONTROL.sub(' ', ...).strip()[:MAX_VALUE]` — the order
    # matters (strip before the cut, so padding cannot push real text past the
    # cap: cutting first would leave 150 characters here) and so does the size:
    # one character over MAX_VALUE is a line too long.
    assert _sub(value) == expected


def test_two_long_values_cannot_make_a_title_longer_than_max_value():
    # matcher.py:167 `sub(template['title'])[:MAX_VALUE]` — however many
    # placeholders a title carries, what is asked for is one line of at most
    # MAX_VALUE characters.
    t = M.validate_template({'title': '{payload.a}{payload.b}', 'objective': 'o'})
    title = M.render(t, MODEL_ADDED, 1, ('k', 'i'),
                     {'a': 'a' * M.MAX_VALUE, 'b': 'b' * M.MAX_VALUE})['title']
    assert title == 'a' * M.MAX_VALUE and len(title) == M.MAX_VALUE


# ── 4. matching: the denial paths first (matcher.py:140-150), then the value tests ──

@pytest.mark.parametrize('trigger, event_type, fired', [
    (_trigger(path='app/x.py'), 'repository.file_added', False),        # matcher.py:142
    ({'kind': 'schedule', 'type': MODEL_ADDED, 'where': {}}, MODEL_ADDED, False),
    ({'kind': 'Event', 'type': MODEL_ADDED, 'where': {}}, MODEL_ADDED, False),
    ({'kind': 'condition', 'type': MODEL_ADDED, 'where': {}}, MODEL_ADDED, False),
    ({'type': MODEL_ADDED, 'where': {}}, MODEL_ADDED, True),            # kind defaults
    ({'kind': 'event', 'type': MODEL_ADDED, 'where': {}}, MODEL_ADDED, True),
], ids=['wrong-type', 'schedule-kind', 'capital-kind', 'condition-kind',
        'kind-defaults-to-event', 'kind-explicit'])
def test_only_an_event_trigger_of_exactly_its_type_can_fire(trigger, event_type, fired):
    # matcher.py:142 `if trigger.get('kind', 'event') != 'event' or event_type !=
    # trigger['type']` — an unknown or mis-cased kind is denied, never treated as
    # an event; dropping the kind half would let a schedule trigger fire on events.
    assert bool(M.matches(trigger, event_type, {'path': 'app/x.py'})[0]) is fired


def test_one_failing_test_denies_the_whole_rule_and_no_rationale_is_left_behind():
    # matcher.py:147-148 `if not _test(want, got): return False, None` — a rule
    # that does not fire returns no partial rationale for the tests it did pass.
    t = _trigger(path='app/x.py', revision='abc', n=1)
    assert M.matches(t, MODEL_ADDED, {'path': 'app/x.py', 'revision': 'abc',
                                      'n': 2}) == (False, None)
    assert M.matches(t, MODEL_ADDED, {'path': 'app/other.py'}) == (False, None)
    assert M.matches(t, MODEL_ADDED, {}) == (False, None)


def test_the_rationale_names_every_test_and_only_the_tested_keys():
    # matcher.py:144-150 — the rationale is the audit trail: each key with the
    # value it saw, and no untested payload key riding along into the mission.
    t = _trigger(path={'not_glob': 'tests/*'}, n=1)
    fired, rationale = M.matches(t, MODEL_ADDED, {'path': 'app/x.py', 'n': 1,
                                                  'secret': 'token', 'extra': None})
    assert fired and rationale == {'type': MODEL_ADDED, 'where': {
        'n': {'test': 1, 'value': 1},
        'path': {'test': {'not_glob': 'tests/*'}, 'value': 'app/x.py'}}}
    # the order of the payload does not reach the answer (E04): sorted at matcher.py:145
    assert M.matches(t, MODEL_ADDED, {'secret': 'token', 'n': 1,
                                      'path': 'app/x.py', 'extra': None})[1] == rationale


@pytest.mark.parametrize('test, value, fired', [
    ({'glob': 'app/*'}, 'app/x.py', True),
    ({'glob': 'app/*'}, 'APP/x.py', False),            # fnmatchcase: never folded
    ({'glob': 'app/*'}, 'tests/x.py', False),
    ({'glob': 'app/*'}, 5, False),                      # matcher.py:135 isinstance(got, str)
    ({'glob': 'app/*'}, None, False),                   # an absent key is not a string
    ({'glob': 'app/*'}, True, False),
    ({'glob': 'app/*'}, b'app/x.py', False),
    ({'glob': 'app/*'}, ['app/x.py'], False),
    ({'glob': '*'}, None, False),                       # '*' cannot match a missing key
    ({'glob': ''}, '', True),
    ({'glob': ''}, 'a', False),
    ({'glob': '?'}, 'ab', False),
    ({'glob': '?'}, 'a', True),
    ({'glob': '[a-c]*'}, 'app/x.py', True),
    ({'glob': '[a-c]*'}, 'App/x.py', False),            # the class is case-sensitive too
    ({'glob': '['}, '[', True),                         # an unterminated class is literal
    ({'glob': 'a*'}, 'a*x', True),                      # '*' is a wildcard over the value
    ({'not_glob': 'tests/*'}, 'tests/x.py', False),
    ({'not_glob': 'tests/*'}, 'app/x.py', True),
    ({'not_glob': 'tests/*'}, None, True),              # a value that cannot match passes
    ({'not_glob': 'tests/*'}, 5, True),                 # ... whatever its type
    ({'not_glob': ''}, '', False),
], ids=['glob-hit', 'glob-case', 'glob-miss', 'glob-int', 'glob-absent', 'glob-bool',
        'glob-bytes', 'glob-list', 'glob-star-absent', 'glob-empty-hit', 'glob-empty-miss',
        'qmark-long', 'qmark-one', 'class-hit', 'class-case', 'class-literal',
        'star-in-value', 'not-glob-hit', 'not-glob-miss', 'not-glob-absent', 'not-glob-int',
        'not-glob-empty'])
def test_a_glob_test_only_ever_tests_a_string_and_never_folds_it(test, value, fired):
    # matcher.py:135 `hit = isinstance(got, str) and fnmatch.fnmatchcase(got,
    # pattern)` — the isinstance half denies every non-string, and fnmatchcase (not
    # fnmatch) is what keeps the answer identical on a case-insensitive filesystem.
    t = _trigger(path=test)
    assert M.matches(t, MODEL_ADDED, {'path': value})[0] is fired
    # an absent key reads as None: it can never satisfy a glob, and always a not_glob
    assert M.matches(t, MODEL_ADDED, {})[0] is ('not_glob' in test)


@pytest.mark.parametrize('test, key, value, fired', [
    ('abc', 'path', 'abc', True),
    ('abc', 'path', 'ABC', False),                        # value tests are exact
    (1, 'n', 1, True),
    (True, 'n', 1, False),                                # matcher.py:137 type(want) is
    (1, 'n', True, False),                                # type(got) and want == got
    (1, 'n', 1.0, False),
    (1.0, 'n', 1.0, True),
    (0, 'n', False, False),
    (None, 'path', None, True),                           # an explicit null matches null
    (None, 'path', '', False),                            # null is not the empty string
    ('None', 'path', None, False),
    (float('nan'), 'n', float('nan'), False),             # == is never true for NaN
    (1e309, 'n', 1e309, True),                            # inf == inf, same type
], ids=['str-hit', 'str-case', 'int-hit', 'bool-vs-int', 'int-vs-bool', 'int-vs-float',
        'float-hit', 'zero-vs-false', 'null-hit', 'null-vs-empty', 'None-text',
        'nan', 'inf'])
def test_a_value_test_is_type_strict_before_it_is_equal(test, key, value, fired):
    # matcher.py:137 `type(want) is type(got) and want == got` — the type half is
    # what stops True firing on 1, 1 on 1.0 and 'None' on null; drop it and a
    # rule written for a boolean fires on every payload that carries a number.
    t = M.validate_trigger({'type': MODEL_ADDED, 'where': {key: test}}, TYPES)
    assert M.matches(t, MODEL_ADDED, {key: value})[0] is fired
    assert M.matches(t, MODEL_ADDED, {})[0] is (test is None)   # absent reads as None


def test_the_rationale_carries_the_values_it_saw_without_editing_anything():
    # matcher.py:149 `seen[k] = {'test': want, 'value': got}` — the rationale
    # quotes the test and the value; it must not be a view the caller can push
    # back into the stored trigger or the event payload.
    t = _trigger(path='app/x.py')
    payload = {'path': 'app/x.py', 'body': {'k': 'v'}}
    fired, rationale = M.matches(t, MODEL_ADDED, payload)
    rationale['where']['path']['value'] = 'forged'
    rationale['type'] = 'forged'
    assert t['where'] == {'path': 'app/x.py'} and t['type'] == MODEL_ADDED
    assert payload == {'path': 'app/x.py', 'body': {'k': 'v'}}
    assert M.matches(t, MODEL_ADDED, payload) == (fired, {'type': MODEL_ADDED, 'where': {
        'path': {'test': 'app/x.py', 'value': 'app/x.py'}}})


# ── 5. the schedule grammar: the two caps and the digit bound (matcher.py:81-99) ──

@pytest.mark.parametrize('every, stored, seconds', [
    ('60s', '60s', 60),                                   # matcher.py:89, exact MIN
    ('59s', None, None),                                  # one second under MIN
    ('1m', '1m', 60),
    ('168h', '168h', 604800),                             # matcher.py:91, exact MAX
    ('169h', None, None),                                 # one hour over MAX
    ('7d', '7d', 604800),
    ('8d', None, None),
    ('999999', None, None),                               # 6 digits, 999999 minutes
    ('999999m', None, None),
    ('1000000', None, None),                              # the digit bound: 7 digits
    ('999999999999d', None, None),
    ('0s', None, None),
    ('0m', None, None),
    ('0d', None, None),
    ('1s', None, None),
    ('15M', None, None),                                  # the unit is lower-case only
    ('15 m ', '15m', 900),                                # whitespace is allowed, then gone
    ('  2  h  ', '2h', 7200),
    ('015m', '15m', 900),                                 # leading zeros normalize
    ('+15m', None, None),
    ('-15m', None, None),
    ('15,5m', None, None),
    ('1_5m', None, None),                                 # int() would accept the underscore
    ('15mx', None, None),
    ('mm', None, None),
    ('', None, None),
    ('   ', None, None),
    ('  \n15m\n', '15m', 900),                            # \s* surrounds the whole form
], ids=['60s', '59s', '1m', '168h', '169h', '7d', '8d', '999999', '999999m', '7-digits',
        'huge', '0s', '0m', '0d', '1s', 'upper-unit', 'spaces', 'wide-spaces', 'zeros',
        'plus', 'minus', 'comma', 'underscore', 'trailing', 'unit-only', 'empty', 'blank',
        'newline'])
def test_the_schedule_period_boundaries_are_exact(every, stored, seconds):
    # matcher.py:89 `if every_s(...) < MIN_EVERY_S` and matcher.py:91
    # `if every_s(...) > MAX_EVERY_S` (both >= / <= would widen the gate),
    # matcher.py:38 `\d{1,6}` and matcher.py:88 the normalization that re-spells
    # the count with its unit, defaulting a bare number to minutes.
    if stored is None:
        with pytest.raises(M.Invalid):
            M.validate_trigger({'kind': 'schedule', 'every': every}, TYPES)
    else:
        t = M.validate_trigger({'kind': 'schedule', 'every': every}, TYPES)
        assert t == {'kind': 'schedule', 'every': stored} and M.every_s(t) == seconds


@pytest.mark.parametrize('every', [15, None, True, 'x', 'm', '1.5m', '15 mm', '1e2m', '1,5h'],
                         ids=['int', 'missing', 'bool', 'letter', 'unit-only', 'decimal',
                              'unit-not-last', 'exponent', 'comma'])
def test_a_period_that_is_not_a_count_and_a_unit_is_refused(every):
    # matcher.py:85-87 `isinstance(trigger.get('every'), str) and
    # _EVERY.fullmatch(...)` — a non-string never reaches fullmatch (None would
    # raise TypeError), and fullmatch is what rejects '1.5m' / '15 mm' outright.
    with pytest.raises(M.Invalid, match='count and a unit'):
        M.validate_trigger({'kind': 'schedule', 'every': every}, TYPES)


@pytest.mark.parametrize('extra', [{'kind': 'schedule', 'every': '1h', 'type': MODEL_ADDED},
                                   {'kind': 'schedule', 'every': '1h', 'where': {}},
                                   {'kind': 'schedule', 'every': '1h', 'cron': '0 * * * *'}],
                         ids=['type', 'where', 'cron'])
def test_a_schedule_trigger_carries_nothing_but_its_period(extra):
    # matcher.py:82-84 `extra = set(trigger) - {'kind', 'every'}` — a schedule
    # that also names an event type would be a second, unpolled way to fire.
    with pytest.raises(M.Invalid, match='a schedule trigger has no'):
        M.validate_trigger(extra, TYPES)


# ── 6. the loop guard: two counters, or'ed, exact at three (matcher.py:171-174) ──

@pytest.mark.parametrize('recent, suspended', [
    ([], False),
    ([ESCALATED, ESCALATED], False),
    ([ESCALATED, ESCALATED, ESCALATED], True),
    ([LIMITED, LIMITED], False),
    ([LIMITED, LIMITED, LIMITED], True),
    ([ESCALATED, ESCALATED, LIMITED], False),               # 2 + 1: neither counter
    ([ESCALATED, ESCALATED, LIMITED, LIMITED], False),      # 2 + 2, and the counts do not add
    ([ESCALATED, ESCALATED, ESCALATED, LIMITED, LIMITED], True),   # or, not and
    ([LIMITED, LIMITED, LIMITED, ESCALATED, ESCALATED], True),     # the other clause alone
    ([ESCALATED, ESCALATED, LIMITED, LIMITED] + [('SKIPPED', 'no_match')] * 40, False),
    ([('ESCALATED', 'rate_limited')] * 3, True),                    # counted by both sums
    ([('escalated', 'depth_exceeded')] * 3, False),                 # the state name is exact
    ([('SKIPPED', 'Rate_Limited')] * 3, False),                     # so is the reason code
    ([('ESCALATED', 'depth_exceeded'), ('SKIPPED', 'rate_limited'),
      ('MISSION_CREATED', 'allowed')], False),                      # one of each
], ids=['empty', '2-escalated', '3-escalated', '2-limited', '3-limited', '2-plus-1',
        '2-plus-2', '3-plus-2', '3-plus-2-reversed', 'many-unrelated', 'both-reasons',
        'lowercase-state', 'mixed-case-reason', 'one-of-each'])
def test_the_loop_guard_counts_two_reasons_separately_and_suspends_at_exactly_three(
        recent, suspended):
    # matcher.py:173-174 `sum(s == 'ESCALATED' ...) >= SUSPEND_AFTER or
    # sum(c == 'rate_limited' ...) >= SUSPEND_AFTER` — `>` instead of `>=` would
    # let a third escalation through, `and` instead of `or` would need both, and
    # summing the two counters would suspend on 2 + 2.
    assert M.should_suspend(list(recent)) is suspended


def test_the_suspension_rule_needs_no_clock_and_reads_only_the_two_fields_it_uses():
    # matcher.py:171-174 unpacks (state, reason_code) only: WINDOW_S is the
    # caller's job, so should_suspend of an empty window is False and a long
    # window of ordinary runs is False too — it never suspends on its own.
    assert M.should_suspend([]) is False
    assert M.should_suspend([('SKIPPED', 'no_match')] * 200) is False