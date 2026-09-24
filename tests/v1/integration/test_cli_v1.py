"""`archeus core` and `archeus status` end to end, and the reserved verbs
(p3.5b design gate §3 D6, §8, §10 J1, J3)."""

import os
import socket
import sys

import pytest

from archeus.cli import main as cli
from archeus.infra import discovery
from v1.integration.test_core_lifecycle import _status
from v1.judge.http import CoreProcess

WINDOWS = sys.platform.startswith('win')


# ── J1 core / status, J3 deferred verbs ──

def test_core_starts_status_answers_and_a_clean_stop_releases_everything(archeus_home, capsys,
                                                                         monkeypatch):
    core = CoreProcess(archeus_home).start()
    assert _status(capsys, monkeypatch)[0] == 0
    if WINDOWS:
        import signal
        core.proc.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        core.proc.terminate()
    assert core.wait(30) == 0, core.output()
    assert not os.path.exists(discovery.core_json_path())
    assert _status(capsys, monkeypatch)[0] == 1


@pytest.mark.parametrize('verb,phase', sorted(cli.DEFERRED.items()))
def test_a_deferred_verb_does_nothing_names_its_phase_and_exits_2(verb, phase, capsys,
                                                                   monkeypatch, archeus_home):
    def refuse(*a, **k):
        raise AssertionError('a deferred verb touched the network or the database')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    from archeus.infra.db import Database
    monkeypatch.setattr(Database, 'open', refuse)
    assert cli.main([verb, 'x']) == 2
    err = capsys.readouterr().err
    assert err.strip() == 'archeus %s is not available yet (arrives with %s); nothing was done' % (
        verb, phase)
    assert not os.path.exists(archeus_home)


def test_the_legacy_entry_point_dispatches_exactly_the_v1_verbs():
    from claude_sessions import cli as legacy
    assert legacy.V1_VERBS == cli.VERBS
