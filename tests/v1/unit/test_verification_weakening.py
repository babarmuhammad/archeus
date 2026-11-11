"""T-1067: the advisory test-weakening detector (`evidence.weakening`,
`evidence.weakening_check`): what a diff does to the tests it touches, recorded as
a `git` check that informs the review and never decides the verdict.

The parser and the table are pure and tested over hand-written `git diff -U0`
text; one test runs the real `LocalNode.git_diff` over a throwaway repository so
the text the parser reads is the text Git writes.
"""

import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from archeus.core.application import verification as V
from archeus.core.verification import evidence
from archeus.core.verification.worker import VerifyWorker
from archeus.node.local import LocalNode
from claude_sessions import proc

BASE, REV = 'a' * 40, 'b' * 40


def _diff(path, *hunks, deleted=False, new=False):
    """A `git diff -U0` of one file; each hunk is (removed lines, added lines)."""
    head = ['diff --git a/%s b/%s' % (path, path)]
    head.append('deleted file mode 100644' if deleted else 'new file mode 100644' if new
                else 'index 1111111..2222222 100644')
    head += ['--- a/%s' % path if not new else '--- /dev/null',
             '+++ b/%s' % path if not deleted else '+++ /dev/null']
    body = []
    for removed, added in hunks:
        body.append('@@ -1,%d +1,%d @@' % (len(removed), len(added)))
        body += ['-' + r for r in removed] + ['+' + a for a in added]
    return '\n'.join(head + body) + '\n'


def _find(path, *hunks, **kw):
    return evidence.weakening(_diff(path, *hunks, **kw))


# ── Python test shapes ──

def test_a_deleted_test_file_is_one_finding_not_one_per_test():
    d = _diff('tests/test_a.py', (['def test_a():', '    assert 1'], []), deleted=True)
    assert evidence.weakening(d) == ['test file deleted: tests/test_a.py']


def test_a_removed_test_function_is_named_and_a_moved_one_is_not():
    gone = _find('tests/test_a.py', (['def test_old():', '    pass'], []))
    assert gone == ['test removed: tests/test_a.py::test_old']
    d = (_diff('tests/test_a.py', (['def test_moved():'], []))
         + _diff('tests/test_b.py', ([], ['def test_moved():']), new=False))
    assert evidence.weakening(d) == []


def test_a_renamed_test_is_not_a_removed_one():
    assert _find('tests/test_a.py', (['def test_old():'], ['def test_new():'])) == [
        'test removed: tests/test_a.py::test_old']      # the name is gone: say so
    assert _find('tests/test_a.py', (['async def test_x():'], ['async def test_x(rig):'])) == []


def test_assertions_removed_are_counted_net_per_file():
    one = _find('tests/test_a.py', (['    assert a == 1', '    assert b == 2'],
                                    ['    assert a == 1']))
    assert one == ['assertions removed: tests/test_a.py (1 net)']
    rewritten = _find('tests/test_a.py', (['    assert a == 1', '    self.assertEqual(b, 2)'],
                                          ['    assert a == 1', '    assert b == 2']))
    assert rewritten == []
    assert _find('tests/test_a.py', (['    with pytest.raises(ValueError):'], [])) == [
        'assertions removed: tests/test_a.py (1 net)']


@pytest.mark.parametrize('marker', [
    '@pytest.mark.skip(reason="flaky")', '@pytest.mark.skipif(sys.platform == "win32")',
    '@pytest.mark.xfail', '    pytest.skip("later")', '    pytest.xfail("later")',
    '@unittest.skip("x")', '@unittest.expectedFailure'])
def test_every_python_off_switch_is_a_finding(marker):
    (f,) = _find('tests/test_a.py', ([], [marker]))
    assert f.startswith('skip/xfail/only marker added: tests/test_a.py: ')


def test_a_marker_that_was_already_there_is_not_added():
    line = '@pytest.mark.xfail'
    assert _find('tests/test_a.py', ([line], [line])) == []


def test_a_raised_timeout_or_threshold_is_a_finding_and_a_lowered_one_is_not():
    up = _find('tests/test_a.py', (['    wait(timeout_s=5)'], ['    wait(timeout_s=60)']))
    assert up == ['timeout raised: tests/test_a.py (5 -> 60)']
    assert _find('tests/test_a.py', (['    TOLERANCE = 0.01'], ['    TOLERANCE = 0.5'])) == [
        'tolerance raised: tests/test_a.py (0.01 -> 0.5)']
    assert _find('tests/test_a.py', (['    wait(timeout_s=60)'], ['    wait(timeout_s=5)'])) == []
    assert _find('tests/test_a.py', (['    wait(timeout_s=5)'], ['    wait(patience=60)'])) == []


# ── TypeScript test shapes ──

def test_typescript_tests_are_told_by_their_file_and_their_it_calls():
    path = 'clients/app/test/notify.test.ts'
    assert _find(path, (["it('shows a toast', () => {", '  expect(x).toBe(1)'], [])) == [
        'test removed: %s::shows a toast' % path, 'assertions removed: %s (1 net)' % path]
    assert _find('src/notify.ts', (["it('shows a toast', () => {"], [])) == []


@pytest.mark.parametrize('marker', [
    "it.only('a', () => {", "describe.skip('a', () => {", "test.todo('a')", "xit('a', f)",
    "fdescribe('a', f)", "it.concurrent.skip('a', f)"])
def test_every_typescript_off_switch_is_a_finding(marker):
    (f,) = _find('src/a.spec.tsx', ([], [marker]))
    assert f.startswith('skip/xfail/only marker added: src/a.spec.tsx: ')


def test_a_typescript_timeout_raised_in_an_options_object_is_a_finding():
    up = _find('test/a.test.js', (['  { timeout: 5_000 }'], ['  { timeout: 30_000 }']))
    assert up == ['timeout raised: test/a.test.js (5000 -> 30000)']


# ── what is not a test, and what the parser must not mistake ──

def test_a_file_that_is_not_a_test_is_never_read():
    d = _diff('archeus/core/a.py', (['    assert x', 'def test_not_a_test():'],
                                    ['@pytest.mark.skip', 'timeout=1']))
    assert evidence.weakening(d) == []
    assert evidence.weakening('') == []


def test_a_removed_line_that_looks_like_a_header_is_a_line():
    d = ('diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n'
         '+++ b/tests/test_a.py\n@@ -1,2 +1,0 @@\n--- a/comment\n-    assert x\n')
    assert evidence.weakening(d) == ['assertions removed: tests/test_a.py (1 net)']


def test_findings_follow_the_order_of_the_diff():
    d = (_diff('tests/test_b.py', (['def test_b():'], []))
         + _diff('tests/test_a.py', (['def test_a():'], [])))
    assert evidence.weakening(d) == ['test removed: tests/test_b.py::test_b',
                                     'test removed: tests/test_a.py::test_a']


def test_a_long_test_name_or_marker_line_is_clipped():
    name = 'test_' + 'x' * 200
    (f,) = _find('tests/test_a.py', (['def %s():' % name], []))
    assert len(f) < 130 and f.endswith('...')
    (g,) = _find('tests/test_a.py', ([], ['@pytest.mark.skip(reason="%s")' % ('y' * 200)]))
    assert len(g) < 150 and g.endswith('...')


def test_a_quoted_header_with_an_invalid_escape_is_read_as_its_text_and_still_reported():
    head = ('diff --git "a/tests/evil\\xz.py" "b/tests/evil\\xz.py"\n'
            'index 1111111..2222222 100644\n'
            '--- "a/tests/evil\\xz.py"\n+++ "b/tests/evil\\xz.py"\n'
            '@@ -1,1 +0,0 @@\n-    assert one()\n')
    assert evidence.weakening(head) == ['assertions removed: tests/evil\\xz.py (1 net)']


# ── the check ──

class _Node:
    def __init__(self, diff):
        self.diff, self.asked = diff, []

    def git_diff(self, *a):
        self.asked.append(a)
        return self.diff


def test_a_change_that_leaves_the_tests_alone_records_nothing():
    node = _Node(_diff('archeus/a.py', (['x'], ['y'])))
    assert evidence.weakening_check(node, 'root', BASE, REV) is None
    assert node.asked == [('root', BASE, REV, evidence._DIFF_BYTES)]


def test_a_finding_is_a_passing_git_check_with_its_findings():
    node = _Node(_diff('tests/test_a.py', (['def test_a():'], [])))
    c = evidence.weakening_check(node, 'root', BASE, REV)
    assert c == {'name': evidence.WEAKENING, 'kind': 'git', 'result': 'pass',
                 'detail': '1 finding(s), advisory',
                 'findings': ['test removed: tests/test_a.py::test_a']}


def test_the_recorded_findings_are_capped_but_the_detail_counts_them_all():
    d = ''.join(_diff('tests/test_%d.py' % i, (['def test_x():'], []), deleted=True)
                for i in range(60))
    c = evidence.weakening_check(_Node(d), 'root', BASE, REV)
    assert c['detail'] == '60 finding(s), advisory\nReport cut: 10 finding(s) omitted.'
    assert len(c['findings']) == 50


def test_rendered_paths_have_a_utf8_byte_cap_and_count_omitted_bytes():
    path = 'tests/' + '\u00e9' * 1000 + '/test_a.py'
    finding, = evidence.weakening(_diff(path, (['def test_a():'], [])))
    rendered = finding.removeprefix('test removed: ').removesuffix('::test_a')
    assert len(rendered.encode('utf-8')) <= evidence._PATH_BYTES
    assert 'path cut:' in rendered and 'bytes omitted]' in rendered
    prefix, omitted = rendered.split('... [path cut: ')
    assert int(omitted.split()[0]) == len(path.encode('utf-8')) - len(prefix.encode('utf-8'))


def test_rendered_report_has_a_total_byte_cap_and_counts_dropped_findings():
    import json
    d = ''.join(_diff('tests/' + '\u00e9' * 200 + '/test_%d.py' % i,
                     (['def test_' + 'x' * 100 + '():'], [])) for i in range(50))
    c = evidence.weakening_check(_Node(d), 'root', BASE, REV)
    assert len(json.dumps(c, ensure_ascii=False).encode('utf-8')) <= evidence._REPORT_BYTES
    omitted = 50 - len(c['findings'])
    assert omitted > 0
    assert c['detail'].endswith('\nReport cut: %d finding(s) omitted.' % omitted)


def test_cut_diff_never_reads_past_cap_or_silently_reports_nothing(monkeypatch):
    prefix = _diff('src/a.py', (['x'], ['y']))
    suffix = _diff('tests/test_a.py', (['def test_a():'], []))
    monkeypatch.setattr(evidence, '_DIFF_BYTES', len(prefix.encode('utf-8')))
    c = evidence.weakening_check(_Node(prefix + suffix), 'root', BASE, REV)
    assert c['result'] == 'pass' and c['detail'] == '1 finding(s), advisory'
    assert c['findings'] == [('Diff cut: %d bytes omitted; '
                              'remaining test changes were not inspected.' % len(suffix.encode('utf-8')))]


def test_cut_diff_keeps_weakening_already_seen_and_discards_partial_line(monkeypatch):
    prefix = _diff('tests/test_a.py', (['def test_a():'], []))
    partial = '+@pytest.mark.skip'
    suffix = partial + '(reason="later")\n'
    monkeypatch.setattr(evidence, '_DIFF_BYTES', len((prefix + partial).encode('utf-8')))
    c = evidence.weakening_check(_Node(prefix + suffix), 'root', BASE, REV)
    assert c['findings'][1:] == ['test removed: tests/test_a.py::test_a']
    assert c['findings'][0] == ('Diff cut: %d bytes omitted; remaining test changes were not inspected.'
                               % len(suffix.encode('utf-8')))


def test_a_diff_git_cannot_read_is_noted_and_never_an_error():
    c = evidence.weakening_check(_Node(None), 'root', BASE, REV)
    assert c['result'] == 'pass' and 'could not read the diff' in c['detail']


def test_the_advisory_check_never_changes_a_verdict():
    command = {'name': 'test: t', 'kind': 'command', 'result': 'pass'}
    weak = {'name': evidence.WEAKENING, 'kind': 'git', 'result': 'pass'}
    assert V.verdict_of([command, weak]) == 'PASSED'
    assert V.verdict_of([dict(command, result='fail'), weak]) == 'FAILED'


def test_the_worker_records_the_check_after_changes_and_only_for_a_code_change(monkeypatch):
    recorded = []
    node = SimpleNamespace(
        git_numstat=lambda *a: [('1', '1', 'tests/test_a.py')], git_head=lambda ws: REV,
        git_dirty=lambda ws, tracked_only=False: False,
        git_diff=lambda *a: _diff('tests/test_a.py', (['def test_a():'], [])))
    me = SimpleNamespace(node=node, timeout_s=1, missions=None,
                         _do=lambda fn, **kw: recorded.append(kw['checks']),
                         _with_base=lambda *a: a[6])      # the T-1068 base check is its own tests'
    task = SimpleNamespace(kind='code_change', plan_id='p')
    VerifyWorker._run_and_record(me, 'vid', None, task, 'root', 'ws', REV, BASE, [], 'v1')
    assert [c['name'] for c in recorded[0]] == ['changes', evidence.WEAKENING]
    VerifyWorker._run_and_record(me, 'vid', None, SimpleNamespace(kind='inspection', plan_id='p'),
                                 'root', 'ws', REV, BASE, [], 'v1')
    assert recorded[1] == []


# ── the real text Git writes ──

def _git(cwd, *args):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                           *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def test_over_a_real_repository_the_detector_reads_what_git_writes(tmp_path):
    root = str(tmp_path)
    _git(root, 'init', '-q')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_a.py').write_text(
        'def test_a():\n    assert f() == 1\n    assert g() == 2\n\n'
        'def test_b():\n    wait(timeout_s=5)\n')
    (tmp_path / 'tests' / 'test_gone.py').write_text('def test_gone():\n    assert 1\n')
    _git(root, 'add', '.')
    _git(root, 'commit', '-q', '-m', 'base')
    base = _git(root, 'rev-parse', 'HEAD').strip()
    (tmp_path / 'tests' / 'test_a.py').write_text(
        'import pytest\n\ndef test_a():\n    assert f() == 1\n\n'
        '@pytest.mark.skip\ndef test_b():\n    wait(timeout_s=60)\n')
    (tmp_path / 'tests' / 'test_gone.py').unlink()
    _git(root, 'add', '-A')
    _git(root, 'commit', '-q', '-m', 'weaken')
    rev = _git(root, 'rev-parse', 'HEAD').strip()
    found = evidence.weakening(LocalNode.git_diff(root, base, rev))
    assert found == ['assertions removed: tests/test_a.py (1 net)',
                     'skip/xfail/only marker added: tests/test_a.py: @pytest.mark.skip',
                     'timeout raised: tests/test_a.py (5 -> 60)',
                     'test file deleted: tests/test_gone.py']
    assert LocalNode.git_diff(root, 'nope', rev) is None


def test_git_diff_runs_no_configured_diff_or_textconv_program(monkeypatch):
    seen = []
    monkeypatch.setattr('archeus.node.local._project_git', lambda root, args, **kw: seen.append(
        (root, args)) or SimpleNamespace(returncode=0, stdout=''))
    assert LocalNode.git_diff('root', BASE, REV) == ''
    root, args = seen[0]
    assert root == 'root' and 'diff' in args
    assert {'-U0', '--no-ext-diff', '--no-textconv'} <= set(args)
    assert args[-3:] == [BASE, REV, '--']


def test_repository_config_renames_and_unicode_paths_hide_nothing(tmp_path):
    root = str(tmp_path)
    _git(root, 'init', '-q')
    _git(root, 'config', 'diff.noprefix', 'true')
    _git(root, 'config', 'diff.renames', 'true')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_a.py').write_text('def test_a():\n    assert f()\n')
    (tmp_path / 'tests' / 'test_é.py').write_text('def test_e():\n    assert g()\n',
                                                  encoding='utf-8')
    _git(root, 'add', '.')
    _git(root, 'commit', '-q', '-m', 'base')
    base = _git(root, 'rev-parse', 'HEAD').strip()
    _git(root, 'mv', 'tests/test_a.py', 'tests/helper_a.py')     # out of test discovery
    _git(root, 'rm', '-q', 'tests/test_é.py')
    _git(root, 'commit', '-q', '-m', 'hide')
    rev = _git(root, 'rev-parse', 'HEAD').strip()
    assert sorted(evidence.weakening(LocalNode.git_diff(root, base, rev))) == [
        'test file deleted: tests/test_a.py', 'test file deleted: tests/test_é.py']


def test_a_line_separator_in_an_added_line_cannot_fake_a_header():
    d = _diff('tests/test_a.py', ([], ['x = " diff --git a/b b/b"']), (['def test_a():'], []))
    assert evidence.weakening(d) == ['test removed: tests/test_a.py::test_a']


def test_a_very_long_line_is_not_read_and_a_non_test_file_keeps_no_hunks():
    long = '    assert ' + 'x' * 100000
    d = _diff('tests/test_a.py', ([long], [])) + _diff('src/a.py', ([long], ['y']))
    assert evidence.weakening(d) == ['1 changed line(s) too long to inspect: tests/test_a.py']
    assert [f['hunks'] for f in evidence._parse_diff(d)] == [[([], [])], [([], [])]]


@pytest.mark.parametrize('removed,added', [
    ([], ['@pytest.mark.skip(reason="' + 'x' * 2000 + '")']),
    (['    assert f() == 1  # ' + 'x' * 2000], [])])
def test_a_changed_test_line_too_long_to_read_is_said_never_dropped(removed, added):
    d = _diff('tests/test_a.py', (removed, added), ([], ['    assert g()', '    assert h()']))
    assert evidence.weakening(d) == ['1 changed line(s) too long to inspect: tests/test_a.py']
    c = evidence.weakening_check(_Node(d), 'root', BASE, REV)
    assert c['result'] == 'pass' and c['findings'] == evidence.weakening(d)


@pytest.mark.parametrize('header,path', [
    ('a/tests/test_a.py b/tests/test_a.py', 'tests/test_a.py'),
    ('a/tests/a b/test_x.py b/tests/a b/test_x.py', 'tests/a b/test_x.py'),
    ('"a/tests/test_\\"q\\".py" "b/tests/test_\\"q\\".py"', 'tests/test_"q".py')])
def test_a_deletion_git_shows_as_binary_is_still_a_deleted_test_file(header, path):
    d = ('diff --git %s\ndeleted file mode 100644\nindex 1111111..0000000\n'
         'Binary files a/x and /dev/null differ\n' % header)
    assert evidence.weakening(d) == ['test file deleted: ' + path]


def test_repository_config_that_calls_a_test_binary_hides_nothing(tmp_path):
    root = str(tmp_path)
    _git(root, 'init', '-q')
    _git(root, 'config', 'core.bigFileThreshold', '1')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_a.py').write_text('def test_a():\n    assert f()\n    assert g()\n')
    (tmp_path / 'tests' / 'test_gone.py').write_text('def test_gone():\n    assert 1\n')
    _git(root, 'add', '.')
    _git(root, 'commit', '-q', '-m', 'base')
    base = _git(root, 'rev-parse', 'HEAD').strip()
    (tmp_path / 'tests' / 'test_a.py').write_text('def test_a():\n    assert f()\n')
    _git(root, 'rm', '-q', 'tests/test_gone.py')
    _git(root, 'commit', '-q', '-a', '-m', 'weaken')
    rev = _git(root, 'rev-parse', 'HEAD').strip()
    assert 'Binary files' in _git(root, 'diff', base, rev)      # the rig is live
    assert evidence.weakening(LocalNode.git_diff(root, base, rev)) == [
        'assertions removed: tests/test_a.py (1 net)', 'test file deleted: tests/test_gone.py']


def test_a_cut_capture_keeps_the_weakening_before_the_cut_and_drops_the_partial_line():
    class _Cut(str):
        cut = True
    prefix = _diff('tests/test_a.py', (['def test_a():'], []))
    text = _Cut(prefix + '+@pytest.mark.skip')
    c = evidence.weakening_check(_Node(text), 'root', BASE, REV)
    assert c['findings'] == ['Diff cut: %d bytes kept; remaining test changes were not inspected.'
                             % len(prefix.encode('utf-8')),
                             'test removed: tests/test_a.py::test_a']


def test_a_capped_read_of_a_real_diff_stops_git_and_keeps_the_weakening_in_the_prefix(
        tmp_path, monkeypatch):
    root = str(tmp_path)
    _git(root, 'init', '-q')
    (tmp_path / 'README').write_text('base\n')
    _git(root, 'add', '.')
    _git(root, 'commit', '-q', '-m', 'base')
    base = _git(root, 'rev-parse', 'HEAD').strip()
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_a.py').write_text(
        'import pytest\n\n@pytest.mark.skip\ndef test_a():\n    assert 1\n')
    (tmp_path / 'zzz_big.txt').write_text('x = 1\n' * 20000)
    _git(root, 'add', '-A')
    _git(root, 'commit', '-q', '-m', 'add the skip and a large file')
    rev = _git(root, 'rev-parse', 'HEAD').strip()
    got = LocalNode.git_diff(root, base, rev, max_bytes=4096)
    assert got.cut and len(got.encode('utf-8')) <= 4096
    monkeypatch.setattr(evidence, '_DIFF_BYTES', 4096)
    c = evidence.weakening_check(LocalNode, root, base, rev)
    assert c['findings'][0].startswith('Diff cut: ') and c['findings'][0].endswith(
        'remaining test changes were not inspected.')
    assert 'skip/xfail/only marker added: tests/test_a.py: @pytest.mark.skip' in c['findings']


def test_a_child_that_keeps_writing_is_stopped_at_the_cap_and_reaped(monkeypatch):
    started = []
    real = subprocess.Popen

    def recording(*a, **kw):
        started.append(real(*a, **kw))
        return started[-1]
    monkeypatch.setattr(proc.subprocess, 'Popen', recording)
    small = proc.run_capped([sys.executable, '-c', "print('hi')"], timeout=5, max_bytes=4096)
    assert small.stdout.split() == [b'hi'] and small.cut is False and small.returncode == 0
    writer = "import sys\nfor _ in range(1024): sys.stdout.buffer.write(b'x' * 65536)\n"
    t0 = time.monotonic()
    r = proc.run_capped([sys.executable, '-c', writer], timeout=5, max_bytes=4096)
    assert r.cut is True and len(r.stdout) == 4096
    assert time.monotonic() - t0 < 2.5
    child = started[-1]
    assert child.poll() is not None and child.returncode != 0
