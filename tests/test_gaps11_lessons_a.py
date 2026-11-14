"""T-1408 · test gaps in claude_sessions/lessons.py extraction, merge and decay
(112-196: extract_lessons, _jaccard, merge_lessons, apply_decay).

Branches, ranked (refusal and drop first, then merge and decay boundaries,
then defaults):

 1. 133-134  a non-dict model result (None, list) yields [].
 2. 142      PREMISE: a non-numeric confidence raises ValueError and nothing
             catches it, so the session scan aborts. Strict xfail.
 3. 136-138  non-dict items and items without a title are skipped.
 4. 136      PREMISE: the cap runs before the filter, so invalid items use up
             the eight slots. Strict xfail.
 5. 139-143  title 80, summary 300, files 4; missing kind is 'decision';
             missing or None confidence is 0.5.
 6. 141      PREMISE: an out-of-enum kind reaches the entity. Strict xfail.
 7. 149-151  _jaccard of two empty texts is 0.0; identical text is 1.0.
 8. 160      auto-approve None disables it; 0 disables it; 0.8 is the default.
 9. 164-171  merge only when Jaccard is strictly above 0.6.
10. 172-179  ids use the batch index; apply_decay keeps pinned lessons,
             non-lessons, a missing last_used, and evicts past the TTL.
"""

import pytest

from claude_sessions import config, lessons, memory

NOW = '2026-11-14T00:00:00+00:00'


@pytest.fixture
def seams(monkeypatch):
    state = {'payload': None, 'settings': {}}
    monkeypatch.setattr(memory, '_claude_json', lambda *a, **k: state['payload'])
    monkeypatch.setattr(lessons, '_transcript_tail', lambda proj, sid: 'USER: fix it')
    monkeypatch.setattr(config, 'load_settings', lambda: dict(state['settings']))
    monkeypatch.setattr(memory, '_iso', lambda: NOW)
    return state


def _extract(state, items):
    state['payload'] = {'lessons': items}
    return lessons.extract_lessons('/proj', '/folder', 'abcdef1234')


def _good(title='Keep', **over):
    item = {'title': title, 'summary': 'usage fetch needs retry-after',
            'kind': 'decision', 'confidence': 0.7, 'files': []}
    item.update(over)
    return item


def test_extract_non_dict_result_is_empty(seams):
    """The model answered with something other than an object: nothing to learn.
    Catches: removing the isinstance guard at lessons.py:133-134."""
    seams['payload'] = None
    assert lessons.extract_lessons('/proj', '/folder', 'abcdef1234') == []
    seams['payload'] = ['not', 'an', 'object']
    assert lessons.extract_lessons('/proj', '/folder', 'abcdef1234') == []


@pytest.mark.xfail(strict=True, reason=(
    "lessons.py:142 float('high') raises ValueError; nothing in extract_lessons, "
    "scan_sessions (lessons.py:228-237) or memory._claude_json catches it, so the "
    "whole session scan aborts and lessons_scanned is never stamped. Reachable on "
    "the fallback JSON path only (--json-schema enforces number)."))
def test_extract_bad_confidence_skips_item_not_session(seams):
    """Expected: a malformed confidence drops or defaults that one item and the
    valid lesson after it is kept. Current: ValueError escapes the call."""
    out = _extract(seams, [_good('Bad', confidence='high'), _good('Good', confidence=0.6)])
    assert 'Good' in [l['title'] for l in out]


def test_extract_skips_non_dict_and_untitled_items(seams):
    """Non-dict items, a missing title and an empty title are all dropped.
    Catches: the filter at lessons.py:137 (removing it or inverting 'not')."""
    out = _extract(seams, ['x', {'summary': 'no title'}, {'title': '', 'summary': 's'},
                           _good('Keep')])
    assert [l['title'] for l in out] == ['Keep']


def test_extract_truncates_and_defaults(seams):
    """Title is cut to 80, summary to 300, files to 4 strings; a missing kind
    becomes 'decision', a missing or None confidence becomes 0.5, a missing
    summary becomes ''. Catches: lessons.py:139-143 truncation and defaults."""
    item = {'title': 'T' * 100, 'files': ['f1', 'f2', 'f3', 'f4', 'f5', 'f6']}
    out = _extract(seams, [item, {'title': 'N', 'summary': 'S' * 400,
                                  'kind': 'preference', 'confidence': None}])
    first, second = out
    assert first['title'] == 'T' * 80
    assert first['summary'] == ''
    assert first['kind'] == 'decision'
    assert first['confidence'] == 0.5
    assert first['files'] == ['f1', 'f2', 'f3', 'f4']
    assert len(second['summary']) == 300
    assert second['kind'] == 'preference'
    assert second['confidence'] == 0.5


@pytest.mark.xfail(strict=True, reason=(
    "lessons.py:136 caps the raw list with [:MAX_LESSONS] before the filter at "
    "lessons.py:137, so eight invalid items leave zero of the two valid ones that "
    "follow. Reachable on the fallback JSON path only."))
def test_extract_cap_counts_only_valid_items(seams):
    """Expected: at most MAX_LESSONS valid lessons, so the two valid items after
    eight invalid ones are returned. Current: the slice keeps only the invalid."""
    items = ['bad'] * 8 + [_good('A'), _good('B')]
    out = _extract(seams, items)
    assert [l['title'] for l in out] == ['A', 'B']


@pytest.mark.xfail(strict=True, reason=(
    "lessons.py:141 copies 'kind' without checking the LESSONS_SCHEMA enum "
    "(lessons.py:95-109); the fallback JSON path does not enforce it, so 'bogus' "
    "reaches the entity."))
def test_extract_unknown_kind_is_coerced(seams):
    """Expected: a kind outside error_fix|decision|correction|preference becomes
    'decision'. Current: it is copied verbatim."""
    out = _extract(seams, [_good('K', kind='bogus')])
    assert out[0]['kind'] == 'decision'


def test_jaccard_empty_and_identical():
    """Both texts with no tokens give 0.0, not ZeroDivisionError; identical text
    gives 1.0; disjoint gives 0.0. Catches: the 'if ta | tb' guard at
    lessons.py:151 and the ratio at lessons.py:150."""
    assert lessons._jaccard('', '') == 0.0
    assert lessons._jaccard('!! --', '   ') == 0.0
    assert lessons._jaccard('retry backoff', 'retry backoff') == 1.0
    assert lessons._jaccard('alpha beta', 'gamma delta') == 0.0


@pytest.mark.parametrize('settings, expected', [
    ({'memory_lessons_autoapprove': None}, 'pending'),
    ({'memory_lessons_autoapprove': 0}, 'pending'),
    ({}, 'approved'),
])
def test_autoapprove_none_disables_auto_approve(seams, settings, expected):
    """An explicit None or 0 turns auto-approve off, while a missing key uses the
    0.8 default. Catches: 'or 0' at lessons.py:160 and the default argument."""
    seams['settings'] = settings
    mem = {'entities': [], 'session_counter': 3}
    lessons.merge_lessons(mem, [{'title': 'L', 'summary': 'lone fact', 'kind': 'decision',
                                 'confidence': 0.95, 'files': []}], 'sid1')
    assert mem['entities'][0]['status'] == expected


def _lesson_entity(summary, confidence=0.5):
    return {'id': 'lesson:old:0', 'name': 'Old', 'type': 'lesson', 'summary': summary,
            'kind': 'decision', 'confidence': confidence, 'status': 'approved',
            'sid': 'old', 'sids': ['old'], 'last_used': 1}


def test_merge_duplicate_is_strict_above_threshold(seams):
    """Jaccard 0.6 exactly is NOT a duplicate: a new entity is added. Jaccard 0.8
    IS: no entity is added, confidence becomes the max, last_used becomes the
    counter and the sid is appended. Catches: the strict '>' at lessons.py:166
    and the merge body at lessons.py:167-170."""
    mem = {'entities': [_lesson_entity('a b c')], 'session_counter': 7}
    equal = {'title': 'T1', 'summary': 'a b c d e', 'kind': 'decision',
             'confidence': 0.9, 'files': []}
    assert lessons.merge_lessons(mem, [equal], 'sidX') == 1
    assert len(mem['entities']) == 2

    mem = {'entities': [_lesson_entity('a b c d', confidence=0.4)], 'session_counter': 7}
    above = {'title': 'T2', 'summary': 'a b c d e', 'kind': 'decision',
             'confidence': 0.9, 'files': []}
    assert lessons.merge_lessons(mem, [above], 'sidY') == 0
    assert len(mem['entities']) == 1
    dup = mem['entities'][0]
    assert dup['confidence'] == 0.9
    assert dup['last_used'] == 7
    assert dup['sids'] == ['old', 'sidY']


def test_merge_ids_use_batch_index(seams):
    """The id is 'lesson:<sid>:<enumerate index>' even when an earlier item
    merged, so the second new lesson is index 1. Catches: the enumerate index
    at lessons.py:172-173."""
    mem = {'entities': [_lesson_entity('a b c d')], 'session_counter': 2}
    new = [_good_merge('a b c d e'), _good_merge('wholly different text here')]
    assert lessons.merge_lessons(mem, new, 'sidZ') == 1
    added = [e for e in mem['entities'] if e['id'].startswith('lesson:sidZ:')]
    assert [e['id'] for e in added] == ['lesson:sidZ:1']


def _good_merge(summary):
    return {'title': 'M', 'summary': summary, 'kind': 'decision', 'confidence': 0.5,
            'files': []}


def test_decay_boundary_is_inclusive_at_ttl(seams):
    """A lesson exactly TTL sessions unused is kept; one more session evicts it.
    Catches: the '<=' at lessons.py:191."""
    mem = {'session_counter': 40, 'entities': [
        dict(_lesson_entity('x'), id='at', last_used=10),
        dict(_lesson_entity('y'), id='over', last_used=9)]}
    removed = lessons.apply_decay(mem, settings={'memory_lessons_ttl': 30})
    assert removed == 1
    assert [e['id'] for e in mem['entities']] == ['at']


def test_decay_keeps_pinned_nonlesson_and_missing_last_used(seams):
    """Pinned lessons, non-lesson entities and a lesson with no last_used are kept
    whatever the counter says. Catches: the early True at lessons.py:189-190 and
    the default at lessons.py:191."""
    mem = {'session_counter': 500, 'entities': [
        dict(_lesson_entity('p'), id='pin', status='pinned', last_used=0),
        {'id': 'fact', 'type': 'fact', 'name': 'F'},
        {'id': 'nolu', 'type': 'lesson', 'status': 'approved', 'name': 'N'}]}
    removed = lessons.apply_decay(mem, settings={'memory_lessons_ttl': 30})
    assert removed == 0
    assert {e['id'] for e in mem['entities']} == {'pin', 'fact', 'nolu'}
