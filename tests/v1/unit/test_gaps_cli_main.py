"""T-707: the highest-risk uncovered branches of `archeus/cli/main.py`.

The CLI is the only place where a person's words become exit codes, and until
now its denial paths lived only inside integration tests that stand a real
Core up (test_cli_v1.py, test_execution_http.py, ...) — one platform, one
happy shape each. The four regressions of test_fix_cli_main.py are the only
unit tests this module had. The ten branches this card names as highest-risk,
fail-closed first, are each quoted in the docstring of the test that owns it:

 1. main.py:368-372  estop: a Core that answers and refuses is not bypassed.
 2. main.py:369-387  estop: a Core that cannot be reached (code `network`)
                     still runs the local stop.
 3. main.py:381-384  estop: a STOP file that cannot be written is exit 2, never
                     a claimed stop.
 4. main.py:256-258  _get: without the local token not one request is built.
 5. main.py:466-468  decide: a target/verdict shape that fits neither is usage,
                     nothing sent.
 6. main.py:212-215  pair: Core's refusal to start a pairing is exit 2.
 7. main.py:673      status: exit 3 exactly when the engine failed.
 8. main.py:650-653  status: an unreadable discovery file sends nothing, exit 2.
 9. main.py:137-140  dispatch: `pause all` never pauses a mission named `all`,
                     and only the exact `pause all --now` is the e-stop.
10. main.py:168-171, 158-159  dispatch: `core` with a malformed --remote-host
                     never reaches runtime.

Six further tests (11-16) close the same file's other uncovered denial and
boundary paths: the `_flags` rejections, the unknown automation action, the
missing create file, `devices revoke` without an id, the resume whose
terminal failed to open, and `_get` saying a refusal in Core's own words.

Style follows tests/v1/unit/test_fix_cli_main.py: monkeypatch the seams that
file already uses — `main._running`, `main._get`, `discovery.discover`,
`discovery.read_local_token`, `client.Core`, `LocalNode.estop_without_core` —
and nothing here opens a socket, a process, a real terminal or the clock of
the OS, so the file runs identically on Linux and Windows.
"""

import pytest

from archeus.cli import main

#: verbs the dispatch tests must never let through, as a sentinel return
ESTOP_RAN = 'sentinel-estop-ran'


# ── 1-3: the emergency stop's three failure modes ──


def test_a_refusing_core_is_not_bypassed_by_the_local_emergency_stop(monkeypatch, capsys):
    """Catchest main.py:368-372 (`except client.CoreError ... if e.code !=
    'network': return 2`): a Core that answers and refuses must not be walked
    around by killing processes here — invert the code test and either the
    refusal is bypassed or an unreachable Core is obeyed."""
    from archeus.cli.tui import client
    from archeus.infra import discovery
    from archeus.node.local import LocalNode

    def refuse(self, path, body):
        raise client.CoreError(403, 'not_permitted', {'why': 'disarmed'})
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', {'pid': 7, 'port': 9}))
    monkeypatch.setattr(discovery, 'read_local_token', lambda: 'tok')
    monkeypatch.setattr(client.Core, 'post', refuse)
    monkeypatch.setattr(LocalNode, 'estop_without_core',
                        staticmethod(lambda: pytest.fail('a refusing Core was bypassed')))
    assert main.estop() == 2
    cap = capsys.readouterr()
    assert 'Core did not accept the e-stop' in cap.err
    assert 'Not permitted: disarmed' in cap.err        # Core's own detail, in its words
    assert 'emergency stop' not in cap.out


def test_an_unreachable_core_still_runs_the_local_kill_of_recorded_processes(monkeypatch,
                                                                             capsys):
    """Catchest main.py:369 (`if e.code != 'network'`) falling through 373-387:
    with Core down the CLI is the only thing that can write the STOP sentinel —
    invert the same test's condition and this dies, not a person's machine."""
    from archeus.cli.tui import client
    from archeus.infra import discovery
    from archeus.node.local import LocalNode

    def refuse(self, path, body):
        raise client.CoreError(0, 'network', {'why': 'ConnectionRefused'})
    killed = []
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', {'pid': 7, 'port': 9}))
    monkeypatch.setattr(discovery, 'read_local_token', lambda: 'tok')
    monkeypatch.setattr(client.Core, 'post', refuse)
    monkeypatch.setattr(LocalNode, 'estop_without_core',
                        staticmethod(lambda: (killed.append(1) or (['p1', 'p2'], None))))
    assert main.estop() == 0
    assert killed == [1]
    assert '2 process(es) killed' in capsys.readouterr().out


def test_a_stop_file_that_cannot_be_written_is_a_failure_not_a_claimed_stop(monkeypatch,
                                                                             capsys):
    """Catchest main.py:381-384 (`except OSError ... return 2`): if the STOP
    sentinel cannot be written the run is a failure — remove it and the
    unwritten stop prints its success line and exits 0."""
    from archeus.infra import discovery
    from archeus.node.local import LocalNode

    def refuse(*a):
        raise OSError(30, 'no room')
    monkeypatch.setattr(discovery, 'discover', lambda: ('not_running', None))
    monkeypatch.setattr(LocalNode, 'estop_without_core', staticmethod(refuse))
    assert main.estop() == 2
    cap = capsys.readouterr()
    assert 'emergency stop failed' in cap.err and 'no room' in cap.err
    assert cap.out == ''                                # nothing was stopped, nothing claimed


# ── 4: the token gate on every request ──


@pytest.mark.parametrize('method', ['GET', 'POST'], ids=['get', 'post'])
def test_without_the_local_token_not_one_request_is_built(method, monkeypatch, capsys):
    """Catchest main.py:256-258 (`token = discovery.read_local_token(); if
    token is None: return None`): A5 — discovery proving the port is ours comes
    first and the token goes nowhere without it. Remove the gate and the fake
    client records the construction it must never see."""
    from archeus.cli.tui import client
    from archeus.infra import discovery

    built = []

    class FakeCore:
        def __init__(self, port, token):
            built.append((port, token))

        def get(self, path):
            return {'never': 'built'}, None

        def post(self, path, body):
            return {'never': 'built'}
    monkeypatch.setattr(discovery, 'read_local_token', lambda: None)
    monkeypatch.setattr(client, 'Core', FakeCore)
    assert main._get({'port': 9}, method, '/v1/health') is None
    assert built == []
    assert capsys.readouterr().err == ''                # silence is fine; a request is not


# ── 5-6: decisions and pairings that Core must never be asked for ──


@pytest.mark.parametrize('target,verdict', [
    ('ver_1', 'changes'),                                # a verification has no `changes`
    ('msn_1', 'approve'),                                # `approve` is not a review verdict
    ('exe_1', 'accept'),                                  # neither id prefix
    ('msn_1', 'changes_requested'),                       # the mapped value is not an input
], ids=['ver-changes', 'msn-approve', 'bad-prefix', 'already-mapped'])
def test_a_decision_shape_that_fits_neither_is_usage_with_nothing_sent(target, verdict,
                                                                        monkeypatch, capsys):
    """Catchest main.py:466-468 (the `else` of decide): the two accepted shapes
    are exact; widen them and a guess becomes an irreversible decision on
    whatever Core holds under that id."""
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    monkeypatch.setattr(main, '_get',
                        lambda *a, **k: pytest.fail('a decision was sent for a bad shape'))
    assert main.decide(target, verdict) == 2
    assert capsys.readouterr().err.startswith('usage:')


def test_cores_refusal_to_start_a_pairing_is_exit_two(monkeypatch, capsys):
    """Catchest main.py:212-215 (`if out is None: ... return 2` in pair): a
    refused pairing must never print a code or exit 0 — drop the check and the
    missing answer raises TypeError instead, or worse reports `None` as a code.
    """
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    monkeypatch.setattr(main, '_get', lambda *a, **k: None)
    assert main.pair({'name': 'phone'}) == 2
    cap = capsys.readouterr()
    assert 'refused to start a pairing' in cap.err
    assert 'pairing code' not in cap.out


# ── 7-8: status's exit codes when Core is not simply fine ──


@pytest.mark.parametrize('state,expected', [('failed', 3), ('running', 0)],
                         ids=['engine-failed', 'engine-running'])
def test_status_exits_three_exactly_when_the_engine_failed(state, expected, monkeypatch,
                                                           capsys):
    """Catchest main.py:673 (`return 3 if e['state'] == 'failed' else 0`): the
    documented contract is 0/1/2/3 — flip it and a dead engine reports fine,
    or a healthy one is an incident."""
    from archeus.infra import discovery
    health = {'core': {'started_at': '2026-01-01T00:00:00Z', 'pid': 7, 'version': '1',
                       'schema': 42, 'ports': 'real'},
              'engine': {'state': state}}
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', {'pid': 7, 'port': 9}))
    monkeypatch.setattr(discovery, 'token_protection', lambda: (True, None))
    monkeypatch.setattr(main, '_get', lambda *a, **k: health)
    assert main.status() == expected
    assert 'engine %s' % state in capsys.readouterr().out


def test_an_unreadable_discovery_file_sends_nothing_and_exits_two(monkeypatch, capsys):
    """Catchest main.py:650-653 (`if state == 'unreadable': ... return 2`): a
    held lock with a missing or stale core.json proves nothing about the port,
    so the token must not go there — the branch is the same A5 gate as `_get`'s."""
    from archeus.infra import discovery
    monkeypatch.setattr(discovery, 'discover', lambda: ('unreadable', None))
    monkeypatch.setattr(main, '_get',
                        lambda *a, **k: pytest.fail('a request was sent to an unproved port'))
    assert main.status() == 2
    assert 'nothing was sent to it' in capsys.readouterr().out


# ── 9-10: dispatch boundaries that must not start or command anything ──


@pytest.mark.parametrize('argv', [
    ['pause', 'all'],                                     # would POST pause to a mission `all`
    ['pause', 'all', '--now', 'extra'],                    # not the exact e-stop shape
], ids=['pause-all-alone', 'pause-all-now-extra'])
def test_pause_all_never_pauses_a_mission_and_only_the_exact_shape_is_estop(argv, monkeypatch,
                                                                             capsys):
    """Catchest main.py:139 (`args[0] != 'all'`) and 137-138 (`args ==
    ['all', '--now']`): drop the guard and `pause all` halts every execution
    of a mission named `all`; loosen `==` to `in` and a mistyped e-stop fires
    or silently does not."""
    monkeypatch.setattr(main, 'pause',
                        lambda *a: pytest.fail('a mission named all was paused'))
    monkeypatch.setattr(main, 'estop',
                        lambda: pytest.fail('the e-stop fired from a near-miss shape'))
    assert main.main(argv) == 2
    assert capsys.readouterr().err.startswith('usage:')


def test_the_exact_pause_all_now_shape_is_the_estop(monkeypatch):
    """Catchest main.py:137-138 from the other side: the one spelling that must
    reach the e-stop does, exactly once, with nothing left over."""
    monkeypatch.setattr(main, 'estop', lambda: ESTOP_RAN)
    assert main.main(['pause', 'all', '--now']) == ESTOP_RAN


@pytest.mark.parametrize('argv', [
    ['core', '--remote-host'],                             # the value is missing
    ['core', '--remote-host', '--open'],                    # a flag is not a host
    ['core', '--nope'],                                    # an unknown flag
], ids=['no-value', 'flag-as-value', 'unknown-flag'])
def test_core_with_a_malformed_remote_host_never_starts(argv, monkeypatch, capsys):
    """Catchest main.py:168-171 (`_core_args` returning None) through 109 and
    158-159: a mistyped host must be a usage error, not a Core started with a
    wrong allowlist — that Core would answer requests nobody asked for."""
    monkeypatch.setattr(main, 'core',
                        lambda **kw: pytest.fail('Core started from bad arguments: %r' % kw))
    assert main.main(argv) == 2
    assert capsys.readouterr().err.startswith('usage:')


def test_a_well_formed_remote_host_reaches_core_once(monkeypatch):
    """Catchest the same 168-171 inverted: `--remote-host h` must arrive at
    `core` as exactly [h] — break the parser the other way and the host is
    silently dropped, leaving Core answering only loopback while its user
    believes the tunnel is allowed."""
    started = []
    monkeypatch.setattr(main, 'core', lambda **kw: started.append(kw) or 0)
    assert main.main(['core', '--remote-host', 'tunnel.example']) == 0
    assert started == [{'open_browser': False, 'remote_hosts': ['tunnel.example']}]


# ── 11-16: the other uncovered denial and error paths of this file ──


@pytest.mark.parametrize('argv', [
    ['sessions', '--project'],                             # odd count: a flag with no value
    ['sessions', '--project', '--mission', 'x'],            # a flag used as a value
    ['sessions', 'positional', 'x'],                        # a bare word where a flag belongs
], ids=['odd-count', 'flag-as-value', 'bare-word'])
def test_a_malformed_flag_pair_for_sessions_is_usage_without_a_request(argv, monkeypatch,
                                                                       capsys):
    """Catchest main.py:569-570 and 573-574 (the two `return None`s of
    `_flags`) through the sessions dispatch: accept them anyway and a
    positional becomes a project filter, quietly listing another project's
    sessions."""
    monkeypatch.setattr(main, 'sessions',
                        lambda *a: pytest.fail('sessions ran with malformed flags'))
    assert main.main(argv) == 2
    assert capsys.readouterr().err.startswith('usage:')


def test_an_unknown_automation_action_is_usage_before_core_is_asked(monkeypatch, capsys):
    """Catchest main.py:482-484 (`what not in ...: return 2`): the action set
    is closed — widen it and the final `else` POSTs any string as a state
    change Core never defined."""
    monkeypatch.setattr(main, '_running',
                        lambda *a: pytest.fail('Core was asked about an unknown action'))
    assert main.main(['automation', 'destroy', 'auto_1']) == 2
    assert capsys.readouterr().err.startswith('usage:')


def test_a_missing_automation_file_is_a_clean_error_before_core_is_asked(tmp_path, monkeypatch,
                                                                          capsys):
    """Catchest main.py:487-492 (`except (OSError, ValueError, RecursionError)`
    on the create file, the OSError arm specifically): without it a missing
    file is a traceback, and a raised-then-ignored one would ask Core to
    create an automation from nobody's file."""
    missing = tmp_path / 'no-such-file.json'
    monkeypatch.setattr(main, '_running',
                        lambda *a: pytest.fail('Core was asked without a readable file'))
    assert main.automation('create', str(missing)) == 2
    assert 'cannot read' in capsys.readouterr().err


def test_devices_revoke_without_an_id_is_usage_not_an_index_error(monkeypatch, capsys):
    """Catchest main.py:115-116 (`len(args) == 2 and args[0] == 'revoke'`
    then `args[1]`): loosen the length check and the dispatch raises IndexError
    — or revokes with `None` interpolated into the revoke path."""
    monkeypatch.setattr(main, 'devices',
                        lambda *a: pytest.fail('devices ran without an id to revoke'))
    assert main.main(['devices', 'revoke']) == 2
    assert capsys.readouterr().err.startswith('usage:')


def test_a_resume_whose_terminal_failed_to_open_exits_two(monkeypatch, capsys):
    """Catchest main.py:619-622 (`if launch.get('error'): return 2`): the
    session resumed but the person has no terminal to see it — exit 0 there
    tells a script everything worked."""
    monkeypatch.setattr(main, '_running', lambda: {'port': 9})
    monkeypatch.setattr(main, '_get', lambda *a, **k: {
        'harness_id': 'h1', 'model': 'm1', 'brief': None,
        'launch': {'error': 'no terminal on this display'}})
    assert main.resume('ses_1', {}) == 2
    cap = capsys.readouterr()
    assert 'the terminal did not open' in cap.err and 'no terminal' in cap.err


def test_a_refusal_in_get_is_said_in_cores_own_words_and_is_none(monkeypatch, capsys):
    """Catchest main.py:262-264 (`except client.CoreError: print(sync.explain(
    e.refusal())); return None`): swallow it and every caller reads a refusal
    as "Core is not running"/a silence; print the exception and Core's code is
    lost. Both halves: the words and the None."""
    from archeus.cli.tui import client
    from archeus.infra import discovery

    def refuse(self, path, body):
        raise client.CoreError(403, 'policy_denied', {'reason': 'locked'})
    monkeypatch.setattr(discovery, 'read_local_token', lambda: 'tok')
    monkeypatch.setattr(client.Core, 'post', refuse)
    assert main._get({'port': 9}, 'POST', '/v1/anything', {}) is None
    err = capsys.readouterr().err
    assert 'The policy denies it: locked' in err         # explain()'s words for this code
