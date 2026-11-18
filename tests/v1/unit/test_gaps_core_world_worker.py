"""T-730: the ten highest-risk uncovered branches of archeus/core/world/worker.py.

Fail-closed and denial paths first — an extractor bug that may only fail its own
inspection, a walk whose repository vanishes under it, a HEAD that moves during
the walk, a crash that leaves a RUNNING row, a revision capped at MAX_ATTEMPTS,
a blob that no longer hashes to its address — then the boundary values (backoff's
zero and its cap, the wake contract, the stop between the items of a pass), then
the error paths as the digest, the drift list and the status read-models see
missing, moved and hostile inputs.

The rig is tests/v1/integration/test_world.py's Harness with every OS call faked
through the seams the existing tests already use: the deterministic walk is the
monkeypatched `inspection.inspect` (as in W05, W12 and W16), and HEAD is plain
`.git` bytes read by the real reader under test_world_units.py's `no_subprocess`
guard on `repos._git`, so no git binary is asked for anywhere and nothing shells
out. Every fixture file is written as explicit bytes with explicit newlines and
ASCII-only names; no assertion reads OS error text or an environment value; the
same assertions hold on Linux and on Windows. One rig per test: they would all
share the one per-test ARCHEUS_HOME.
"""

import os
import shutil
import time

import pytest

from archeus.core.application import world
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.world import inspection
from archeus.core.world import digest as world_digest
from archeus.core.world import status as world_status
from archeus.core.world.worker import World, backoff
from archeus.infra.artifacts import store as artifacts
from archeus.infra.db import Database, rows
from claude_sessions import repos

#: commit ids as HEAD would name them (40 lowercase hex, what head_revision accepts)
SHA_A, SHA_B = 'a' * 40, 'b' * 40


class _Crash(BaseException):
    """Core dying under an inspection: not an `Exception`, so the extractor-bug
    net at worker.py:138 cannot catch it and the row is left RUNNING on purpose."""


class Clock:
    """Wall time that a test moves forward: `failed_at` is the writer's real
    clock (test_world.py's), so this one keeps pace with it and adds only what
    the test skips — which may also be negative, to stand behind a `failed_at`."""

    def __init__(self):
        self.skipped = 0.0

    def __call__(self):
        return time.time() + self.skipped


class _Stop:
    """The worker's `stopping` hook: records every call pass_once made of it,
    answering from a scripted list (the last answer keeps)."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def __call__(self):
        self.calls.append(self.answers[0] if len(self.answers) == 1 else self.answers.pop(0))
        return self.calls[-1]


class Walk:
    """The deterministic pass, faked the way test_world.py fakes it (W05, W12,
    W16): `inspection.inspect` replaced on the module, each call running the
    side effect scripted for it (if any) and then answering. Every path it was
    asked to walk is recorded, and an answer can be set per path."""

    def __init__(self, monkeypatch):
        self.real, self.seen, self.side = inspection.inspect, [], {}

        def fake(path):
            self.seen.append(path)
            hook = self.side.get(path)
            if hook is not None:
                hook(path)
            return self.answer(path)
        monkeypatch.setattr(inspection, 'inspect', fake)

    def answer(self, path):
        files = ['app/a.py', 'app/models.py']
        payload = {'extractor_version': inspection.EXTRACTOR_VERSION, 'files': files,
                   'edges': [['app/a.py', 'app/models.py']], 'dependencies': [],
                   'truncated': False}
        obs = {'dirty': False, 'complete': True, 'languages': [['Python', 2]],
               'frameworks': [], 'docs': [], 'test_commands': ['python -m pytest'],
               'build_commands': [], 'notes': [], 'agent_config': []}
        return obs, payload

    def boom(self, path, exc):
        """The next walk of *path* raises *exc* (a BaseException stays raised:
        that is the crash Core does not catch, an Exception the extractor bug)."""
        def hook(_p):
            raise exc
        self.side[path] = hook

    def then(self, path, hook):
        """The next walk of *path* runs *hook* first — how a test moves HEAD or
        removes a directory underneath the very pass reading it."""
        self.side[path] = hook

    def calm(self, path):
        """Walks of *path* answer again: the scripted failure is over."""
        self.side.pop(path, None)


class Repo:
    """A registered repository: where its bytes live, and which rows it owns."""

    def __init__(self, name, path, project_id, id):
        self.name, self.path, self.project_id, self.id = name, path, project_id, id


class Rig:
    """One world worker over a real database of real rows, its filesystem read
    from bytes the test itself wrote, its walk faked. Exactly one per test."""

    def __init__(self, tmp_path, monkeypatch):
        self.db = Database.open()
        self.user = Ref('user_device', ids.new_id('principal'))
        self.worker = World(self.db, actor=Ref('system', ids.new_id('principal')),
                            clock=Clock())
        self.walk = Walk(monkeypatch)
        self.parent = str(tmp_path / 'repos')
        os.makedirs(self.parent)
        # test_world_units.py's `no_subprocess`: HEAD that needs a subprocess is
        # a bug the test catches, not a call the machine's git gets to answer
        monkeypatch.setattr(repos, '_git', self._no_git)

    @staticmethod
    def _no_git(*a, **k):
        raise AssertionError('HEAD was resolved with a subprocess')

    def run(self, command, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.user))

    def read(self, fn, *a):
        with self.db.read() as conn:
            return fn(conn, *a)

    def plan(self):
        with self.db.read() as conn:
            return self.worker.plan(conn)

    def pending(self):
        return self.worker.pending()

    def repo_dir(self, name, head=SHA_A):
        """A working tree in bytes: content with explicit newlines, and a `.git`
        whose HEAD is one raw sha — which the real `head_revision` resolves from
        the file alone, so no git binary and no subprocess is ever asked for."""
        path = os.path.join(self.parent, name)
        os.makedirs(os.path.join(path, 'app'))
        with open(os.path.join(path, 'app', 'a.py'), 'wb') as f:
            f.write(b'a = 1\n')
        with open(os.path.join(path, 'app', 'models.py'), 'wb') as f:
            f.write(b'class M:\n    pass\n')
        os.makedirs(os.path.join(path, '.git'))
        self.set_head_bytes(path, head)
        return path

    @staticmethod
    def set_head_bytes(path, sha):
        with open(os.path.join(path, '.git', 'HEAD'), 'wb') as f:
            f.write((sha + '\n').encode('ascii'))

    def set_head(self, repo, sha):
        self.set_head_bytes(repo.path, sha)

    def register(self, name, head=SHA_A):
        path = self.repo_dir(name, head)
        out = self.run(world.create_project, name=name, root_paths=[path])
        return Repo(name, path, out['project']['id'], out['repositories'][0]['id'])

    def repo(self, rid):
        return self.read(lambda c: rows.get(c, entities.Repository, rid).entity)

    def inspections(self, rid):
        return self.read(lambda c: [r.entity for r in rows.where(
            c, entities.RepositoryInspection, repository_id=rid)])

    def artifacts_(self):
        return self.read(lambda c: [r.entity for r in rows.where(c, entities.Artifact)])

    def status(self):
        return self.read(world_status.status)

    def digest(self):
        return self.read(world_digest.digest)

    def corrupt(self, sha):
        """The blob at *sha* stops hashing to its address. Returns the original
        bytes: the test puts them back, because a blob is immutable by contract
        and only its bytes on disk were attacked."""
        p = artifacts.path_for(sha)
        with open(p, 'rb') as f:
            original = f.read()
        with open(p, 'wb') as f:
            f.write(original[:-1] + bytes([original[-1] ^ 0x01]))   # one bit, one blob
        return original

    def restore(self, sha, original):
        with open(artifacts.path_for(sha), 'wb') as f:
            f.write(original)

    def close(self):
        self.db.close()


@pytest.fixture
def rig(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    yield r
    r.close()


# ── fail-closed and denial ──────────────────────────────────────────────────

def test_an_extractor_bug_fails_its_inspection_and_not_the_pass(rig):
    # worker.py:138-142 (`except Exception`): a crashing extractor is recorded
    # as `error: <Type>: <msg>` on its own inspection and counts toward the cap;
    # the pass itself goes on with the next repository, Core stays up, and the
    # counted failure is now gated by backoff instead of being retried hot
    bad, good = rig.register('buggy'), rig.register('good')
    rig.walk.boom(bad.path, RuntimeError('boom'))
    assert rig.worker.pass_once() == {'changed': True, 'done': 2}
    (i,) = rig.inspections(bad.id)
    assert (i.state, i.failure, i.attempts) == ('FAILED', 'error: RuntimeError: boom', 1)
    assert i.failed_at is not None and rig.repo(bad.id).architecture_state == 'UNKNOWN'
    g = rig.inspections(good.id)[-1]                      # the rest of the pass ran
    assert (g.state, g.revision) == ('COMPLETED', SHA_A)
    assert rig.repo(good.id).architecture_state == 'CONSISTENT'
    assert rig.walk.seen == [bad.path, good.path] and rig.pending() == 0


def test_a_repository_that_vanishes_during_the_walk_completes_nothing(rig):
    # worker.py:143-146 and 147-150: HEAD readable before the walk and unreadable
    # after it means the walk read files of more than one revision — the answer
    # is a FAILED `revision_moved_during` with attempts 0, no COMPLETED row, no
    # artifact row, and a status that says exactly that instead of guessing
    r = rig.register('gone')
    rig.walk.then(r.path, lambda p: shutil.rmtree(p))     # this test's own bytes
    assert rig.worker.pass_once() == {'changed': True, 'done': 1}
    (i,) = rig.inspections(r.id)
    assert (i.state, i.failure, i.attempts) == ('FAILED', 'revision_moved_during', 0)
    assert rig.artifacts_() == [] and rig.repo(r.id).architecture_state == 'UNKNOWN'
    (p,) = rig.status()['projects']
    (entry,) = p['repositories']
    assert (entry['architecture_state'], entry['last_inspection']['state'],
            entry['last_inspection']['failure']) == ('UNKNOWN', 'FAILED', 'revision_moved_during')
    # with the directory gone the next pass plans an `unreadable` item naming
    # the reason — a reason recorded, never a guess about the missing tree
    assert [(a, x.entity.id, d['why']) for a, x, d in rig.plan()] == \
        [('unreadable', r.id, 'repository_missing')]


def test_a_moved_head_during_the_walk_is_retried_at_once(rig):
    # worker.py:147-150 with 56-57: a HEAD that moves mid-walk is a failure that
    # says nothing about the repository (UNCOUNTED), so the retry is due now —
    # here with the worker's clock standing *behind* the failure's own stamp,
    # which is exactly when the plain backoff gate at :58 would wrongly refuse
    r = rig.register('mover')
    rig.worker.stopping = _Stop([False, False])             # asked on every item
    moved = []

    def commit(_p):
        if not moved:
            moved.append(rig.set_head(r, SHA_B))
    rig.walk.then(r.path, commit)
    assert rig.worker.pass_once() == {'changed': True, 'done': 1}
    first = rig.inspections(r.id)[0]
    assert (first.state, first.failure, first.attempts) == ('FAILED', 'revision_moved_during', 0)
    assert rig.repo(r.id).architecture_state == 'UNKNOWN'
    rig.worker.clock.skipped = -10 ** 6                    # stand behind failed_at
    assert rig.worker.pass_once() == {'changed': True, 'done': 1}
    got = [(i.revision, i.state, i.attempts) for i in rig.inspections(r.id)]
    assert got == [(SHA_A, 'FAILED', 0), (SHA_B, 'COMPLETED', 0)]
    assert rig.repo(r.id).last_revision == SHA_B and rig.worker.stopping.calls == [False, False]


def test_the_boot_sweep_frees_a_crashed_row_and_it_is_due_at_once(rig):
    # worker.py:112-113 with 52-58: an inspection RUNNING now was running under
    # a Core that died; the boot sweep fails it as `core_restarted` (UNCOUNTED:
    # the crash is no fault of the repository), the earlier counted attempt keeps
    # its attempts count, and the retry is due immediately — even with the
    # worker's clock standing behind the sweep's own failed_at
    r = rig.register('crashed')
    rig.walk.boom(r.path, RuntimeError('first failure'))
    rig.worker.pass_once()
    assert [(i.state, i.attempts) for i in rig.inspections(r.id)] == [('FAILED', 1)]
    rig.worker.clock.skipped += backoff(1) + 1
    rig.walk.boom(r.path, _Crash('core died mid-walk'))
    with pytest.raises(_Crash):                             # Core dies mid-walk
        rig.worker.pass_once()
    (running,) = rig.inspections(r.id)
    assert running.state == 'RUNNING'
    woke = []
    rig.worker.on_wake = lambda: woke.append(1)
    rig.worker.clock.skipped = -7200.0                      # behind failed_at and its 60 s
    assert rig.worker.sweep() == [running.id]
    (failed,) = rig.inspections(r.id)
    assert (failed.state, failed.failure, failed.attempts) == ('FAILED', 'core_restarted', 1)
    assert rig.pending() == 1 and woke == [1]
    rig.walk.calm(r.path)                                   # the extractor is fine again
    assert rig.worker.pass_once() == {'changed': True, 'done': 1}
    (done,) = rig.inspections(r.id)                         # the same row retried
    assert (done.id, done.state, done.revision, done.attempts) == (running.id, 'COMPLETED',
                                                                    SHA_A, 1)


def test_a_capped_revision_waits_for_head_to_move_and_never_blocks_a_new_one(rig):
    # worker.py:54-55 with 88-96: a revision that failed MAX_ATTEMPTS counted
    # times stops asking for a retry however far the clock is wound — and the
    # cap binds the revision, not the repository: a HEAD that moves is new work
    # the cap must not hold back, exactly as the module docstring promises
    r = rig.register('capped')
    rig.walk.boom(r.path, RuntimeError('boom'))
    for n in (1, 2, 3):
        assert rig.worker.pass_once() == {'changed': True, 'done': 1}
        assert rig.inspections(r.id)[-1].attempts == n
        rig.worker.clock.skipped += backoff(n) + 1
    rig.worker.clock.skipped = 10 ** 6                      # far past any backoff
    assert rig.pending() == 0 and rig.plan() == []
    assert rig.repo(r.id).architecture_state == 'UNKNOWN'
    assert rig.status()['drift'] == []
    rig.walk.calm(r.path)                                     # the extractor is fixed
    rig.set_head(r, SHA_B)                                  # HEAD moves: the wait is over
    assert rig.worker.pending() == 1
    assert rig.worker.pass_once() == {'changed': True, 'done': 1}
    got = [(i.revision, i.state, i.attempts) for i in rig.inspections(r.id)]
    assert got == [(SHA_A, 'FAILED', 3), (SHA_B, 'COMPLETED', 0)]
    assert rig.repo(r.id).architecture_state == 'CONSISTENT'


def test_a_corrupt_previous_payload_completes_nothing(rig):
    # worker.py:153-158 (the `artifacts.get` at :156): the diff against the
    # previous observation reads that older blob back, and the store verifies
    # it — bytes that no longer hash to their address are reported, never
    # returned. The pass dies on the ValueError with its inspection still
    # RUNNING and nothing committed; a diff built on an unverified blob would
    # be a lie, so nothing may exist that says otherwise
    r = rig.register('rot')
    rig.worker.pass_once()
    (first,) = rig.inspections(r.id)
    original = rig.corrupt(first.payload_sha256)
    rig.set_head(r, SHA_B)
    with pytest.raises(ValueError) as e:
        rig.worker.pass_once()
    assert 'corrupt' in str(e.value)
    second = rig.inspections(r.id)[-1]
    assert (second.state, second.revision) == ('RUNNING', SHA_B)
    assert rig.repo(r.id).last_revision == SHA_A
    assert rig.repo(r.id).architecture_state == 'STALE'     # moved, not yet observed
    rig.restore(first.payload_sha256, original)
    assert rig.worker.sweep() == [second.id]                # the crashed row goes first
    assert rig.worker.pass_once() == {'changed': True, 'done': 1}
    done = rig.inspections(r.id)[-1]
    assert (done.id, done.state) == (second.id, 'COMPLETED')
    assert done.diff_from_previous is not None              # the diff really was rebuilt
    assert rig.repo(r.id).architecture_state == 'CONSISTENT'


def test_an_unverifiable_payload_is_never_assessed(rig):
    # worker.py:164-167 (the `artifacts.get` at :167): a constraint declared
    # after an inspection re-evaluates the stored payload — read back through
    # the store's digest check. Hostile bytes at that address must not become
    # findings: the pass raises, the repository keeps saying STALE with no
    # findings of a set it never really saw, the drift list stays empty and the
    # digest reports no drift found; restore the blob and the same work lands,
    # violated, in status and in the digest
    r = rig.register('poison')
    rig.worker.pass_once()
    (first,) = rig.inspections(r.id)
    rig.run(world.declare_constraint, project_id=r.project_id, statement='ghost module',
            kind='module_exists', spec={'path': 'app/ghost.py'})
    assert rig.plan()[0][0] == 'assess'
    original = rig.corrupt(first.payload_sha256)
    with pytest.raises(ValueError) as e:
        rig.worker.pass_once()
    assert 'corrupt' in str(e.value)
    repo = rig.repo(r.id)
    assert (repo.architecture_state, repo.findings) == ('STALE', ())
    assert rig.status()['drift'] == []
    assert 'drift_found' not in {g['headline'] for g in rig.digest()['groups']}
    rig.restore(first.payload_sha256, original)
    assert rig.worker.pass_once() == {'changed': True, 'done': 1}
    repo = rig.repo(r.id)
    assert (repo.architecture_state, repo.findings[0]['status'],
            repo.findings[0]['reason']) == ('DRIFTED', 'violated', 'no file matches app/ghost.py')
    assert [d['repository_id'] for d in rig.status()['drift']] == [r.id]
    assert ('drift_found' in {g['headline'] for g in rig.digest()['groups']})


# ── boundary values ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('attempts,want', [
    (0, 0.0),                                                # worker.py:37 zero case
    (1, 60.0), (2, 120.0), (3, 240.0), (6, 1920.0),
    (7, 3600.0),                                             # worker.py:37 cap boundary
    (8, 3600.0), (64, 3600.0),                               # and it stays capped
], ids=['zero', 'once', 'twice', 'thrice', 'sixth', 'cap-at', 'past', 'huge'])
def test_backoff_starts_at_zero_and_never_exceeds_the_cap(attempts, want):
    # worker.py:35-37: no wait after zero failures (a fresh revision is due now),
    # doubling after each counted one, capped so a long outage never becomes an
    # unbounded sleep that outlives the reason for the retry
    assert backoff(attempts) == want
    assert backoff(attempts + 1) >= want                    # never asked to wait less


def test_pending_wakes_the_worker_only_when_work_is_due(rig):
    # worker.py:99-105 (§14 A1): `pending()` is exactly the work the next pass
    # would do — one wake when there is any, none when there is none — and a
    # missing repository is work too: its failure item is due, so it wakes
    woke = []
    rig.worker.on_wake = lambda: woke.append(1)
    r = rig.register('sleeper')
    assert rig.worker.pending() == 1 and woke == [1]
    rig.worker.pass_once()
    assert rig.worker.pending() == 0 and woke == [1]        # settled: nobody is woken
    shutil.rmtree(r.path)                                    # this test's own bytes
    assert rig.worker.pending() == 1 and woke == [1, 1]
    rig.worker.on_wake = None                                # a caller without a wake
    assert rig.worker.pending() == 1                         # still counts the work


def test_a_stopping_worker_leaves_the_rest_of_the_pass(rig):
    # worker.py:118-120 (`if self.stopping(): break`): asked to stop between the
    # items, the worker finishes nothing further — the repository it never
    # reaches has no inspection row at all, was never walked, and its work is
    # still planned next time; the item before the stop keeps its result
    a, b = rig.register('first'), rig.register('second')
    rig.worker.stopping = _Stop([False, True])
    assert rig.worker.pass_once() == {'changed': True, 'done': 2}
    assert rig.worker.stopping.calls == [False, True]
    assert [i.state for i in rig.inspections(a.id)] == ['COMPLETED']
    assert rig.inspections(b.id) == [] and rig.walk.seen == [a.path]
    assert rig.repo(b.id).architecture_state == 'UNKNOWN'
    assert [(x.entity.id, a_) for a_, x, d in rig.plan()] == [(b.id, 'inspect')]


# ── the error paths as the read-models see them ─────────────────────────────

def test_failures_leave_no_news_and_a_stale_assessment_is_labelled_stale(rig):
    # worker.py:124-127 and 135-137 (`failure=why`, `failure=e.reason` through
    # `fail_inspection`): what an unreadable or moved repository leaves
    # behind is a FAILED row naming its reason and a status telling the truth —
    # architecture unchanged, no drift claimed, and a digest that reports no
    # drift news of any kind, because a failure is not a finding
    missing, moved = rig.register('missing'), rig.register('moved')
    rig.walk.boom(moved.path, inspection.Unreadable('head_unresolvable', 'synthetic'))
    shutil.rmtree(missing.path)                              # this test's own bytes
    assert rig.worker.pass_once() == {'changed': True, 'done': 2}
    assert [(i.failure, i.attempts, i.revision) for i in rig.inspections(missing.id)] \
        == [('repository_missing', 1, None)]
    assert [(i.failure, i.attempts, i.revision) for i in rig.inspections(moved.id)] \
        == [('head_unresolvable', 1, SHA_A)]
    st = rig.status()
    by_repo = {e['id']: e for p in st['projects'] for e in p['repositories']}
    assert (by_repo[missing.id]['architecture_state'],
            by_repo[missing.id]['last_inspection']['state']) == ('UNKNOWN', 'FAILED')
    assert (by_repo[moved.id]['architecture_state'],
            by_repo[moved.id]['last_inspection']['failure']) == ('UNKNOWN', 'head_unresolvable')
    assert st['drift'] == [] and st['unchecked'] == []
    assert {g['headline'] for g in rig.digest()['groups']} <= {'progressed'}
