"""T-1184: the ten highest-risk uncovered branches of
``claude_sessions/harnesses.py`` lines 448-834.

Coverage at the card's tip is 67% on this module (52 of 159 lines), and the misses
are not spread evenly. They sit on the functions that ANSWER something the accounts
list and the launch modal render — ``auth_state``, ``launch_targets``,
``default_target``, ``exe``, ``home_env`` — and on the two places that DECIDE
something: which home owns a file, and which argv spends model quota.

Ranked by risk, denial and fail-closed cases first, then boundaries, then error
paths:

1. ``auth_state`` for a non-Claude home is answered by that CLI's own reader, and
   only by it (line 661).
2. ``auth_state`` cannot invent readiness from an unreadable credential file
   (lines 663-668).
3. ``login_argv`` invents no argv for a home with no binary, and an unknown id
   gets the documented default rather than another CLI's binary (lines 674-676).
4. A name that is not a harness is not a launch target and not the default target
   (lines 461, 623-626, 719-720).
5. ``of_argv``/``is_inference`` do not know the ``.cmd``/``.bat`` shim names of
   the two CLIs whose ``exe_names`` stop at ``.exe`` (lines 805-813) - the MISS
   direction, an inference call no gate counts.  Kept as a strict xfail: the
   registry disagrees with what this project itself treats as that CLI.
6. ``exe`` reaches PATH only through ``proc.which``, the lookup that refuses a
   CWD or a relative PATH entry (lines 745-748).
7. ``of_path`` matches a home by path SEGMENTS, so a sibling whose name merely
   starts like the home is not inside it (line 511).
8. ``of_path`` resolves overlapping homes by LONGEST prefix (line 511).
9. ``home_env`` writes exactly one variable, the one that CLI names, for a home
   that is not the built-in one (lines 782-785).
10. ``of_argv``/``is_inference`` match no harness for an executable look-alike,
    in either direction of the mistake (lines 805-813, 828-830).

Three of the card's starting probes are NOT repeated here because the suite already
holds them: a second configured home is covered by ``test_multihome.py::
test_a_second_home_is_listed_after_the_built_in_one`` (its ``of()`` half — the
placement a launch round trip depends on — is case 9 below), a disabled harness by
``test_multihome.py::test_a_disabled_harness_contributes_no_homes`` and
``test_harnesses.py::test_turning_one_off_hides_it_everywhere``, and duplicate
normalized homes by ``test_multihome.py::test_a_home_named_twice_is_one_home``.
They are replaced by cases 5, 6 and 10, which cover branches nothing else reaches:
the shim name the registry cannot see (case 5), the binary coming only from the
guarded PATH lookup (case 6) and an argv that only looks like a harness call
(case 10).

Every input invented here is fake and every privileged call is faked BEFORE it is
reached: no real ``CLAUDE_CONFIG_DIR``, no credential file on disk, no request, no
child process started, no permission bit changed.
"""

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox                                    # noqa: E402
from claude_sessions import codex as _codex                    # noqa: E402
from claude_sessions import config as _c                       # noqa: E402
from claude_sessions import harnesses as _h                    # noqa: E402
from claude_sessions import proc as _proc                      # noqa: E402
from claude_sessions import usage as _usage                    # noqa: E402


def _installed(monkeypatch, present=('claude', 'codex', 'pi')):
    """Pretend which CLIs this machine has. The one seam `instances()` and
    `launch_targets()` ask before they will list a harness."""
    monkeypatch.setattr(_h, 'exe', lambda hid=None: ('C:\\bin\\%s.exe' % hid
                                                     if hid in present else None))


def _settings(monkeypatch, **over):
    s = _c.load_settings()
    s.update(over)
    monkeypatch.setattr(_c, 'load_settings', lambda: dict(s))
    return s


def _extra_home(monkeypatch, tmp_path, hid, name, rel):
    """Register a second home for a non-Claude harness, as the Accounts page does."""
    d = os.path.join(str(tmp_path), *rel.split('/'))
    os.makedirs(d, exist_ok=True)
    _settings(monkeypatch, homes={hid: [{'name': name, 'dir': d}]})
    return d


# ── 1-2. auth_state: nothing in this function may invent readiness ────────

def test_an_accounts_row_asks_that_cli_and_never_a_claude_login(monkeypatch, tmp_path):
    """`auth_state` is asked once per row of the accounts list. For Codex and pi
    the answer is that CLI's own business (line 661: `impl('auth_state', ...)`),
    and only for a home with no reader of its own does archeus look at Claude
    Code's OAuth token (663-668).

    Closest existing tests: `test_usage.py::
    test_status_expired_token_skips_the_http_call` and `test_usage.py::
    test_status_no_creds`. Both drive `usage._read_token` and `_token_expired`
    for the usage bar with a real Claude home, so their assertions miss these two
    lines entirely — nothing in them puts a Codex home in front of `auth_state`,
    which is where a wrong answer costs the most: a Codex row reported signed in
    because a Claude token was found, or answered from a default instead of from
    the reader that was asked.
    """
    Sandbox(monkeypatch, tmp_path)
    _installed(monkeypatch)
    home = _extra_home(monkeypatch, tmp_path, 'codex', 'second', 'codex-second')
    asked = []

    def spy(cfgdir):
        asked.append(cfgdir)
        return 'ok'

    monkeypatch.setattr(_codex, 'auth_state', spy)
    reads = []
    monkeypatch.setattr(_usage, '_read_token',
                        lambda cfgdir=None: reads.append(cfgdir) or None)
    assert _h.auth_state(home) == 'ok'
    assert len(asked) == 1, 'the reader was asked exactly once'
    assert os.path.normcase(asked[0]) == os.path.normcase(home), \
        'a home is answered about its own directory, resolved'
    assert reads == [], 'a Codex home was answered from a Claude Code login'
    # the answer is the reader's, verbatim: an empty one is not read as signed in
    monkeypatch.setattr(_codex, 'auth_state', lambda cfgdir: '')
    assert _h.auth_state(home) != 'ok'
    # and the fallback, with no token in front of it, says 'missing'
    assert _h.auth_state(os.path.join(str(tmp_path), 'no-home-at-all')) == 'missing'


def test_a_credential_file_that_cannot_be_read_is_unknown_and_never_ok(
        monkeypatch, tmp_path):
    """Lines 663-668: `_read_token` and `_token_expired` read a file another
    process writes and rotates under it. The `except Exception` is the whole
    difference between "I cannot tell" and "signed in", and nothing covered it.

    Closest existing test: `test_usage.py::test_status_no_creds` — the same two
    readers, but with a real home and a real absent file, and answered by `usage`
    rather than by `auth_state`. Its assertion cannot see the unreadable-file
    case, so a version that let the exception escape (taking the whole accounts
    list down with it) or that answered 'ok' because the read did not say
    otherwise would still look like a working accounts page.
    """
    Sandbox(monkeypatch, tmp_path)
    _installed(monkeypatch)
    cfg = os.path.join(str(tmp_path), 'acct')
    tried = []

    def token(_cfgdir=None):
        return {'access': 'an-invented-fake-token'}

    def expired(_cfgdir=None):
        tried.append(1)
        raise OSError('credential file is locked')

    monkeypatch.setattr(_usage, '_read_token', token)
    monkeypatch.setattr(_usage, '_token_expired', expired)
    assert _h.auth_state(cfg) == 'unknown'
    assert tried, 'the expiry check was reached, and it is the thing that failed'
    monkeypatch.setattr(_usage, '_token_expired', lambda _c=None: True)
    assert _h.auth_state(cfg) == 'expired'


# ── 3. no binary, no argv: nothing that could be spawned ─────────────────

def test_a_home_with_no_binary_gets_no_login_argv_and_no_invented_command(
        monkeypatch, tmp_path):
    """`login_argv` is the argv the Accounts page spawns (line 676). The `else []`
    is the denial: with no binary there is nothing to run, and an argv of
    `[None, 'login']` is a spawn that raises inside the request instead.

    No test calls `login_argv` at all. The closest is
    `test_harnesses.py::test_the_home_variable_follows_the_harness`, which checks
    what `account_env` writes for a home and never the command that is run with
    it; so its assertion misses both the denial and the fact that an unknown
    harness id resolves through the documented default (line 461) — which is right
    for the descriptor, and must not become another CLI's binary in an argv nobody
    authorised.
    """
    Sandbox(monkeypatch, tmp_path)
    started = []
    monkeypatch.setattr(_proc, 'spawn_terminal',
                        lambda argv, **kw: started.append(argv))
    _installed(monkeypatch, present=())                      # nothing installed
    assert _h.login_argv('codex') == []
    assert _h.login_argv('no-such-cli') == []
    assert _h.login_argv(None) == []
    assert started == [], 'absence of a binary must be absence of a spawn'
    # documented default: an id from settings another version wrote is Claude Code
    assert _h.descriptor('no-such-cli') is _h.HARNESSES[_h.DEFAULT]
    assert _h.descriptor(None) is _h.HARNESSES[_h.DEFAULT]
    assert _h.login_argv('no-such-cli') == []
    # installed: the binary first, then that CLI's own login argv, in that order
    _installed(monkeypatch, present=('codex', 'claude'))
    argv = _h.login_argv('codex')
    assert argv and argv[0] == 'C:\\bin\\codex.exe'
    assert argv[1:] == list(_h.HARNESSES['codex']['login_argv'])
    assert _h.login_argv('ghost-not-a-harness') == [str('C:\\bin\\claude.exe')] + \
        list(_h.HARNESSES['claude']['login_argv']), \
        'the default CLI, never another harness\'s binary'


# ── 4. a name that is not a harness owns no surface ───────────────────────

def test_a_name_that_is_not_a_harness_is_neither_a_row_nor_the_default(
        monkeypatch, tmp_path):
    """Three lines that all trust settings written elsewhere: `descriptor` falls
    back to the default for an unknown id (461), `launch_targets` skips a provider
    profile with no id (624-626) and `default_target` returns `launch_default`
    verbatim when it is a key of that list (719-720).

    Closest existing tests: `test_harnesses.py::
    test_a_disabled_backend_leaves_the_picker` and `test_an_unplaceable_directory_
    is_claude_code`. The first switches a well-formed profile off and the second
    reads only `descriptor(...)['id']`, so between them the assertions miss the two
    shapes settings actually arrives with: a `providers` entry with no id, which
    would otherwise hand the modal a launch row, a blank tab and a `provider`
    field the launch endpoint trusts, and a `launch_default` naming a key that no
    profile can back, which would open the modal on a target nothing could run
    (`test_the_default_falls_back_to_claude_code_not_to_whatever_sorts_first`
    tries an id that was never in settings at all).
    """
    _installed(monkeypatch)
    _settings(monkeypatch,
              homes={'ghost': [{'name': 'left behind', 'dir': 'Z:/gone'}]},
              providers=[{'name': 'no id at all'}, {'id': '', 'name': 'nor this'}],
              providers_disabled=[], launch_default='ghost')
    assert _h.descriptor('ghost') is _h.HARNESSES[_h.DEFAULT]
    rows = _h.launch_targets()
    keys = [r['key'] for r in rows]
    assert 'ghost' not in keys, 'a settings name is not a harness'
    assert 'provider:' not in keys, \
        'a profile with no id behind it is not something a launch can carry'
    assert _h.default_target() == _h.DEFAULT, \
        'the picker may not open on a target that has no row'
    _settings(monkeypatch, launch_default='provider:')
    assert _h.default_target() == _h.DEFAULT
    _settings(monkeypatch, launch_default='codex')
    assert _h.default_target() == 'codex', 'a real row is still honoured'


# ── 5. the shim a CLI is installed AS is still that CLI ───────

@pytest.mark.xfail(strict=True, reason=(
    'The registry resolves a binary under one name and then refuses to recognise '
    'it under the name it resolved. `exe()` asks `proc.which`, which on Windows '
    'tries every PATHEXT suffix (proc.py:580-585), so `which("claude")` answers '
    'with `...\\npm\\claude.cmd` - a path the resolver itself returned. '
    '`of_argv` then compares that basename against Claude Code\'s '
    'exe_names=("claude.exe","claude") and finds nothing, so `is_inference` is '
    'False and the call is ungated. The project disagrees with the registry '
    'three times over: conftest._CLAUDE_EXE counts claude.cmd and claude.bat as '
    'a Claude launch, test_process_leak.py\'s ARGV table says an argv carrying '
    '`claude.cmd` is one that must be BLOCKED, and '
    'test_versions.py::test_an_npm_install_is_reported_not_overwritten uses '
    '`AppData/Roaming/npm/claude.cmd` as Claude\'s path - while pi, the third '
    'CLI, carries `pi.cmd` in its own list. Source disagreement: a name the '
    'project treats as that CLI must place as it in the registry too.'))
def test_an_inference_call_through_the_npm_shim_is_still_that_call(monkeypatch,
                                                                    tmp_path):
    """Lines 788-830: `of_argv` compares one basename against `exe_names`, and
    Claude Code's and Codex's lists stop at `.exe` and the bare name while pi's
    carries `pi.cmd`. The chain that breaks is entirely inside the registry:
    `exe()` may answer with a PATHEXT-spelled shim (`proc.which` tries
    `.com/.exe/.bat/.cmd` on Windows), the app spawns what that returned, and the
    guard then asks what that argv was.

    Closest existing tests: `test_harnesses.py::
    test_one_argv_gets_one_answer_on_every_platform`, whose Windows spellings are
    `codex.exe`, `pi.cmd` and the bare names, and
    `test_nothing_that_places_a_binary_asks_what_platform_this_is`, which only
    asks that each list HOLD a `.exe`/`.cmd` form and a bare one. Neither puts
    the spelling `exe()` can itself return in front of `of_argv`, so both stay
    green while a resolution the registry makes is a name the registry cannot
    place - the miss direction, an inference call no gate ever counts.
    """
    Sandbox(monkeypatch, tmp_path)
    npm = 'C:\\Users\\t\\AppData\\Roaming\\npm'
    shim = os.path.join(npm, 'claude.cmd')
    # what `proc.which` may answer on Windows, faked here rather than depended
    # on: the PATHEXT loop, not the platform
    monkeypatch.setattr(_proc, 'which',
                        lambda name, path=None, avoid=():
                        shim if name in ('claude', 'claude.exe') else None)
    assert _h.exe('claude') == shim, 'the resolver hands the app this path'
    # what is already true today, and must stay true
    assert _h.of_argv([os.path.join(npm, 'claude'), '-p', 'go'])['id'] == 'claude'
    assert _h.is_inference([os.path.join(npm, 'claude.exe'), '--print', 'go'])
    assert _h.of_argv([os.path.join(npm, 'pi.cmd'), '-p', 'go'])['id'] == 'pi'
    # the same call, through the path that same call resolved to
    assert _h.of_argv([shim, '-p', 'go']) is not None,         'claude.cmd is Claude Code in conftest, in test_process_leak, on PATH'
    assert _h.of_argv([shim, '-p', 'go'])['id'] == 'claude'
    assert _h.is_inference([shim, '-p', 'go']),         'a call archeus spawns through its own resolved path spends that quota'
    assert _h.of_argv([os.path.join(npm, 'claude.bat'), '-p', 'go'])['id'] == 'claude'
    assert _h.of_argv([os.path.join(npm, 'codex.cmd'), 'exec', 'go'])['id'] == 'codex'
    assert _h.is_inference([os.path.join(npm, 'codex.cmd'), 'exec', 'go'])


# ── 6. the binary is found on the PATH the guarded way, never in CWD ─────

def test_the_binary_comes_from_the_guarded_path_lookup_only(monkeypatch, tmp_path):
    """Lines 745-748: when no install directory matched, `exe` asks `proc.which`,
    which deliberately never searches a relative entry or a CWD. A PATH containing
    `.` — or the empty entry that means the same — makes a `claude.exe` dropped in
    the project the binary archeus spawns.

    Closest existing test: `test_codex.py::test_the_newest_install_directory_wins`,
    which only ever writes a file under the profile and asserts the glob answer,
    and `test_the_search_stays_inside_the_profile_it_is_given`, which asserts the
    globs are relative and that nothing is found. Neither reaches the PATH
    fallback, so their assertions miss it being replaced by `shutil.which` or a
    plain `PATH.split()`: a repo-local binary resolves, and every test that has a
    real installation stays green.
    """
    Sandbox(monkeypatch, tmp_path)
    code = '\n'.join(ln for ln in inspect.getsource(_h.exe).splitlines()
                     if not ln.strip().startswith('#'))
    assert 'shutil.which' not in code and 'os.environ' not in code, \
        'a raw PATH lookup finds whatever sits in the working directory'
    monkeypatch.setattr(_proc, 'which', lambda name, avoid=(): None)
    assert _h.exe('claude') is None, 'nothing found is nothing found'
    decoy = os.path.join(str(tmp_path), 'repo', 'claude.exe')   # invented, fake
    asked = []

    def fake_which(name, avoid=()):
        asked.append(name)
        return decoy if name == 'claude.exe' else None

    monkeypatch.setattr(_proc, 'which', fake_which)
    assert _h.exe('claude') == decoy
    assert asked, 'the guarded lookup is the only way to the PATH'
    monkeypatch.setattr(_proc, 'which', lambda name, avoid=(): None)
    assert _h.exe('claude') is None, 'a miss stays a miss'


# ── 7-8. of_path: which home owns this file ───────────────────────────────

def test_a_sibling_that_shares_a_homes_name_is_not_inside_it(monkeypatch, tmp_path):
    """Line 511 matches `h + os.sep`, not `h`. Drop that separator and the backup
    copy a user makes of their own home — `<home>-scratch`, `<home>.old`, any
    sibling whose name starts with it — is claimed by that harness, and everything
    under it gets that harness's fold, its transcript rule and its account.

    Closest existing tests: `test_harnesses.py::
    test_a_transcript_is_placed_by_the_home_it_sits_under` and `test_multihome.py::
    test_a_transcript_under_a_second_home_is_still_that_cli`, which check a file
    under a home and a file under nothing. Both of those still pass with the `+
    os.sep` gone, because nothing there puts a file under a directory whose name
    merely STARTS LIKE a home.
    """
    Sandbox(monkeypatch, tmp_path)
    _installed(monkeypatch)
    home = _extra_home(monkeypatch, tmp_path, 'codex', 'work', 'codex-home')
    sibling = home + '-scratch'                                 # NOT under the home
    os.makedirs(os.path.join(sibling, 'sessions'), exist_ok=True)
    stale = home + '.old'
    os.makedirs(stale, exist_ok=True)
    assert _h.of_path(os.path.join(home, 'sessions', 'a.jsonl'))['id'] == 'codex'
    assert _h.of_path(os.path.join(sibling, 'sessions', 'b.jsonl'))['id'] == \
        _h.DEFAULT, 'a sibling of a home is not inside that home'
    assert _h.of_path(stale)['id'] == _h.DEFAULT
    assert _h.of_path(home)['id'] == _h.DEFAULT, 'the home itself is not under it'
    assert _h.of_path('')['id'] == _h.DEFAULT, 'no path is the documented default'


def test_the_deeper_home_owns_the_file_when_homes_overlap(monkeypatch, tmp_path):
    """Line 511 keeps the LONGEST matching home. Two homes can overlap — a second
    `PI_CODING_AGENT_DIR` pointed inside a Codex home is the ordinary way it
    happens — and then the shorter match is the wrong answer: the file sits in a
    home with another login, another fold and another quota.

    Closest existing test: `test_pi.py::
    test_a_pi_session_file_is_placed_by_its_path` (and its twin in
    `test_multihome.py`), where only ONE home ever contains the file. Its
    assertion misses the case where two do: dropping `len(h) > len(best[1])`, or
    reversing it, still passes there.
    """
    Sandbox(monkeypatch, tmp_path)
    _installed(monkeypatch)
    outer = _h.home_dir('codex')                                # the shorter home
    inner = _extra_home(monkeypatch, tmp_path, 'pi', 'nested',
                        '.codex/work/agent')                     # inside it
    deep = os.path.join(inner, 'sessions', '2026', '09', '15', 'rollout-s.jsonl')
    assert len(os.path.normcase(os.path.abspath(inner))) > \
        len(os.path.normcase(os.path.abspath(outer))), 'the fixture is the overlap'
    assert [d for hid, d in _h._homes() if hid in ('codex', 'pi') and
            os.path.normcase(d) in (os.path.normcase(inner),
                                    os.path.normcase(outer))] == [outer, inner]
    assert _h.of_path(deep)['id'] == 'pi', \
        'the home the file is really under owns it, not the one that encloses it'
    assert _h.of_path(os.path.join(outer, 'sessions', 'shallow.jsonl'))['id'] == \
        'codex', 'and the enclosing home still owns its own files'


# ── 9. the launch environment of a home that is not the built-in one ─────

def test_a_second_home_is_placed_and_gets_that_clis_own_variable(
        monkeypatch, tmp_path):
    """`home_env` (782-785) is what selects the login for a spawned child: `of()`
    decides the harness and `resolve_config_dir` decides the value. Nothing calls
    it in the suite — `test_harnesses.py::
    test_the_home_variable_follows_the_harness` covers `account_env`, the sibling
    half of the same surface, and `test_pi.py::
    test_pi_is_a_home_with_two_components` only reads the descriptor's NAME.

    So their assertions miss both halves: `of()` matching only the built-in home
    (a second `CODEX_HOME` then launches its child with `CLAUDE_CONFIG_DIR` — the
    wrong login entirely, from a row the picker showed as Codex) and the value
    going out un-normalised, which is a child pointed at a directory that is
    whichever account was active.
    """
    Sandbox(monkeypatch, tmp_path)
    _installed(monkeypatch)
    home = _extra_home(monkeypatch, tmp_path, 'codex', 'work', 'codex-work')
    row = [r for r in _h.launch_targets() if r['hid'] == 'codex'][0]
    assert _h.of(row['cfgdir'])['id'] == 'codex', \
        'the cfgdir a launch row carries must place as that harness'
    env = _h.home_env(home)
    assert list(env) == ['CODEX_HOME'], \
        'exactly the one variable that CLI reads, and never Claude Code\'s'
    assert os.path.normcase(env['CODEX_HOME']) == \
        os.path.normcase(os.path.abspath(home))
    assert env['CODEX_HOME'] == _c.resolve_config_dir(home)
    # a home spelled with a redundant component is still that home, resolved
    spelled = os.path.join(home, 'above', '..')
    assert _h.of(spelled)['id'] == 'codex'
    assert _h.home_env(spelled) == {'CODEX_HOME': _c.resolve_config_dir(spelled)}
    assert _h.home_env(_h.home_dir('pi')) == \
        {'PI_CODING_AGENT_DIR': _c.resolve_config_dir(_h.home_dir('pi'))}
    assert _h.home_env(os.path.join(str(tmp_path), 'unplaceable')) == \
        {_h.HARNESSES[_h.DEFAULT]['home_env']:
            _c.resolve_config_dir(os.path.join(str(tmp_path), 'unplaceable'))}, \
        'what archeus cannot place is the documented default'


# ── 10. the argv that spends quota, and the ones that only look like it ───

def test_an_executable_lookalike_is_nobody_s_call(monkeypatch, tmp_path):
    """`of_argv` (805-813) compares one basename against every name a CLI can
    have, with and without its extension, and `is_inference` (828-830) adds that
    CLI's flags or subcommand. Both directions of a wrong answer are the bug: a
    MISS is an inference call that goes ungated, and a FALSE MATCH spends another
    account's quota and resolves the wrong home.

    Closest existing tests: `test_harnesses.py::
    test_one_argv_gets_one_answer_on_every_platform` and
    `test_something_that_is_not_a_harness_at_all_is_not_inference`. The first
    pins four exact spellings that all DO match; the second tries names no CLI
    shares at all (`git`, `python`). Neither puts a look-alike in front of the
    matcher — a helper binary named for a harness, a harness name with a suffix,
    a rotated `.bak` of a real binary — nor a malformed argv, where the
    `except (IndexError, TypeError, KeyError)` is the difference between "nobody's
    call" and a traceback from inside the quota guard.
    """
    Sandbox(monkeypatch, tmp_path)
    _installed(monkeypatch)
    for argv in (['C:\\tools\\pi-helper\\pi-helper', '-p', 'go'],
                 ['C:/bin/claude-code', '-p', 'go'],
                 ['claude.exe.old', '--print', 'go'],
                 ['codex-tools', 'exec', 'go'],
                 ['pic', '--print', 'go'],
                 ['pip', '-p', 'go']):
        assert _h.of_argv(argv) is None, argv
        assert _h.is_inference(argv) is False, argv
    # a management subcommand of a real binary is nobody's quota either
    for argv in (['C:\\x\\claude', 'mcp', 'list'],
                 ['C:\\x\\codex', 'login'],
                 ['C:\\x\\pi', '--mode', 'extend']):
        assert _h.of_argv(argv) is not None, argv
        assert _h.is_inference(argv) is False, argv
    for argv in ([], None, [None], {}, {'a': 1}, [0]):
        assert _h.of_argv(argv) is None, argv
        assert _h.is_inference(argv) is False, argv
    # a real binary name is still not a call that spends anything
    assert _h.of_argv(['C:\\x\\claude.exe'])['id'] == 'claude'
    assert _h.is_inference(['C:\\x\\claude.exe']) is False
    assert _h.is_inference(['C:\\x\\codex.exe', 'exec', 'go']) is True
    assert _h.is_inference(['C:\\x\\codex.exe', 'login']) is False
