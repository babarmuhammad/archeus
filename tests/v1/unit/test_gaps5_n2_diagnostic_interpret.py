"""The conclusions n2_check.diag_interpret draws from row labels.

Labels come from the real diag_result over a fake host read, so a fixture slip fails in _labels
and never looks like an interpretation defect. Nothing here touches the host: the tripwire turns
filesystem or subprocess calls into failures while diag_interpret runs.
"""

import os

import pytest

from tools.pv20_mxc.native import n2_check as n2

BASELINE = 'baseline creation and workspace write proved'
WRITEFAIL = ('baseline child started, write not proved with its control passing: investigate (3), '
             'inherited cwd and environment versus grants')
EXITONLY = 'baseline exit proved; the write row gives no workspace conclusion'
ALLEXIT = ('all exit rows did not return 37: inconclusive for blanket denial (2); six rows cannot '
           'prove it. Image dependencies, UI initialization and environment remain alternatives')
IMAGE = ('image location or access, cause (1), strongly supported; '
         'loader dependency access still possible')
SYSTEM32 = 'missing System32 access or dependency grant, cause (1), strongly supported'
NOTUSABLE = 'A1 baseline not usable: no conclusion about image or System32 access'
NOBULLET = 'no interpretation bullet matches: '
REFUSED = 'launch refused'
ORDER = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')


def _proved(row, label):
    return '; child start proved by %s (%s)' % (row, label)


def _lay(tmp_path):
    lay = n2.layout(str(tmp_path / 'root'))
    n2.make_dirs(lay)
    return lay


def _ok_files(row):
    return {i.path: i.secret for i in list(row.controls) + [row.done]}


def _look(files):
    return lambda p: files.get(p)


class _Tokens:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return 'T%dZ' % (100000000 + self.n)


def _rows(tmp_path, monkeypatch):
    monkeypatch.setattr(n2, 'new_token', _Tokens())
    return {r.id: r for r in n2.diag_rows(_lay(tmp_path), r'C:\Windows', 'SEED')}


def _files_for(row, goal):
    ok = _ok_files(row)
    if goal == 'control failed':
        files = {k: v for k, v in ok.items() if k != row.controls[0].path}
        files[row.ev] = row.tok if row.kind == 'exit' else 'OBSERVED'
        return files
    if goal == 'no evidence':
        return dict(ok)
    files = dict(ok)
    if row.kind == 'exit':
        if goal == n2.RET_37:
            files[row.ev] = row.tok + '\r\n'
        elif goal == n2.NOT_37:
            files[row.ev] = 'OTHER'
        else:
            raise AssertionError('exit row %s cannot read as %r' % (row.id, goal))
    elif goal == n2.W_OK:
        files[row.child] = row.tok
        files[row.ev] = 'OBSERVED'
    elif goal == n2.W_UNPROVED:
        files[row.ev] = 'OBSERVED'
    elif goal == n2.W_NOT:
        files[row.ev] = 'OTHER'
    else:
        raise AssertionError('write row %s cannot read as %r' % (row.id, goal))
    return files


def _labels(tmp_path, monkeypatch, want):
    rows = _rows(tmp_path, monkeypatch)
    files = {}
    for rid in ORDER:
        if want.get(rid) not in (None, REFUSED):
            files.update(_files_for(rows[rid], want[rid]))
    seen = {}
    for rid in ORDER:
        goal = want.get(rid)
        if goal is None:
            continue
        if goal == REFUSED:
            seen[rid] = REFUSED
            continue
        got = n2.diag_result(rows[rid], _look(files))
        assert got == goal, 'fixture cannot make %s read as %s: it reads as %s' % (rid, goal, got)
        seen[rid] = got
    return seen


HOST_CALLS = ('remove', 'rmdir', 'removedirs', 'makedirs', 'mkdir', 'unlink', 'replace',
              'rename', 'kill', 'spawnv', 'spawnve', 'startfile', 'link', 'symlink')
CHILD_CALLS = ('Popen', 'run', 'call', 'check_call', 'check_output')


def _tree(root):
    seen = []
    for base, dirs, names in os.walk(str(root)):
        for name in sorted(dirs) + sorted(names):
            seen.append(os.path.relpath(os.path.join(base, name), str(root)))
    return sorted(seen)


def _interpret(monkeypatch, tmp_path, labels):
    def boom(*args, **kwargs):
        raise AssertionError('interpretation reached for the host: %r %r' % (args, kwargs))

    with monkeypatch.context() as ctx:
        for name in HOST_CALLS:
            ctx.setattr(n2.os, name, boom, raising=False)
        for name in CHILD_CALLS:
            ctx.setattr(n2.subprocess, name, boom, raising=False)
        before = _tree(tmp_path)
        text = n2.diag_interpret(labels)
        after = _tree(tmp_path)
    assert isinstance(text, str) and text
    assert after == before
    assert 'PASS' not in text and 'FAIL' not in text
    return text


def test_launch_refused_rows_are_named_and_prove_nothing(tmp_path, monkeypatch):
    labels = _labels(tmp_path, monkeypatch, {
        'A1': n2.RET_37, 'A2': n2.W_OK,
        'B1': REFUSED, 'B2': REFUSED,
        'C1': 'no evidence', 'C2': 'control failed'})
    assert labels['B1'] == REFUSED and labels['C1'] == 'no evidence'
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == ('rows not usable (B1, B2, C1, C2): %s%s'
                    % (BASELINE, _proved('A2', n2.W_OK)))
    assert IMAGE not in text and SYSTEM32 not in text


def test_baseline_success_wins_over_granted_successes_and_needs_both_rows(tmp_path, monkeypatch):
    labels = _labels(tmp_path, monkeypatch, {
        'A1': n2.RET_37, 'A2': n2.W_OK,
        'B1': n2.RET_37, 'B2': 'no evidence',
        'C1': n2.RET_37, 'C2': 'control failed'})
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == ('rows not usable (B2, C2): %s%s' % (BASELINE, _proved('A2', n2.W_OK)))
    assert IMAGE not in text and SYSTEM32 not in text

    half = _interpret(monkeypatch, tmp_path, {'A1': n2.RET_37, 'B1': n2.RET_37})
    assert half == EXITONLY
    assert BASELINE not in half


def test_baseline_write_failure_blames_inherited_state_not_blanket_denial(tmp_path, monkeypatch):
    labels = _labels(tmp_path, monkeypatch, {
        'A1': n2.RET_37, 'A2': n2.W_UNPROVED,
        'B1': 'control failed', 'B2': 'no evidence',
        'C1': 'no evidence', 'C2': 'no evidence'})
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == ('rows not usable (B1, B2, C1, C2): %s%s'
                    % (WRITEFAIL, _proved('A2', n2.W_UNPROVED)))
    assert 'inconclusive for blanket denial' not in text


def test_all_available_exits_failing_stays_inconclusive(tmp_path, monkeypatch):
    labels = _labels(tmp_path, monkeypatch, {
        'A1': n2.NOT_37, 'B1': n2.NOT_37, 'C1': n2.NOT_37,
        'A2': 'no evidence', 'B2': REFUSED, 'C2': 'control failed'})
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == 'rows not usable (A2, B2, C2): %s' % ALLEXIT
    assert 'proved' not in text and 'strongly supported' not in text


def test_unusable_image_and_system32_rows_name_both_cause_clauses_in_order(tmp_path, monkeypatch):
    labels = _labels(tmp_path, monkeypatch, {
        'A1': n2.NOT_37,
        'B1': n2.RET_37, 'B2': n2.W_OK,
        'C1': n2.RET_37, 'C2': n2.W_OK})
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == ('%s; %s%s%s' % (IMAGE, SYSTEM32,
                                    _proved('B2', n2.W_OK), _proved('C2', n2.W_OK)))
    assert text.index('image location') < text.index('missing System32')
    assert _interpret(monkeypatch, tmp_path, dict(labels)) == text


@pytest.mark.parametrize('a1', [REFUSED, 'control failed'])
def test_a_void_baseline_with_a_granted_row_running_gives_no_cause_clause(
        tmp_path, monkeypatch, a1):
    only_c = _interpret(monkeypatch, tmp_path, {'A1': a1, 'C1': n2.RET_37})
    assert only_c == 'rows not usable (A1): %s' % NOTUSABLE
    assert IMAGE not in only_c


def test_write_only_labels_cannot_reach_the_all_exit_failed_bullet(tmp_path, monkeypatch):
    labels = _labels(tmp_path, monkeypatch, {'A2': n2.W_OK, 'B2': n2.W_OK, 'C2': n2.W_OK})
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == (NOBULLET + 'A2=%s, B2=%s, C2=%s' % ((n2.W_OK,) * 3)
                    + _proved('A2', n2.W_OK) + _proved('B2', n2.W_OK) + _proved('C2', n2.W_OK))
    assert 'all exit rows' not in text
    assert 'inconclusive for blanket denial' not in text


def test_every_row_unusable_names_every_id_and_claims_nothing(tmp_path, monkeypatch):
    labels = _labels(tmp_path, monkeypatch, {
        'A1': 'control failed', 'A2': 'no evidence',
        'B1': REFUSED, 'B2': 'control failed',
        'C1': 'no evidence', 'C2': REFUSED})
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == 'rows not usable (A1, A2, B1, B2, C1, C2): %s' % NOBULLET
    assert 'proved' not in text and 'inconclusive for blanket denial' not in text


def test_no_labels_at_all_returns_the_bare_fallback_and_touches_nothing(tmp_path, monkeypatch):
    labels = {}
    text = _interpret(monkeypatch, tmp_path, labels)
    assert text == NOBULLET
    assert labels == {}
    assert 'rows not usable' not in text


@pytest.mark.parametrize('near', ['returned 37?', 'returned 37 ', 'RETURNED 37',
                                  'returned 37 (unverified)', 'returned 370'])
def test_a_label_that_only_resembles_returned_37_is_never_positive_evidence(near, tmp_path,
                                                                            monkeypatch):
    text = _interpret(monkeypatch, tmp_path, {'A1': near, 'B1': 'returned 37 (probably)',
                                              'C1': near + 'x'})
    assert text == ALLEXIT
    assert IMAGE not in text and SYSTEM32 not in text
    assert BASELINE not in text
    listing = _interpret(monkeypatch, tmp_path, {'A2': near})
    assert listing == NOBULLET + 'A2=%s' % near


def test_the_same_findings_read_identically_in_any_insertion_order(tmp_path, monkeypatch):
    sets = ({'A1': n2.RET_37, 'A2': n2.W_OK, 'B1': REFUSED, 'B2': REFUSED,
             'C1': n2.NOT_37, 'C2': n2.W_UNPROVED},
            {'A1': n2.NOT_37, 'B1': n2.RET_37, 'B2': n2.W_OK,
             'C1': 'no evidence', 'C2': REFUSED},
            {'A1': 'no evidence', 'A2': n2.W_OK, 'B2': n2.W_NOT, 'C2': 'control failed'})
    for want in sets:
        labels = _labels(tmp_path, monkeypatch, want)
        keys = list(labels)
        reverse = {k: labels[k] for k in sorted(keys, reverse=True)}
        rotate = {k: labels[k] for k in keys[2:] + keys[:2]}
        forward = _interpret(monkeypatch, tmp_path, labels)
        assert _interpret(monkeypatch, tmp_path, reverse) == forward
        assert _interpret(monkeypatch, tmp_path, rotate) == forward
        assert forward.startswith('rows not usable (')
