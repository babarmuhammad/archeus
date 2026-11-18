"""Evidence precedence and false-positive resistance of n2_check.diag_result.

Nothing here launches a process, loads a native library, opens a real handle or reads a real
profile: the host lookup is a fake mapping, and n2.look_at is sabotaged so any real read fails.
"""

import os

import pytest

from tools.pv20_mxc.native import n2_check as n2

SYSTEMROOT = r'C:\Windows'
SEED = 'SEED'


def _lay(tmp_path):
    lay = n2.layout(str(tmp_path / 'root'))
    n2.make_dirs(lay)
    return lay


def _ok_files(row):
    return {i.path: i.secret for i in row.controls + [row.done]}


def _look(files):
    return lambda p: files.get(p)


class HostRead(Exception):
    pass


class Look:
    def __init__(self, files, raises=()):
        self._files = dict(files)
        self._raises = list(raises)
        self.asked = []

    def __call__(self, path):
        self.asked.append(path)
        if path in self._raises:
            raise HostRead('lookup refused for %r' % (path,))
        return self._files.get(path)


class Tokens:
    def __init__(self):
        self.next = 100000
        self.step = 7

    def __call__(self):
        tok = 'T%dZ' % self.next
        self.next += self.step
        return tok


@pytest.fixture
def lay(tmp_path):
    return _lay(tmp_path)


@pytest.fixture
def rows(lay, monkeypatch):
    monkeypatch.setattr(n2, 'new_token', Tokens())
    return {r.id: r for r in n2.diag_rows(lay, SYSTEMROOT, SEED)}


@pytest.fixture
def no_disk_reads(monkeypatch):
    seen = []

    def sabotage(path):
        seen.append(path)
        raise HostRead('look_at must not be called for %r' % (path,))

    monkeypatch.setattr(n2, 'look_at', sabotage)
    return seen


def _own_paths(row):
    return {row.ev, row.child, row.done.path} | {i.path for i in row.controls}


def _assert_no_side_effects(lay, row, no_disk_reads):
    assert os.listdir(lay['p']['state']) == []
    for path in _own_paths(row):
        if path is not None:
            assert not os.path.lexists(path)
    assert no_disk_reads == []


def test_control_write_holding_the_wrong_text_overrides_an_exact_child_token(
        rows, lay, no_disk_reads):
    row = rows['A2']
    ctl_w, ctl_r = row.controls
    ok = _ok_files(row)
    ok[ctl_w.path] = ctl_r.secret
    files = {**ok, row.child: row.tok, row.ev: 'OBSERVED'}
    assert files[ctl_r.path] == ctl_r.secret
    assert n2.diag_result(row, _look(files)) == 'control failed'
    _assert_no_side_effects(lay, row, no_disk_reads)


@pytest.mark.parametrize('marker', ['<dir>', '<link>'])
def test_done_marker_that_is_a_directory_or_link_never_leaves_a_row_with_evidence(
        rows, lay, no_disk_reads, marker):
    write_row = rows['A2']
    files = {**_ok_files(write_row), write_row.child: write_row.tok,
             write_row.ev: 'OBSERVED', write_row.done.path: marker}
    assert n2.diag_result(write_row, _look(files)) == 'no evidence'
    exit_row = rows['A1']
    files = {**_ok_files(exit_row), exit_row.ev: exit_row.tok, exit_row.done.path: marker}
    assert n2.diag_result(exit_row, _look(files)) == 'no evidence'
    _assert_no_side_effects(lay, write_row, no_disk_reads)


def test_a_failed_control_or_done_marker_short_circuits_the_later_reads(rows, lay,
                                                                        no_disk_reads):
    row = rows['A2']
    ctl_w, ctl_r = row.controls
    planted = {**_ok_files(row), row.child: row.tok, row.ev: 'OBSERVED'}
    assert n2.diag_result(row, Look(planted)) == n2.W_OK
    failed_control = Look({k: v for k, v in planted.items() if k != ctl_w.path})
    assert n2.diag_result(row, failed_control) == 'control failed'
    assert failed_control.asked == [ctl_w.path]
    failed_done = Look({k: v for k, v in planted.items() if k != row.done.path})
    assert n2.diag_result(row, failed_done) == 'no evidence'
    for probe in (failed_control, failed_done):
        assert set(probe.asked) <= _own_paths(row)
        assert row.child not in probe.asked
    assert row.ev not in failed_done.asked
    _assert_no_side_effects(lay, row, no_disk_reads)


@pytest.mark.parametrize('shape', ['dir', 'link', 'bytes', 'int', 'empty'])
def test_exit_evidence_that_is_not_a_plain_string_is_no_evidence(rows, lay, no_disk_reads,
                                                                 shape):
    row = rows['A1']
    seen = {'dir': '<dir>', 'link': '<link>', 'bytes': row.tok.encode('utf-8'),
            'int': 42, 'empty': ''}[shape]
    files = {**_ok_files(row), row.ev: seen}
    assert n2.diag_result(row, _look(files)) == 'no evidence'
    _assert_no_side_effects(lay, row, no_disk_reads)


@pytest.mark.parametrize('noise,expect', [
    ('prefix', 'no evidence'),
    ('suffix', 'no evidence'),
    ('padded', 'no evidence'),
    ('case_flip', 'no evidence'),
    ('truncated', 'no evidence'),
    ('other_row_token', 'no evidence'),
    ('whitespace_only', n2.RET_37),
])
def test_only_the_exact_token_proves_the_child_ran_and_padding_must_be_whitespace(
        rows, lay, no_disk_reads, noise, expect):
    row, foreign = rows['A1'], rows['B1']
    wrap = {'prefix': lambda t, f: 'X' + t,
            'suffix': lambda t, f: t + 'X',
            'padded': lambda t, f: 'X' + t + 'Y',
            'case_flip': lambda t, f: t.lower(),
            'truncated': lambda t, f: t[:-1],
            'other_row_token': lambda t, f: f,
            'whitespace_only': lambda t, f: ' \t' + t + ' \r\n'}[noise]
    seen = wrap(row.tok, foreign.tok)
    assert foreign.tok != row.tok
    assert (seen.strip() == row.tok) is (expect == n2.RET_37)
    files = {**_ok_files(row), row.ev: seen}
    assert n2.diag_result(row, _look(files)) == expect
    _assert_no_side_effects(lay, row, no_disk_reads)


@pytest.mark.parametrize('seen,expect', [
    ('OTHER', n2.NOT_37),
    ('  OTHER \r\n', n2.NOT_37),
    ('OTHER extra', 'no evidence'),
    ('OTHER\nOTHER', 'no evidence'),
    ('OTHERS', 'no evidence'),
    ('other', 'no evidence'),
])
def test_only_the_bare_other_marker_says_the_child_did_not_run(rows, lay, no_disk_reads,
                                                               seen, expect):
    row = rows['A1']
    files = {**_ok_files(row), row.ev: seen}
    assert n2.diag_result(row, _look(files)) == expect
    _assert_no_side_effects(lay, row, no_disk_reads)


def test_a_write_row_needs_the_observed_marker_before_its_child_token_is_read(
        rows, lay, no_disk_reads):
    row = rows['A2']
    files = {**_ok_files(row), row.child: row.tok}
    look = Look(files)
    assert n2.diag_result(row, look) == 'no evidence'
    assert row.child not in look.asked
    _assert_no_side_effects(lay, row, no_disk_reads)


@pytest.mark.parametrize('marker', ['<dir>', '<link>', 'OBSERVEDX', ' OBSERVED X', 'observed'])
def test_a_wrong_child_token_with_a_non_observed_parent_marker_is_no_evidence(
        rows, lay, no_disk_reads, marker):
    row, foreign = rows['A2'], rows['B2']
    assert row.tok not in foreign.tok
    files = {**_ok_files(row), row.child: foreign.tok, row.ev: marker}
    assert n2.diag_result(row, _look(files)) == 'no evidence'
    _assert_no_side_effects(lay, row, no_disk_reads)


def test_a_wrong_child_token_behind_an_observed_marker_is_never_a_proved_write(
        rows, lay, no_disk_reads):
    row, foreign = rows['A2'], rows['C1']
    files = {**_ok_files(row), row.child: foreign.tok, row.ev: 'OBSERVED'}
    label = n2.diag_result(row, _look(files))
    assert label == n2.W_UNPROVED
    assert label != n2.W_OK
    _assert_no_side_effects(lay, row, no_disk_reads)


def test_other_marker_on_a_write_row_reads_as_the_child_did_not_return(rows, lay,
                                                                       no_disk_reads):
    row = rows['A2']
    files = {**_ok_files(row), row.child: row.tok, row.ev: 'OTHER'}
    assert n2.diag_result(row, _look(files)) == n2.W_NOT
    _assert_no_side_effects(lay, row, no_disk_reads)


@pytest.mark.parametrize('failing', ['control-write', 'control-read', 'done'])
def test_a_lookup_that_raises_while_judging_gates_propagates_without_a_fallback_read(
        rows, lay, no_disk_reads, failing):
    row = rows['A1']
    ctl_w, ctl_r = row.controls
    gate = {'control-write': ctl_w.path, 'control-read': ctl_r.path,
            'done': row.done.path}[failing]
    files = {**_ok_files(row), row.ev: row.tok}
    look = Look(files, raises=[gate])
    with pytest.raises(HostRead):
        n2.diag_result(row, look)
    assert look.asked[-1] == gate
    assert row.child not in look.asked
    _assert_no_side_effects(lay, row, no_disk_reads)
