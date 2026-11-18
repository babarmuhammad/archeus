"""T-727: the highest-risk uncovered branches of `archeus/harnesses/calls.py`.

Style and fixtures follow the closest existing tests of this module —
`tests/v1/unit/test_knowledge_units.py` (L13-L15), `tests/v1/unit/test_pi_discovery.py`
and `tests/v1/unit/test_fix_harnesses_calls.py`: one stand-in for every OS touch the
adapters make (`llmcall.run_headless`, `llmcall.budget_args`, `config.account_env`,
`config.get_claude_exe`, `harnesses.exe`/`harnesses.disabled`), the same `Runner`
shape as L13, `spawn.seen == []` as the proof that a refusal spawned nothing, and
real files only under `tmp_path`. No CLI, no network, no real process, no sleep, and
nothing that needs Windows over Linux or Linux over Windows: the two OS reads the
module makes (`os.path.isdir`, in `PiCaller.authenticate`) are exercised through
`tmp_path`, and no test reads or asserts on a value of the ambient environment.

The emphasis is the card's: adapter parsing of malformed and hostile provider
output, and the discovery/denial paths that must refuse before anything is spawned.
`calls.py` carries no hook payload of its own — the hook-related branch is the
`enforcement` an adapter declares (calls.py:76), asserted in G19. Each test names
here, and in the card's report, the source branch whose removal or inversion it
would catch.
"""

import json

import pytest

from archeus.harnesses import base, calls
from claude_sessions import config, harnesses, llmcall

#: what a real `config.account_env` answer always looks like: it is
#: `os.environ.copy()` plus the account's home variable (claude_sessions/config.py:904),
#: so Core's own and pytest's prefixes are in it and only calls.py:28-29 can drop them
ACCOUNT_ENV = {'PATH': '/opt/bin', 'HOME': '/opt/home', 'ANTHROPIC_API_KEY': 'ambient-key',
               'ARCHEUS_HOME': '/opt/core-run', 'ARCHEUS_HOOK_TOKEN': 'brk_x',
               'PYTEST_CURRENT_TEST': 'x'}

#: a `claude -p --output-format json` envelope that says everything well
ENVELOPE = json.dumps({'structured_output': {'decisions': []}, 'result': 'ok',
                       'usage': {'input_tokens': 11, 'output_tokens': 2},
                       'total_cost_usd': 0.25})

_SPEC = dict(route_decision_id='rte_1', purpose='brain', prompt='P', workdir='.',
             schema=None, model=None, limits={}, no_tools=False)


def _spec(home='acct-home', **kw):
    return base.CallSpec(**dict(dict(_SPEC, account=base.AccountRef('acc', home)), **kw))


def _result(rc=0, stdout='', reason='', error='', timed_out=False):
    return llmcall.Result(rc, stdout, reason, error, timed_out)


class Runner:
    """`llmcall.run_headless`: records every (argv, stdin, kwargs) and answers with
    `result`. The same stand-in as `test_knowledge_units.Runner`, so a test that
    forgets to set one still gets a run that says nothing."""

    def __init__(self, result=None):
        self.result, self.seen = result, []

    def __call__(self, cmd, input_text=None, **kw):
        self.seen.append((cmd, input_text, kw))
        return self.result


@pytest.fixture
def spawn(monkeypatch, tmp_path):
    """Every seam the two adapters reach the OS through, stood in one place: the
    spawn, the budget cap, the account environment and where each CLI is."""
    r = Runner(_result(stdout='{}'))
    monkeypatch.setattr(llmcall, 'run_headless', r)
    monkeypatch.setattr(llmcall, 'budget_args', lambda: [])
    monkeypatch.setattr(config, 'account_env', lambda home, harness=None: dict(ACCOUNT_ENV))
    monkeypatch.setattr(config, 'get_claude_exe', lambda: str(tmp_path / 'claude.exe'))
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: str(tmp_path / 'pi.exe'))
    monkeypatch.setattr(harnesses, 'disabled', lambda: set())
    return r


# ── nothing is spawned unless the harness is really there ───────────────────

def test_g01_a_claude_call_without_the_binary_refuses_before_anything_spawns(spawn,
                                                                             monkeypatch):
    """calls.py:97-99 `if not exe: return CallResult(error='unavailable', ...)`, and
    calls.py:68-70 `bool(exe)`: without the guard the adapter spawns `None -p …`; with
    `installed` hardcoded True the router elects a CLI that is not on the machine."""
    monkeypatch.setattr(config, 'get_claude_exe', lambda: None)
    got = calls.ClaudeCodeCaller().call(_spec(schema={'type': 'object'}))
    assert (got.error, got.detail, got.text, got.parsed, got.usage) == (
        'unavailable', 'Claude Code is not installed', '', None, {})
    assert spawn.seen == []
    info = calls.ClaudeCodeCaller().discover()
    assert (info.id, info.installed, info.executable) == ('claude_code', False, None)


def test_g02_a_pi_call_without_the_binary_refuses_before_anything_spawns(spawn,
                                                                         monkeypatch):
    """calls.py:163-165 `if not exe: return CallResult(error='unavailable', ...)`:
    the same refusal on the pi side, whose argv is built by another module and so
    would fail somewhere less legible than an `unavailable`."""
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: None)
    got = calls.PiCaller().call(_spec(schema={'type': 'object'}))
    assert (got.error, got.detail, got.text, got.parsed) == (
        'unavailable', 'pi is not installed', '', None)
    assert spawn.seen == []
    info = calls.PiCaller().discover()
    assert (info.id, info.installed, info.executable) == ('pi', False, None)


def test_g03_a_switched_off_pi_is_not_installed_even_with_the_binary_on_disk(spawn,
                                                                             monkeypatch):
    """calls.py:139-141 `None if 'pi' in harnesses.disabled() else harnesses.exe('pi')`:
    read the switch the other way round and a harness the user turned off is still
    discovered, elected and spawned — `disabled()` is the only say the user has here."""
    monkeypatch.setattr(harnesses, 'disabled', lambda: {'pi'})
    c = calls.PiCaller()
    info = c.discover()
    assert (info.installed, info.executable) == (False, None)
    got = c.call(_spec())
    assert got.error == 'unavailable' and got.parsed is None
    assert spawn.seen == []


# ── a run that did not succeed is never read as an answer ──────────────────

def test_g04_a_failed_claude_run_is_never_read_as_an_answer(spawn):
    """calls.py:117-118 `if r.returncode != 0: return _failed(r)`: the runner merges
    stderr into stdout, so a crash and an answer look identical to every later line
    of this function; drop the check and the CLI's last words, read as a structured
    envelope, become Core's answer."""
    spawn.result = _result(rc=1, stdout=ENVELOPE, reason='the CLI crashed')
    got = calls.ClaudeCodeCaller().call(_spec(schema={'type': 'object'}))
    assert (got.error, got.detail, got.parsed, got.usage, got.text) == (
        'failed', 'the CLI crashed', None, {}, '')


@pytest.mark.parametrize('result,want', [
    (_result(rc=None, error='timed out after 600s', timed_out=True), 'timeout'),
    (_result(rc=1, error='timed out after 600s', timed_out=True), 'timeout'),
    (_result(rc=None, error='could not start'), 'unavailable'),
    (_result(rc=1, reason='Model "claude-opus-9" is unknown to this account'),
     'model_unavailable'),
    (_result(rc=1, reason='', error='The MODEL says it does not exist'), 'model_unavailable'),
    (_result(rc=1, reason='the model is busy, try again later'), 'failed'),
    (_result(rc=1, reason='provider foo does not exist'), 'failed'),
    (_result(rc=1, reason='You have hit your session limit'), 'failed'),
], ids=['timed-out', 'timed-out-beats-exit-code', 'no-exit-code', 'model-unknown',
        'model-read-from-error', 'model-without-a-why', 'a-why-without-a-model', 'neither'])
def test_g05_a_run_that_did_not_succeed_is_named_by_what_is_true_first(spawn, result, want):
    """calls.py:51-58: `if r.timed_out` before `if r.returncode is None` (swapping
    them reports a timeout as `unavailable`, which retires a healthy harness), and
    `why = r.reason or r.error` with BOTH `_MODEL_REFUSED` and `_MODEL_WHY` needed
    (either test alone calls a busy model a missing one, or a missing provider a
    refused model)."""
    spawn.result = result
    got = calls.PiCaller().call(_spec())
    assert (got.error, got.parsed, got.text) == (want, None, '')
    assert got.detail == (result.reason or result.error)


# ── an answer is parsed only when one was asked for ────────────────────────

def test_g06_a_claude_call_that_asked_for_no_shape_gets_no_parsed_answer(spawn):
    """calls.py:123 `... if spec.schema is not None else None`: without the gate Core
    is handed a `parsed` it never asked for, dug out of prose the model wrote for a
    human — and a hostile stdout then chooses what Core validates."""
    spawn.result = _result(stdout=ENVELOPE)
    got = calls.ClaudeCodeCaller().call(_spec(schema=None))
    assert (got.parsed, got.error, got.text) == (None, None, ENVELOPE)
    assert got.usage == {'tokens_in': 11, 'tokens_out': 2, 'cost_usd': 0.25}
    # asked for the shape, and the very same stdout is read (the positive side)
    assert calls.ClaudeCodeCaller().call(_spec(
        schema={'type': 'object'})).parsed == {'decisions': []}


def test_g07_a_pi_call_that_asked_for_no_shape_gets_no_parsed_answer(spawn):
    """calls.py:175 `parsed=llmcall.parse_json(r.stdout) if spec.schema else None`:
    `parse_json` recovers JSON from prose on purpose, so without the gate an
    unrequested call gets a `parsed` manufactured out of free text."""
    spawn.result = _result(stdout='{"decisions": []}')
    got = calls.PiCaller().call(_spec(schema=None))
    assert (got.parsed, got.text, got.error) == (None, '{"decisions": []}', None)
    assert calls.PiCaller().call(_spec(schema={'type': 'object'})).parsed == {'decisions': []}


def test_g21_an_empty_schema_is_a_schema_for_both_adapters(spawn):
    """calls.py:166/175 against calls.py:100/123: `{}` is a JSON Schema (the
    most permissive one there is), and the two gates inside one function must not
    disagree about whether one was asked for."""
    spawn.result = _result(stdout='{"ok": true}')
    asked = _spec(schema={})
    claude, pi = (calls.ClaudeCodeCaller().call(asked), calls.PiCaller().call(asked))
    assert claude.error is None and pi.error is None
    assert pi.parsed == claude.parsed == {'ok': True}


# ── hostile and malformed provider output ─────────────────────────────────

@pytest.mark.parametrize('stdout', [
    'I cannot help with that.',
    '[{"usage": {"input_tokens": 9}}]',
    'null',
    '{"usage": "not a record"}',
    '{"usage": {"input_tokens": {"nested": 1}}}',
], ids=['prose', 'array-envelope', 'null', 'usage-a-string', 'tokens-a-dict'])
def test_g08_output_that_is_not_an_envelope_reports_no_figures_and_is_not_a_failure(spawn,
                                                                                    stdout):
    """calls.py:119-125 `try: json.loads … except ValueError: envelope = None` plus
    the `isinstance(envelope, dict)` guards of calls.py:38 and :125: with the except
    narrowed or dropped a CLI that prints a traceback raises inside the call, and
    with the isinstance gone a JSON array or `null` reaches `.get`."""
    spawn.result = _result(stdout=stdout)
    got = calls.ClaudeCodeCaller().call(_spec())
    assert (got.error, got.usage, got.text) == (None, {}, stdout)


@pytest.mark.parametrize('value,kept', [
    (True, None), (False, None), ('0.25', None), (None, None),
    (-1, None), (-0.5, None), (float('nan'), None), (float('inf'), None),
    (float('-inf'), None), (0, 0.0), (0.25, 0.25), (7, 7.0), (10 ** 20, 1e20),
], ids=['true', 'false', 'string', 'null', 'neg-int', 'neg-float', 'nan', 'inf',
        'minus-inf', 'zero', 'cents', 'int', 'huge'])
def test_g09_a_cost_is_a_finite_non_negative_number_or_absent(spawn, value, kept):
    """calls.py:126-127 `isinstance(cost, (int, float)) and not isinstance(cost, bool)
    and math.isfinite(cost) and cost >= 0`: `true` is 1, `NaN`/`Infinity` are JSON
    and are not numbers any ledger may add, and a negative would buy the caller
    budget back. Each guard dropped lets one of them into `usage`."""
    spawn.result = _result(stdout=json.dumps({'usage': {'input_tokens': 3},
                                              'total_cost_usd': value}))
    got = calls.ClaudeCodeCaller().call(_spec())
    assert got.error is None and got.usage['tokens_in'] == 3
    if kept is None:
        assert 'cost_usd' not in got.usage
    else:
        assert isinstance(got.usage['cost_usd'], float) and got.usage['cost_usd'] == kept


@pytest.mark.parametrize('envelope', [None, 'no', 7, [], {'usage': []}, {'usage': 'x'},
                                      {'usage': None}],
                         ids=['none', 'str', 'int', 'list', 'usage-list', 'usage-str',
                              'usage-null'])
def test_g10_an_envelope_that_is_not_a_usage_record_reports_nothing(envelope):
    """calls.py:38-40 `u = envelope.get('usage') if isinstance(envelope, dict) else
    None` / `if not isinstance(u, dict): return {}`: without either guard a hostile
    envelope raises (a list has no `.get`, `'x'` has no `.items`) or silently
    reports figures read off a string."""
    assert calls._usage(envelope) == {}


def test_g11_only_a_plain_non_negative_number_is_a_figure():
    """calls.py:44-46 `isinstance(u.get(theirs), int) and not isinstance(…, bool)
    and u[theirs] >= 0`, and the four names it maps: `true` is 1 token, `'12'` is
    not a count, `0` IS one (inverting `>=` to `>` loses a real zero), and an
    unknown field is never invented from a near-miss name."""
    assert calls._usage({'usage': {'input_tokens': 0, 'output_tokens': True,
                                   'cache_read_input_tokens': False,
                                   'cache_creation_input_tokens': '12',
                                   'input_tokens_out': 9, 'total_tokens': 5}}) == {'tokens_in': 0}
    assert calls._usage({'usage': {'cache_read_input_tokens': 4,
                                   'cache_creation_input_tokens': 5}}) == {
        'cache_read': 4, 'cache_write': 5}
    assert calls._usage({'usage': {'input_tokens': 2 ** 53}}) == {'tokens_in': 2 ** 53}


# ── discovery of what an account can run, and of the account itself ────────

def test_g12_a_pi_home_that_raises_offers_nothing_rather_than_crashing_routing(spawn,
                                                                              tmp_path,
                                                                              monkeypatch):
    """calls.py:208-211 `except Exception as e: return (), 'pi model discovery
    failed: %s: %s'`: widen it, or let it return the catalogue instead of nothing,
    and one unreadable home either takes routing down with it or offers models that
    home cannot run."""
    from claude_sessions import pi as pl

    def boom(home=None):
        raise OSError('pi state is unreadable')

    monkeypatch.setattr(pl, 'configured', boom)
    home = str(tmp_path / 'pi-home')
    assert calls.pi_offers(base.AccountRef('acc_p', home)) == (
        (), 'pi model discovery failed: OSError: pi state is unreadable')
    assert calls.pi_models(home) == ()
    caps = calls.PiCaller().capabilities(base.AccountRef('acc_p', home))
    assert caps.models == ()
    assert caps.models_note.startswith('pi model discovery failed: OSError')


def test_g13_a_catalogue_row_that_is_not_a_tiered_model_is_never_offered(monkeypatch):
    """calls.py:188-192 `t = CLAUDE_TIERS.get(r.get('family'))` /
    `if t is not None and r.get('id')`: a cached catalogue is user-writable disk,
    so a row of another family, of no family or of an empty id must add nothing —
    drop the two guards and a `--model` Core never declared is offered to the router."""
    from claude_sessions import models
    monkeypatch.setattr(models, 'roster', lambda: [
        {'family': 'opus', 'id': 'claude-opus-4-6-20260101'},
        {'family': 'not-a-family', 'id': 'claude-weird-1'},
        {'family': 'sonnet'},
        {'family': 'haiku', 'id': ''},
        {'id': 'claude-fable-1'},
        {'family': 'fable', 'id': None},
    ])
    got = {m.id: m.tier for m in calls.claude_models()}
    assert got == {'haiku': 'small', 'sonnet': 'mid', 'opus': 'large', 'fable': 'large',
                   'claude-opus-4-6': 'large'}


def test_g14_pi_is_authed_only_at_a_directory_that_exists(tmp_path):
    """calls.py:150-153 `bool(account.home_ref) and os.path.isdir(account.home_ref)`:
    the `and` order is the whole test — reversed, an account with no home raises
    `TypeError` inside the registration check instead of refusing; and a file, or a
    path that is gone, is never a login."""
    home = tmp_path / 'pi-home'
    home.mkdir()
    assert calls.PiCaller().authenticate(base.AccountRef('a', str(home))) == (
        base.AuthStatus(True, ''))
    away = calls.PiCaller().authenticate(base.AccountRef('a', str(tmp_path / 'nowhere')))
    assert away.ok is False and away.detail == 'no pi home at %s' % str(tmp_path / 'nowhere')
    a_file = tmp_path / 'pi-home-file'
    a_file.write_bytes(b'{}')
    assert calls.PiCaller().authenticate(base.AccountRef('a', str(a_file))).ok is False
    none = calls.PiCaller().authenticate(base.AccountRef('a', None))
    assert none.ok is False and none.detail == 'no pi home at None'


def test_g15_a_claude_account_is_authed_only_on_a_stored_login(monkeypatch, tmp_path):
    """calls.py:79-83 `ok = bool(usage._creds(account.home_ref))` and the detail
    beside it: asked about the ACTIVE home rather than the account's own, every
    account reports the login of whichever account happens to be current."""
    from claude_sessions import usage
    seen = []
    monkeypatch.setattr(usage, '_creds', lambda cfgdir=None: (seen.append(cfgdir), {})[1])
    home = str(tmp_path / 'claude-home')
    got = calls.ClaudeCodeCaller().authenticate(base.AccountRef('a', home))
    assert (got.ok, got.detail) == (False, 'no Claude login in %s' % home)
    assert seen == [home]
    monkeypatch.setattr(usage, '_creds', lambda cfgdir=None: {'accessToken': 'x'})
    assert calls.ClaudeCodeCaller().authenticate(base.AccountRef('a', home)) == (
        base.AuthStatus(True, ''))


def test_g16_what_an_adapter_declares_about_enforcement_and_usage_is_the_whole_truth(monkeypatch,
                                                                                      tmp_path):
    """calls.py:73-80 (Claude Code: enforcement `hook`, `usage_measures` of tokens
    ONLY, so a cost budget is refused — ADR-0048 §3) and calls.py:143-148 (pi: `none`,
    `prompted`, and a failed discovery carried as `models_note` with no models):
    declaring `cost` here, or guessing models, is what lets Core budget a call in
    dollars the harness cannot report, or elect an account that can run nothing."""
    monkeypatch.setattr(calls, 'claude_models', lambda: (base.ModelInfo('opus', 'large'),))
    c = calls.ClaudeCodeCaller().capabilities()
    assert (c.enforcement, c.structured_output, tuple(sorted(c.usage_measures))) == (
        'hook', 'native', ('tokens',))
    assert 'headless' in c.capabilities and 'cost' not in c.usage_measures
    assert [m.id for m in c.models] == ['opus']
    from claude_sessions import pi as pl
    monkeypatch.setattr(pl, 'configured',
                        lambda home=None: {'ok': False, 'models': [], 'why': 'exited 1'})
    p = calls.PiCaller().capabilities(base.AccountRef('a', str(tmp_path / 'pi-home')))
    assert (p.enforcement, p.structured_output, p.models) == ('none', 'prompted', ())
    assert p.models_note == 'exited 1'


# ── the two things an own call always carries: a deadline, and the mark ────

@pytest.mark.parametrize('caller', [calls.ClaudeCodeCaller, calls.PiCaller],
                         ids=['claude', 'pi'])
def test_g17_an_own_call_is_never_handed_no_deadline(spawn, caller):
    """calls.py:116 and :171 `timeout=spec.limits.get('timeout_s', 600)`: with the
    default gone (or the key misspelled) a wedged CLI is waited on forever, which is
    the hang the whole P0.5 runner exists to avoid."""
    caller().call(_spec(limits={'timeout_s': 7}))
    assert [kw['timeout'] for _, _, kw in spawn.seen] == [7]
    caller().call(_spec())
    assert [kw['timeout'] for _, _, kw in spawn.seen] == [7, 600]


@pytest.mark.parametrize('caller', [calls.ClaudeCodeCaller, calls.PiCaller],
                         ids=['claude', 'pi'])
def test_g18_an_own_call_leaves_the_mark_so_its_transcript_is_never_a_user_session(spawn,
                                                                                   caller):
    """calls.py:113 / :167, which go through `llmcall.build_headless_args` for
    HEADLESS_MARK (sessions.HEADLESS_MARK; `sessions.is_headless` is what keeps the
    transcript out of the user's session list and out of auto-memory): an adapter
    that spawned its own argv instead would write a transcript nobody recognises
    as archeus talking to itself."""
    from claude_sessions.sessions import HEADLESS_MARK
    caller().call(_spec())
    (cmd, stdin, kw), = spawn.seen
    assert stdin.startswith('P\n\n') and stdin.endswith(HEADLESS_MARK)
    assert HEADLESS_MARK not in [str(c) for c in cmd]


def test_g19_a_no_tools_claude_call_still_asks_for_its_shape(spawn):
    """calls.py:100-101 and :110-111 `extra = (…tool-less flags…) + extra`: lose the
    `+ extra` and a call that is BOTH tool-less and structured silently drops
    `--json-schema`; the prose that comes back is then unparseable, and Core sees an
    empty answer rather than a broken request."""
    schema = {'type': 'object', 'properties': {'b': {'type': 'integer'},
                                               'a': {'type': 'string'}}}
    calls.ClaudeCodeCaller().call(_spec(schema=schema, no_tools=True))
    (cmd, stdin, kw), = spawn.seen
    assert cmd.count('--tools') == 1 and cmd[cmd.index('--tools') + 1] == ''
    i = cmd.index('--json-schema')
    assert cmd[i - 2:i] == ['--output-format', 'json']
    assert cmd[i + 1] == json.dumps(schema, sort_keys=True)
    assert kw['env']['CLAUDE_CODE_DISABLE_CLAUDE_MDS'] == '1'
    assert kw['env']['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] == '1'
    assert not [k for k in kw['env'] if k.startswith(('ARCHEUS_', 'PYTEST_'))]


def test_g20_the_default_callers_are_exactly_the_two_clis_that_declare_headless():
    """calls.py:218-220 `return [ClaudeCodeCaller(), PiCaller()]`: this is what a
    Core with no ports named can spend, so a third adapter in here — one that cannot
    express `no_tools`, or Codex, whose `exec` logs progress into the answer — would
    be elected by the ordinary ordering with nothing refusing it."""
    assert [type(c).__name__ for c in calls.real_callers()] == ['ClaudeCodeCaller',
                                                                'PiCaller']
    assert [c.id for c in calls.real_callers()] == ['claude_code', 'pi']
