import calendar
import os

import pytest

from archeus.core.application import sessions as S
from archeus.core.sessions import service as SV
from archeus.harnesses.sessions import ClaudeCodeSessions

from v1.unit import test_gaps_core_sessions_service as g


@pytest.fixture
def rig(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    work.mkdir()
    r = g.Rig(work)
    monkeypatch.setattr(SV, 'rows', r.rows)
    return r


def test_a_brief_that_cannot_be_read_is_a_reported_launch_and_leaves_no_empty_file(rig):
    s = rig.session(launch_seq=1)
    out = rig.service._launch(s.id, 'f' * 64, 'the context')
    assert out['launched'] is False and out['error']
    assert rig.data(S.launched)['error'] == out['error']
    assert not os.path.exists(rig.delivery(s.id)) and rig.term.opened == []


def test_the_sweep_goes_on_after_one_session_cannot_be_asked(rig):
    bad = rig.session(state='OPEN', provider_session_ref='ref-bad')
    gone = rig.session(state='OPEN', provider_session_ref='ref-gone')
    real = rig.fa.locate

    def locate(ref, home, cwd):
        if ref == 'ref-bad':
            raise OSError('home unreadable')
        return real(ref, home, cwd)

    rig.fa.locate = locate
    out = rig.service.sweep()
    assert out['moved'] == [(gone.id, 'LOST')]
    assert bad.id not in [c.data['session_id'] for c in rig.calls(S.vanished)]


def test_epoch_is_utc_in_every_season():
    for iso in ('2026-01-15T12:00:00Z', '2026-07-15T12:00:00Z'):
        assert SV._epoch(iso) == calendar.timegm((int(iso[:4]), int(iso[5:7]), 15, 12, 0, 0))


def test_a_ref_that_is_a_path_never_leaves_the_project_folder(tmp_path):
    outside = tmp_path / 'outside.jsonl'
    outside.write_text('{}\n')
    home = tmp_path / 'home'
    (home / 'projects').mkdir(parents=True)
    assert ClaudeCodeSessions().locate(str(outside)[:-len('.jsonl')], str(home),
                                       str(tmp_path / 'work')) is None
