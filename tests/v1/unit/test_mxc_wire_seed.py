# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-804 wiring: an injected seed stager runs after the create intent and before the
child is made, and an injected re-check runs as the very last act before the single
resume; a refusal at either point ends the launch not clean. Same fakes as the wire tests."""

import os

import pytest

from archeus.node import local, mxc, mxc_ledger as ledger_mod, staging

from .test_mxc_wire import args, journal_ops, native_parts, wire  # noqa: F401

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)


class Seam:
    def __init__(self, h, stage=None, recheck=None):
        self.h, self.seen, self.stage_fn, self.recheck_fn = h, [], stage, recheck
        h.launch.seed_stage, h.launch.seed_recheck = self.stage, self.recheck

    def snapshot(self, name):
        events = self.h.api.events
        self.seen.append((name, journal_ops(self.h.journal), events.count('create'),
                          events.count('resume')))

    def stage(self):
        self.snapshot('stage')
        if self.stage_fn:
            self.stage_fn()

    def recheck(self):
        self.snapshot('recheck')
        if self.recheck_fn:
            self.recheck_fn()


def raising(error):
    def act():
        raise error
    return act


def refused_not_clean(h):
    assert h.launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    assert h.api.events.count('resume') == 0
    assert h.boundary.closed == [] and h.job in h.boundary.open


def test_the_default_has_no_seed_seam_and_starts_as_before(wire):
    h = wire(**OK)
    assert h.launch.seed_stage is None and h.launch.seed_recheck is None
    h.launch.start(job=h.job)
    assert journal_ops(h.journal) == ['intent', 'ownership']
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN


def test_the_stager_runs_after_the_intent_and_before_the_child_is_made(wire):
    h = wire(**OK)
    seam = Seam(h)
    h.launch.start(job=h.job)
    assert seam.seen[0] == ('stage', ['intent'], 0, 0)
    h.launch.process.terminate()


def test_the_recheck_runs_after_the_ownership_and_just_before_the_resume(wire):
    h = wire(**OK)
    seam = Seam(h)
    h.launch.start(job=h.job)
    assert seam.seen[1] == ('recheck', ['intent', 'ownership'], 1, 0)
    assert [name for name, *_ in seam.seen] == ['stage', 'recheck']
    assert h.api.events.count('resume') == 1
    h.launch.process.terminate()


def test_the_recheck_runs_after_the_watchdog_is_recorded(wire):
    h = wire(**OK)
    order = []
    h.launch.watchdog = type('Dog', (), {'record': lambda self, job: order.append('record')})()
    Seam(h, recheck=lambda: order.append('recheck'))
    h.launch.start(job=h.job)
    assert order == ['record', 'recheck']
    h.launch.process.terminate()


@pytest.mark.parametrize('failure', [staging.StageError('refused'), OSError('lost'),
                                     RuntimeError('boom')])
def test_a_stager_that_refuses_never_makes_the_child(wire, failure):
    h = wire(**OK)
    seam = Seam(h, stage=raising(failure))
    with pytest.raises(type(failure)):
        h.launch.start(job=h.job)
    assert [name for name, *_ in seam.seen] == ['stage']
    assert h.api.events.count('create') == 0 and h.api.events.count('kill') == 0
    assert h.api.handles == {} and h.launch.process is None
    assert journal_ops(h.journal) == ['intent', 'quarantine']
    refused_not_clean(h)


@pytest.mark.parametrize('failure', [staging.StageError('drift'), OSError('lost'),
                                     RuntimeError('boom')])
def test_a_recheck_that_refuses_terminates_the_child_and_never_resumes(wire, failure):
    h = wire(**OK)
    Seam(h, recheck=raising(failure))
    with pytest.raises(type(failure)):
        h.launch.start(job=h.job)
    assert h.api.events.count('create') == 1 and h.api.events.count('kill') == 1
    assert h.api.handles == {} and h.launch.process is None
    refused_not_clean(h)


def test_a_refused_start_is_never_started_again(wire):
    h = wire(**OK)
    Seam(h, recheck=raising(staging.StageError('drift')))
    with pytest.raises(staging.StageError):
        h.launch.start(job=h.job)
    with pytest.raises(staging.StageError, match='consumed'):
        h.launch.start(job=h.job)


def test_the_real_wrappers_stage_and_recheck_a_seed_and_the_launch_ends_clean(wire, tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'a.txt').write_bytes(b'one')
    dest = tmp_path / 'seeded'
    h = wire(**OK)
    h.launch.seed_stage = lambda: staging.seed_execution({'a.txt': str(source / 'a.txt')}, dest)
    h.launch.seed_recheck = lambda: staging.recheck_execution(dest)
    h.launch.start(job=h.job)
    assert (dest / 'a.txt').read_bytes() == b'one'
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN


def test_a_seed_that_gained_a_second_name_before_the_resume_ends_not_clean(wire, tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'a.txt').write_bytes(b'one')
    dest = tmp_path / 'seeded'

    def stage():
        staging.seed_execution({'a.txt': str(source / 'a.txt')}, dest)
        try:
            os.link(dest / 'a.txt', tmp_path / 'outside.txt')
        except OSError:
            pytest.skip('no hardlinks on this volume')

    h = wire(**OK)
    h.launch.seed_stage = stage
    h.launch.seed_recheck = lambda: staging.recheck_execution(dest)
    with pytest.raises(staging.StageError, match='scan refused'):
        h.launch.start(job=h.job)
    assert h.api.events.count('kill') == 1
    refused_not_clean(h)


def test_a_seed_that_vanished_before_the_resume_ends_not_clean(wire, tmp_path):
    h = wire(**OK)
    h.launch.seed_recheck = lambda: staging.recheck_execution(tmp_path / 'never-seeded')
    h.launch.seed_stage = lambda: None
    with pytest.raises(staging.StageError):
        h.launch.start(job=h.job)
    refused_not_clean(h)


@pytest.mark.parametrize('stage, recheck', [(lambda: None, None), (None, lambda: None),
                                            ('no', lambda: None), (lambda: None, 'no')])
def test_a_stager_and_its_recheck_come_together(args, wire, stage, recheck):
    h = wire()
    with pytest.raises(staging.StageError, match='seed stager'):
        local.MxcLaunch(api=h.api, boundary=h.boundary, ledger=h.journal,
                        schema_validator=lambda raw: True, execution_id='e9',
                        outcome=lambda process: 0, seed_stage=stage, seed_recheck=recheck,
                        **args)


def test_a_seed_seam_without_a_journalled_launch_is_refused(args):
    with pytest.raises(staging.StageError, match='seed stager'):
        local.MxcLaunch(backend=object(), outcome=lambda process: 0,
                        seed_stage=lambda: None, seed_recheck=lambda: None, **args)


# ── B5: the seed fills the workspace the launch was already granted ──

def source_files(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'a.txt').write_bytes(b'one')
    return {'a.txt': str(source / 'a.txt')}


def seeded_launch(args, wire, files):
    """The launch is built over the empty workspace Core made, so its grants name a
    directory that exists; the seed then fills that same directory."""
    workspace = args['workspace']
    h = wire(**OK)
    h.launch.seed_stage = lambda: staging.seed_execution(files, workspace)
    h.launch.seed_recheck = lambda: staging.recheck_execution(workspace)
    return h, workspace


def test_the_empty_workspace_is_granted_then_seeded_in_place_then_the_launch_ends_clean(
        tmp_path, args, wire):
    files = source_files(tmp_path)
    h, workspace = seeded_launch(args, wire, files)
    assert os.listdir(workspace) == []
    assert h.launch.policy.raw['filesystem']['readwritePaths'] == [workspace]
    seam = Seam(h, stage=h.launch.seed_stage, recheck=h.launch.seed_recheck)
    h.launch.start(job=h.job)
    assert [row[:2] for row in seam.seen] == [('stage', ['intent']),
                                              ('recheck', ['intent', 'ownership'])]
    assert open(os.path.join(workspace, 'a.txt'), 'rb').read() == b'one'
    assert os.stat(os.path.join(workspace, 'a.txt')).st_nlink == 1
    assert h.launch.wait() == 0
    assert h.launch.end_state['state'] == ledger_mod.DEAD_CLEAN


def test_a_workspace_that_already_holds_something_is_never_seeded_and_never_runs(
        tmp_path, args, wire):
    files = source_files(tmp_path)
    h, workspace = seeded_launch(args, wire, files)
    open(os.path.join(workspace, 'planted.txt'), 'wb').write(b'x')
    with pytest.raises(staging.StageError, match='already exists and is not empty'):
        h.launch.start(job=h.job)
    assert os.listdir(workspace) == ['planted.txt']
    assert h.api.events.count('create') == 0 and h.launch.process is None
    assert journal_ops(h.journal) == ['intent', 'quarantine']
    refused_not_clean(h)


def test_a_second_name_planted_in_the_seeded_workspace_never_gets_a_child(
        tmp_path, args, wire):
    # the workspace is a grant, so the policy gate's own scan sees the second name
    # before the child is made, ahead of the re-check that would catch it at the resume
    files = source_files(tmp_path)
    h, workspace = seeded_launch(args, wire, files)
    stage = h.launch.seed_stage

    def plant():
        stage()
        try:
            os.link(os.path.join(workspace, 'a.txt'), tmp_path / 'outside.txt')
        except OSError:
            pytest.skip('no hardlinks on this volume')

    h.launch.seed_stage = plant
    with pytest.raises(mxc.MxcUnavailable, match='a second name.: a.txt'):
        h.launch.start(job=h.job)
    assert h.api.events.count('create') == 0 and h.launch.process is None
    refused_not_clean(h)


def test_the_launch_is_refused_a_workspace_that_does_not_exist_before_anything_is_seeded(
        tmp_path, args, wire):
    args['workspace'] = args['cwd'] = str(tmp_path / 'never-made')
    with pytest.raises(OSError):
        wire(**OK)
