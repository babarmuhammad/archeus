"""T-841 — hand-mutant pins for `archeus/node/local.py` lines 650-1300.

Each test here names one condition of that range which no existing test of the
repo fails when the condition is inverted, removed or loosened; the twenty
verdicts (COVERED / UNCOVERED) are the T-841 report. Git is never reached and no
child is started: every `proc.git`, `proc.run` and store seam is answered by a
recording fake, and the module's own guard below turns any attempt to reach the
real Git or `Popen` into a failure of the test that tried.
"""

import hashlib
import os
import subprocess
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import LocalNode, StoreError

OK = SimpleNamespace(returncode=0, stdout='', stderr='')
SHA = 'a' * 40


def _done(stdout=''):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr='')


@pytest.fixture(autouse=True)
def no_git_and_no_child(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('a T-841 pin reached the real Git: %r' % (a[:1] or k,))
    monkeypatch.setattr(local, '_git_exe', boom)
    local._VERSION.clear()
    monkeypatch.setattr(subprocess, 'Popen',
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError('a T-841 pin started a child process')))
    yield
    local._VERSION.clear()


def _fake_git(monkeypatch, answer):
    asked = []

    def git(args, cwd, timeout=15):
        asked.append(list(args))
        return answer(list(args)) if callable(answer) else answer
    monkeypatch.setattr(local.proc, 'git', git)
    return asked


def _fake_run(monkeypatch, results):
    asked = []

    def run(args, *, cwd=None, env=None, timeout=30, stdin=None, check=False):
        asked.append(list(args))
        return results.pop(0) if isinstance(results, list) else results
    monkeypatch.setattr(local.proc, 'run', run)
    return asked


# ── git_branch: only a real branch is a branch (local.py:731) ─────────────────

@pytest.mark.parametrize('out,want', [('feature/x\n', 'feature/x'), ('main', 'main'),
                                      ('HEAD\n', None), ('\n', None), ('  \n', None),
                                      ('', None), (None, None)],
                         ids=['branch', 'stripped', 'detached', 'newline', 'spaces',
                              'empty', 'git-failed'])
def test_git_branch_answers_only_a_named_branch(monkeypatch, out, want):
    asked = _fake_git(monkeypatch, lambda a: out)
    assert LocalNode.git_branch('wd') == want
    assert asked == [['rev-parse', '--abbrev-ref', 'HEAD']]


def test_git_branch_asks_nothing_without_a_workdir(monkeypatch):
    asked = _fake_git(monkeypatch, 'main')
    assert LocalNode.git_branch(None) is None and LocalNode.git_branch('') is None
    assert asked == []


# ── git_remotes: each url form, and the first line of a remote wins (744-745) ─

REMOTES = ('origin\tgit@host-one.example:org/repo.git (fetch)\n'
           'origin\thttps://user@host-two.example:8080/org/repo.git (push)\n'
           'backup\thttps://host-three.example/org/repo.git (fetch)\n'
           'dl\tdl-user@host-four.example:org/x//y (fetch)\n'
           'plain\tweird (fetch)\n'
           'odd\t:8080/x (fetch)\n'
           'loner\n')


def test_git_remotes_reads_scp_and_url_forms_and_keeps_the_first(monkeypatch):
    _fake_git(monkeypatch, REMOTES)
    assert LocalNode.git_remotes('wd') == {'origin': 'host-one.example',
                                           'backup': 'host-three.example',
                                           'dl': 'host-four.example',
                                           'plain': 'weird', 'odd': None}
    assert LocalNode.git_remotes(None) == {}


# ── diff_stat: thirty stripped lines, never more (local.py:763) ───────────────

def test_diff_stat_is_thirty_stripped_lines_at_most(monkeypatch, tmp_path):
    out = ''.join(' f%02d.py | 1 +\n\n' % i for i in range(35))
    _fake_git(monkeypatch, out)
    assert LocalNode.diff_stat(str(tmp_path)) == ['f%02d.py | 1 +' % i for i in range(30)]


@pytest.mark.parametrize('workdir', [None, ''], ids=['none', 'empty'])
def test_diff_stat_reads_nothing_for_a_missing_workdir(monkeypatch, workdir):
    asked = _fake_git(monkeypatch, ' a.py | 1 +\n')
    assert LocalNode.diff_stat(workdir) == [] and asked == []


def test_diff_stat_of_a_folder_that_is_there_but_says_nothing(monkeypatch, tmp_path):
    _fake_git(monkeypatch, None)
    assert LocalNode.diff_stat(str(tmp_path)) == []


# ── add_worktree: a failed git is a refusal, not a path (local.py:818) ────────

def test_add_worktree_refuses_when_git_says_no(monkeypatch, tmp_path):
    _fake_git(monkeypatch, None)
    path = str(tmp_path / 'wt' / 'task')
    _fake_run(monkeypatch, SimpleNamespace(returncode=128, stdout='', stderr='fatal: nope'))
    with pytest.raises(OSError, match='worktree add failed: fatal: nope'):
        LocalNode.add_worktree(str(tmp_path), path, 'task.k')
    assert not os.path.exists(path)


def test_add_worktree_refuses_when_git_cannot_even_run(monkeypatch, tmp_path):
    _fake_git(monkeypatch, None)
    asked = _fake_run(monkeypatch, None)
    with pytest.raises(OSError, match='no git'):
        LocalNode.add_worktree(str(tmp_path), str(tmp_path / 'wt' / 't2'), 'task.k')
    assert asked == [['git', *local._WORKTREE, 'add', '-b', 'task.k', '--',
                      str(tmp_path / 'wt' / 't2'), 'HEAD']]


def test_add_worktree_takes_a_made_worktree(monkeypatch, tmp_path):
    _fake_git(monkeypatch, None)
    _fake_run(monkeypatch, OK)
    path = str(tmp_path / 'wt' / 'ok')
    assert LocalNode.add_worktree(str(tmp_path), path, 'task.k') == path


# ── remove_worktree: only what git lists, and only that (local.py:826-831) ────

def test_remove_worktree_only_touches_what_git_lists(monkeypatch, tmp_path):
    mine = str(tmp_path / 'wt')
    other = str(tmp_path / 'elsewhere')
    decoy = 'x' * len('worktree ') + other            # the target once 'worktree ' is cut

    def git(args, cwd, timeout=15):
        asked.append(list(args))
        if args[:2] == ['worktree', 'list']:
            return ('worktree %s\nHEAD 0123456789ab\nbranch refs/heads/main\n%s\n'
                    % (mine, decoy))
        return ''
    asked = []
    monkeypatch.setattr(local.proc, 'git', git)
    assert LocalNode.remove_worktree(str(tmp_path / 'root'), mine) is True
    assert asked[-1] == [*local._WORKTREE, 'remove', '--force', '--', mine]
    assert LocalNode.remove_worktree(str(tmp_path / 'root'), other) is False
    assert asked[-1][:2] == ['worktree', 'list']      # nothing removed for `other`


@pytest.mark.parametrize('listing', [None, ''], ids=['none', 'empty'])
def test_remove_worktree_trusts_only_what_git_answered(monkeypatch, listing):
    asked = _fake_git(monkeypatch, listing)
    assert LocalNode.remove_worktree('root', 'somewhere') is False
    assert all(a[:2] == ['worktree', 'list'] for a in asked)     # never a removal


# ── git_dirty: the flag follows the caller, a failed git is None (853-855) ────

@pytest.mark.parametrize('out,want', [(' M a.py\n', True), ('?? new.py\n', True),
                                      ('\n', False), ('', False), (None, None)],
                         ids=['edited', 'untracked', 'newline', 'empty', 'git-failed'])
def test_git_dirty_reports_exactly_what_git_said(monkeypatch, out, want):
    asked = _fake_git(monkeypatch, lambda a: out)
    assert LocalNode.git_dirty('wd') is want
    assert asked[-1] == ['status', '--porcelain=v1']
    assert LocalNode.git_dirty('wd', tracked_only=True) is want
    assert asked[-1] == ['status', '--porcelain=v1', '--untracked-files=no']


# ── git_numstat: whole three-field records only (local.py:896-898) ────────────

def test_git_numstat_keeps_only_whole_records(monkeypatch):
    out = '1\t2\tok.py\n-\t-\tdata.bin\n7\t0\tpa\tth.txt\nbroken\n1\t2\n'
    asked = _fake_git(monkeypatch, out)
    assert LocalNode.git_numstat('root', 'base', 'rev') == [('1', '2', 'ok.py'),
                                                            ('-', '-', 'data.bin'),
                                                            ('7', '0', 'pa\tth.txt')]
    assert asked == [['diff', '--numstat', 'base', 'rev', '--']]


def test_git_numstat_is_none_when_git_cannot_tell(monkeypatch):
    _fake_git(monkeypatch, None)
    assert LocalNode.git_numstat('root', 'base', 'rev') is None


# ── mission_worktree: an existing branch is attached, never moved (912-918) ───

def test_mission_worktree_moves_no_branch_it_did_not_make(monkeypatch, tmp_path):
    _fake_git(monkeypatch, SHA + '\n')                 # the branch exists
    asked = _fake_run(monkeypatch, OK)
    path = str(tmp_path / 'mission-wt')
    assert LocalNode.mission_worktree(str(tmp_path), path, 'm.k', 'HEAD') == path
    assert asked == [['git', *local._WORKTREE, 'add', '--', path, 'm.k']]


def test_mission_worktree_refuses_a_failed_add(monkeypatch, tmp_path):
    _fake_git(monkeypatch, SHA + '\n')
    _fake_run(monkeypatch, SimpleNamespace(returncode=1, stdout='', stderr='fatal: busy'))
    with pytest.raises(OSError, match='worktree add failed: fatal: busy'):
        LocalNode.mission_worktree(str(tmp_path), str(tmp_path / 'm2'), 'm.k', 'HEAD')


def test_mission_worktree_refuses_when_git_cannot_even_run(monkeypatch, tmp_path):
    _fake_git(monkeypatch, SHA + '\n')
    asked = _fake_run(monkeypatch, None)
    path = str(tmp_path / 'm3')
    with pytest.raises(OSError, match='no git'):
        LocalNode.mission_worktree(str(tmp_path), path, 'm.k', 'HEAD')
    assert asked == [['git', *local._WORKTREE, 'add', '--', path, 'm.k']]


# ── git_merge: a failure that conflicts with nothing is not a conflict (936) ──

class _Merge:
    def __init__(self, monkeypatch, merge, unmerged):
        self.runs, self.merge, self.unmerged = [], merge, unmerged
        monkeypatch.setattr(local.proc, 'run', self._run)
        monkeypatch.setattr(local.proc, 'git', self._git)

    def _run(self, args, **kw):
        self.runs.append(list(args))
        if 'merge' in args and '--abort' not in args:
            return self.merge
        return OK

    def _git(self, args, cwd, timeout=15):
        return self.unmerged if args[0] == 'diff' else SHA + '\n'


def test_a_merge_that_fails_with_no_conflicts_raises_after_the_abort(monkeypatch):
    m = _Merge(monkeypatch, SimpleNamespace(returncode=1, stdout='', stderr='fatal: nope'),
               '')
    with pytest.raises(OSError, match='git merge failed: fatal: nope'):
        LocalNode.git_merge('wd', SHA, 'merge it')
    assert m.runs[-1] == ['git', 'merge', '--abort']


def test_a_merge_git_could_not_run_raises(monkeypatch):
    _Merge(monkeypatch, None, None)
    with pytest.raises(OSError, match='merge could not run'):
        LocalNode.git_merge('wd', SHA, 'merge it')


def test_a_conflict_names_its_files_and_leaves_the_branch(monkeypatch):
    m = _Merge(monkeypatch, SimpleNamespace(returncode=1, stdout='', stderr=''),
               'a.py\nb.py\n')
    assert LocalNode.git_merge('wd', SHA, 'merge it') == ('conflict', ['a.py', 'b.py'])
    assert m.runs[-1] == ['git', 'merge', '--abort']


def test_a_merge_that_lands_reports_the_new_head(monkeypatch, tmp_path):
    _Merge(monkeypatch, OK, None)
    assert LocalNode.git_merge(str(tmp_path), SHA, 'merge it') == ('merged', SHA)


# ── store_read: a diff never runs a driver or a textconv (local.py:1108) ──────

def test_a_store_diff_never_runs_a_driver_or_a_textconv(monkeypatch):
    seen = []
    monkeypatch.setattr(LocalNode, 'store_open', staticmethod(lambda pid, *, workdirs: 'st'))

    def git(mode, args, *, workdirs, git_dir=None, stdin=None, timeout=120, sink=None):
        seen.append((mode, list(args), git_dir))
        return 'ok'
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(git))
    args = ['diff', 'HEAD']
    assert LocalNode.store_read('p', args, workdirs=()) == 'ok'
    assert seen == [('trusted', ['diff', '--no-ext-diff', '--no-textconv', 'HEAD'], 'st')]
    assert args == ['diff', 'HEAD']                     # the caller's list is not the target
    LocalNode.store_read('p', ['cat-file', '-t', 'x'], workdirs=())
    assert seen[-1] == ('trusted', ['cat-file', '-t', 'x'], 'st')     # only a diff changes


# ── store_fetch: HEAD is a source rev Core may name (local.py:1119) ───────────

@pytest.mark.parametrize('rev_name', ['HEAD', 'refs/heads/main', 'heads/main'],
                         ids=['head', 'full-ref', 'unqualified'])
def test_only_the_shapes_core_describes_start_a_fetch(monkeypatch, tmp_path, rev_name):
    monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
    sources = []
    monkeypatch.setattr(local, '_source', lambda root, workdirs: sources.append(root) or 'gd')

    def opened(pid, *, workdirs):
        raise StoreError('reached-the-store')
    monkeypatch.setattr(LocalNode, 'store_open', staticmethod(opened))
    root = str(tmp_path / 'src')
    want = 'not a fetch Core may make' if rev_name == 'heads/main' else 'reached-the-store'
    with pytest.raises(StoreError, match=want):
        LocalNode.store_fetch(ids.new_id('project'), root, rev_name, '0' * 40,
                              'refs/archeus/exec/e1/seed', workdirs=())
    assert sources == ([] if want == 'not a fetch Core may make' else [root])


# ── import_workspace: nothing is believed before it is read back (1222-1224) ───

BLOB_TWO = hashlib.sha1(b'blob 4\0two\n').hexdigest()
BLOB_NEW = hashlib.sha1(b'blob 4\0new\n').hexdigest()
REV, TREE = 'b' * 40, 'c' * 40


def _import_fakes(monkeypatch, tmp_path, commit=None, back_extra=b'', ref_exists=False):
    """`store_git` answered by hand around one workspace of two four-byte files."""
    eid = ids.new_id('execution')
    work = paths.ExecPaths(eid).work
    os.makedirs(work)
    for name, data in (('a.txt', b'two\n'), ('new.txt', b'new\n')):
        with open(os.path.join(work, name), 'wb') as f:
            f.write(data)
    ref = local._import_ref(eid)
    seed_recs = b'100644 blob ' + BLOB_TWO.encode() + b' 4\ta.txt\0'
    back = b''.join(b'%s blob %s 4\t%s\0' % (m.encode(), o.encode(), p.encode())
                    for p, (m, o) in sorted({'a.txt': ('100644', BLOB_TWO),
                                             'new.txt': ('100644', BLOB_NEW)}.items()))
    calls = []

    def git(mode, args, *, workdirs, git_dir=None, stdin=None, timeout=120, sink=None):
        calls.append((mode, tuple(args)))
        if args[0] == 'rev-parse' and args[-1] == ref:
            if ref_exists:
                return REV + '\n'
            raise StoreError('git rev-parse failed: nothing there')
        if args[0] == 'ls-tree' and args[-1] == SHA:
            sink.feed(seed_recs)
        elif args[0] == 'fast-import':
            assert mode == 'import' and stdin is not None
            for _chunk in stdin:
                pass
        elif args[0] == 'rev-parse':
            return REV + '\n'
        elif args[0] == 'cat-file':
            return 'tree %s\nparent %s\n\nthe workspace\n' % (TREE, SHA) if commit is None \
                else commit
        else:
            sink.feed(back + back_extra)
        sink.end()
        return ''
    monkeypatch.setattr(LocalNode, 'store_git', staticmethod(git))
    monkeypatch.setattr(LocalNode, 'store_open', staticmethod(lambda pid, *, workdirs: 'st'))
    return eid, calls


def test_an_import_that_is_read_back_as_sent_is_recorded(monkeypatch, tmp_path):
    eid, calls = _import_fakes(monkeypatch, tmp_path)
    got = LocalNode.import_workspace('p', eid, SHA, workdirs=())
    assert (got['revision'], got['tree']) == (REV, TREE)
    assert got['files_changed'] == ['A new.txt'] and got['deleted'] == 0
    assert calls[0][1][:3] == ('rev-parse', '--verify', '-q')


def test_an_import_ref_that_exists_already_is_never_written_again(monkeypatch, tmp_path):
    eid, calls = _import_fakes(monkeypatch, tmp_path, ref_exists=True)
    with pytest.raises(StoreError, match='exists already'):
        LocalNode.import_workspace('p', eid, SHA, workdirs=())
    assert len(calls) == 1                              # nothing was sent after the look


@pytest.mark.parametrize('what', ['two-parents', 'no-parent', 'no-tree', 'extra', 'changed'],
                         ids=['two-parents', 'no-parent', 'no-tree', 'extra', 'changed'])
def test_an_import_that_is_not_what_core_sent_is_refused(monkeypatch, tmp_path, what):
    extra = {'two-parents': ('tree %s\nparent %s\nparent %s\n\nx\n' % (TREE, SHA, 'd' * 40), b''),
             'no-parent': ('tree %s\n\nx\n' % TREE, b''),
             'no-tree': ('parent %s\n\nx\n' % SHA, b''),
             'extra': (None, b'100644 blob ' + BLOB_NEW.encode() + b' 4\tghost.txt\0'),
             'changed': (None, b'100755 blob ' + BLOB_NEW.encode() + b' 4\tnew.txt\0')}[what]
    eid, _calls = _import_fakes(monkeypatch, tmp_path, commit=extra[0], back_extra=extra[1])
    with pytest.raises(StoreError, match='is not what Core sent'):
        LocalNode.import_workspace('p', eid, SHA, workdirs=())
