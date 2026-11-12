"""T-778 — the highest-risk uncovered branches of `archeus/node/local.py` lines
650-1300, as unit tests. The section is the hook mailbox, the e-stop, the git reads the
boundary checks need, the worktrees, merge-back, the checks and the store readers; the
file `test_node_local_staging_gaps.py` (T-210/T-232) already holds the seal, the fetch
gate, the import plan, the seed, the byte core, the hostile source and the e-stop, so
this file goes after what those tests never reach, refusal paths first.

What it holds, each row naming the source branch it would catch:

1  local.py:936-937   `git_merge` — a merge that failed with nothing unmerged raises;
                      it is never reported as `('conflict', …)`
2  local.py:930-931   `git_merge` — a child that could not run raises before anything
                      is asked of the worktree
3  local.py:812-815 with 884-886 — a branch is force-moved only when `merge-base
                      --is-ancestor` really ran and said yes
4  local.py:783-784, 788-789 — `end_state`: one failed read is no state at all, never
                      a digest of half of it
5  local.py:826-832   `remove_worktree` — only a path Git itself lists is removed
6  local.py:1105-1109 — `store_read`'s allowlist (no `fetch`, no `update-ref`, no
                      `ls-files`) and the diff pin against ext-diff and textconv
7  local.py:1180-1182 — `store_seed_ref` refuses a commit that is not a full id,
                      before the store is opened
8  local.py:1167-1172 — `resolve_base`: only a store refusal falls back to HEAD, and a
                      resolved branch never reads HEAD
9  local.py:730-731, 740-745 — `git_branch` (a detached HEAD is no branch) and
                      `git_remotes` (the first url wins; a host the line does not carry
                      is None, never a guess)
10 local.py:967-975, 976-982 — `run_check`: a child that outlives its kill is reported
                      as the timeout and nothing else, and `truncated` is `size > keep`

Beyond the ten: `git_snapshot`'s staged-unknown branch (872-876) and its per-step
refusals (864-868), `git_numstat` (891-899), `git_head`/`git_resolve` on whitespace
(837-847), `diff_stat`'s cap and absence rules (756-763), the untracked list's sort and
empty filter (785-787), `store_fetch`'s `REF_MAX` boundary and its four-call order
(1128-1150), `_publish_once`'s refusal of a ref naming another commit (1299-1311),
`mission_worktree`'s no-new-branch form (912-917), `run_check`'s "could not run"
answer (962-965) and `open_terminal`'s pass-through (750-754).

Style follows `test_node_local_staging_gaps.py` and `test_repo_store.py`: every OS call
is answered in-process at the seam the existing tests fake (`proc.git`, `proc.run`,
`subprocess.Popen`), a refusal is asserted together with zero calls, and a positive
control sits beside every refusal so no row can pass vacuously.
Nothing here starts a process, a Git or a thread, and nothing asserts on an operating
system's wording: fixtures are bytes with explicit newlines, paths come from `tmp_path`,
and the one platform-dependent expectation (`start_new_session`) is stated as the same
expression the source uses.
"""

import hashlib
import json
import os
import subprocess
import zlib
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.infra import paths
from archeus.node import local
from archeus.node.local import EMPTY_TREE, STORE_HEAD, LocalNode, StoreError

#: the executable every pin record names: resolved, never started
GIT = os.path.join(os.sep, 'fake', 'git', 'cmd', 'git.exe' if os.name == 'nt' else 'git')
#: the version string a pin record holds where Git is never started
VERSION = 'git version 2.50.0'
#: what `init --bare -q --object-format=sha1 --template=<empty folder>` writes (T-048)
INIT_CONFIG = (b'[core]\n\trepositoryformatversion = 0\n\tfilemode = false\n'
               b'\tbare = true\n\tsymlinks = false\n\tignorecase = true\n')
COMMIT = 'c' * 40


# ── the seams, answered in-process ───────────────────────────────────────────

@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Core's own state, inside the run's temp area: the store, its claim and its pin
    record are what the store rows below make and read, and none of them may land in
    the real `~/.archeus` of the machine reviewing this file."""
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'archeus-home'))
    return tmp_path / 'archeus-home'


@pytest.fixture(autouse=True)
def no_real_os_call(monkeypatch):
    """This module's own guard: nothing in it may reach Git, a child or the process
    table. A test that wants one of them installs its own fake over these, which
    monkeypatch lets it do; anything it forgets trips here instead of running
    something on the machine that reviews it."""
    def boom(*a, **k):
        raise AssertionError('a real OS call was reached: %r %r' % (a[:1], sorted(k)))
    for name in ('git', 'run', 'kill_tree', 'kill_pid_tree', 'spawn_terminal',
                 'spawn_detached', 'pid_alive', 'process_create_time'):
        monkeypatch.setattr(local.proc, name, boom)
    monkeypatch.setattr(subprocess, 'Popen', boom)
    monkeypatch.setattr(subprocess, 'run', boom)
    monkeypatch.setattr(local.shutil, 'which', lambda name: GIT)
    local._git_exe.cache_clear()
    local._VERSION.clear()
    local._VERSION[GIT] = VERSION                 # the pin's version: never asked for
    yield
    local._VERSION.clear()
    local._git_exe.cache_clear()


def ok(stdout='', stderr=''):
    return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)


def bad(stdout='', stderr=''):
    return SimpleNamespace(returncode=1, stdout=stdout, stderr=stderr)


class Seam:
    """`proc.git` and `proc.run` recorded and answered, nothing started.

    An answer is a value, or for `git` a callable of `argv`, or for `run` a callable of
    `(argv, stdin)`: what a row needs to see before it can answer."""

    def __init__(self, monkeypatch, git=None, run=None):
        self.git_calls, self.run_calls = [], []
        self._git, self._run = git, run
        monkeypatch.setattr(local.proc, 'git', self.git)
        monkeypatch.setattr(local.proc, 'run', self.run)
        monkeypatch.setattr(local, '_project_git_text', lambda root, args, timeout=60:
                            self.git(args, root, timeout))
        monkeypatch.setattr(local, '_project_git', lambda root, args, timeout=60:
                            self.run(['git'] + list(args), cwd=root, timeout=timeout))

    def git(self, args, cwd, timeout=15):
        self.git_calls.append(SimpleNamespace(argv=list(args), cwd=cwd, timeout=timeout))
        a = self._git
        return a(list(args)) if callable(a) else a

    def run(self, argv, *, cwd=None, env=None, timeout=30, stdin=None, check=False):
        self.run_calls.append(SimpleNamespace(argv=list(argv), cwd=cwd, env=env,
                                             timeout=timeout, stdin=stdin))
        a = self._run
        return a(list(argv), stdin) if callable(a) else a

    @property
    def run_argvs(self):
        return [c.argv for c in self.run_calls]

    @property
    def git_argvs(self):
        return [c.argv for c in self.git_calls]


class Spawn:
    """`subprocess.Popen` as `run_check` starts it. The bytes the child "wrote" go to
    the file object Core handed it, and how long it "ran" is what the row says: a child
    that exits, one that times out and is freed by its kill, or one that outlives it."""

    def __init__(self, monkeypatch, *, data=b'', code=0, timeouts=0, kill_frees=True):
        self.started, self.kills = [], []
        self._data, self._code = data, code
        self._timeouts, self._kill_frees = timeouts, kill_frees
        monkeypatch.setattr(local.proc, 'kill_tree', self.kill)
        monkeypatch.setattr(subprocess, 'Popen', self)

    def kill(self, child):
        self.kills.append(child)
        if self._kill_frees and self._timeouts > 1:
            self._timeouts = 1                    # the kill worked: the next wait returns

    def __call__(self, argv, **kw):
        child = Child(self, argv, kw)
        self.started.append(child)
        return child


class Child:
    def __init__(self, spawn, argv, kw):
        self.argv, self.kw, self.spawn = list(argv), kw, spawn
        self.returncode, self.waited = None, []

    def wait(self, timeout=None):
        self.waited.append(timeout)
        if len(self.waited) <= self.spawn._timeouts:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        if self.returncode is None:
            out = self.kw['stdout']
            out.write(self.spawn._data)
            out.flush()                           # Core asks the file's size next
            self.returncode = self.spawn._code
        return self.returncode


# ── Core's store, made by hand: `store_open` then needs no Git at all ────────

def _sealed_store(pid=None):
    """A store exactly as a seal leaves it: Core's config, HEAD, the empty-tree object,
    Core's claim and Core's pin record. Reopening it spawns nothing, which is what makes
    the refusals below provable with zero calls."""
    pid = pid or ids.new_id('project')
    store = paths.repo_store(pid)
    os.makedirs(os.path.join(store, 'refs'))
    with open(os.path.join(store, 'config'), 'wb') as f:
        f.write(INIT_CONFIG)
    with open(os.path.join(store, 'HEAD'), 'wb') as f:
        f.write(STORE_HEAD.encode())
    objects = os.path.join(store, 'objects', EMPTY_TREE[:2])
    os.makedirs(objects)
    with open(os.path.join(objects, EMPTY_TREE[2:]), 'wb') as f:
        f.write(zlib.compress(b'tree 0\x00'))
    os.makedirs(os.path.join(paths.repos_dir(), '.pin'))
    open(os.path.join(paths.repos_dir(), '.pin', pid + '.owned'), 'xb').close()
    with open(os.path.join(paths.repos_dir(), '.pin', pid + '.json'), 'w',
              encoding='utf-8') as f:
        json.dump(local._pin_record(store, VERSION), f, sort_keys=True)
    return pid, store


def _source_repo(where):
    """A plain directory holding a plain `.git` directory with the metadata `_source`
    reads: enough to be taken for a repository, with nothing else in it to read
    through."""
    root = os.path.join(str(where), 'u')
    gd = os.path.join(root, '.git')
    for d in (('objects', 'info'), ('objects', 'pack'), ('refs', 'heads')):
        os.makedirs(os.path.join(gd, *d))
    with open(os.path.join(gd, 'HEAD'), 'wb') as f:
        f.write(b'ref: refs/heads/main\n')
    with open(os.path.join(gd, 'config'), 'wb') as f:
        f.write(b'[core]\n\tbare = false\n')
    return root


# ── 1-3: merge-back, where a wrong answer loses the user's work ──────────────

class TestMergeBack:
    def test_a_merge_that_failed_with_nothing_unmerged_is_never_reported_as_one(
            self, monkeypatch, tmp_path):
        """local.py:936-937 — the conflict answer is only ever the unmerged list. A
        merge that failed for another reason and reports no conflict must raise: taken
        for a conflict, Core would ask someone to resolve files that are not there and
        call a clean branch conflicted forever."""
        s = Seam(monkeypatch, git='',                 # `--diff-filter=U`: nothing unmerged
                 run=bad(stderr='fatal: refusing to merge unrelated histories'))
        with pytest.raises(OSError, match='git merge failed: fatal: refusing to merge'):
            LocalNode.git_merge(str(tmp_path), COMMIT, 'Merge the task back')
        assert ['git', 'merge', '--abort'] in s.run_argvs              # the tree was left alone
        assert s.git_argvs == [['diff', '--name-only', '--diff-filter=U']]

    def test_a_merge_that_could_not_run_raises_and_asks_nothing_after(self, monkeypatch,
                                                                      tmp_path):
        """local.py:930-931 — no child, no answer about the worktree at all: reading a
        missing child as a clean merge, or as a conflict, is how work is lost."""
        s = Seam(monkeypatch, run=None, git=COMMIT + '\n')
        with pytest.raises(OSError, match='git merge could not run'):
            LocalNode.git_merge(str(tmp_path), COMMIT, 'Merge')
        assert len(s.run_calls) == 1 and s.run_calls[0].argv[-1] == COMMIT
        assert s.git_argvs == []                    # no HEAD read, no conflict query, no abort

    def test_a_merge_lands_as_archeus_and_asks_nothing_else_of_git(self, monkeypatch,
                                                                  tmp_path):
        """local.py:932-933 — the positive control of the two rows above on the same
        seam: a clean merge is `('merged', head)`, as Archeus, and nothing else runs."""
        s = Seam(monkeypatch, run=ok(), git='  fed  \n')
        assert LocalNode.git_merge(str(tmp_path), COMMIT, 'Merge it') == ('merged', 'fed')
        argv = s.run_calls[0].argv
        assert 'user.name=Archeus' in argv and 'user.email=archeus@localhost' in argv
        assert 'commit.gpgsign=false' in argv       # never the user's identity, and no hook
        assert argv[-8:] == ['merge', '--no-ff', '--no-edit', '--no-gpg-sign',
                             '--no-verify-signatures', '-m', 'Merge it', COMMIT]
        assert s.run_calls[0].cwd == str(tmp_path) and s.run_calls[0].timeout == 120
        assert s.git_argvs == [['rev-parse', '--verify', '-q', 'HEAD']]
        assert len(s.run_calls) == 1

    def test_a_conflict_is_aborted_before_it_is_reported(self, monkeypatch, tmp_path):
        """local.py:934-935, 938 — an aborted merge is the only answer Core may act on;
        one left half-merged and reported is a branch the next attempt inherits."""
        def answered(argv, stdin=None):
            if argv[:3] == ['git', 'merge', '--abort']:
                assert len(s.run_calls) >= 2      # the merge itself went first
                return ok()
            return bad(stderr='merge went badly') if 'merge' in argv else ok()
        s = Seam(monkeypatch, run=answered,
                 git=lambda argv: 'a.txt\nb.txt\n' if argv[0] == 'diff' else COMMIT + '\n')
        kind, changed = LocalNode.git_merge(str(tmp_path), COMMIT, 'Merge it')
        assert (kind, changed) == ('conflict', ['a.txt', 'b.txt'])
        assert 'merge' in s.run_argvs[0] and '--abort' not in s.run_argvs[0]
        assert s.run_argvs[-1] == ['git', 'merge', '--abort']           # before the answer
        assert len(s.run_calls) == 2                                    # one merge, one abort

    def test_a_branch_is_never_moved_when_the_ancestor_check_could_not_run(
            self, monkeypatch, tmp_path):
        """local.py:812-815 with 884-886 — `git merge-base --is-ancestor` that cannot
        run is False, never True: taken for an ancestor, `add_worktree` would run
        `worktree add -B` and move a branch holding commits nothing else has."""
        root, path = str(tmp_path / 'root'), os.path.join(str(tmp_path), 'wt')
        monkeypatch.setattr(local, 'GIT_DIR_MAX', None)         # the cap has its own rows
        s = Seam(monkeypatch, run=None, git=COMMIT + '\n')      # the branch resolves
        with pytest.raises(OSError, match='holds commits main does not; it is left as it is'):
            LocalNode.add_worktree(root, path, 'task.key', base='main')
        assert [a for a in s.run_argvs if 'worktree' in a] == []        # nothing was added
        assert s.run_argvs[-1] == ['git', 'merge-base', '--is-ancestor', 'task.key', 'main']
        assert s.run_calls[-1].cwd == root and s.run_calls[-1].timeout == 15

    def test_a_worktree_git_refuses_is_an_oserror_naming_what_git_said(self, monkeypatch,
                                                                      tmp_path):
        """local.py:818-820 — both ways `git worktree add` can fail: no child at all,
        and a child that came back unhappy. Taken as success, Core would go on writing
        into a worktree that was never made."""
        root, path = str(tmp_path / 'root'), os.path.join(str(tmp_path), 'wt')
        monkeypatch.setattr(local, 'GIT_DIR_MAX', None)
        s = Seam(monkeypatch, run=None, git='')                  # the branch is absent
        with pytest.raises(OSError, match='git worktree add failed: no git'):
            LocalNode.add_worktree(root, path, 'task.key', base='HEAD')
        assert s.run_argvs == [['git', '-c', 'core.longpaths=true', 'worktree', 'add',
                                '-b', 'task.key', '--', path, 'HEAD']]
        assert s.run_calls[0].cwd == root and s.run_calls[0].timeout == 60
        assert os.path.isdir(os.path.dirname(path))              # only its parent was made
        s._run = bad(stderr="fatal: 'main' is not a valid object name\n")
        with pytest.raises(OSError, match="worktree add failed: fatal: 'main' is not"):
            LocalNode.add_worktree(root, path, 'task.key', base='main')

    def test_a_mission_worktree_of_a_branch_that_exists_is_checked_out_not_rebuilt(
            self, monkeypatch, tmp_path):
        """local.py:912-917 — with the branch already there the worktree is made from
        it with no `-b` and no `-B` at all (either would re-create, or move, the mission
        branch out from under the executions running on it), and its failure refuses."""
        root, path = str(tmp_path / 'root'), os.path.join(str(tmp_path), 'mission')
        monkeypatch.setattr(local, 'GIT_DIR_MAX', None)
        s = Seam(monkeypatch, run=None, git=COMMIT + '\n')
        with pytest.raises(OSError, match='git worktree add failed: no git'):
            LocalNode.mission_worktree(root, path, 'archeus/m', base='HEAD')
        assert s.run_argvs == [['git', '-c', 'core.longpaths=true', 'worktree', 'add',
                                '--', path, 'archeus/m']]
        assert [x for a in s.run_argvs for x in a if x in ('-b', '-B')] == []

    def test_only_a_worktree_git_itself_lists_is_removed(self, monkeypatch, tmp_path):
        """local.py:826-832 — Git's own listing is the only authority for a removal: an
        unreadable listing, a line that is not a `worktree ` record, and a path that is
        merely a prefix or a parent of one all remove nothing."""
        path = os.path.join(str(tmp_path), 'wt')
        root, mine = str(tmp_path / 'root'), os.path.abspath(os.path.join(str(tmp_path), 'wt'))
        s = Seam(monkeypatch, git='worktree %s\nHEAD %s\nbranch refs/heads/x\n' % (mine, COMMIT))
        assert LocalNode.remove_worktree(root, path) is True
        assert s.git_argvs[0] == ['worktree', 'list', '--porcelain']
        assert s.git_argvs[1] == ['-c', 'core.longpaths=true', 'worktree', 'remove',
                                  '--force', '--', path]
        assert s.git_calls[1].timeout == 60 and s.git_calls[1].cwd == root
        for what, answer in (                       # every way the listing can fail to say it
                ('silent', None),                                   # git could not answer
                ('empty', ''),                                      # nothing listed
                ('prefix', 'worktree %s\n' % (mine + 'e')),          # another path, by one byte
                ('parent', 'worktree %s\n' % os.path.dirname(mine)),
                ('indented', '  worktree %s\n' % mine),               # not a record line
                ('lookalike', 'worktrees %s\n' % mine),               # another word
                ('bare', '%s\n' % mine)):                            # no keyword at all
            del s.git_calls[:]
            s._git = answer
            assert LocalNode.remove_worktree(root, path) is False, what
            assert s.git_argvs == [['worktree', 'list', '--porcelain']], what   # nothing removed


# ── 4: the digest the guard measures progress with ───────────────────────────

def _digest(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode('utf-8', 'surrogateescape'))
        h.update(b'\0')
    return h.hexdigest()


class TestEndState:
    HEAD = '  %s \n' % COMMIT
    DIFF = 'diff --git a/a.txt b/a.txt\n'
    OTHERS = 'b.txt\0a.txt\0'
    HASHES = 'h:a.txt\nh:b.txt\n'

    def _reads(self, **over):
        """The four reads `end_state` makes, each answerable whole: an answer is a
        child, `None` for a child that could not run, or a callable of `(argv, stdin)`.
        A read outside these four is a failure of the row, not a free pass."""
        answers = {'rev-parse': ok(self.HEAD), 'diff': ok(self.DIFF),
                   'ls-files': ok(self.OTHERS), 'hash-object': ok(self.HASHES)}
        answers.update(over)

        def run(argv, stdin):
            what = argv[2]
            if what not in answers:
                raise AssertionError('end_state read something unexpected: %r' % (argv,))
            a = answers[what]
            return a(argv, stdin) if callable(a) else a
        return run

    @pytest.mark.parametrize('failing', ['rev-parse', 'diff', 'ls-files', 'hash-object'])
    def test_a_state_that_cannot_be_fully_measured_is_no_state_at_all(self, monkeypatch,
                                                                     tmp_path, failing):
        """local.py:783-784, 788-789 — HEAD, the tracked diff, the untracked list and
        the blob ids are one measurement, so any one of them failing is `None`, which
        the guard reads as no progress. A digest of half the state would be compared
        against a whole one, and work that never happened would read as progress."""
        for answer in (bad(stderr='fatal: the object store is gone'), None):
            s = Seam(monkeypatch, run=self._reads(**{failing: answer}))
            assert LocalNode.end_state(str(tmp_path)) is None, (failing, answer)
            assert [c.argv[2] for c in s.run_calls] == (
                ['rev-parse', 'diff', 'ls-files'] if failing != 'hash-object'
                else ['rev-parse', 'diff', 'ls-files', 'hash-object']), (failing, answer)

    def test_the_whole_state_is_the_digest_and_no_part_of_it_is_dropped(self, monkeypatch,
                                                                       tmp_path):
        """local.py:790-794 — the four parts, each terminated, in this order, and every
        one of them inside the digest: a part left out makes two different states
        measure the same thing."""
        s = Seam(monkeypatch, run=self._reads())
        got = LocalNode.end_state(str(tmp_path))
        assert got == _digest(self.HEAD.strip(), self.DIFF, 'a.txt\0b.txt', self.HASHES)
        assert s.run_calls[0].argv[:2] == ['git', '--no-optional-locks']    # reads only
        for what, value in (('diff', self.DIFF + '+++ b/new\n'),            # a tracked edit
                            ('hash-object', 'h:a.txt\nh:OTHER\n'),          # an untracked one
                            ('rev-parse', '%s\n' % ('d' * 40))):            # a moved HEAD
            s = Seam(monkeypatch, run=self._reads(**{what: ok(value)}))
            assert LocalNode.end_state(str(tmp_path)) != got, what

    def test_the_untracked_list_is_sorted_and_emptied_before_it_is_hashed(self, monkeypatch,
                                                                        tmp_path):
        """local.py:785-787 — `-z` answers in Git's order and with a trailing empty
        field. Unsorted, one state digests twice; keeping the empty name, it digests a
        file that is not there."""
        def hashes(argv, stdin):                  # one id per path, in the order it came
            return ok(''.join('h:%s\n' % p for p in stdin.split('\n') if p))
        s = Seam(monkeypatch, run=self._reads(**{'ls-files': ok('b.txt\0\0a.txt\0'),
                                                 'hash-object': hashes}))
        first = LocalNode.end_state(str(tmp_path))
        assert s.run_calls[-1].stdin == 'a.txt\nb.txt\n'           # sorted, no empty name
        assert first == _digest(self.HEAD.strip(), self.DIFF, 'a.txt\0b.txt',
                                'h:a.txt\nh:b.txt\n')
        s = Seam(monkeypatch, run=self._reads(**{'ls-files': ok('a.txt\0b.txt\0'),
                                                 'hash-object': hashes}))
        assert LocalNode.end_state(str(tmp_path)) == first         # one state, one digest

    def test_a_state_with_nothing_untracked_asks_for_no_hashes_at_all(self, monkeypatch,
                                                                     tmp_path):
        """local.py:786-787 — `if paths else ''`: with nothing untracked there is no
        `hash-object` to run, and one run on an empty list invents an answer."""
        s = Seam(monkeypatch, run=self._reads(**{'ls-files': ok('\0\0')}))
        assert LocalNode.end_state(str(tmp_path)) == _digest(self.HEAD.strip(), self.DIFF,
                                                             '', '')
        assert [c.argv[2] for c in s.run_calls] == ['rev-parse', 'diff', 'ls-files']

    def test_nothing_outside_a_real_directory_is_a_state(self, monkeypatch, tmp_path):
        """local.py:774-775 — no path, a path that is not there and a plain file are
        all `None`, and none of them asks Git anything. A run_check workdir that went
        missing must not measure as an empty state that "did not change"."""
        a_file = tmp_path / 'a-file'
        a_file.write_bytes(b'not a directory\n')
        s = Seam(monkeypatch, run=ok(stdout='anything at all'))
        for where in (None, '', str(tmp_path / 'absent'), str(a_file)):
            assert LocalNode.end_state(where) is None, where
        assert s.run_calls == []


# ── 9: the git reads the boundary checks decide on ───────────────────────────

class TestBoundaryReads:
    def test_a_detached_head_is_no_branch_and_an_absent_workdir_asks_nothing(self, monkeypatch,
                                                                            tmp_path):
        """local.py:727-731 — `HEAD` back from `--abbrev-ref` means detached: kept as a
        branch name it is compared against the mission branch as if it named one, and a
        detached worktree reads as being on the mission branch."""
        s = Seam(monkeypatch, git='anything at all')
        assert [LocalNode.git_branch(w) for w in (None, '')] == [None, None]
        assert s.git_calls == []                        # nothing asked of no workdir
        for answer, want in ((None, None), ('', None), ('  \n', None), ('HEAD', None),
                             ('HEAD\n', None), ('refs/heads/x', 'refs/heads/x'),
                             ('  archeus/m.t1 \n', 'archeus/m.t1')):
            del s.git_calls[:]
            s._git = answer
            got = LocalNode.git_branch(str(tmp_path))
            assert got == want and (got is None) == (want is None), answer
            assert s.git_calls[0].argv == ['rev-parse', '--abbrev-ref', 'HEAD']
            assert s.git_calls[0].cwd == str(tmp_path)

    def test_a_remote_git_does_not_name_is_none_and_the_first_url_wins(self, monkeypatch,
                                                                      tmp_path):
        """local.py:734-745 — the host is what Core's canonical-host rule matches, and
        `git remote -v` lists one remote twice: the first url has to win, and a line
        carrying no host is `None`, never a guess. A second url overwriting the first,
        or an unreadable line becoming a host of its own, is a remote Core lets through."""
        s = Seam(monkeypatch, git='anything at all')
        assert [LocalNode.git_remotes(w) for w in (None, '')] == [{}, {}]
        assert s.git_calls == []
        s._git = '\n'.join([
            'origin\thttps://GitHub.com/u/r.git\t(fetch)',        # case is Git's own answer
            'origin\thttps://evil.example/u/r.git\t(push)',       # the second listing of it
            'up\tgit@github.com:u/r.git\t(fetch)',                # scp-like, no scheme
            'nohost\t:user/repo.git\t(fetch)',                    # no host before the colon
            'broken\thttps://[bad\t(fetch)',                      # no host of any kind
            'lonely',                                             # not a listing line
            'blank\t\t(fetch)',                                   # a line with no url
        ])
        assert LocalNode.git_remotes(str(tmp_path)) == {'origin': 'github.com',
                                                        'up': 'github.com', 'nohost': None,
                                                        'broken': None,
                                                        # `line.split()` collapses the empty url, so
                                                        # the only token left becomes the "host": a
                                                        # name no allowlisted host can ever equal
                                                        'blank': '(fetch)'}
        assert 'lonely' not in LocalNode.git_remotes(str(tmp_path))   # not a listing line
        assert s.git_calls[0].argv == ['remote', '-v'] and s.git_calls[0].cwd == str(tmp_path)

    def test_the_checkpoint_stat_is_nothing_when_git_cannot_say_and_capped_when_it_can(
            self, monkeypatch, tmp_path):
        """local.py:756-763 — a checkpoint's evidence is 30 lines and no more, blanks
        dropped, and a workdir that is not there asks Git nothing at all."""
        s = Seam(monkeypatch, git='a line git should never be asked for')
        for where in (None, '', str(tmp_path / 'absent')):
            assert LocalNode.diff_stat(where) == [], where
        assert s.git_calls == []
        lines = ['a.txt | %d +' % i for i in range(40)]        # as Git's own answer reads
        s._git = '\n'.join([''] + ['  %s  ' % x for x in lines])
        assert LocalNode.diff_stat(str(tmp_path)) == lines[:30]      # the cap, in order
        assert s.git_calls[0].argv == ['diff', '--stat', 'HEAD']
        for answer in ('\n \n\t\n', None):                           # nothing to report
            s._git = answer
            assert LocalNode.diff_stat(str(tmp_path)) == [], answer

    def test_a_status_git_cannot_give_is_nobody_said_not_a_clean_tree(self, monkeypatch,
                                                                     tmp_path):
        """local.py:849-855 — `None` and `False` are different answers: the first is
        unknown, the second a tree Core may merge back. Read together, an unreadable
        worktree becomes a clean one."""
        s = Seam(monkeypatch, git=None)
        assert LocalNode.git_dirty(str(tmp_path)) is None
        assert s.git_argvs == [['status', '--porcelain=v1']]          # untracked counted too
        s._git = '   \n\n'
        assert LocalNode.git_dirty(str(tmp_path)) is False
        s._git = '?? dropper.exe\n'
        assert LocalNode.git_dirty(str(tmp_path)) is True
        s._git = ' M kept.txt\n'
        assert LocalNode.git_dirty(str(tmp_path), tracked_only=True) is True
        assert s.git_argvs[-1] == ['status', '--porcelain=v1', '--untracked-files=no']

    def test_an_empty_revision_is_no_revision(self, monkeypatch, tmp_path):
        """local.py:837-847 — whitespace off Git's stdout is `None`: a caller cannot
        carry `''` onward to the database as a commit, nor past a `--verify`."""
        s = Seam(monkeypatch, git='\n  \t \n')
        assert LocalNode.git_head(str(tmp_path)) is None
        assert s.git_argvs == [['rev-parse', '--verify', '-q', 'HEAD']]
        s._git = ' %s \n' % COMMIT
        assert LocalNode.git_head(str(tmp_path)) == COMMIT
        s._git = ''
        assert LocalNode.git_head(str(tmp_path / 'absent')) is None    # not even asked
        assert LocalNode.git_resolve(str(tmp_path), 'tag-1') is None
        assert s.git_argvs[-1] == ['rev-parse', '--verify', '-q', 'tag-1^{commit}']

    def test_a_numstat_line_that_is_not_three_fields_is_no_line(self, monkeypatch):
        """local.py:891-899 — a row Core reports as changed lines comes only from three
        tab-separated fields: a half line is dropped rather than counted, and a path
        holding a tab is kept whole rather than cut into a path that names nothing."""
        s = Seam(monkeypatch, git=None)
        assert LocalNode.git_numstat('/r', 'base', COMMIT) is None     # git could not tell
        assert s.git_argvs == [['diff', '--numstat', 'base', COMMIT, '--']]
        assert s.git_calls[0].timeout == 60
        s._git = ('1\t2\tok.txt\ngarbage\n3\t4\n'
                  '-\t-\tbin.dat\n5\t6\ttwo\twords.txt\n\t\t\tspaced.txt\n')
        assert LocalNode.git_numstat('/r', 'base', COMMIT) == [
            ('1', '2', 'ok.txt'), ('-', '-', 'bin.dat'), ('5', '6', 'two\twords.txt'),
            ('', '', '\tspaced.txt')]

    def test_a_snapshot_that_staged_nothing_reports_the_head_it_did_not_move(
            self, monkeypatch, tmp_path):
        """local.py:869-871 — `git diff --cached --quiet` saying the index is clean is
        the one case that commits nothing: the HEAD read back is the answer, and no
        commit is made on a clean tree."""
        s = Seam(monkeypatch, run=ok(), git=' %s \n' % COMMIT)
        assert LocalNode.git_snapshot(str(tmp_path), 'WIP') == COMMIT
        assert [a[:3] for a in s.run_argvs] == [['git', 'add', '-A'],
                                                ['git', 'diff', '--cached']]
        assert [a for a in s.run_argvs if 'commit' in a] == []
        assert s.run_calls[0].cwd == str(tmp_path) and s.run_calls[0].timeout == 60

    def test_a_snapshot_that_cannot_tell_whether_anything_staged_commits_anyway(
            self, monkeypatch, tmp_path):
        """local.py:872-876 — `staged is None` is treated as "something is staged": the
        work is committed rather than dropped, and both ways `add` and `commit` can
        fail are an OSError naming git's reason, never a silent success."""
        s = Seam(monkeypatch, run=None, git=COMMIT + '\n')          # no child at all
        with pytest.raises(OSError, match='git add failed: no git'):
            LocalNode.git_snapshot(str(tmp_path), 'WIP')

        def answers(argv, stdin=None):                # argv[1] is the subcommand
            if argv[1] == 'add':
                return ok()
            return bad() if argv[1] == 'diff' else None   # something is staged; the commit dies
        s._run = answers
        with pytest.raises(OSError, match='git commit failed: no git'):
            LocalNode.git_snapshot(str(tmp_path), 'WIP')
        committed = [a for a in s.run_argvs if 'commit' in a][-1]
        assert committed[:2] == ['git', '-c']                    # as Archeus, per command
        assert 'user.name=Archeus' in committed and 'user.email=archeus@localhost' in committed
        assert 'commit.gpgsign=false' in committed
        assert committed[committed.index('commit'):] == ['commit', '-q', '--no-verify',
                                                         '-m', 'WIP']

    def test_a_terminal_is_the_users_own_and_is_passed_through_untouched(self, monkeypatch):
        """local.py:750-754 — Core neither supervises nor re-decides what the user
        opens: a dropped `cwd`, `env` or `title` here quietly changes whose shell it is."""
        seen = []

        def terminal(argv, *, cwd, env, title):
            seen.append((list(argv), cwd, env, title))
            return object(), ''
        monkeypatch.setattr(local.proc, 'spawn_terminal', terminal)
        made, error = LocalNode.open_terminal(['cmd', '/c', 'dir'], cwd='the-cwd',
                                              env={'PATH': 'x'}, title='the title')
        assert made is not None and error == ''
        assert seen == [(['cmd', '/c', 'dir'], 'the-cwd', {'PATH': 'x'}, 'the title')]


# ── 10: the check that has to be killable ────────────────────────────────────

class TestRunCheck:
    def test_a_check_that_outlives_its_kill_is_reported_as_the_timeout_and_nothing_else(
            self, monkeypatch, tmp_path):
        """local.py:967-975 — a child that ignores its kill gets one bounded second
        wait and is then reported as the timeout: nothing is waited on forever, no
        exception leaves the node, and the record says a verifier faulted rather than
        naming an exit code the child never returned. A child freed by its kill is the
        same row: still the timeout, still no exit code."""
        for frees, timeout in ((False, 7), (True, 3)):
            sp = Spawn(monkeypatch, data=b'work done before the kill\n', code=0,
                       timeouts=2, kill_frees=frees)
            out = str(tmp_path / 'logs' / ('check-%s.log' % frees))     # its parent is made too
            r = LocalNode.run_check(str(tmp_path), ['the-tool', '--check'], timeout=timeout,
                                    out_path=out, keep=1024)
            assert r['error'] == 'timed out after %ds' % timeout, frees
            assert r['exit_code'] is None, frees                  # never a code it did not give
            assert len(sp.kills) == 1 and sp.kills[0] is sp.started[0], frees
            assert sp.started[0].waited == [timeout, 30], frees    # one kill, one wait after it
            assert len(sp.started) == 1 and os.path.isfile(out), frees
            # what the child did write before it died is still the evidence
            assert r['output_bytes'] == (frees * len(b'work done before the kill\n')), frees

    def test_output_kept_exactly_to_keep_bytes_is_not_reported_as_cut(self, monkeypatch,
                                                                      tmp_path):
        """local.py:976-982 — `truncated` is `size > keep`, so the boundary is one byte:
        whole at *keep*, the tail and the flag one byte past it. The file holds
        everything either way, and the child is started the way a check has to be."""
        out = str(tmp_path / 'o.log')
        sp = Spawn(monkeypatch, data=b'0123456789', code=0)
        r = LocalNode.run_check(str(tmp_path), ['the-tool'], timeout=5, out_path=out, keep=10)
        assert (r['output'], r['output_bytes'], r['truncated'], r['exit_code']) == \
            (b'0123456789', 10, False, 0)
        assert r['error'] is None and isinstance(r['duration_ms'], int)
        assert open(out, 'rb').read() == b'0123456789'             # the whole record on disk
        kw = sp.started[0].kw
        assert kw['stdin'] is subprocess.DEVNULL                    # it reads nobody's terminal
        assert kw['stderr'] is subprocess.STDOUT                    # one record, not two
        assert sp.started[0].argv == ['the-tool'] and kw['cwd'] == str(tmp_path)
        assert kw['creationflags'] == local.proc.no_window_flags
        assert kw['start_new_session'] is (os.name != 'nt')         # the source's own expression
        assert not [k for k in kw['env'] if k.startswith(('PYTEST_', 'ARCHEUS_'))]
        assert kw['env']['GIT_TERMINAL_PROMPT'] == '0' and kw['env']['PYTHONDONTWRITEBYTECODE']

        Spawn(monkeypatch, data=b'0123456789X', code=3)             # one byte past the keep
        r = LocalNode.run_check(str(tmp_path), ['the-tool'], timeout=5, out_path=out, keep=10)
        assert (r['output'], r['output_bytes'], r['truncated'], r['exit_code']) == \
            (b'123456789X', 11, True, 3)

    def test_a_check_whose_output_is_shorter_than_the_keep_is_returned_whole(self, monkeypatch,
                                                                            tmp_path):
        """local.py:978-980 — `max(0, size - keep)`: below the keep the read starts at
        0; a negative seek is either an error or the whole file by accident, and the
        second is what a check reporting nothing would look like."""
        Spawn(monkeypatch, data=b'ab', code=0)
        r = LocalNode.run_check(str(tmp_path), ['the-tool'], timeout=5,
                                out_path=str(tmp_path / 'o.log'), keep=64)
        assert (r['output'], r['output_bytes'], r['truncated'], r['exit_code']) == \
            (b'ab', 2, False, 0)

    def test_a_check_that_could_not_be_started_is_a_verifier_fault_and_not_an_exit(
            self, monkeypatch, tmp_path):
        """local.py:962-965 — `Popen` refusing is reported the same way a timeout is:
        no exit code, no output, an error naming why. Core reads an exit code as the
        work's verdict and an error as the verifier's."""
        def refuses(argv, **kw):
            raise OSError(2, 'the tool is not there')
        monkeypatch.setattr(subprocess, 'Popen', refuses)
        r = LocalNode.run_check(str(tmp_path), ['the-tool'], timeout=5,
                                out_path=str(tmp_path / 'o.log'), keep=64)
        assert r['exit_code'] is None and r['error'].startswith('could not run: [Errno 2]')
        assert r['output'] == b'' and r['output_bytes'] == 0 and r['truncated'] is False


# ── 6-8: the store readers, every refusal before a spawn ─────────────────────

class TestStoreReaders:
    @pytest.mark.parametrize('args', [
        pytest.param([], id='empty'),
        pytest.param(['fetch', 'origin'], id='fetch'),
        pytest.param(['update-ref', 'refs/heads/x', COMMIT], id='update-ref'),
        pytest.param(['fast-import', '--done'], id='fast-import'),
        pytest.param(['ls-files', '-s'], id='ls-files'),
        pytest.param(['read-tree', COMMIT], id='read-tree'),
        pytest.param(['symbolic-ref', 'HEAD', 'refs/heads/x'], id='symbolic-ref'),
        pytest.param(['config', '--list'], id='config'),
        pytest.param(['write-tree'], id='not-a-plumbing-read-core-names'),
    ])
    def test_a_store_read_never_writes_although_the_spawner_would(self, monkeypatch, args):
        """local.py:1104-1106 — `STORE_READS` is narrower than `_STORE_ARGS['trusted']`,
        which also allows `fetch` and `update-ref`, and narrower than `seed` and
        `import`: a read that could fetch, move a ref or write objects would let a
        caller write the store Core owns through the door meant for reading."""
        s = Seam(monkeypatch, git='', run=ok(stdout=''))
        with pytest.raises(StoreError, match='is not a store read'):
            LocalNode.store_read(ids.new_id('project'), args, workdirs=())
        assert s.run_calls == [] and s.git_calls == []                # refused before anything
        assert not os.path.lexists(paths.repos_dir())                 # not even the pin area

    def test_a_store_read_diff_cannot_be_asked_for_an_external_driver(self, monkeypatch):
        """local.py:1107-1109 — a diff of a store must never reach an external diff
        driver or a textconv filter: both are a program the repository names, and both
        are exactly what a store fetched from somebody else's tree can carry."""
        pid, store = _sealed_store()
        s = Seam(monkeypatch, run=ok(stdout=''), git='')
        assert LocalNode.store_read(pid, ['diff', '--stat', 'HEAD'], workdirs=()) == ''
        (call,) = s.run_calls
        at = call.argv.index('diff')
        assert call.argv[at:at + 4] == ['diff', '--no-ext-diff', '--no-textconv', '--stat']
        assert call.argv[call.argv.index('--git-dir') + 1] == store
        assert call.cwd == store and call.env['GIT_NO_LAZY_FETCH'] == '1'
        assert call.argv[call.argv.index('--attr-source') + 1] == EMPTY_TREE   # not a repo's

    @pytest.mark.parametrize('commit', [
        pytest.param('', id='empty'),
        pytest.param('c' * 39, id='short'),
        pytest.param('c' * 41, id='long'),
        pytest.param('C' * 40, id='capitals'),
        pytest.param('c' * 39 + '\n', id='newline'),
        pytest.param(' ' + 'c' * 39, id='leading-space'),
        pytest.param('HEAD', id='a-revision-not-a-commit'),
    ])
    def test_a_seed_ref_is_written_only_for_a_full_commit_core_resolved(self, monkeypatch,
                                                                        commit):
        """local.py:1179-1182 — the seed ref is the base of every retry of the
        execution, and it is written with `update-ref`, which resolves what it is
        given: a loose revision would be resolved by Git rather than by Core, and the
        retry would seed off a commit nobody verified."""
        s = Seam(monkeypatch, run=ok(stdout=COMMIT + '\n'), git='')
        with pytest.raises(StoreError, match='not a commit Core seeds from'):
            LocalNode.store_seed_ref(ids.new_id('project'), ids.new_id('execution'),
                                     commit, workdirs=())
        assert s.run_calls == [] and s.git_calls == []
        assert not os.path.lexists(paths.repos_dir())         # no store, no claim, no pin

    def test_a_seed_ref_names_the_executions_own_ref_and_is_written_once(self, monkeypatch):
        """local.py:1179 with 1183-1184 and `_publish_once` — the positive control of
        the rows above: the execution's own ref, created at the commit and read back,
        in that order, and nothing else started."""
        pid, store = _sealed_store()
        eid = ids.new_id('execution')
        s = Seam(monkeypatch, run=ok(stdout=COMMIT + '\n'), git='')
        assert LocalNode.store_seed_ref(pid, eid, COMMIT, workdirs=()) == COMMIT
        ref = 'refs/archeus/exec/%s/seed' % eid
        assert len(s.run_calls) == 2 and s.run_calls[0].cwd == store
        assert s.run_argvs[0][s.run_argvs[0].index('update-ref'):] == \
            ['update-ref', ref, COMMIT, '']                    # created, the old value empty
        assert s.run_argvs[1][-1] == ref + '^{commit}'         # then read back, never moved

    def test_a_seed_ref_that_names_another_commit_is_refused_after_being_written(
            self, monkeypatch):
        """local.py (through `_publish_once`, 1299-1311) — an existing ref is not moved
        out of the way: what it names decides, and a `update-ref` that failed because
        the ref is there is answered by reading it, not by trying again."""
        pid, store = _sealed_store()
        eid = ids.new_id('execution')
        ref = 'refs/archeus/exec/%s/seed' % eid
        seen = []

        def by_command(argv, stdin):
            seen.append('update-ref' if 'update-ref' in argv else 'rev-parse')
            if argv[-1] == ref + '^{commit}':                   # the read-back, asked anyway
                return ok(stdout='%s\n' % ('d' * 40))           # it names something else
            if 'update-ref' in argv:
                return bad(stderr='cannot lock ref %s' % ref)
            raise AssertionError('a seed ref call Core did not make: %r' % (argv,))
        s = Seam(monkeypatch, run=by_command, git='')
        with pytest.raises(StoreError, match='names %s, not %s' % ('d' * 40, COMMIT)):
            LocalNode.store_seed_ref(pid, eid, COMMIT, workdirs=())
        assert seen == ['update-ref', 'rev-parse']              # one attempt, then the read

    def test_only_a_store_refusal_falls_back_to_head_and_nothing_else_does(self, monkeypatch,
                                                                          tmp_path):
        """local.py:1544-1551 — only a silent `NoSuchRevision` falls back to HEAD: a git
        failure that says something, or an I/O failure under the read, must not be
        answered with HEAD, which would seed an execution
        off a commit nobody resolved, and a branch that does resolve must not leave the
        HEAD read in place either."""
        root, branch = _source_repo(tmp_path), 'refs/heads/archeus/m'

        def good(argv, stdin=None):
            return ok(COMMIT + '\n') if argv[-1].endswith('^{commit}') else ok(VERSION)
        s = Seam(monkeypatch, run=good)
        assert LocalNode.resolve_base(root, 'archeus/m', workdirs=()) == (branch, COMMIT)
        assert [c.argv[-1] for c in s.run_calls] == [branch + '^{commit}']       # HEAD unread

        def branch_missing(argv, stdin=None):
            return bad() if argv[-1] in (branch + '^{commit}', branch) else good(argv, stdin)
        s = Seam(monkeypatch, run=branch_missing)
        assert LocalNode.resolve_base(root, 'archeus/m', workdirs=()) == ('HEAD', COMMIT)
        assert [c.argv[-1] for c in s.run_calls] == [branch + '^{commit}', branch,
                                                      'HEAD^{commit}']

        def branch_not_a_commit(argv, stdin=None):
            return bad() if argv[-1] == branch + '^{commit}' else good(argv, stdin)
        s = Seam(monkeypatch, run=branch_not_a_commit)
        with pytest.raises(StoreError, match='names no commit'):
            LocalNode.resolve_base(root, 'archeus/m', workdirs=())
        assert 'HEAD^{commit}' not in [c.argv[-1] for c in s.run_calls]

        def branch_fails(argv, stdin=None):
            return bad(stderr='fatal: not a valid object name')                 if argv[-1] == branch + '^{commit}' else good(argv, stdin)
        s = Seam(monkeypatch, run=branch_fails)
        with pytest.raises(StoreError, match='not a valid object name'):
            LocalNode.resolve_base(root, 'archeus/m', workdirs=())
        assert 'HEAD^{commit}' not in [c.argv[-1] for c in s.run_calls]

        def explodes(argv, stdin=None):
            if argv[-1] == branch + '^{commit}':
                raise OSError(5, 'the volume for the repository is gone')
            return good(argv, stdin)
        s = Seam(monkeypatch, run=explodes)
        with pytest.raises(OSError) as got:
            LocalNode.resolve_base(root, 'archeus/m', workdirs=())
        assert got.value.errno == 5
        assert 'HEAD^{commit}' not in [c.argv[-1] for c in s.run_calls]          # never asked

    @pytest.mark.parametrize('branch', [
        pytest.param('a..b', id='double-dot'),
        pytest.param('has space', id='space'),
        pytest.param('name\x00nul', id='nul-in-the-name'),
        pytest.param('semi;colon', id='semicolon'),
        pytest.param('ünïcode', id='non-ascii'),
        pytest.param('tab\tname', id='tab'),
        pytest.param('back\\slash', id='foreign-separator'),
    ])
    def test_a_mission_branch_git_could_not_hold_is_refused_before_anything_is_read(
            self, monkeypatch, tmp_path, branch):
        """local.py:1156-1158 — the name is Core's own namespace and the only thing a
        first attempt may resolve: a name Git would refuse, or would read as something
        else, is refused without the source being opened or anything started. (The
        `refs/heads/` prefix is Core's to add, so a caller cannot supply one.)"""
        root = _source_repo(tmp_path)
        s = Seam(monkeypatch, run=ok(COMMIT + '\n'))
        with pytest.raises(StoreError, match='not a mission branch'):
            LocalNode.resolve_base(root, branch, workdirs=())
        assert s.run_calls == []

    def test_a_fetch_writes_the_incoming_ref_then_the_public_one_and_never_past_the_cap(
            self, monkeypatch, tmp_path):
        """local.py:1128-1150 — the ref cap is enforced before the store is opened and
        before anything is written, and an accepted fetch lands as four calls in this
        order: fetch into `incoming`, verify it still names what Core resolved, create
        the public ref, read it back."""
        pid, store = _sealed_store()
        root = _source_repo(tmp_path)
        tail = 'exec/' + 'e' * (local.REF_MAX - len('refs/archeus/') - len('exec/'))
        ref = 'refs/archeus/' + tail
        assert len(ref) == local.REF_MAX
        s = Seam(monkeypatch, run=lambda argv, stdin: ok(COMMIT + '\n'), git='')
        monkeypatch.setattr(LocalNode, 'store_fetch_accepted', True)
        got = LocalNode.store_fetch(pid, root, 'refs/heads/main', COMMIT, ref, workdirs=())
        assert got == COMMIT and len(s.run_calls) == 4
        assert s.run_argvs[0][s.run_argvs[0].index('fetch'):] == [
            'fetch', '--no-tags', '--no-recurse-submodules', '--no-write-fetch-head',
            '--no-auto-gc', '--end-of-options', root,
            '+%s:%s' % ('refs/heads/main', 'refs/archeus/incoming/' + tail)]
        assert s.run_argvs[1][-1] == 'refs/archeus/incoming/' + tail + '^{commit}'
        assert 'update-ref' in s.run_argvs[2] and s.run_argvs[3][-1] == ref + '^{commit}'

        del s.run_calls[:]
        with pytest.raises(StoreError, match='characters long; a store takes at most'):
            LocalNode.store_fetch(pid, root, 'refs/heads/main', COMMIT, ref + 'x', workdirs=())
        assert s.run_calls == []                                  # nothing written at all
