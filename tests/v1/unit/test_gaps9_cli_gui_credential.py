"""T-1368: a failed redemption never returns a half-built shell client.

Source slice: archeus/cli/gui.py 120-160 at tip 10d688c0 (`attach`'s credential step,
`_credential`, `estop`); `Shell.__init__` and the class attributes at 154-158 are in
the slice too.

Candidate probes ranked denial first, then boundaries, then error paths. Selected
(ranked) branches and the test that pins each:

  1. 139-141    a redeem answer with no `token` must not escape attach as KeyError
                (STRICT XFAIL, see its reason)       -> test_a_redeem_without_a_token_is_no_shell
  2. 135-136    a launch-code answer with no `code` must not escape attach as KeyError
                (STRICT XFAIL, see its reason)       -> test_a_launch_code_without_a_code_is_no_shell
  3. 133, 141   the redeemed client talks to info['port'] with the redeemed token only
                                                     -> test_the_shell_client_is_the_redeemed_token_on_the_port
  4. 125-127    no module-level name keeps either token after attach
                                                     -> test_no_module_name_keeps_a_token
  5. 154-158    a Shell holds info and own only; estop_confirm is the constant
                                                     -> test_a_shell_holds_only_its_info_and_own_credential
  6. 143-151    an estop that raises restores both streams and the error reaches the caller
                                                     -> test_an_estop_that_raises_restores_the_streams
  7. 143-151    empty or whitespace output is returned as an empty string with the code
                                                     -> test_empty_estop_output_is_an_empty_strip
  8. 125-141    no path writes the local token file during an attach
                                                     -> test_attach_never_writes_the_local_token
  9. 134-138    a refused launch code is requested once and the redeem is never tried
                                                     -> test_a_refused_launch_code_is_asked_once
 10. 139-140    a network failure (status 0) on redeem gives None, not a client
                                                     -> test_a_network_failure_on_redeem_is_no_client

No Windows API, token file, Core process or socket is touched: client.Core.post/get
are faked, discovery is faked, estop's command is faked, and time is a fake.
"""

import sys
import types

import pytest

from archeus.cli import gui
from archeus.cli import main as cli_main
from archeus.cli._api import endpoints
from archeus.cli.tui import client
from archeus.infra import discovery

LOCAL = 'local-token-synthetic'
OWN = 'own-token-synthetic'
INFO = {'port': 8123, 'pid': 1, 'create_time': 0.0}
MISSING = 'Archeus Core on port 8123 did not give the shell a credential'


@pytest.fixture
def rig(monkeypatch):
    rig = types.SimpleNamespace(calls=[], answers={}, token=LOCAL,
                                state=('running', dict(INFO)))

    def post(self, path, body):
        rig.calls.append(('POST', path, body, self._token, self.base))
        out = rig.answers['POST ' + path]
        if isinstance(out, BaseException):
            raise out
        return out

    def no_socket(*a, **k):
        raise AssertionError('the test opened a real socket')

    monkeypatch.setattr(client.Core, 'post', post)
    monkeypatch.setattr(client.Core, '_open', no_socket)
    monkeypatch.setattr(discovery, 'discover', lambda: rig.state)
    monkeypatch.setattr(discovery, 'read_local_token', lambda: rig.token)
    monkeypatch.setattr(discovery, 'core_json_path', lambda: 'core.json')
    monkeypatch.setattr(discovery, 'write_local_token',
                        lambda token: rig.calls.append(('WRITE', token)))
    monkeypatch.setattr(gui, 'time', types.SimpleNamespace(monotonic=lambda: 0.0,
                                                           sleep=lambda s: None))
    return rig


def _redeemable(rig):
    rig.answers['POST ' + endpoints.launch_code()] = {'code': 'CODE1'}
    rig.answers['POST ' + endpoints.launch_redeem()] = {'token': OWN}


def _never(*a, **k):
    raise AssertionError('the shell started Core')


@pytest.mark.xfail(strict=True, reason="archeus/cli/gui.py:141 out['token'] is unguarded: a "
                   "redeem answer without a token raises KeyError out of attach instead of "
                   "returning (None, why)")
def test_a_redeem_without_a_token_is_no_shell(rig):
    """139-141 (STRICT XFAIL). `_credential` reads `out['token']` at gui.py:141 with no
    guard, so a redeem answer that lacks it raises KeyError out of attach, through
    main(), instead of giving (None, why). The attach contract the code itself keeps
    for every other refusal (`except client.CoreError: return None`, and the
    'no traceback' promise at gui.py:216-219) says it should be `(None, MISSING)`."""
    rig.answers['POST ' + endpoints.launch_code()] = {'code': 'CODE1'}
    rig.answers['POST ' + endpoints.launch_redeem()] = {}
    shell, why = gui.attach(start=_never)
    assert shell is None
    assert why == MISSING


@pytest.mark.xfail(strict=True, reason="archeus/cli/gui.py:135-136 ['code'] is unguarded: a "
                   "launch-code answer without a code raises KeyError out of attach instead "
                   "of returning (None, why)")
def test_a_launch_code_without_a_code_is_no_shell(rig):
    """135-136 (STRICT XFAIL). `local.post(...)['code']` at gui.py:135-136 raises
    KeyError when the launch-code answer has no `code`, escaping attach. The same
    contract applies as in the redeem case: a half answer is no shell, `(None, MISSING)`."""
    rig.state = ('running', dict(INFO))
    rig.answers['POST ' + endpoints.launch_code()] = {}
    shell, why = gui.attach(start=_never)
    assert shell is None
    assert why == MISSING


def test_the_shell_client_is_the_redeemed_token_on_the_port(rig):
    """133 and 141: the first client carries the local token to info['port'] for the
    pairing; the returned client carries only the redeemed token to the same port.
    Returning the local token, or the wrong port, is caught here."""
    _redeemable(rig)
    shell = gui._credential(dict(INFO))
    assert isinstance(shell, client.Core)
    assert shell._token == OWN
    assert shell.base == client.Core(INFO['port'], LOCAL).base
    assert [c[3] for c in rig.calls] == [LOCAL, LOCAL]
    assert all(c[4] == client.Core(INFO['port'], LOCAL).base for c in rig.calls)


def test_no_module_name_keeps_a_token(rig):
    """125-127: the credential lives only in the returned Shell. After a successful
    attach and after a refused one, no module-level name of gui holds either token."""
    _redeemable(rig)
    shell, why = gui.attach(start=_never)
    assert why is None and shell._own._token == OWN
    assert all(v not in (LOCAL, OWN) for v in vars(gui).values() if isinstance(v, str))
    rig.answers['POST ' + endpoints.launch_code()] = client.CoreError(403, 'not_permitted')
    gui.attach(start=_never)
    assert all(v not in (LOCAL, OWN) for v in vars(gui).values() if isinstance(v, str))


def test_a_shell_holds_only_its_info_and_own_credential(rig):
    """154-158: a Shell stores exactly `info` and the redeemed client; the estop
    confirmation is the constant itself and the estop is gui.estop."""
    _redeemable(rig)
    shell, _ = gui.attach(start=_never)
    assert set(vars(shell)) == {'info', '_own'}
    assert shell.info == dict(INFO) and shell._own._token == OWN
    assert shell.estop_confirm is gui.ESTOP_CONFIRM
    assert shell.estop is gui.estop


def test_an_estop_that_raises_restores_the_streams(monkeypatch, capsys):
    """143-151: the stdout and stderr redirect is a context manager, so a raising
    `main.estop` must leave both streams as they were and the error reaches the caller.
    Swapping the with-block for a plain call would leak the redirect into the tray."""
    before = (sys.stdout, sys.stderr)

    def estop():
        print('half a sentence')
        raise RuntimeError('estop broke')
    monkeypatch.setattr(cli_main, 'estop', estop)
    with pytest.raises(RuntimeError, match='estop broke'):
        gui.estop()
    assert (sys.stdout, sys.stderr) == before
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('printed', ['', '   \n  '], ids=['empty', 'whitespace'])
def test_empty_estop_output_is_an_empty_strip(monkeypatch, printed):
    """143-151: no output, or whitespace only, comes back as an empty string with the
    command's code. The strip must not turn a silent estop into a non-empty message."""
    def estop():
        if printed:
            print(printed, end='')
        return 0
    monkeypatch.setattr(cli_main, 'estop', estop)
    assert gui.estop() == (0, '')


def test_attach_never_writes_the_local_token(rig):
    """125-141: attach reads the local token and never writes it. Checked on the success
    path and on a refused code, where the token must not be rotated or persisted."""
    _redeemable(rig)
    gui.attach(start=_never)
    rig.answers['POST ' + endpoints.launch_code()] = client.CoreError(403, 'not_permitted')
    gui.attach(start=_never)
    assert [c for c in rig.calls if c[0] == 'WRITE'] == []


def test_a_refused_launch_code_is_asked_once(rig):
    """134-138: one launch-code request, refused, and no redeem. A retry inside the
    credential step would send the local token again and spend a second code."""
    rig.answers['POST ' + endpoints.launch_code()] = client.CoreError(403, 'not_permitted')
    assert gui._credential(dict(INFO)) is None
    posts = [c[1] for c in rig.calls]
    assert posts == [endpoints.launch_code()]


def test_a_network_failure_on_redeem_is_no_client(rig):
    """139-140: a status-0 network failure (Core unreachable mid-pairing) on the redeem
    gives None, the same as a refusal. A client built from a partial answer would be
    the half-built object this card is about."""
    rig.answers['POST ' + endpoints.launch_code()] = {'code': 'CODE1'}
    rig.answers['POST ' + endpoints.launch_redeem()] = client.CoreError(0, 'network')
    assert gui._credential(dict(INFO)) is None
    assert [c[1] for c in rig.calls] == [endpoints.launch_code(), endpoints.launch_redeem()]
