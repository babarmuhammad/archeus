"""Unit tests for tools/pv20_mxc/native/n2_check.py (the N2 native script).

Nothing here launches a process, creates a Job, loads a native library or touches a real
profile: every Windows-facing seam (live_ctime, look_at, the harness, the api) is a fake,
and the production modules are imported only where they are pure (mxc, win32_mxc).
"""

import ast
import json
import ntpath
import os
import re
import stat
from types import SimpleNamespace

import pytest

from tools.pv20_mxc.native import common, n2_check as n2
from tools.pv20_mxc.native.common import StopRun
from archeus.node import linkscan, mxc, staging
from tools.pv20_mxc.protocol import STAGES

REAL_PARENT_OK = n2.parent_ok

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), 'tools', 'pv20_mxc', 'native', 'n2_check.py')


class Rec:
    """Records what a step reports; FAIL stops the step the way the real Recorder does."""

    def __init__(self):
        self.rows = []

    def record(self, case, status, detail=''):
        self.rows.append((case, status, detail))
        if status == 'FAIL':
            raise StopRun(case)


# ---------------------------------------------------------------- parent and system

@pytest.mark.parametrize('parent', [
    'D:\\archeus-worktrees\\pv20-fixtures', 'D:\\archeus-worktrees\\pv20-fixtures\\run', 'd:\\Archeus-Worktrees\\PV20-Fixtures\\run\\x_y.z-1'])
def test_parent_ok_accepts_the_fixture_base_and_below(parent):
    assert n2.parent_ok(parent)


@pytest.mark.parametrize('parent', [
    '', None, 5, 'D:\\', 'D:\\pv20-fixtures', 'D:\\pv20-fixtures\\run',
    'D:\\archeus-worktrees', 'D:\\archeus-worktrees\\archeus-int14',
    'D:\\archeus-worktrees\\_scratch\\pv20-fixtures',
    'D:\\archeus-worktrees\\pv20-fixtures-evil', 'D:\\archeus-worktrees\\pv20-fixturesX\\run', 'D:\\other',
    'C:\\pv20-fixtures', 'pv20-fixtures', 'D:pv20-fixtures', '\\\\host\\share\\pv20-fixtures',
    'D:\\archeus-worktrees\\pv20-fixtures\\', 'D:\\archeus-worktrees\\pv20-fixtures\\\\run', 'D:\\archeus-worktrees\\pv20-fixtures\\..', 'D:\\archeus-worktrees\\pv20-fixtures\\.\\run',
    'D:\\archeus-worktrees\\pv20-fixtures\\..\\other', 'D:\\archeus-worktrees\\pv20-fixtures\\run.', 'D:\\archeus-worktrees\\pv20-fixtures\\run ',
    'D:\\archeus-worktrees\\pv20-fixtures\\a b', 'D:\\archeus-worktrees\\pv20-fixtures\\a&b', 'D:\\archeus-worktrees\\pv20-fixtures\\a^b', 'D:/pv20-fixtures/run',
    'D:\\archeus-worktrees\\pv20-fixtures\\r\u00fcn', '\\\\?\\D:\\archeus-worktrees\\pv20-fixtures'])
def test_parent_ok_refuses_everything_else(parent):
    assert not n2.parent_ok(parent)


def test_systemroot_must_be_a_plain_drive_windows_folder():
    assert n2.systemroot_ok('C:\\Windows') and n2.systemroot_ok('D:\\WINDOWS')
    for bad in ('', None, 'C:\\Windows\\', 'C:\\Windows\\System32', 'C:\\Win dows', '\\\\h\\s\\Windows',
                'C:\\Windows & calc'):
        assert not n2.systemroot_ok(bad)


# ---------------------------------------------------------------- layout and grants

def _lay(tmp_path):
    lay = n2.layout(str(tmp_path / 'root'))
    n2.make_dirs(lay)
    return lay


def _under(path, folder):
    return os.path.normcase(path).startswith(os.path.normcase(folder) + os.sep)


def test_every_directory_lies_under_the_root(tmp_path):
    lay = _lay(tmp_path)
    flat = [v for v in lay.values() if isinstance(v, str)]
    nested = [v for k in ('p', 'q', 'core') for v in lay[k].values()]
    for path in flat + nested:
        assert path == lay['root'] or _under(path, lay['root'])
        assert os.path.isdir(path) or path in (lay['sdk'], lay['ledger'])


def test_grants_give_the_seven_classes_their_own_boundaries(tmp_path):
    lay = _lay(tmp_path)
    for who, peer in (('p', 'q'), ('q', 'p')):
        rw, ro = n2.grants(lay, who)
        assert rw == (lay[who]['request'], lay[who]['state'])          # classes 1 and 7, workspace last
        assert ro == (lay[who]['response'], lay[who]['sentinel'], lay['runtime'])
        granted = rw + ro
        assert len(set(granted)) == len(granted)
        for a in granted:                                               # no grant nests in another
            assert not any(a != b and _under(a, b) for b in granted)
        for cls, path in lay['core'].items():                           # classes 4, 5, 6 are never granted
            assert not any(path == g or _under(path, g) or _under(g, path) for g in granted), cls
        for path in lay[peer].values():                                 # the peer's classes neither
            assert not any(path == g or _under(path, g) or _under(g, path) for g in granted)
        assert lay['outside'] not in granted and lay['private'] not in granted
        assert lay['ledger'] not in granted and lay['envhome'] not in granted


def test_seed_dirs_cover_every_class_with_a_distinct_label(tmp_path):
    lay = _lay(tmp_path)
    seeds = n2.seed_dirs(lay)
    assert {'p.request', 'p.response', 'p.sentinel', 'p.state', 'q.request', 'q.state',
            'core.lifecycle', 'core.halt', 'core.core-private', 'outside', 'runtime', 'rev'} <= set(seeds)
    assert len(set(seeds.values())) == len(seeds)


# ---------------------------------------------------------------- production policy

def test_the_production_compiler_accepts_this_layout_and_the_checker_agrees(tmp_path):
    from archeus.node import mxc
    lay = _lay(tmp_path)
    for who in ('p', 'q'):
        rw, ro = n2.grants(lay, who)
        env = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': lay['localappdata']}
        policy = mxc.compile_policy(workspace=rw, readonly=ro, cwd=rw[-1], command_line='x',
                                    env=env, timeout_ms=1000)
        assert n2.policy_problems(policy.raw, rw, ro, env) == []


def _policy(tmp_path):
    from archeus.node import mxc
    lay = _lay(tmp_path)
    rw, ro = n2.grants(lay, 'p')
    env = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': lay['localappdata']}
    raw = mxc.compile_policy(workspace=rw, readonly=ro, cwd=rw[-1], command_line='x', env=env,
                             timeout_ms=1000).raw
    return raw, rw, ro, env


@pytest.mark.parametrize('mutate,expect', [
    (lambda r: r['network']['egress'].update(default='allow'), 'network'),
    (lambda r: r['network']['ingress'].update(hostLoopback='allow'), 'network'),
    (lambda r: r['ui'].update(disable=False), 'ui'),
    (lambda r: r['ui'].update(clipboard='read'), 'ui'),
    (lambda r: r['process'].update(inheritDefaultEnv=True), 'inherited'),
    (lambda r: r['process']['env'].append('USERPROFILE=x'), 'environment'),
    (lambda r: r['filesystem']['readwritePaths'].append('x'), 'grants'),
    (lambda r: r['filesystem']['readonlyPaths'].pop(), 'grants'),
    (lambda r: r['filesystem'].update(deniedPaths=['x']), 'grants'),
    (lambda r: r.update(runtimeConfig={'networkProxy': 'http://127.0.0.1:1'}), 'proxy'),
])
def test_policy_problems_names_each_way_the_policy_can_be_weaker(tmp_path, mutate, expect):
    raw, rw, ro, env = _policy(tmp_path)
    mutate(raw)
    assert any(expect in p for p in n2.policy_problems(raw, rw, ro, env))


# ---------------------------------------------------------------- command lines

def test_chain_runs_through_one_cmd_with_the_outer_quotes_only(tmp_path):
    items = [n2.w_ok('a', 'D:\\x\\a.txt'), n2.w_no('b', 'D:\\x\\b.txt'),
             n2.r_ok('c', 'D:\\x\\s.txt', 'D:\\x\\e.txt', 'S1Z')]
    line = n2.command_line(n2.cmd_argv('C:\\Windows\\System32\\cmd.exe', n2.chain_of(items)))
    assert line.startswith('C:\\Windows\\System32\\cmd.exe /d /s /c "echo ')
    assert line.endswith('e.txt"') and line.count('"') == 2          # no nested quoting
    assert ' & ' in line


@pytest.mark.parametrize('argv', [[], ['a', ''], ['a', 5], ['a', 'b\0'], ['x' * 7000]])
def test_command_line_refuses_a_bad_or_oversized_argv(argv):
    with pytest.raises(ValueError):
        n2.command_line(argv)


def test_tokens_end_in_a_letter_so_cmd_never_reads_a_handle_number():
    seen = {n2.new_token() for _ in range(50)}
    assert len(seen) == 50
    assert all(re.fullmatch(r'T\d{9}Z', t) for t in seen)
    cmd = n2.w_ok('a', 'D:\\x\\a.txt').cmd
    assert re.fullmatch(r'echo T\d{9}Z>D:\\x\\a\.txt', cmd)           # token directly before '>' is not a digit


def test_descendant_items_build_nested_cmd_without_a_redirect():
    child = n2.sub('C:\\c.exe', 'dir_ok', 'x', 'D:\\a', 'md D:\\a')
    grand = n2.sub('C:\\c.exe', 'dir_no', 'y', 'D:\\b', 'md D:\\b', depth=2)
    assert child.cmd == 'C:\\c.exe /d /c md D:\\a'
    assert grand.cmd == 'C:\\c.exe /d /c C:\\c.exe /d /c md D:\\b'
    assert '>' not in child.cmd + grand.cmd


# ---------------------------------------------------------------- the host-side verdict

def _world(**files):
    return lambda path: files.get(path)


ITEMS = [n2.Item('write_ok', 'wok', 'c', 'W', 'TOK'), n2.Item('read_ok', 'rok', 'c', 'R', 'SEC'),
         n2.Item('dir_ok', 'dok', 'c', 'D', None), n2.Item('write_no', 'wno', 'c', 'WN', None),
         n2.Item('read_no', 'rno', 'c', 'RN', 'LEAK'), n2.Item('dir_no', 'dno', 'c', 'DN', None),
         n2.Item('write_ok', 'done', 'c', 'DONE', 'DT')]
GOOD = dict(W='x TOK', R='SEC', D='<dir>', RN='', DONE='DT')


def test_judge_passes_a_container_that_did_exactly_the_allowed_things():
    assert n2.judge(ITEMS, _world(**GOOD)) is None
    assert n2.judge(ITEMS, _world(**dict(GOOD, RN=None))) is None     # a denied read may leave no file


@pytest.mark.parametrize('change,expected', [
    ({'W': None}, ('control', 'wok')),
    ({'W': 'no token here'}, ('control', 'wok')),
    ({'W': '<link>'}, ('control', 'wok')),
    ({'R': ''}, ('control', 'rok')),                                  # an empty evidence file is not a read
    ({'R': None}, ('control', 'rok')),
    ({'D': None}, ('control', 'dok')),
    ({'D': 'file text'}, ('control', 'dok')),
    ({'WN': 'bad'}, ('breach', 'wno')),
    ({'WN': ''}, ('breach', 'wno')),                                  # any file there is a breach
    ({'RN': 'LEAK'}, ('breach', 'rno')),
    ({'RN': 'prefix LEAK suffix'}, ('breach', 'rno')),
    ({'DN': '<dir>'}, ('breach', 'dno')),
    ({'DONE': None}, ('control', 'done')),
])
def test_judge_names_the_first_failure_and_its_kind(change, expected):
    assert n2.judge(ITEMS, _world(**dict(GOOD, **change))) == expected


def test_a_missing_done_marker_outranks_every_other_verdict():
    world = _world(**dict(GOOD, DONE=None, WN='bad'))
    assert n2.judge(ITEMS, world) == ('control', 'done')


def test_judge_rejects_an_unknown_kind():
    with pytest.raises(ValueError):
        n2.judge([n2.Item('maybe', 'x', 'c', 'P', None)], _world())


def test_file_ok_needs_non_blank_content():
    item = [n2.file_ok('env', 'set>P', 'P')]
    assert n2.judge(item, _world(P='A=1')) is None
    assert n2.judge(item, _world(P='  \n')) == ('control', 'env')
    assert n2.judge(item, _world()) == ('control', 'env')


# ---------------------------------------------------------------- items per class

def _harness(tmp_path):
    lay = _lay(tmp_path)
    seeds = {k: 'S_%s_Z' % k for k in n2.seed_dirs(lay)}
    return SimpleNamespace(lay=lay, seeds=seeds, cmd='C:\\Windows\\System32\\cmd.exe', env={})


@pytest.mark.parametrize('who,peer', [('p', 'q'), ('q', 'p')])
def test_class_items_cover_all_seven_classes_and_both_peers_in_one_direction(tmp_path, who, peer):
    h = _harness(tmp_path)
    items = n2.class_items(h, who, peer)
    labels = {i.label for i in items}
    assert {'request-write', 'state-write', 'response-read', 'sentinel-read', 'response-write',
            'sentinel-write', 'runtime-write', 'lifecycle-read', 'lifecycle-write', 'halt-read',
            'halt-write', 'core-private-read', 'core-private-write'} <= labels
    assert {'peer-%s-%s' % (c, a) for c in ('request', 'response', 'sentinel', 'state')
            for a in ('read', 'write')} <= labels
    rw, ro = n2.grants(h.lay, who)
    for i in items:
        if i.kind in ('read_no', 'write_no') and i.label.startswith(('peer-', 'lifecycle', 'halt', 'core-')):
            if i.kind == 'read_no':                                    # evidence goes to the workspace
                assert _under(i.path, rw[-1])
                target = re.fullmatch(r'type (\S+)>\S+', i.cmd).group(1)   # what is read is not granted
            else:
                target = i.path
            assert not any(target == g or _under(target, g) for g in rw + ro), i.label
        if i.label in ('response-write', 'sentinel-write', 'runtime-write'):
            assert any(_under(i.path, g) for g in ro)                  # denied by access, inside a ro grant
        if i.label in ('request-write', 'state-write'):
            assert any(_under(i.path, g) for g in rw)
    # every read_no names the seed of the folder it reads, so a leak is detectable
    for i in items:
        if i.kind == 'read_no':
            assert i.secret.startswith('S_') and i.secret in h.seeds.values()


def test_no_denial_row_names_a_file_the_other_direction_writes(tmp_path):
    """Both directions run in one fixture, and a denial row fails when its file exists:
    a row aimed at a file the peer's own run wrote reads as a breach that never happened."""
    h = _harness(tmp_path)
    written = {i.path for who, peer in (('p', 'q'), ('q', 'p'))
               for i in n2.class_items(h, who, peer) if i.kind == 'write_ok'}
    denied = {i.path for who, peer in (('p', 'q'), ('q', 'p'))
              for i in n2.class_items(h, who, peer) if i.kind == 'write_no'}
    assert written and denied and not written & denied


def test_class_items_chain_fits_one_command_line(tmp_path):
    h = _harness(tmp_path)
    for who, peer in (('p', 'q'), ('q', 'p')):
        n2.command_line(n2.cmd_argv(h.cmd, n2.chain_of(n2.class_items(h, who, peer)
                                                       + [n2.done_item(h.lay[who]['state'])])))


# ---------------------------------------------------------------- environment, journals

def test_env_findings_requires_the_explicit_entries_and_flags_a_host_profile():
    want = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'D:\\f\\localappdata'}
    ok = 'SystemRoot=C:\\Windows\nLOCALAPPDATA=d:\\F\\LocalAppData\nPROMPT=$P$G\n'
    f = n2.env_findings(ok, want)
    assert f == {'missing': [], 'mismatched': [], 'profile_leak': False, 'extra': ['PROMPT']}
    assert n2.env_findings('SystemRoot=C:\\Windows\n', want)['missing'] == ['LOCALAPPDATA']
    assert n2.env_findings('SystemRoot=C:\\Win\nLOCALAPPDATA=d:\\f\\localappdata', want)['mismatched'] == ['SYSTEMROOT']
    leak = ok + 'TEMP=C:\\Users\\someone\\AppData\\Local\\Temp\n'
    assert n2.env_findings(leak, want)['profile_leak'] is True
    assert n2.env_findings('', want)['missing'] == ['LOCALAPPDATA', 'SYSTEMROOT']


def test_oracle_state_knows_only_the_shapes_the_run_makes():
    assert n2.oracle_state(n2.CLEAN) is None
    assert n2.oracle_state(n2.QUARANTINED) == n2.DEAD_UNVERIFIED
    assert n2.oracle_state(n2.QUARANTINED_EARLY) == n2.DEAD_UNVERIFIED
    for odd in (['intent'], ['intent', 'ownership'], ['intent', 'ownership', 'disposal'], []):
        with pytest.raises(ValueError):
            n2.oracle_state(odd)


def test_compare_reconcile_is_exact_in_both_directions():
    expected = {'a': None, 'b': 'DEAD_UNVERIFIED', 'c': 'STILL_RUNNING'}
    assert n2.compare_reconcile({'b': 'DEAD_UNVERIFIED', 'c': 'STILL_RUNNING'}, expected) == []
    assert len(n2.compare_reconcile({'b': 'DEAD_UNVERIFIED', 'c': 'DEAD_CLEAN'}, expected)) == 1
    assert len(n2.compare_reconcile({'a': 'DEAD_UNVERIFIED', 'b': 'DEAD_UNVERIFIED',
                                     'c': 'STILL_RUNNING'}, expected)) == 1
    assert len(n2.compare_reconcile({'b': 'DEAD_UNVERIFIED', 'c': 'STILL_RUNNING', 'z': 'DEAD_CLEAN'}, expected)) == 1
    assert len(n2.compare_reconcile({}, expected)) == 2


def test_journal_ops_reads_through_the_injected_production_reader():
    ledger = SimpleNamespace(journals=lambda: {'e': b'data'})
    reader = lambda data, eid: ([{'op': 'intent'}, {'op': 'quarantine'}], False)  # noqa: E731
    assert n2.journal_ops(reader, ledger, 'e') == (['intent', 'quarantine'], False)


# ---------------------------------------------------------------- import isolation

def test_import_isolated_points_every_home_variable_away_and_restores_them():
    environ = {'USERPROFILE': 'real', 'TEMP': 'realtemp', 'PATH': 'keep'}
    seen = []

    def fake_import(name):
        seen.append((name, {k: environ.get(k) for k in n2.HOME_VARS}))
        return name

    mods = n2.import_isolated(('m1', 'm2'), 'HOME_DIR', environ, fake_import, loaded={})
    assert mods == {'m1': 'm1', 'm2': 'm2'}
    for _, view in seen:
        assert set(view.values()) == {'HOME_DIR'}
    assert environ == {'USERPROFILE': 'real', 'TEMP': 'realtemp', 'PATH': 'keep'}   # absent ones stay absent


def test_import_isolated_restores_after_a_failing_import():
    environ = {'USERPROFILE': 'real'}

    def boom(name):
        raise ImportError(name)

    with pytest.raises(ImportError):
        n2.import_isolated(('m',), 'H', environ, boom, loaded={})
    assert environ == {'USERPROFILE': 'real'}


def test_import_isolated_refuses_when_the_config_module_already_read_the_real_profile():
    called = []
    with pytest.raises(n2.SetupError):
        n2.import_isolated(('m',), 'H', {}, lambda n: called.append(n), loaded={'claude_sessions.config': 1})
    assert called == []


def test_the_production_module_list_names_what_the_harness_uses():
    assert {'archeus.node.local', 'archeus.node.win32_mxc', 'archeus.node.mxc_ledger',
            'archeus.node.isolation', 'archeus.node.staging', 'archeus.node.mxc'} == set(n2.PROD)


# ---------------------------------------------------------------- budget, finish, look_at

def test_budget_raises_only_after_the_limit():
    clock = iter([0.0, 10.0, 99.0, 101.0])
    b = n2.Budget(100.0, clock=lambda: next(clock))
    b.check()
    b.check()
    with pytest.raises(n2.SetupError):
        b.check()


@pytest.mark.parametrize('code,removed', [(0, True), (1, False), (2, False), (3, False)])
def test_finish_deletes_the_fixture_only_on_exit_zero(code, removed):
    gone, said = [], []
    assert n2.finish(code, 'D:\\archeus-worktrees\\pv20-fixtures\\run\\x', gone.append, said.append) == code
    assert bool(gone) is removed and said


def test_look_at_classifies_without_following(tmp_path):
    f = tmp_path / 'a.txt'
    f.write_text('hello', encoding='utf-8')
    d = tmp_path / 'd'
    d.mkdir()
    assert n2.look_at(str(tmp_path / 'missing')) is None
    assert n2.look_at(str(f)) == 'hello'
    assert n2.look_at(str(d)) == '<dir>'
    big = tmp_path / 'big.txt'
    big.write_bytes(b'x' * (n2.EVIDENCE_MAX + 1))
    assert n2.look_at(str(big)) == '<link>'
    twin = tmp_path / 'twin.txt'
    try:
        os.link(f, twin)
    except OSError:
        pytest.skip('hardlinks unavailable')
    assert n2.look_at(str(f)) == '<link>' and n2.look_at(str(twin)) == '<link>'


def test_look_at_never_reads_through_a_symlink(tmp_path):
    target = tmp_path / 't.txt'
    target.write_text('secret', encoding='utf-8')
    link = tmp_path / 'l.txt'
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip('symlinks need a privilege here')
    assert n2.look_at(str(link)) == '<link>'


def test_look_at_treats_a_reparse_point_as_a_link(tmp_path, monkeypatch):
    f = tmp_path / 'r.txt'
    f.write_text('x', encoding='utf-8')
    real = os.lstat(f)
    fake = SimpleNamespace(st_mode=real.st_mode, st_nlink=1, st_size=1, st_file_attributes=0x400)
    monkeypatch.setattr(n2.os, 'lstat', lambda p: fake)
    assert n2.look_at(str(f)) == '<link>'


# ---------------------------------------------------------------- recorder journal

def test_recorder_journals_every_verdict_redacted_and_still_stops_on_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(common, '_username', lambda: 'zed_user')
    monkeypatch.setattr(common, '_machine_name', lambda: 'box-7')
    rec = n2._Rec('N2')
    rec.journal = str(tmp_path / 'j.jsonl')
    rec.record('revocation', 'PASS', 'ok')
    with pytest.raises(StopRun):
        rec.record('effective-policy', 'FAIL', 'owner zed_user on box-7 S-1-5-21-1-2-3')
    lines = (tmp_path / 'j.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    assert 'zed_user' not in lines[1] and 'box-7' not in lines[1] and 'S-1-5-21' not in lines[1]
    with pytest.raises(ValueError):
        rec.record('not-a-case', 'PASS')
    with pytest.raises(ValueError):
        rec.record('revocation', 'MAYBE')
    assert len((tmp_path / 'j.jsonl').read_text(encoding='utf-8').splitlines()) == 2
    assert rec.exit_code() == 1


# ---------------------------------------------------------------- the api counters

def test_counting_api_counts_calls_and_keeps_the_created_list_across_resets(monkeypatch):
    from archeus.node import win32_mxc as w
    monkeypatch.setattr(w.Win32Api, 'create_process_w', lambda self, **kw: ('proc', 'thr', 77))
    monkeypatch.setattr(w.Win32Api, 'creation_time', lambda self, process: 1234)
    monkeypatch.setattr(w.Win32Api, 'resume_thread', lambda self, thread: 1)
    api = object.__new__(n2._counting_api(w))
    api.reset()
    assert api.create_process_w(application='a') == ('proc', 'thr', 77)
    assert api.creation_time('proc') == 1234
    assert api.resume_thread('thr') == 1
    assert (api.creates, api.resumes, api.created) == (1, 1, [(77, 1234)])
    api.reset()
    assert (api.creates, api.resumes, api.created) == (0, 0, [(77, 1234)])


def test_job_ref_closes_once():
    closed = []
    ref = n2.JobRef(SimpleNamespace(close_job=closed.append), 99)
    ref.close()
    ref.close()
    assert closed == [99] and ref.handle is None


def test_fixture_reader_says_gone_only_when_pid_and_creation_time_no_longer_match(monkeypatch):
    h = n2.Harness.__new__(n2.Harness)
    owner = {'pid': 9, 'create_time': 500}
    for live, answer in ((None, True), (501, True), (500, ['e1'])):
        monkeypatch.setattr(n2, 'live_ctime', lambda pid, v=live: v)
        assert h.reader('e1', owner) == answer


def test_live_ctime_is_none_unless_the_process_is_still_active(monkeypatch):
    monkeypatch.setattr(common, '_process_creation_time', lambda pid: 42)
    for code, want in ((n2.STILL_ACTIVE, 42), (0, None), (1, None), (None, None)):
        monkeypatch.setattr(n2, '_exit_code', lambda pid, c=code: c)
        assert n2.live_ctime(5) == want


# ---------------------------------------------------------------- steps over a fake harness

class FakeApi:
    def __init__(self):
        self.creates = self.resumes = 0
        self.created = []

    def reset(self):
        self.creates = self.resumes = 0


class FakeHarness:
    def __init__(self, tmp_path, **kw):
        self.lay = _lay(tmp_path)
        self.api = FakeApi()
        self.journals_now = {}
        self.ledger = SimpleNamespace(journals=lambda: dict(self.journals_now))
        self.ended = {}
        self.cmd = r'C:\Windows\System32\cmd.exe'
        self.__dict__.update(kw)


def test_refusal_passes_only_when_production_refused_and_spawned_nothing(tmp_path):
    h = FakeHarness(tmp_path)

    def refuses():
        raise OSError('second name')

    rec = Rec()
    n2._refusal(h, rec, 'case', refuses)
    assert rec.rows[-1][:2] == ('setup-faults-no-spawn', 'PASS')


@pytest.mark.parametrize('how', ['accepted', 'spawned', 'resumed', 'journalled'])
def test_refusal_fails_on_every_way_the_refusal_can_be_hollow(tmp_path, how):
    h = FakeHarness(tmp_path)

    def build():
        if how == 'accepted':
            return 'e', SimpleNamespace()
        if how == 'spawned':
            h.api.creates = 1
        if how == 'resumed':
            h.api.resumes = 1
        if how == 'journalled':
            h.journals_now['e'] = b'x'
        raise OSError('late refusal')

    with pytest.raises(StopRun):
        n2._refusal(h, Rec(), 'case', build)


def test_a_launch_time_refusal_needs_the_plant_and_the_refusal_after_it(tmp_path):
    h = FakeHarness(tmp_path, job=lambda eid: SimpleNamespace(handle=1))
    order = []

    def start(job):
        order.append('start')
        raise OSError('second name')

    rec = Rec()
    n2._refusal(h, rec, 'case', lambda: ('e', SimpleNamespace(start=start)), plant=lambda: order.append('plant'))
    assert order == ['plant', 'start'] and rec.rows[-1][1] == 'PASS'
    # a start that does not refuse is a FAIL
    with pytest.raises(StopRun):
        n2._refusal(h, Rec(), 'case', lambda: ('e', SimpleNamespace(start=lambda job: None)),
                    plant=lambda: None)


def test_a_launch_time_case_that_is_refused_early_did_not_test_the_launch_recheck(tmp_path):
    h = FakeHarness(tmp_path)

    def early():
        raise OSError('refused at grant time')

    with pytest.raises(StopRun):
        n2._refusal(h, Rec(), 'case', early, plant=lambda: None)


def test_a_fault_in_the_plant_itself_is_not_counted_as_a_refusal(tmp_path):
    h = FakeHarness(tmp_path, job=lambda eid: SimpleNamespace(handle=1))

    def plant():
        raise OSError('os.link failed')

    with pytest.raises(OSError):
        n2._refusal(h, Rec(), 'case', lambda: ('e', SimpleNamespace(start=lambda job: None)), plant=plant)


def _fault_harness(tmp_path, monkeypatch, **over):
    monkeypatch.setattr(n2.time, 'sleep', lambda s: None)
    h = FakeHarness(tmp_path)
    state = dict(creates=1, resumes=0, ops=n2.QUARANTINED_EARLY, invalid=False, members=0, alive=False,
                 raises=True, marker=False)
    state.update(over)
    h.api.created = []

    def make(tag, argv, rw, ro, **kw):
        def start(job):
            h.api.creates = state['creates']
            h.api.resumes = state['resumes']
            h.api.created.append((321, 7))
            if state['marker']:
                with open(os.path.join(h.lay['outside'], 'spawned_t.txt'), 'w') as fh:
                    fh.write('X')
            if state['raises']:
                raise OSError('injected')
        return 'eid', SimpleNamespace(start=start)

    h.make = make
    h.job = lambda eid, boundary=None: SimpleNamespace(handle=5)
    h.ops = lambda eid: (state['ops'], state['invalid'])
    h.wait_job = lambda job, want, seconds: state['members']
    monkeypatch.setattr(n2, 'live_ctime', lambda pid: 7 if state['alive'] else None)
    return h


def test_a_fault_launch_passes_when_created_never_resumed_and_gone(tmp_path, monkeypatch):
    h = _fault_harness(tmp_path, monkeypatch)
    rec = Rec()
    n2._fault_launch(h, rec, 'label', 't')
    assert rec.rows[-1][1] == 'PASS' and h.ended['eid'] == n2.QUARANTINED_EARLY


@pytest.mark.parametrize('over', [
    {'raises': False}, {'creates': 0}, {'creates': 2}, {'resumes': 1}, {'marker': True},
    {'ops': n2.QUARANTINED}, {'ops': n2.CLEAN}, {'invalid': True}, {'members': 1}, {'alive': True}])
def test_a_fault_launch_fails_on_each_sign_the_child_ran_or_lingered(tmp_path, monkeypatch, over):
    h = _fault_harness(tmp_path, monkeypatch, **over)
    with pytest.raises(StopRun):
        n2._fault_launch(h, Rec(), 'label', 't')


def _probe_harness(tmp_path, monkeypatch, files, ops=None):
    h = FakeHarness(tmp_path)
    h.cmd = 'C:\\Windows\\System32\\cmd.exe'
    h.go = lambda tag, argv, rw, ro: SimpleNamespace(code=0, out='', err='', ops=ops or n2.CLEAN)
    monkeypatch.setattr(n2, 'look_at', lambda path: files.get(path))
    return h


def test_probe_returns_on_a_held_boundary_and_fails_on_a_breach_a_control_or_an_unclean_end(tmp_path, monkeypatch):
    rw = ('R1', 'R2')
    items = [n2.Item('write_ok', 'ctl', 'c', 'in', 'TOK'), n2.Item('write_no', 'out', 'c', 'outside', None)]
    done = n2.done_item(rw[-1])
    monkeypatch.setattr(n2, 'done_item', lambda d: n2.Item('write_ok', 'done', 'c', 'donefile', 'D'))
    base = {'in': 'TOK', 'donefile': 'D'}
    h = _probe_harness(tmp_path, monkeypatch, base)
    assert n2.probe(h, Rec(), 'positive-controls', 't', items, rw, ()).ops == n2.CLEAN
    for files, ops, what in ((dict(base, outside='bad'), None, 'BREACH'),
                             ({'donefile': 'D'}, None, 'control'),
                             ({'in': 'TOK'}, None, 'control'),
                             (base, n2.QUARANTINED, 'not clean')):
        h = _probe_harness(tmp_path, monkeypatch, files, ops)
        rec = Rec()
        with pytest.raises(StopRun):
            n2.probe(h, rec, 'positive-controls', 't', items, rw, ())
        assert what in rec.rows[-1][2]
    assert done.label == 'done'


# ---------------------------------------------------------------- main, over fakes

def _main_world(tmp_path, monkeypatch, behave, left=0):
    parent = tmp_path / 'fx'
    sdk = parent.joinpath(*n2.SDK_TAIL)
    sdk.mkdir(parents=True)
    (sdk / 'package.json').write_text('{}', encoding='utf-8')
    root = tmp_path / 'root'
    root.mkdir()
    calls = SimpleNamespace(removed=[], winddown=0, safe_root=0)

    def fake_safe_root(p):
        calls.safe_root += 1
        return str(root)

    class FakeH:
        def __init__(self, *a):
            pass

        def wind_down(self):
            calls.winddown += 1
            return left

    monkeypatch.setattr(n2, 'parent_ok', lambda p: True)
    monkeypatch.setattr(n2, '_on_windows', lambda: True)
    monkeypatch.setattr(n2, '_system_ok', lambda v: True)
    monkeypatch.setattr(n2, 'safe_root', fake_safe_root)
    monkeypatch.setattr(n2, 'remove_fixture', calls.removed.append)
    monkeypatch.setattr(n2, 'Harness', FakeH)
    monkeypatch.setattr(n2, 'run', behave)
    monkeypatch.setenv('SystemRoot', 'C:\\Windows')
    return str(parent), str(root), calls


def _all(h, rec, status='PASS', but=None):
    for case in STAGES['N2'].cases:
        rec.record(case, but if case == 'revocation' and but else status, 'x')


def test_main_exit_zero_removes_the_fixture_exactly_once(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all)
    assert n2.main([parent]) == 0
    assert calls.removed == [root] and calls.winddown == 1


def test_main_keeps_the_fixture_on_inconclusive(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, lambda h, rec: _all(h, rec, but='INCONCLUSIVE'))
    assert n2.main([parent]) == 2
    assert calls.removed == []


def test_main_stops_at_the_first_fail_and_keeps_the_fixture(tmp_path, monkeypatch):
    seen = []

    def behave(h, rec):
        rec.record('production-adapter', 'FAIL', 'bad')
        seen.append('ran past the fail')

    parent, root, calls = _main_world(tmp_path, monkeypatch, behave)
    assert n2.main([parent]) == 1
    assert calls.removed == [] and seen == [] and calls.winddown == 1


@pytest.mark.parametrize('exc', [n2.SetupError('x'), RuntimeError('boom'), KeyError('k'), KeyboardInterrupt()])
def test_main_setup_and_unexpected_errors_exit_three_and_keep_the_fixture(tmp_path, monkeypatch, exc):
    def behave(h, rec):
        raise exc

    parent, root, calls = _main_world(tmp_path, monkeypatch, behave)
    assert n2.main([parent]) == 3
    assert calls.removed == [] and calls.winddown == 1


def test_a_surviving_launcher_turns_a_clean_run_into_exit_three_without_deleting(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all, left=1)
    assert n2.main([parent]) == 3
    assert calls.removed == []


def test_a_run_that_recorded_nothing_never_passes(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, lambda h, rec: None)
    assert n2.main([parent]) == 2
    assert calls.removed == []


def test_main_refuses_before_creating_anything(tmp_path, monkeypatch, capsys):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all)
    monkeypatch.setattr(n2, 'parent_ok', REAL_PARENT_OK)
    assert n2.main([parent]) == 3                                    # a parent outside the fixture base
    monkeypatch.setattr(n2, 'parent_ok', lambda p: True)
    assert n2.main([]) == 3 and n2.main([parent, 'extra']) == 3
    monkeypatch.setattr(n2, '_on_windows', lambda: False)
    assert n2.main([parent]) == 3
    monkeypatch.setattr(n2, '_on_windows', lambda: True)
    monkeypatch.setattr(n2, '_system_ok', lambda v: False)
    assert n2.main([parent]) == 3
    monkeypatch.setattr(n2, '_system_ok', lambda v: True)
    assert n2.main([str(tmp_path / 'nope')]) == 3
    (tmp_path / 'fx' / 'sdk').rename(tmp_path / 'fx' / 'sdk2')
    assert n2.main([parent]) == 3                                    # staged SDK missing
    assert calls.safe_root == 0 and calls.removed == [] and capsys.readouterr().out


def test_main_does_not_delete_when_the_removal_itself_refuses(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all)

    def refuse(r):
        raise ValueError('root is not a fixture tree')

    monkeypatch.setattr(n2, 'remove_fixture', refuse)
    assert n2.main([parent]) == 3


# ---------------------------------------------------------------- the script's own source

def _tree():
    with open(SRC, encoding='utf-8') as fh:
        text = fh.read()
    return text, ast.parse(text)


def test_every_protocol_case_is_recorded_and_every_stub_names_a_case():
    text, tree = _tree()
    recorded = {n.args[0].value for n in ast.walk(tree)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'record'
                and n.args and isinstance(n.args[0], ast.Constant)}
    assert recorded == set(STAGES['N2'].cases)
    assert {case for case, _ in n2.STUBS} <= set(STAGES['N2'].cases)
    assert all(why.startswith(('missing contract', 'stand-in')) for _, why in n2.STUBS)
    assert n2.STAGE == 'N2' and n2.BUDGET_S < STAGES['N2'].budget


def test_the_source_uses_no_acl_network_shell_or_recursive_delete_facility():
    text, tree = _tree()
    banned_words = ('icacls', 'takeown', 'set-acl', 'powershell', 'taskkill', 'rmtree', 'socket', 'urllib',
                    'http.client', 'requests', 'curl', 'os.system', 'shell=True', 'win32security')
    low = text.lower()
    code_only = re.sub(r'"""[\s\S]*?"""', '', low)
    for word in banned_words:
        assert word.lower() not in code_only, word
    assert '.format(' not in text                                    # no str.format on brace-bearing strings
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert not [c for c in calls if isinstance(c.func, ast.Attribute) and c.func.attr == 'format']


def _function_of(tree, node):
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.ClassDef)) and any(n is node for n in ast.walk(fn)):
            yield fn.name


def test_destructive_calls_are_confined_to_the_functions_that_own_them():
    _, tree = _tree()
    where = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in ('rmdir', 'unlink', 'link', '_terminate_process',
                                                         'remove', 'rename', 'replace'):
            where.setdefault(n.attr, set()).update(f for f in _function_of(tree, n))
    assert where['rmdir'] == {'_unjunction'}
    assert where['_terminate_process'] == {'wind_down', 'Harness'}
    assert where.get('unlink') <= {'step_faults'}
    assert where.get('link') <= {'step_faults', 'main'} and 'remove' not in where and 'rename' not in where


def test_the_only_environment_reads_are_systemroot_and_the_import_window():
    _, tree = _tree()
    reads = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in ('environ', 'getenv'):
            reads.append(set(_function_of(tree, n)) - {'Harness'})
    assert reads and all(r <= {'import_isolated', 'main'} for r in reads)
    sysroot = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == 'get' and n.args and isinstance(n.args[0], ast.Constant)
               and n.args[0].value == 'SystemRoot']
    assert len(sysroot) == 1


def test_only_the_names_the_native_contract_allows_are_imported_from_common():
    _, tree = _tree()
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             and n.module == 'tools.pv20_mxc.native.common' for a in n.names}
    assert names == {'Recorder', 'StopRun', 'redact', 'remove_fixture', 'safe_root'}


def test_no_stat_bit_of_the_fixture_is_changed_by_the_pure_helpers(tmp_path):
    lay = _lay(tmp_path)
    before = {p: os.lstat(p).st_mode for p in (lay['outside'], lay['runtime'])}
    n2.look_at(lay['outside'])
    assert before == {p: os.lstat(p).st_mode for p in before}
    assert stat.S_ISDIR(before[lay['outside']])


# ---------------------------------------------------------------- the descendant diagnostic

CMD = r'C:\Windows\System32\cmd.exe'
RET, NOT = n2.RET_37, n2.NOT_37
WOK, WDEN, WNOT = n2.W_OK, n2.W_DENIED, n2.W_NOT
ADMITTED = {'path': r'C:\Windows\System32', 'admitted': True, 'reason': None}
REFUSED = {'path': r'C:\Windows\System32', 'admitted': False,
           'reason': 'multiple links in grant (a second name): a.dll'}


def test_exit_and_write_templates_are_exact():
    w = r'C:\fx\p\state'
    assert n2.exit_chain(CMD, 'T1Z', w + r'\a1.txt') == (
        r'C:\Windows\System32\cmd.exe /d /c exit /b 37 & (if errorlevel 38 (echo OTHER) else '
        r'(if errorlevel 37 (echo T1Z) else (echo OTHER)))>C:\fx\p\state\a1.txt')
    assert n2.write_chain(CMD, 'T1Z', w + r'\a2-child.txt', w + r'\a2.txt') == (
        r'C:\Windows\System32\cmd.exe /d /c "echo T1Z>C:\fx\p\state\a2-child.txt & exit /b 41" & '
        r'(if errorlevel 42 (echo OTHER) else (if errorlevel 41 (echo OBSERVED) else (echo OTHER)))'
        r'>C:\fx\p\state\a2.txt')


def test_write_chain_returns_its_own_code_and_never_the_exit_code_or_a_conditional_and():
    chain = n2.write_chain(CMD, 'T1Z', r'C:\fx\c.txt', r'C:\fx\e.txt')
    assert '41' in chain and '37' not in chain and '&&' not in chain and '^' not in chain


def test_final_command_lines_are_pinned_and_only_the_write_needs_the_raw_line():
    w = r'C:\fx\p\state'
    exit_chain = n2.exit_chain(CMD, 'T1Z', w + r'\a1.txt')
    write_chain = n2.write_chain(CMD, 'T1Z', w + r'\a2-child.txt', w + r'\a2.txt')
    assert n2.diag_line(CMD, exit_chain) == (
        r'C:\Windows\System32\cmd.exe /d /s /c "C:\Windows\System32\cmd.exe /d /c exit /b 37 & '
        r'(if errorlevel 38 (echo OTHER) else (if errorlevel 37 (echo T1Z) else (echo OTHER)))>C:\fx\p\state\a1.txt"')
    assert n2.diag_line(CMD, write_chain) == (
        r'C:\Windows\System32\cmd.exe /d /s /c "C:\Windows\System32\cmd.exe /d /c "echo T1Z>C:\fx\p\state\a2-child.txt & exit /b 41" & '
        r'(if errorlevel 42 (echo OTHER) else (if errorlevel 41 (echo OBSERVED) else (echo OTHER)))>C:\fx\p\state\a2.txt"')
    assert n2.command_line(n2.cmd_argv(CMD, exit_chain)) == n2.diag_line(CMD, exit_chain)
    assert n2.command_line(n2.cmd_argv(CMD, write_chain)) != n2.diag_line(CMD, write_chain)
    assert '\\"echo T1Z' in n2.command_line(n2.cmd_argv(CMD, write_chain))


def test_diag_line_refuses_an_overlong_chain():
    with pytest.raises(ValueError):
        n2.diag_line(CMD, 'x' * (n2.CHAIN_MAX + 1))


def test_row_table_grants_pairs_and_fresh_tokens(tmp_path):
    lay = _lay(tmp_path)
    rows = {r.id: r for r in n2.diag_rows(lay, r'C:\Windows', 'SEED')}
    assert list(rows) == ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    state = lay['p']['state']
    k = os.path.join(lay['root'], 'toolchain')
    assert rows['A1'].exe == CMD and rows['A1'].flag is None and rows['A1'].extra is None
    assert rows['A2'].pair == 'A1' and rows['A2'].child == os.path.join(state, 'a2-child.txt')
    assert rows['A2'].ev == os.path.join(state, 'a2.txt') and rows['A1'].child is None
    assert rows['B1'].exe == os.path.join(k, 'cmd.exe') and rows['B1'].extra == k
    assert rows['B1'].flag == n2.IMAGE_FLAG and rows['B2'].pair == 'B1'
    assert rows['C1'].exe == CMD and rows['C1'].extra == r'C:\Windows\System32'
    assert rows['C1'].flag == n2.SYSTEM_FLAG and rows['C2'].pair == 'C1'
    assert len({r.tok for r in rows.values()}) == 6
    assert rows['A1'].done.path == os.path.join(state, 'done_a1.txt')
    assert [i.label for i in rows['A1'].controls] == ['control-write', 'control-read']
    assert rows['A1'].controls[1].secret == 'SEED'


def test_gate_runs_only_the_a_rows_unless_a_flag_is_passed(tmp_path):
    rows = n2.diag_rows(_lay(tmp_path), r'C:\Windows', 'SEED')
    ids = lambda rs: [r.id for r in rs]
    run, skipped = n2.diag_gate(rows, set())
    assert ids(run) == ['A1', 'A2'] and ids(skipped) == ['B1', 'B2', 'C1', 'C2']
    run, skipped = n2.diag_gate(rows, {n2.IMAGE_FLAG})
    assert ids(run) == ['A1', 'A2', 'B1', 'B2'] and ids(skipped) == ['C1', 'C2']
    run, skipped = n2.diag_gate(rows, {n2.IMAGE_FLAG, n2.SYSTEM_FLAG})
    assert ids(run) == ids(rows) and skipped == []


def _ok_files(row):
    return {i.path: i.secret for i in row.controls + [row.done]}


def _look(files):
    return lambda p: files.get(p)


def test_exit_row_labels_say_only_whether_the_child_returned_37(tmp_path):
    row = n2.diag_rows(_lay(tmp_path), r'C:\Windows', 'SEED')[0]
    ok = _ok_files(row)
    assert n2.diag_result(row, _look({**ok, row.ev: row.tok + '\r\n'})) == 'returned 37'
    assert n2.diag_result(row, _look({**ok, row.ev: 'OTHER'})) == 'did not return 37'
    assert n2.diag_result(row, _look(ok)) == 'no evidence'
    assert n2.diag_result(row, _look({row.ev: row.tok})) == 'control failed'
    assert n2.diag_result(row, _look({**ok, row.ev: row.tok, row.done.path: 'x'})) == 'no evidence'


def test_write_row_labels_come_from_its_own_evidence_only(tmp_path):
    row = [r for r in n2.diag_rows(_lay(tmp_path), r'C:\Windows', 'SEED') if r.id == 'A2'][0]
    ok = _ok_files(row)
    assert n2.diag_result(row, _look({**ok, row.child: row.tok, row.ev: 'OBSERVED'})) == 'started, write ok'
    assert n2.diag_result(row, _look({**ok, row.ev: 'OBSERVED'})) == 'started, write not proved'
    assert n2.diag_result(row, _look({**ok, row.ev: 'OTHER'})) == 'did not return code'
    assert n2.diag_result(row, _look({**ok, row.child: row.tok, row.ev: 'OTHER'})) == 'did not return code'
    assert n2.diag_result(row, _look(ok)) == 'no evidence'
    assert n2.diag_result(row, _look({row.child: row.tok, row.ev: 'OBSERVED'})) == 'control failed'


def test_a_failed_control_is_never_a_pass_even_when_the_child_ran(tmp_path):
    row = n2.diag_rows(_lay(tmp_path), r'C:\Windows', 'SEED')[0]
    files = {k: v for k, v in _ok_files(row).items() if k != row.controls[1].path}
    files[row.ev] = row.tok
    assert n2.diag_result(row, _look(files)) == 'control failed'
    assert 'PASS' not in n2.diag_interpret({'A1': 'control failed'})


@pytest.mark.parametrize('labels, wants', [
    ({'A1': RET, 'A2': WOK}, 'baseline creation and workspace write proved'),
    ({'A1': RET, 'A2': WDEN}, 'write not proved with its control passing: investigate (3), inherited cwd and environment versus grants'),
    ({'A1': RET, 'A2': WNOT}, 'baseline exit proved; the write row gives no workspace conclusion'),
    ({'A1': RET}, 'baseline exit proved; the write row gives no workspace conclusion'),
    ({'A1': NOT}, 'all exit rows did not return 37: inconclusive for blanket denial (2)'),
    ({'A1': NOT, 'A2': WDEN}, 'child start proved by A2 (started, write not proved)'),
    ({'A1': NOT, 'B1': RET, 'B2': WOK}, 'image location or access, cause (1), strongly supported'),
    ({'A1': NOT, 'C1': RET}, 'missing System32 access or dependency grant, cause (1), strongly supported'),
    ({'B1': RET}, 'A1 baseline not usable: no conclusion about image or System32 access'),
    ({'A1': 'launch refused', 'C1': RET}, 'A1 baseline not usable: no conclusion about image or System32 access'),
    ({}, 'no interpretation bullet matches'),
])
def test_every_interpretation_line(labels, wants):
    assert wants in n2.diag_interpret(labels)


def test_a_write_row_without_its_token_file_is_not_called_a_denial():
    text = n2.diag_interpret({'A1': RET, 'A2': WDEN})
    assert 'denied' not in text and 'write not proved' in text
    assert 'denied' not in n2.diag_interpret({'A1': NOT, 'A2': WDEN})


def test_a_write_row_that_did_not_return_its_code_is_not_called_a_write_failure():
    text = n2.diag_interpret({'A1': RET, 'A2': WNOT})
    assert 'investigate' not in text and 'write failed' not in text


def test_void_rows_are_named_and_count_for_nothing():
    text = n2.diag_interpret({'A1': RET, 'A2': WOK, 'B1': 'control failed'})
    assert 'rows not usable (B1): baseline creation and workspace write proved' in text
    text = n2.diag_interpret({'A1': NOT, 'B1': 'control failed'})
    assert 'rows not usable (B1)' in text and 'inconclusive' in text and 'strongly supported' not in text
    text = n2.diag_interpret({'A1': NOT, 'C1': 'not admissible', 'C2': 'not admissible'})
    assert 'rows not usable (C1, C2)' in text
    text = n2.diag_interpret({'A1': RET, 'A2': 'diagnostic error'})
    assert 'rows not usable (A2)' in text and 'baseline exit proved' in text
    text = n2.diag_interpret({'A1': 'control failed', 'C1': RET})
    assert 'rows not usable (A1)' in text and 'no conclusion about image or System32 access' in text


class DiagHarness:
    def __init__(self, tmp_path):
        self.lay = _lay(tmp_path)
        self.cmd = CMD
        self.env = {'SYSTEMROOT': r'C:\Windows'}
        self.seeds = {'p.state': 'SEED'}
        self.launches = []
        self.m = SimpleNamespace(staging=staging, mxc=mxc)

    def prepare(self):
        pass

    def go(self, tag, argv, rw, ro, **kw):
        self.launches.append((tag, ro, kw['line']))
        policy = SimpleNamespace(raw={})
        return SimpleNamespace(ops=['intent', 'ownership', 'disposal', 'completion'],
                               launch=SimpleNamespace(policy=policy), job=None, code=0, out='', err='')

    def job_count(self, job):
        return 0


def test_diagnose_without_flags_launches_only_a_rows_and_never_stages(tmp_path, monkeypatch, capsys):
    h = DiagHarness(tmp_path)
    monkeypatch.setattr(n2, 'stage_toolchain', lambda *a: pytest.fail('staged without the flag'))
    assert n2.diagnose(h, {n2.DIAG}, ADMITTED) == 2
    assert [t for t, _, _ in h.launches] == ['diag-a1', 'diag-a2']
    assert all(not any('toolchain' in p or 'System32' in p for p in ro) for _, ro, _ in h.launches)
    out = capsys.readouterr().out
    assert 'B1 SKIPPED not authorized (--allow-image-copy)' in out and 'C2 SKIPPED not authorized' in out


def test_diagnose_with_image_flag_stages_once_and_adds_only_the_toolchain_grant(tmp_path, monkeypatch):
    h = DiagHarness(tmp_path)
    staged = []
    monkeypatch.setattr(n2, 'stage_toolchain', lambda src, folder: staged.append((src, folder)) or ('ab', 'x'))
    n2.diagnose(h, {n2.DIAG, n2.IMAGE_FLAG}, ADMITTED)
    k = os.path.join(h.lay['root'], 'toolchain')
    assert staged == [(CMD, k)]
    assert [t for t, _, _ in h.launches] == ['diag-a1', 'diag-a2', 'diag-b1', 'diag-b2']
    b1 = [ro for t, ro, _ in h.launches if t == 'diag-b1'][0]
    assert b1[-1] == k and not any('System32' in p for _, ro, _ in h.launches for p in ro)


def test_a_refused_grant_leaves_the_c_rows_unlaunched_and_the_a_and_b_rows_run(tmp_path, monkeypatch, capsys):
    h = DiagHarness(tmp_path)
    monkeypatch.setattr(n2, 'stage_toolchain', lambda *a: ('ab', 'x'))
    assert n2.diagnose(h, {n2.DIAG, n2.IMAGE_FLAG, n2.SYSTEM_FLAG}, REFUSED) == 2
    assert [t for t, _, _ in h.launches] == ['diag-a1', 'diag-a2', 'diag-b1', 'diag-b2']
    out = capsys.readouterr().out
    assert 'C1 not admissible' in out and 'C2 not admissible' in out and 'a second name' in out
    assert 'rows not usable (A1, A2, B1, B2, C1, C2)' in out


@pytest.mark.parametrize('exc, label', [
    (staging.StageError('a second name for x'), 'launch refused'),
    (mxc.MxcUnavailable('alias in grant: x'), 'launch refused'),
    (ValueError('bug in the diagnostic'), 'diagnostic error'),
    (TimeoutError('launcher I/O deadline'), 'diagnostic error'),
])
def test_only_admission_refusals_are_refusals_every_other_exception_is_a_diagnostic_error(
        tmp_path, capsys, exc, label):
    h = DiagHarness(tmp_path)
    go = h.go

    def fail_a1(tag, *a, **kw):
        if tag == 'diag-a1':
            raise exc
        return go(tag, *a, **kw)
    h.go = fail_a1
    assert n2.diagnose(h, {n2.DIAG}, ADMITTED) == 2
    assert [t for t, _, _ in h.launches] == ['diag-a2']
    out = capsys.readouterr().out
    assert 'A1 %s' % label in out and 'rows not usable (A1' in out
    assert type(exc).__name__ in out and str(exc) in out
    if label == 'diagnostic error':
        assert 'in phase setup' in out


def test_a_failure_while_reading_evidence_is_a_diagnostic_error_in_the_evidence_phase(tmp_path, monkeypatch, capsys):
    h = DiagHarness(tmp_path)

    def boom(path):
        raise staging.StageError('unreadable entry: x')
    monkeypatch.setattr(n2, 'look_at', boom)
    assert n2.diagnose(h, {n2.DIAG}, ADMITTED) == 2
    out = capsys.readouterr().out
    assert 'A1 diagnostic error' in out and 'in phase evidence' in out and 'launch refused' not in out


def test_a_budget_overrun_still_stops_the_matrix_and_keeps_what_was_recorded(tmp_path):
    h = DiagHarness(tmp_path)

    def over(*a, **kw):
        raise n2.SetupError('time budget exceeded')
    h.go = over
    with pytest.raises(n2.SetupError):
        n2.diagnose(h, {n2.DIAG}, ADMITTED)
    assert os.path.isfile(os.path.join(h.lay['root'], n2.RESULTS))


def test_the_run_leaves_one_json_record_of_every_row(tmp_path):
    h = DiagHarness(tmp_path)
    n2.diagnose(h, {n2.DIAG}, ADMITTED)
    doc = json.load(open(os.path.join(h.lay['root'], n2.RESULTS), encoding='utf-8'))
    assert doc['system32'] == ADMITTED
    assert [r['row'] for r in doc['rows']] == ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    first = doc['rows'][0]
    assert first['label'] == 'control failed' and first['launcher_rc'] == 0
    assert set(first['evidence']) == {'ev', 'child'} and first['precheck'] is None
    assert doc['rows'][1]['label'] == 'control failed' and doc['rows'][2]['label'] == 'not authorized'
    assert 'interpretation' in doc


def test_the_c_rows_carry_the_precheck_result_in_the_record(tmp_path, monkeypatch):
    h = DiagHarness(tmp_path)
    monkeypatch.setattr(n2, 'stage_toolchain', lambda *a: ('ab', 'x'))
    n2.diagnose(h, {n2.DIAG, n2.IMAGE_FLAG, n2.SYSTEM_FLAG}, REFUSED)
    doc = json.load(open(os.path.join(h.lay['root'], n2.RESULTS), encoding='utf-8'))
    c1 = [r for r in doc['rows'] if r['row'] == 'C1'][0]
    assert c1['label'] == 'not admissible' and c1['precheck'] == REFUSED and c1['launcher_rc'] is None


def test_a_failed_results_write_is_reported_and_never_replaces_the_setup_error_in_flight(tmp_path, capsys):
    h = DiagHarness(tmp_path)
    open(os.path.join(h.lay['root'], n2.RESULTS), 'wb').close()

    def over(*a, **kw):
        raise n2.SetupError('time budget exceeded')
    h.go = over
    with pytest.raises(n2.SetupError, match='time budget exceeded'):
        n2.diagnose(h, {n2.DIAG}, ADMITTED)
    assert any(line.startswith('pv20 N2 results not written: FileExistsError')
               for line in capsys.readouterr().out.splitlines())


def test_a_failed_results_write_after_a_clean_run_makes_diagnose_return_three(tmp_path, capsys):
    h = DiagHarness(tmp_path)
    open(os.path.join(h.lay['root'], n2.RESULTS), 'wb').close()
    assert n2.diagnose(h, {n2.DIAG}, ADMITTED) == 3
    assert any(line.startswith('pv20 N2 results not written: FileExistsError')
               for line in capsys.readouterr().out.splitlines())


def test_an_existing_results_file_is_refused_and_its_bytes_are_kept(tmp_path, capsys):
    h = DiagHarness(tmp_path)
    path = os.path.join(h.lay['root'], n2.RESULTS)
    with open(path, 'wb') as fh:
        fh.write(b'OLD')
    assert n2.diagnose(h, {n2.DIAG}, ADMITTED) == 3
    with open(path, 'rb') as fh:
        assert fh.read() == b'OLD'
    assert any(line.startswith('pv20 N2 results not written: FileExistsError')
               for line in capsys.readouterr().out.splitlines())


def test_a_non_ascii_user_name_is_redacted_before_json_escapes_it(tmp_path, monkeypatch):
    monkeypatch.setattr(common, '_username', lambda: 'Zo\u00eb')
    n2.write_results(str(tmp_path), {'interpretation': 'run by Zo\u00eb',
                                     'rows': [{'error': 'C:\\Users\\Zo\u00eb\\x'}]})
    with open(os.path.join(str(tmp_path), n2.RESULTS), encoding='utf-8') as fh:
        text = fh.read()
    assert 'Zo\u00eb' not in text and 'Zo\\u00eb' not in text
    assert text.count('[REDACTED-USER]') == 2


def _plain_tree(tmp_path):
    tree = tmp_path / 'System32'
    tree.mkdir()
    (tree / 'a.dll').write_bytes(b'x')
    return tree


def _scans():
    return linkscan.check_grants, staging.scan_grants, staging.StageError


def test_grant_admission_refuses_a_second_name_and_names_the_file(tmp_path):
    tree = _plain_tree(tmp_path)
    os.link(str(tree / 'a.dll'), str(tree / 'b.dll'))
    reason = n2.grant_admission(str(tree), *_scans())
    assert reason is not None and 'second name' in reason and 'a.dll' in reason


def test_grant_admission_refuses_a_reparse_entry_through_the_lstat_seam(tmp_path, monkeypatch):
    tree = _plain_tree(tmp_path)
    (tree / 'sub').mkdir()
    (tree / 'sub' / 'f.dll').write_bytes(b'x')
    real, marked = os.lstat, os.path.normcase(str(tree / 'sub'))

    def lstat(p, *a, **k):
        st = real(p, *a, **k)
        if os.path.normcase(os.fspath(p)) == marked:
            return SimpleNamespace(st_mode=st.st_mode, st_nlink=st.st_nlink, st_file_attributes=0x400)
        return st
    monkeypatch.setattr(os, 'lstat', lstat)
    reason = n2.grant_admission(str(tree), *_scans())
    assert reason is not None and 'alias' in reason and 'sub' in reason


def test_grant_admission_admits_a_plain_tree(tmp_path):
    assert n2.grant_admission(str(_plain_tree(tmp_path)), *_scans()) is None


def test_grant_admission_runs_the_two_production_scans_in_launch_order_and_stops_at_the_first_refusal():
    calls = []

    def check(roots, error):
        calls.append(('check', roots))

    def scan(grants):
        calls.append(('scan', grants))
    assert n2.grant_admission(r'C:\Windows\System32', check, scan, ValueError) is None
    assert calls == [('check', (r'C:\Windows\System32',)), ('scan', (r'C:\Windows\System32',))]

    calls.clear()

    def refuse(roots, error):
        raise error('multiple links in grant (a second name): a.dll')
    assert 'a.dll' in n2.grant_admission(r'C:\Windows\System32', refuse, scan, ValueError)
    assert calls == []

    def unreadable(grants):
        raise PermissionError(13, 'Access is denied', r'C:\Windows\System32\config')
    reason = n2.grant_admission(r'C:\Windows\System32', check, unreadable, ValueError)
    assert reason == 'grant scan failed: PermissionError'


def _fresh_isolation(monkeypatch):
    real = n2.import_isolated
    monkeypatch.setattr(n2, 'import_isolated', lambda modules, home: real(modules, home, loaded={}))


def test_system32_admission_reports_the_production_refusal_for_a_linked_tree(tmp_path, monkeypatch):
    _fresh_isolation(monkeypatch)
    windows = tmp_path
    _plain_tree(windows)
    os.link(str(windows / 'System32' / 'a.dll'), str(windows / 'System32' / 'b.dll'))
    result = n2.system32_admission(str(windows), str(tmp_path))
    assert result['admitted'] is False and 'a.dll' in result['reason']
    assert result['path'] == ntpath.join(str(windows), 'System32')


def test_system32_admission_admits_a_plain_tree(tmp_path, monkeypatch):
    _fresh_isolation(monkeypatch)
    windows = tmp_path
    _plain_tree(windows)
    assert n2.system32_admission(str(windows), str(tmp_path)) == {
        'path': ntpath.join(str(windows), 'System32'), 'admitted': True, 'reason': None}


def _fake_ref(closed, name, exc=None):
    class Ref:
        def close(self):
            closed.append(name)
            if exc is not None:
                raise exc
    return Ref()


def test_wind_down_closes_every_job_even_when_one_close_raises(tmp_path, capsys):
    h = n2.Harness(str(tmp_path), 'src', r'C:\Windows', n2.Budget(10))
    closed = []
    h.jobs = [_fake_ref(closed, 'a', OSError('x')), _fake_ref(closed, 'b'),
              _fake_ref(closed, 'c', RuntimeError('y'))]
    assert h.wind_down() == 2
    assert closed == ['a', 'b', 'c']
    assert 'Job 1 could not be closed' in capsys.readouterr().out


def test_wind_down_still_closes_the_rest_when_interrupted(tmp_path):
    h = n2.Harness(str(tmp_path), 'src', r'C:\Windows', n2.Budget(10))
    closed = []
    h.jobs = [_fake_ref(closed, 'a', KeyboardInterrupt()), _fake_ref(closed, 'b')]
    assert h.wind_down() == 1
    assert closed == ['a', 'b']


def test_wind_down_checks_every_launcher_even_when_one_check_raises(tmp_path, monkeypatch, capsys):
    h = n2.Harness(str(tmp_path), 'src', r'C:\Windows', n2.Budget(10))
    h.api = SimpleNamespace(created=[(1, 'c1'), (2, 'c2')])
    checked = []

    def wait_dead(pid, ctime, seconds):
        checked.append(pid)
        if pid == 1:
            raise OSError('query failed')
        return True
    monkeypatch.setattr(h, 'wait_dead', wait_dead)
    assert h.wind_down() == 1
    assert checked == [1, 2]
    assert 'launcher 1 could not be checked: OSError query failed' in capsys.readouterr().out


@pytest.mark.parametrize('admission, code', [(ADMITTED, 0), (REFUSED, 2)])
def test_diag_precheck_runs_only_the_precheck_and_creates_nothing(tmp_path, monkeypatch, admission, code):
    parent = tmp_path / 'fx'
    parent.mkdir()
    monkeypatch.setattr(n2, 'parent_ok', lambda p: True)
    monkeypatch.setattr(n2, '_on_windows', lambda: True)
    monkeypatch.setattr(n2, '_system_ok', lambda v: True)
    monkeypatch.setenv('SystemRoot', 'C:\\Windows')
    seen = []
    monkeypatch.setattr(n2, 'system32_admission', lambda root, p: seen.append((root, p)) or admission)
    for name in ('safe_root', 'Harness', 'diagnose', 'run'):
        monkeypatch.setattr(n2, name, lambda *a, _n=name, **k: pytest.fail(_n + ' called'))
    assert n2.main([str(parent), n2.DIAG_PRECHECK]) == code
    assert seen == [('C:\\Windows', str(parent))]
    assert not os.path.exists(os.path.join(str(parent), 'run'))


def test_a_diagnostic_run_takes_the_system32_admission_before_any_root_and_before_any_row(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all)
    events = []
    monkeypatch.setattr(n2, 'system32_admission', lambda r, p: events.append('admission') or ADMITTED)
    monkeypatch.setattr(n2, 'safe_root', lambda p: events.append('root') or root)
    monkeypatch.setattr(n2, 'diagnose', lambda h, flags, adm: events.append('diagnose') or 2)
    assert n2.main([parent, n2.DIAG]) == 2
    assert events == ['admission', 'root', 'diagnose']


def _plain_info(mode, attrs=0):
    return SimpleNamespace(st_mode=mode, st_file_attributes=attrs)


def test_stage_copies_the_bytes_and_refuses_links_and_reparse_points(tmp_path):
    src, folder = tmp_path / 'cmd.exe', tmp_path / 'toolchain'
    src.write_bytes(b'MZ-fake-cmd')
    folder.mkdir()
    digest, dst = n2.stage_toolchain(str(src), str(folder))
    assert open(dst, 'rb').read() == b'MZ-fake-cmd' and len(digest) == 64
    (folder / 'cmd.exe').unlink()

    real = {str(src): os.lstat(str(src)), str(folder): os.lstat(str(folder))}
    fakes = ({str(src): _plain_info(stat.S_IFREG, 0x400)}, {str(src): _plain_info(stat.S_IFLNK)},
             {str(folder): _plain_info(stat.S_IFLNK)}, {str(folder): _plain_info(stat.S_IFREG)})
    for fake in fakes:
        lstat = lambda p, fake=fake: fake.get(p, real[p])
        with pytest.raises(n2.SetupError):
            n2.stage_toolchain(str(src), str(folder), lstat=lstat)
        assert not (folder / 'cmd.exe').exists()


def test_stage_refuses_a_copy_whose_hash_differs():
    assert n2.verify_copy(b'abc', b'abc') == n2.verify_copy(b'abc', b'abc')
    with pytest.raises(n2.SetupError):
        n2.verify_copy(b'abc', b'abd')
