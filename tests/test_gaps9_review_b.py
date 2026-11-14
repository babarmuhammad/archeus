"""T-1358: claude_sessions/review.py lines 124-198 at tip 10d688c0 (parse_findings,
_sev_key, run_review: empty-diff gate, model-result shape, confidence gate and
severity sort). T-1357 owns lines 29-80 in test_gaps9_review_a.py; not repeated.

Selected candidates, not measured coverage. Ranked denial/fail-closed first,
then boundaries, then error paths:

1.  191        PREMISE, strict xfail: a non-numeric confidence ('high') raises
               ValueError out of run_review instead of the finding being dropped
2.  191        confidence equal to min_confidence is kept; one below is dropped
3.  184-189    a _claude_json result that is neither dict nor list gives
               findings [] and raw_count 0, and is not treated as a dict
4.  91         non-dict items are dropped and do not count toward raw_count
5.  145-146    parse_findings drops non-dict items from a list
6.  162-163    min_confidence None uses review_min_confidence (80 when absent);
               an explicit 0 setting stays 0; an explicit argument wins
7.  166-168    a whitespace-only diff returns empty True and makes no model call
8.  130-133    a fenced json block is preferred over bracketed prose around it
9.  135-143    when the bracket slice does not parse, the {findings}/{issues}
               wrapper is read through memory._parse_json
10. 149-151,192 sort by severity rank, then confidence descending; unknown
               severity sorts last
11. 172-181    the silent flag is reset in finally when _claude_json raises

Seams: config.load_settings (run_review imports it at call time), review.get_diff,
review.gather_guidance and memory._claude_json are replaced; no model call, no
subprocess, no real home or settings. Synthetic values only.
"""

import pytest

from claude_sessions import config, memory, review


def _install(monkeypatch, reply, diff='diff --git a b\n+changed', settings=None):
    calls = []

    def fake_claude_json(prompt, cwd, schema, **kw):
        calls.append(kw)
        if callable(reply):
            return reply()
        return reply

    monkeypatch.setattr(review, 'get_diff', lambda *a, **k: diff)
    monkeypatch.setattr(review, 'gather_guidance', lambda *a, **k: '')
    monkeypatch.setattr(config, 'load_settings', lambda: dict(settings or {}))
    monkeypatch.setattr(memory, '_claude_json', fake_claude_json)
    return calls


def _f(summary, confidence, severity='high', **extra):
    d = {'file': 'a.py', 'line': 1, 'confidence': confidence,
         'severity': severity, 'summary': summary}
    d.update(extra)
    return d


@pytest.mark.xfail(strict=True, reason="claude_sessions/review.py:191 int(f.get('confidence', 0) or 0) raises ValueError on a non-numeric confidence from the unvalidated _parse_json fallback, instead of dropping the finding")
def test_non_numeric_confidence_is_dropped_not_raised(monkeypatch, tmp_path):
    _install(monkeypatch, {'findings': [_f('bad', 'high'), _f('real', 95)]})
    r = review.run_review(str(tmp_path), silent=True)
    assert [f['summary'] for f in r['findings']] == ['real']


def test_confidence_gate_keeps_equal_to_minimum_and_drops_below(monkeypatch, tmp_path):
    _install(monkeypatch, {'findings': [_f('below', 79), _f('equal', 80), _f('above', 81)]},
             settings={'review_min_confidence': 80})
    r = review.run_review(str(tmp_path), silent=True)
    assert [f['summary'] for f in r['findings']] == ['above', 'equal']
    assert r['raw_count'] == 3 and r['min'] == 80


@pytest.mark.parametrize('reply', [None, 'a plain string', 7])
def test_a_model_result_that_is_not_object_or_list_gives_no_findings(monkeypatch, tmp_path, reply):
    _install(monkeypatch, reply)
    r = review.run_review(str(tmp_path), silent=True)
    assert r['findings'] == [] and r['raw_count'] == 0 and r['empty'] is False


def test_non_dict_items_are_dropped_and_not_counted(monkeypatch, tmp_path):
    _install(monkeypatch, {'findings': [1, 'x', None, _f('ok', 90)]})
    r = review.run_review(str(tmp_path), silent=True)
    assert [f['summary'] for f in r['findings']] == ['ok']
    assert r['raw_count'] == 1


def test_parse_findings_keeps_only_dict_items_from_a_list():
    out = '[1, "x", null, {"file":"a","line":1,"confidence":90,"severity":"low","summary":"ok"}]'
    got = review.parse_findings(out)
    assert [f['summary'] for f in got] == ['ok']


def test_min_confidence_default_is_80_and_an_explicit_zero_setting_stays_zero(monkeypatch, tmp_path):
    _install(monkeypatch, {'findings': [_f('low', 79), _f('ok', 80)]}, settings={})
    r = review.run_review(str(tmp_path), silent=True)
    assert r['min'] == 80 and [f['summary'] for f in r['findings']] == ['ok']

    _install(monkeypatch, {'findings': [_f('zero', 0)]},
             settings={'review_min_confidence': 0})
    r = review.run_review(str(tmp_path), silent=True)
    assert r['min'] == 0 and [f['summary'] for f in r['findings']] == ['zero']


def test_an_explicit_min_confidence_argument_overrides_the_setting(monkeypatch, tmp_path):
    _install(monkeypatch, {'findings': [_f('zero', 0)]},
             settings={'review_min_confidence': 80})
    r = review.run_review(str(tmp_path), min_confidence=0, silent=True)
    assert r['min'] == 0 and [f['summary'] for f in r['findings']] == ['zero']


def test_a_whitespace_only_diff_is_empty_and_makes_no_model_call(monkeypatch, tmp_path):
    calls = _install(monkeypatch, {'findings': [_f('never', 99)]}, diff=' \n\t\n')
    r = review.run_review(str(tmp_path), silent=True)
    assert r['empty'] is True and r['findings'] == [] and r['raw_count'] == 0
    assert calls == []


def test_a_fenced_block_wins_over_bracketed_prose_around_it():
    text = ('See [note] first.\n```json\n'
            '[{"file":"a","line":1,"confidence":90,"severity":"low","summary":"fenced"}]'
            '\n```\nand [more] later.')
    got = review.parse_findings(text)
    assert [f['summary'] for f in got] == ['fenced']


@pytest.mark.parametrize('key', ['findings', 'issues'])
def test_wrapper_is_read_when_the_bracket_slice_does_not_parse(key):
    text = ('{"note": "[see below", "%s": [{"file":"a","line":2,'
            '"confidence":85,"severity":"medium","summary":"wrapped"}]}' % key)
    got = review.parse_findings(text)
    assert [f['summary'] for f in got] == ['wrapped']


def test_sort_breaks_confidence_ties_and_puts_unknown_severity_last(monkeypatch, tmp_path):
    findings = [_f('low90', 90, severity='low'),
                _f('high80', 80, severity='high'),
                _f('high95', 95, severity='high'),
                _f('weird99', 99, severity='urgent'),
                _f('weird90', 90, severity=None)]
    _install(monkeypatch, {'findings': findings})
    r = review.run_review(str(tmp_path), silent=True)
    assert [f['summary'] for f in r['findings']] == [
        'high95', 'high80', 'low90', 'weird99', 'weird90']


def test_silent_flag_is_set_during_the_call_and_cleared_when_it_raises(monkeypatch, tmp_path):
    seen = []

    def boom():
        seen.append(getattr(memory._tls, 'silent', False))
        raise RuntimeError('model call failed')

    _install(monkeypatch, boom)
    with pytest.raises(RuntimeError):
        review.run_review(str(tmp_path), silent=True)
    assert seen == [True]
    assert getattr(memory._tls, 'silent', False) is False
