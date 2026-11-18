
import os
import stat
import subprocess

import pytest

from tools.pv20_mxc.native import n2_check as n2

CMD = r'C:\Windows\System32\cmd.exe'
STATE = r'D:\fx\p\state'
SYSTEMROOT = r'C:\Windows'
SEED = 'SYNTH-SEED-9f3'


def _lay(tmp_path):
    return n2.layout(str(tmp_path / 'root'))


def _ok_files(row):
    return {i.path: i.secret for i in row.controls + [row.done]}


def _look(files):
    return lambda p: files.get(p)


def _rows(tmp_path):
    return {r.id: r for r in n2.diag_rows(_lay(tmp_path), SYSTEMROOT, SEED)}


def _ids(rows):
    return [r.id for r in rows]


def _synth_row(rid, flag):
    return n2.Row(rid, 'exit', CMD, flag, None, None, 'chain-' + rid, 'ev-' + rid, None,
                  'T100000001Z', [], None)


_LISTDIR = os.listdir


class _Sealed:

    def __init__(self, real, allowed, touched, label):
        self._real, self._allowed, self._touched, self._label = real, frozenset(allowed), \
            touched, label

    def __getattr__(self, name):
        if name in self._allowed:
            return getattr(self._real, name)
        touched, label = self._touched, self._label

        def refusal(*a, **kw):
            touched.append('%s.%s' % (label, name))
            raise AssertionError('the pure builder called %s.%s' % (label, name))

        return refusal


def _no_privileged_calls(monkeypatch):
    touched = []
    monkeypatch.setattr(n2, 'os', _Sealed(os, ('path',), touched, 'os'))
    monkeypatch.setattr(n2, 'subprocess', _Sealed(subprocess, (), touched, 'subprocess'))
    return touched


class _Stat:

    def __init__(self, mode, attrs=None):
        self.st_mode = mode
        if attrs is not None:
            self.st_file_attributes = attrs


def test_plain_is_fail_closed_for_links_reparse_points_and_the_wrong_kind():
    reg = stat.S_IFREG | 0o644
    dir_ = stat.S_IFDIR | 0o755
    assert n2.plain(_Stat(reg), stat.S_ISREG)
    assert n2.plain(_Stat(dir_), stat.S_ISDIR)
    assert not n2.plain(_Stat(stat.S_IFLNK | 0o644), stat.S_ISLNK)
    assert not n2.plain(_Stat(stat.S_IFLNK | 0o644), stat.S_ISREG)
    assert not n2.plain(_Stat(reg, n2.REPARSE), stat.S_ISREG)
    assert not n2.plain(_Stat(dir_, n2.REPARSE), stat.S_ISDIR)
    assert not n2.plain(_Stat(reg, n2.REPARSE | 0x80 | 0x20), stat.S_ISREG)
    assert n2.plain(_Stat(reg, 0x80 | 0x20), stat.S_ISREG)
    assert n2.plain(_Stat(reg, 0), stat.S_ISREG)
    assert n2.plain(_Stat(reg), stat.S_ISREG)
    assert not n2.plain(_Stat(reg), stat.S_ISDIR)
    assert not n2.plain(_Stat(dir_), stat.S_ISREG)


def test_gate_with_system32_flag_alone_runs_a_and_c_and_still_skips_b(tmp_path):
    lay = _lay(tmp_path)
    rows = n2.diag_rows(lay, SYSTEMROOT, SEED)
    run, skipped = n2.diag_gate(rows, {n2.SYSTEM_FLAG})
    assert _ids(run) == ['A1', 'A2', 'C1', 'C2']
    assert _ids(skipped) == ['B1', 'B2']
    assert all(r.flag == n2.IMAGE_FLAG for r in skipped)
    toolchain = os.path.join(lay['root'], 'toolchain')
    assert all(r.exe.startswith(toolchain) for r in skipped)
    assert not any(toolchain in r.chain for r in run)
    assert [r.id for r in run if r.flag is None] == ['A1', 'A2']
    run, skipped = n2.diag_gate(rows, {n2.IMAGE_FLAG})
    assert _ids(run) == ['A1', 'A2', 'B1', 'B2'] and _ids(skipped) == ['C1', 'C2']
    assert all(r.flag == n2.SYSTEM_FLAG for r in skipped)
    run, skipped = n2.diag_gate(rows, set())
    assert _ids(run) == ['A1', 'A2'] and _ids(skipped) == ['B1', 'B2', 'C1', 'C2']


def test_gate_uses_exact_flag_membership_and_partitions_the_input_in_order():
    granted = [_synth_row('C2', n2.SYSTEM_FLAG), _synth_row('A1', None),
               _synth_row('B2', n2.IMAGE_FLAG), _synth_row('A2', None),
               _synth_row('B1', n2.IMAGE_FLAG), _synth_row('C1', n2.SYSTEM_FLAG)]
    run, skipped = n2.diag_gate(granted, {n2.IMAGE_FLAG})
    assert _ids(run) == ['A1', 'B2', 'A2', 'B1']
    assert _ids(skipped) == ['C2', 'C1']
    assert all(any(r is x for x in granted) for r in run + skipped)
    assert not any(r is s for r in run for s in skipped)
    assert sorted(id(r) for r in run + skipped) == sorted(id(r) for r in granted)
    near = (n2.IMAGE_FLAG, n2.IMAGE_FLAG, n2.SYSTEM_FLAG + ' ', ' ' + n2.SYSTEM_FLAG,
            n2.SYSTEM_FLAG.upper(), '--allow-system32', n2.SYSTEM_FLAG.replace('-', ''),
            n2.IMAGE_FLAG + '-extra', '', n2.DIAG, 'x')
    run, skipped = n2.diag_gate(granted, near)
    assert _ids(run) == ['A1', 'B2', 'A2', 'B1']
    assert _ids(skipped) == ['C2', 'C1']
    run, skipped = n2.diag_gate(granted, near + (n2.SYSTEM_FLAG,))
    assert _ids(run) == _ids(granted) and skipped == []
    run, skipped = n2.diag_gate(granted, ())
    assert _ids(run) == ['A1', 'A2'] and _ids(skipped) == ['C2', 'B2', 'B1', 'C1']
    solo = [_synth_row('B1', n2.IMAGE_FLAG), _synth_row('C1', n2.SYSTEM_FLAG)]
    assert _ids(n2.diag_gate(solo, {n2.IMAGE_FLAG})[0]) == ['B1']
    assert _ids(n2.diag_gate(solo, {n2.SYSTEM_FLAG})[1]) == ['B1']


def test_gate_over_no_rows_returns_two_empty_lists_without_layout_or_launch(tmp_path):
    for flags in (set(), {n2.DIAG}, {n2.DIAG, n2.IMAGE_FLAG, n2.SYSTEM_FLAG}):
        run, skipped = n2.diag_gate([], flags)
        assert run == [] and skipped == []
        assert isinstance(run, list) and isinstance(skipped, list)
        assert run is not skipped
    rows = n2.diag_rows(_lay(tmp_path), SYSTEMROOT, SEED)
    before = list(rows)
    n2.diag_gate(rows, {n2.IMAGE_FLAG})
    n2.diag_gate([], set())
    assert rows == before


def test_write_chain_sends_the_token_to_the_child_and_observed_to_the_evidence(tmp_path):
    rows = _rows(tmp_path)
    for rid in ('A2', 'B2', 'C2'):
        r = rows[rid]
        quoted = r.chain.split('"')
        assert quoted[0] == r.exe + ' /d /c '
        assert quoted[1] == 'echo ' + r.tok + '>' + r.child + ' & exit /b 41'
        assert quoted[2] == (' & (if errorlevel 42 (echo OTHER) else (if errorlevel 41 (echo OBSERVED) '
                             'else (echo OTHER)))>' + r.ev)
        assert r.chain.count('"') == 2 and r.chain.count('>') == 2
        assert 'OBSERVED' not in quoted[1] and r.ev not in quoted[1]
        assert r.tok not in quoted[2] and r.child not in quoted[2]
        pair = rows[rid[0] + '1']
        assert pair.kind == 'exit' and pair.child is None and pair.ev != r.child
    chains = [r.chain for r in rows.values()]
    for r in rows.values():
        assert sum(c.count(r.tok) for c in chains) == 1


def test_exit_chain_tests_errorlevel_38_before_37_and_redirects_only_to_evidence(tmp_path):
    rows = _rows(tmp_path)
    for rid in ('A1', 'B1', 'C1'):
        r = rows[rid]
        assert r.chain.startswith(r.exe + ' /d /c exit /b 37 & (if errorlevel 38 (echo OTHER) ')
        assert r.chain.index('errorlevel 38') < r.chain.index('errorlevel 37')
        after = r.chain[r.chain.index('errorlevel 37'):]
        assert after.startswith('errorlevel 37 (echo ' + r.tok + ') else (echo OTHER')
        head = r.chain[r.chain.index('errorlevel 38'):r.chain.index('errorlevel 37')]
        assert head.startswith('errorlevel 38 (echo OTHER)') and r.tok not in head
        assert r.chain.count('errorlevel ') == 2 and r.chain.count('OTHER') == 2
        assert r.chain.endswith('>' + r.ev) and r.chain.count('>') == 1
        assert '"' not in r.chain and r.chain.count('&') == 1
        assert rows[rid[0] + '2'].child not in r.chain


def test_write_rows_own_a_distinct_child_path_and_exit_rows_have_none(tmp_path):
    lay = _lay(tmp_path)
    rows = n2.diag_rows(lay, SYSTEMROOT, SEED)
    w = lay['p']['state']
    children = []
    for r in rows:
        low = r.id.lower()
        assert r.ev == os.path.join(w, low + '.txt')
        assert r.done.path == os.path.join(w, 'done_' + low + '.txt')
        if r.kind == 'write':
            assert r.child == os.path.join(w, low + '-child.txt')
            children.append(r.child)
        else:
            assert r.child is None
        assert r.child != r.ev and r.done.path not in (r.ev, r.child)
    assert sorted(children) == [os.path.join(w, c + '-child.txt') for c in ('a2', 'b2', 'c2')]
    paths = [r.ev for r in rows] + children + [i.path for r in rows for i in
                                               list(r.controls) + [r.done]]
    assert len(paths) == len(set(paths)) == 27
    for r in [x for x in rows if x.kind == 'exit']:
        assert not any(c in r.chain for c in children)


def test_one_fresh_token_per_row_and_no_row_can_carry_another_rows_token(monkeypatch, tmp_path):
    issued = []

    def fake_token():
        issued.append('T%09dZ' % len(issued))
        return issued[-1]

    monkeypatch.setattr(n2, 'new_token', fake_token)
    rows = n2.diag_rows(_lay(tmp_path), SYSTEMROOT, SEED)
    assert len(issued) == 18 and len(set(issued)) == 18
    assert [r.tok for r in rows] == issued[0::3]
    texts = [r.chain for r in rows] + [i.cmd for r in rows for i in list(r.controls) + [r.done]]
    for r in rows:
        assert r.tok in r.chain and r.chain.count(r.tok) == 1
        assert sum(t.count(r.tok) for t in texts) == 1
        assert r.tok not in (r.controls[0].secret, r.controls[1].secret, r.done.secret)
        assert r.tok not in (r.ev, r.child or r.ev)
        assert r.controls[0].secret in issued and r.done.secret in issued
    assert len({r.tok for r in rows}) == 6


def test_controls_carry_the_supplied_seed_and_the_builder_touches_no_filesystem(tmp_path,
                                                                                monkeypatch):
    touched = _no_privileged_calls(monkeypatch)
    lay = _lay(tmp_path)
    rows = n2.diag_rows(lay, SYSTEMROOT, SEED)
    assert touched == []
    assert _LISTDIR(str(tmp_path)) == []
    w = lay['p']['state']
    for r in rows:
        low = r.id.lower()
        cw, cr = r.controls
        assert [i.label for i in r.controls] + [r.done.label] == ['control-write',
                                                                  'control-read', 'done']
        assert (cw.kind, cr.kind, r.done.kind) == ('write_ok', 'read_ok', 'write_ok')
        assert cw.path == os.path.join(w, 'ctl_w_' + low + '.txt')
        assert cr.path == os.path.join(w, 'ctl_r_' + low + '.txt')
        assert cw.cmd == 'echo %s>%s' % (cw.secret, cw.path) and cw.secret not in (None, SEED)
        assert cr.secret == SEED
        assert cr.cmd == 'type %s>%s' % (os.path.join(w, 'seed.txt'), cr.path)
        assert r.done.path == os.path.join(w, 'done_' + low + '.txt')
        assert r.done.secret not in (None, SEED)
        assert len({r.done.path, cw.path, cr.path, r.ev, r.child}) == 5
    assert len({r.controls[1].path for r in rows}) == 6
    assert len({r.done.path for r in rows}) == 6
    a = rows[0]
    items = list(a.controls) + [a.done]
    assert n2.judge(items, _look(_ok_files(a))) is None
    assert n2.judge(items, _look({**_ok_files(a), a.controls[1].path: 'OTHER'})) == \
        ('control', 'control-read')
    assert n2.judge(items, _look({})) == ('control', 'done')


def test_diag_line_accepts_exactly_chain_max_and_refuses_one_more_even_with_inner_quotes():
    body = '"a" & b>c %d'
    chain = body + 'q' * (n2.CHAIN_MAX - len(body))
    assert len(chain) == n2.CHAIN_MAX and '"' in chain and '&' in chain and '>' in chain
    line = n2.diag_line(CMD, chain)
    assert line == CMD + ' /d /s /c "' + chain + '"'
    assert '\\"' not in line and line.count('"') == chain.count('"') + 2
    assert line.count('/d /s /c ') == 1 and line.endswith(chain + '"')
    assert line[len(CMD):].count(CMD) == 0
    with pytest.raises(ValueError):
        n2.diag_line(CMD, chain + 'q')
    with pytest.raises(ValueError):
        n2.diag_line(CMD, 'x' * (n2.CHAIN_MAX + 1))
    real = n2.write_chain(CMD, 'T123456789Z', STATE + r'\a2-child.txt', STATE + r'\a2.txt')
    assert n2.diag_line(CMD, real) == CMD + ' /d /s /c "' + real + '"'
    with pytest.raises(ValueError):
        n2.diag_line(CMD, real + 'y' * (n2.CHAIN_MAX - len(real) + 1))
