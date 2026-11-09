"""T-733 (verification-hardening): the branches of the evidence collector
(`archeus/core/verification/evidence.py`) that no test in tests/v1 reached —
the fail-closed and denial paths first, then the boundary values, then the
error paths.

The rig is the one tests/v1/unit/test_gaps_core_verification_worker.py built
for this package, reduced to what these functions need: the real database of
real rows for the reads that go through `rows` (so `commands` and
`project_root` really query P4's rows), the real artifact store under the
test's own `ARCHEUS_HOME` (the autouse fixture of tests/v1/conftest.py) for
what `check_of` stores, and a fake for each call out of the process (the
node, `shutil.which`). A node call no fake was given for fails the test where
it is made, so evidence that reached git or a command where it must not is
caught here. Nothing needs a real repository, a process, the network or
Windows; every OS question is asked through the seam the worker file uses
(the interpreter's own directory as the staged toolchain) or through a
monkeypatched `shutil.which`.
"""

import hashlib
import os
import sys
from types import SimpleNamespace

import pytest

from archeus.core.application import verification as V
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.verification import evidence
from archeus.infra import paths
from archeus.infra.artifacts import store
from archeus.infra.db import Database

#: revisions as git would name them
REV, REV2, BASE = 'a' * 40, 'b' * 40, 'd' * 40


@pytest.fixture
def db(archeus_home):                     # as in tests/v1/unit/test_gaps_core_metrics.py
    d = Database.open()
    try:
        yield d
    finally:
        d.close()


@pytest.fixture
def stage():
    """The directory of one real program and the program's own name, as the
    worker file's fixture defines it: what `confined_argv` accepts as confined
    and nothing else. The interpreter's directory rather than a file written
    under `tmp_path`, because the real `shutil.which` asks the platform
    whether a file may run at all, and a noexec mount would decide what these
    tests decide."""
    exe = os.path.realpath(sys.executable)
    return os.path.dirname(exe), os.path.basename(exe)


class _Node:
    """The evidence module's node: every call recorded, each answered by the
    fake given for it, and any call no fake was given for fails the test where
    it is made — that is how these tests say that *nothing* reached git or a
    command."""

    def __init__(self, **fake):
        self.fake, self.calls = fake, []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name, a, k))
            if name not in self.fake:
                raise AssertionError('evidence called node.%s%r' % (name, a))
            return self.fake[name](*a, **k)
        return call


def _result(exit_code=0, error=None, output=b'ok', **extra):
    """One command run, as the node reports it: the shape `check_of` reads."""
    return dict({'exit_code': exit_code, 'duration_ms': 1, 'error': error, 'output': output,
                 'output_bytes': len(output or b''), 'truncated': False}, **extra)


# ── the one writer command: P4's rows as an inspection pass left them ───────

def _place(db, *items, project=None):
    """Place *items* as an earlier pass left them, with the event that records
    them: a mutation without an event is rolled back (writer.py)."""
    actor = Ref('system', ids.new_id('principal'))
    mid = ids.new_id('mission')
    mission = entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE,
                               title='Fix add', objective='Make add add',
                               state='EXECUTING')

    def put(tx, *, actor):
        tx.insert(mission, actor=actor)
        for x in items:
            tx.insert(x, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor,
                            payload={'fields': [], 'placed_by': 'T-733'},
                            workspace=ids.GLOBAL_WORKSPACE, project=project))
    return db.writer.execute(put, {'actor': actor})


def _repo_rows(project_id, path, inspections):
    """One repository at *path* and its inspections: *inspections* is a list of
    (state, test_commands, build_commands), placed oldest first — `commands`
    reads `rows.where`, which answers in insertion order."""
    rid = ids.new_id('repository')
    rows = [entities.Repository(id=rid, workspace_id=ids.GLOBAL_WORKSPACE,
                                project_id=project_id, path=path,
                                path_key=os.path.normcase(os.path.abspath(path)))]
    for state, tests, builds in inspections:
        rows.append(entities.RepositoryInspection(
            id=ids.new_id('repository_inspection'), repository_id=rid,
            extractor_version=1, state=state,
            test_commands=tuple(tests), build_commands=tuple(builds)))
    return rows


def _read(db, fn):
    with db.read() as conn:
        return fn(conn)


# ── commands(): what may run at all comes from rows, and from rows alone ────

def test_no_commands_when_the_project_or_the_root_is_unknown(db, tmp_path):
    # evidence.py:28-29: a verification that does not know which project, or
    # where on disk, must run nothing — fail-closed before any query. Remove
    # the guard and `rows.where` raises (or the normcase of None raises) here.
    proj = ids.new_id('project')
    root = str(tmp_path / 'project')
    _place(db, entities.Project(id=proj, workspace_id=ids.GLOBAL_WORKSPACE,
                                name='repo', root_paths=(root,)),
           *_repo_rows(proj, root, [('COMPLETED', ('tool --check',), ('build',))]),
           project=proj)
    assert _read(db, lambda c: evidence.commands(c, None, root)) == ((), ())
    assert _read(db, lambda c: evidence.commands(c, proj, None)) == ((), ())
    assert _read(db, lambda c: evidence.commands(c, None, None)) == ((), ())


def test_no_commands_when_the_project_has_no_repository(db, tmp_path):
    # evidence.py:34-35: a project with no repository row has no facts; the
    # verification gets no commands, so it goes to a person rather than to an
    # invented runner.
    proj = ids.new_id('project')
    _place(db, entities.Project(id=proj, workspace_id=ids.GLOBAL_WORKSPACE,
                                name='repo', root_paths=(str(tmp_path),)),
           project=proj)
    assert _read(db, lambda c: evidence.commands(c, proj, str(tmp_path))) == ((), ())


def test_no_commands_from_an_inspection_that_never_completed(db, tmp_path):
    # evidence.py:38-40: only a COMPLETED inspection is facts. An extractor
    # that started and died leaves candidate commands behind; handing them to
    # the verifier as if the inspection had vouched for them is the forgery
    # this branch refuses. Flip the `== 'COMPLETED'` filter and the task runs
    # commands nobody inspected.
    proj = ids.new_id('project')
    root = str(tmp_path / 'project')
    _place(db, entities.Project(id=proj, workspace_id=ids.GLOBAL_WORKSPACE,
                               name='repo', root_paths=(root,)),
           *_repo_rows(proj, root, [('RUNNING', ('tool --check',), ('build',))]),
           project=proj)
    assert _read(db, lambda c: evidence.commands(c, proj, root)) == ((), ())


def test_the_matching_repository_and_the_last_completed_inspection_answer(
        db, tmp_path):
    # evidence.py:32-33 and 41: with two repositories the one whose real,
    # case-folded path matches answers — not the first row — so the commands
    # of an unrelated checkout are never run here; with no match the fallback
    # is the first repository (documented behaviour pinned here so a change is
    # a decision, not an accident). `done[-1]`: the newest COMPLETED inspection
    # answers, and a newer inspection that failed does not erase it.
    proj = ids.new_id('project')
    root = str(tmp_path / 'here')
    rows_a = _repo_rows(proj, str(tmp_path / 'other'),
                        [('COMPLETED', ('stale --a',), ())])
    rows_b = _repo_rows(proj, root, [('COMPLETED', ('early --b0',), ('earlyb',)),
                                     ('COMPLETED', ('right --b',), ('buildb',)),
                                     ('FAILED', ('forged --b2',), ())])
    _place(db, entities.Project(id=proj, workspace_id=ids.GLOBAL_WORKSPACE,
                                name='repo', root_paths=(root,)),
           *rows_a, *rows_b, project=proj)
    assert _read(db, lambda c: evidence.commands(c, proj, root)) == (('right --b',),
                                                                     ('buildb',))
    # no match at all: the first repository answers, which is why the matching
    # row must win when one exists (the case-folded identity is the platform's
    # own `normcase`, so nothing here depends on case)
    assert _read(db, lambda c: evidence.commands(c, proj, str(tmp_path / 'none'))) == \
        (('stale --a',), ())


# ── project_root(): no root is better than a guessed one ────────────────────

def test_project_root_refuses_every_shape_of_not_there(db, tmp_path):
    # evidence.py:46-50: no project id, no project row, and a project with no
    # root are all None, never a guess; a real project answers with its FIRST
    # root. Return the second root, or guess a cwd, and the verification reads
    # the wrong checkout.
    assert _read(db, lambda c: evidence.project_root(c, None)) is None
    assert _read(db, lambda c: evidence.project_root(c, ids.new_id('project'))) is None
    bare = ids.new_id('project')
    two = ids.new_id('project')
    _place(db, entities.Project(id=bare, workspace_id=ids.GLOBAL_WORKSPACE, name='bare'),
           entities.Project(id=two, workspace_id=ids.GLOBAL_WORKSPACE, name='two',
                            root_paths=(str(tmp_path / 'first'), str(tmp_path / 'second'))))
    assert _read(db, lambda c: evidence.project_root(c, bare)) is None
    assert _read(db, lambda c: evidence.project_root(c, two)) == str(tmp_path / 'first')


# ── argv_of / confined_argv: a program either is found where it may be, or
#    nothing runs ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('line', ['', '   ', '"', "echo 'unclosed"],
                         ids=['empty', 'spaces', 'unclosed-quote', 'unclosed-single'])
def test_a_line_that_is_not_a_command_is_no_argv_for_either_builder(line):
    # evidence.py:58-61 and 72-74: an unparseable or empty line is None for the
    # unconfined AND the confined builder — None is what turns into an error
    # check upstream, never into an empty argv handed to a process.
    assert evidence.argv_of(line) is None
    assert evidence.confined_argv(line, [os.curdir]) is None


def test_argv_of_resolves_the_program_on_path_and_keeps_the_rest(tmp_path, monkeypatch):
    # evidence.py:62-63: `which` is asked for argv[0] alone (so `npm` finds
    # `npm.cmd` on Windows) and only the program is replaced — the arguments
    # pass through verbatim; a program PATH does not hold is kept as written.
    seen = []
    found = os.path.join(str(tmp_path), 'tool-resolved')

    def which(cmd, **kw):
        seen.append((cmd, kw))
        return found if cmd == 'tool' else None
    monkeypatch.setattr(evidence, 'shutil', SimpleNamespace(which=which))
    assert evidence.argv_of('tool --check x') == [found, '--check', 'x']
    assert seen == [('tool', {})]
    assert evidence.argv_of('other --check') == ['other', '--check']


def test_confined_argv_never_asks_the_platform_outside_the_toolchain(
        tmp_path, monkeypatch):
    # evidence.py:76: the search is pinned to the staged directories
    # (`path=os.pathsep.join(toolchain)`). Drop that argument and `which`
    # consults the machine's PATH — a program the stage never held would then
    # be reported as confined, which is exactly the escape T-054 Q1 A closes.
    seen = []
    tc = [str(tmp_path / 'tc-a'), str(tmp_path / 'tc-b')]

    def which(cmd, **kw):
        seen.append((cmd, kw))
        return None
    monkeypatch.setattr(evidence, 'shutil', SimpleNamespace(which=which))
    assert evidence.confined_argv('tool --check', tc) is None
    assert seen == [('tool', {'path': os.pathsep.join(tc)})]


@pytest.mark.parametrize('found', ['missing', 'elsewhere', 'subdir'],
                         ids=['not-found', 'outside-stage', 'in-a-subdir'])
def test_confined_argv_refuses_every_program_the_stage_does_not_hold(
        tmp_path, monkeypatch, found):
    # evidence.py:79-80: not found at all, found in a directory the stage does
    # not hold (Windows' `which` looks in the current directory first), or
    # found in a SUBdirectory of one — the stage is exactly its listed
    # directories, so all three are refusals. Invert the `not in dirs` test or
    # compare against the stage root instead of its directories, and a
    # non-staged binary is here reported as confined.
    tc = os.path.join(str(tmp_path), 'stage')
    answers = {'missing': None,
               'elsewhere': os.path.join(str(tmp_path), 'elsewhere', 'tool.exe'),
               'subdir': os.path.join(tc, 'sub', 'tool')}
    monkeypatch.setattr(evidence, 'shutil',
                        SimpleNamespace(which=lambda cmd, **kw: answers[found]))
    assert evidence.confined_argv('tool --check', [tc]) is None


def test_confined_argv_accepts_a_staged_program_by_its_real_seam(stage):
    # evidence.py:81: a program the stage really holds is accepted — through
    # the platform's own `which`, pinned to the stage — as its absolute path
    # plus the untouched arguments. Return the bare name, or argv[0] itself,
    # and this fails on every platform.
    out = evidence.confined_argv('%s --version' % stage[1], [stage[0]])
    assert os.path.normcase(out[0]) == os.path.normcase(os.path.join(*stage))
    assert out[1:] == ['--version']


def test_confined_argv_records_the_absolute_normalised_path(tmp_path, monkeypatch):
    # evidence.py:81 again, deterministically: what the check row records is
    # `os.path.abspath(found)`, not whatever string `which` happened to answer
    # — a recorded path with `.` or `..` segments in it is the same program to
    # run but a different string to every comparison and log that follows.
    # (Verified caught: replacing `abspath(found)` with `found` fails this
    # test — a mutation probe on scratch/mutation_check.py confirmed.)
    tc = os.path.join(str(tmp_path), 'stage')
    found = os.path.join(tc, '.', 'nest', '..', 'tool')
    monkeypatch.setattr(evidence, 'shutil',
                        SimpleNamespace(which=lambda cmd, **kw: found))
    out = evidence.confined_argv('tool --check', [tc])
    assert out == [os.path.abspath(found), '--check']


def test_confined_argv_refuses_a_real_program_the_stage_does_not_hold(stage, tmp_path):
    # evidence.py:79-80 again, with the real `shutil.which`: the interpreter
    # exists on PATH, but the stage is an empty directory, so it is not
    # confined here. Widen the search to the machine's PATH and this finds it.
    assert evidence.confined_argv('%s --version' % stage[1], [str(tmp_path)]) is None


# ── check_of(): what a run means, and what is kept of it ────────────────────

def test_an_error_is_an_error_even_with_a_zero_exit_code():
    # evidence.py:95-99: the node's `error` outranks the exit code — a run the
    # node could not complete is an ERROR even if it somehow reports exit 0
    # (a timeout with no exit code, a spawn that never happened). Swap the
    # order of the checks, or trust a reported 0, and a never-finished run
    # becomes a pass. The full shape is pinned too: an error check still names
    # the command and keeps the bytes the node reported.
    c = evidence.check_of('test', 'tool --check', ['tool', '--check'],
                          _result(exit_code=0, error='timed out after 7s',
                                  output=b'half a log'))
    assert c['name'] == 'test: tool --check' and c['kind'] == 'command'
    assert c['argv'] == ['tool', '--check'] and c['exit_code'] == 0
    assert c['output_sha256'] == hashlib.sha256(b'half a log').hexdigest()
    assert (c['result'], c['detail']) == ('error', 'timed out after 7s')
    c = evidence.check_of('test', 'tool', ['tool'], _result(exit_code=None, error='nope'))
    assert c['result'] == 'error'
    assert evidence.check_of('test', 'tool', ['tool'], _result(exit_code=0))['result'] \
        == 'pass'
    c = evidence.check_of('test', 'tool', ['tool'], _result(exit_code=3, output=b''))
    assert (c['result'], c['detail']) == ('fail', 'exit 3')


def test_a_check_stores_its_output_once_and_carries_only_its_own_confinement(
        monkeypatch):
    # evidence.py:88-94: the output is stored exactly as the node gave it and
    # named by its sha256; NO bytes means NO artifact (`if r['output']`, not
    # "always put"); `confinement` travels only when the run was confined —
    # an unconfined check that grew one would vouch for an isolation that
    # never happened.
    puts = []

    def spy(data):
        puts.append(data)
        return store.put(data)                      # the real store, under ARCHEUS_HOME
    monkeypatch.setattr(evidence, 'store', SimpleNamespace(put=spy))
    c = evidence.check_of('test', 'tool', ['tool'], _result(output=b'hello'))
    assert puts == [b'hello']
    out = b'the full log'
    c = evidence.check_of('test', 'tool', ['tool'], _result(output=out))
    assert c['output_sha256'] == hashlib.sha256(out).hexdigest()
    assert store.get(c['output_sha256']) == out                    # stored once, verbatim
    puts[:] = []
    assert evidence.check_of('test', 'tool', ['tool'],
                             _result(output=None))['output_sha256'] is None
    assert evidence.check_of('test', 'tool', ['tool'],
                             _result(output=b''))['output_sha256'] is None
    assert puts == []
    c = evidence.check_of('test', 'tool', ['tool'],
                          _result(confinement={'isolated': True, 'job': 'fake'}))
    assert c['confinement'] == {'isolated': True, 'job': 'fake'}
    assert 'confinement' not in evidence.check_of('test', 'tool', ['tool'], _result())


def test_a_check_cannot_be_rewritten_through_the_argv_it_was_built_from():
    # evidence.py:90: `list(argv)` — the check keeps a copy. Drop the copy and
    # a caller that reuses or mutates its argv after the fact rewrites evidence
    # that was already recorded.
    argv = ['tool', '--check']
    c = evidence.check_of('test', 'tool', argv, _result())
    argv.append('--forged')
    assert c['argv'] == ['tool', '--check']


# ── run_commands(): an unparseable line never reaches a process ─────────────

def test_a_command_that_cannot_be_split_is_an_error_and_starts_nothing(
        tmp_path):
    # evidence.py:114-116 and 117-120 (§8.3): a line `argv_of` refuses is
    # recorded as an error check with NO argv and NO exit code, and the node
    # is never called for it — but the other commands still run, each to its
    # own numbered log under run/verify/<verification id>/ and with the
    # caller's timeout, not the module default. Remove the `continue` and the
    # node gets an argv built from garbage; renumber the logs from the checks
    # and the surviving command's log name moves.
    calls = []

    def run_check(ws, argv, **kw):
        calls.append((ws, list(argv), kw))
        return _result()
    node = SimpleNamespace(run_check=run_check)
    cmds = (('test', "this is not 'split"), ('build', 'tool --build'))
    checks = evidence.run_commands(node, 'ws', cmds, verification_id='vid-1',
                                   timeout_s=7, verifier_version=V.VERIFIER_VERSION)
    assert [c['result'] for c in checks] == ['error', 'pass']
    assert checks[0]['detail'] == 'the command line cannot be parsed'
    assert 'argv' not in checks[0] and 'exit_code' not in checks[0]
    assert len(calls) == 1
    (ws, argv, kw) = calls[0]
    assert (ws, argv) == ('ws', ['tool', '--build'])
    assert kw['timeout'] == 7
    assert kw['out_path'] == os.path.join(paths.run_dir(), 'verify', 'vid-1', '1.log')
    assert os.path.isabs(kw['out_path'])


# ── changes_check(): the diff is evidence or it is nothing ──────────────────

def test_changes_check_refuses_to_compare_without_a_base_or_a_revision():
    # evidence.py:127-129 (§8.3): with nothing to compare against there is no
    # evidence of a change — an ERROR, and no call to git at all. Fall through
    # to numstat with a None rev and git's answer about a garbage range is
    # what would decide the task.
    node = _Node()
    for base, rev in ((None, REV), (BASE, None), (None, None)):
        c = evidence.changes_check(node, 'root', base, rev)
        assert (c['result'], c['detail']) == ('error', 'no base revision to compare with')
        assert (c['name'], c['kind']) == ('changes', 'git')
    assert node.calls == []


def test_a_failed_or_empty_diff_is_never_a_pass():
    # evidence.py:131-135: git failing to diff is an ERROR (never a silent
    # pass), and a diff of nothing is a FAILURE — a task that wrote nothing
    # did not do the work. Invert `if not stat` and an empty diff vouches for
    # the task; drop the `stat is None` test and a dead git is a pass.
    c = evidence.changes_check(_Node(git_numstat=lambda *a: None), 'root', BASE, REV)
    assert c['result'] == 'error'
    assert c['detail'] == 'git could not diff %s..%s' % (BASE[:12], REV[:12])
    node = _Node(git_numstat=lambda *a: [])
    c = evidence.changes_check(node, 'root', BASE, REV)
    assert (c['result'], c['detail']) == ('fail', 'the task changed nothing (%s..%s)'
                                         % (BASE[:12], REV[:12]))
    assert node.calls[0][1] == ('root', BASE, REV)      # asked about exactly this range


def test_a_real_diff_passes_and_the_file_list_is_capped_at_fifty():
    # evidence.py:137-141: what did change is proven by a non-empty numstat;
    # the detail counts EVERY file but the recorded list is capped at 50 —
    # the check is evidence, not an unbounded blob in the row. Drop the slice
    # and 61 names land in the record; count the capped list and the number
    # lies about the change.
    stat = [(1, 1, 'pkg/mod_%02d.py' % i) for i in range(61)]
    c = evidence.changes_check(_Node(git_numstat=lambda *a: stat), 'root', BASE, REV)
    assert (c['result'], c['detail']) == ('pass', '61 file(s) changed')
    assert c['files'] == ['pkg/mod_%02d.py' % i for i in range(50)]


# ── reported_model / provenance: the stream is heard, never trusted ─────────

def _write_stream(eid, *lines):
    """The execution's stream, written as bytes with explicit newlines (the
    same file the process's writer would leave), under the test's ARCHEUS_HOME."""
    p = paths.ExecPaths(eid)
    os.makedirs(p.dir, exist_ok=True)
    with open(p.stream, 'wb') as f:
        f.write(b'\n'.join(lines) + b'\n')


def test_a_stream_that_is_not_there_claims_nothing():
    # evidence.py:149-151 (§22): no stream, or one that cannot be read, is
    # None — an absent execution corroborates nothing, and the file is smaller
    # than `_STREAM_READ`, so the `max(0, size - _STREAM_READ)` seek must not
    # go negative (drop max() and the seek raises, which the guard swallows
    # into None and every real claim disappears too — the claim tests below
    # pin the other side of that).
    eid = ids.new_id('execution')
    assert evidence.reported_model(eid) is None
    _write_stream(eid, b'')
    assert evidence.reported_model(eid) is None


def test_only_the_last_real_claim_of_the_stream_survives():
    # evidence.py:153-166 (§22): garbage is skipped, not fatal (a truncated
    # tail of a crashed run still answers); only a JSON OBJECT can claim; a
    # model must be a non-empty string, or sit as a string inside `message`
    # (`model` beats the nested one); and the LAST claim wins. Drop the
    # `isinstance(ev, dict)` guard and a `[...]` line crashes the read; drop
    # `and m` and '' overwrites a real claim; take the first instead of the
    # last and a hijacked tail line no longer wins — which is the whole point
    # of "corroborating, never trusted".
    eid = ids.new_id('execution')
    _write_stream(eid,
                  b'not json at all',
                  b'[1, 2]',
                  b'42',
                  b'{"model": 7}',
                  b'{"model": "", "message": 5}',
                  b'{"model": "m-first"}',
                  b'{"model": {"x": 1}, "message": [1]}',
                  b'{"message": {"model": "m-last"}}',
                  b'{"model": ""}')          # a dropped `and m` makes this the answer
    assert evidence.reported_model(eid) == 'm-last'
    eid2 = ids.new_id('execution')
    _write_stream(eid2, b'{"model": "m-top", "message": {"model": "m-under"}}')
    assert evidence.reported_model(eid2) == 'm-top'
    eid3 = ids.new_id('execution')
    _write_stream(eid3, b'{"model": "m-kept"}', b'{"model": 0}', b'garbage')
    assert evidence.reported_model(eid3) == 'm-kept'      # a bad line never clears it


def test_provenance_matches_rows_and_claims_without_blaming_either():
    # evidence.py:169-173 (§22): the routed model comes from the ROW; a claim
    # is compared, never adopted; and no claim, or no routed model, is
    # `match: True` — an unknown is not a contradiction. Remove `reported is
    # None or` and an execution with no stream becomes a mismatch, and missing
    # evidence starts failing verifications.
    def prov(model, *lines):
        eid = ids.new_id('execution')
        if lines:
            _write_stream(eid, *lines)
        return evidence.provenance(SimpleNamespace(id=eid, model=model))
    assert prov('m-large') == {'routed_model': 'm-large', 'reported_model': None,
                               'match': True}
    assert prov('m-large', b'{"model": "m-large"}') == {
        'routed_model': 'm-large', 'reported_model': 'm-large', 'match': True}
    assert prov('m-large', b'{"model": "someone-else"}')['match'] is False
    assert prov(None, b'{"model": "someone-else"}') == {
        'routed_model': None, 'reported_model': 'someone-else', 'match': True}
