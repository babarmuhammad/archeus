"""T-1162 — the highest-risk uncovered branches of `archeus/harnesses/calls.py`
lines 1-233 inclusive (the whole module: `_env`, `_usage`, `_failed`,
`ClaudeCodeCaller`, `PiCaller`, `claude_models`, `pi_models`, `pi_offers`,
`real_callers`). No source file is edited by this card; nothing here imports
another `test_gaps3` file or depends on queue order.

The ten branches this file owns, in the order the card asked for them (fail-closed
and denial first, then boundaries, then error paths), each stated as the source
line whose removal or inversion its test would catch:

1. calls.py:91-94   `why_not` asks `quota.reason(account.home_ref)` — the account's
                    own home, never the active one.
2. calls.py:100-111 `extra = (…) if spec.schema is None` joined with the T-086
                    hidden-source tuple: the tool-less fence and `--safe-mode`
                    survive a call that asked for no shape.
3. calls.py:102/112 `env = _env(…)`, then `env.update(CLAUDE_CODE_DISABLE_…)`: the
                    override wins over the account's own value and is never written
                    back into the mapping `config.account_env` handed out.
4. calls.py:174-175 `build_headless_args(…, harness='pi', no_tools=spec.no_tools)`:
                    a tool-less pi call is tool-less whether or not a schema was asked.
5. calls.py:179-180 `if r.returncode != 0 or not r.stdout.strip(): return _failed(r)`
                    on the pi side, plus pi's `CallResult` carrying no `usage` at all.
6. calls.py:125-127 `if … envelope.get('is_error') is True: return CallResult(…)`:
                    an error envelope is refused whole — no text, no parsed, no figures.
7. calls.py:115/176 `cwd=spec.workdir`: the call runs where the spec says, not where
                    Core happens to be, and not on the account's home.
8. calls.py:72-78/150-155 `Capabilities(…)`: each adapter declares exactly what its
                    own `call()` can honour — pi declares no `shell`/`code_edit`/
                    `resume` and reports no usage measure at all.
9. calls.py:51-58   `_failed`: `if r.timed_out` / `if r.returncode is None` both come
                    before the `_MODEL_REFUSED`/`_MODEL_WHY` naming.
10. calls.py:119-131 `except ValueError: envelope = llmcall.parse_json(…) if
                    spec.schema is not None else None` and the `isinstance(envelope,
                    dict)` guards beside it, on a TRUNCATED warning-prefixed answer.

Style and rig follow the closest existing tests of this module
(`tests/v1/unit/test_gaps_harnesses_calls.py`, and test_l13/test_l14/test_l15 at
`tests/v1/unit/test_knowledge_units.py:202`/:226/:257): one stand-in for every OS
touch (`llmcall.run_headless`, `llmcall.budget_args`, `config.account_env`,
`config.get_claude_exe`, `harnesses.exe`/`harnesses.disabled`), nothing but synthetic
environment mappings (no test here reads or copies a value of the ambient
environment), invented credential values, every path under `tmp_path`, portable
`.exe` names, no network, no real subprocess, no sleep and no thread inventory. The
one `os` call in this file is `os.getcwd()` of the test process, compared and never
printed. The only real filesystem read inside the slice is `os.path.isdir` in
`PiCaller.authenticate` (calls.py:157-160), and `tests/v1/unit/test_gaps_harnesses_calls.py:308`
(G14) already owns it: branch ownership does not move out of this slice.
"""

import json
import os

import pytest

from archeus.harnesses import base, calls
from claude_sessions import config, harnesses, llmcall
from claude_sessions import quota

#: what `config.account_env` really hands back (claude_sessions/config.py:924-929:
#: `os.environ.copy()` plus the account's own home variable, minus its `env_pops`).
#: Every value below is invented for this file; none is read from the environment.
ACCOUNT_ENV = {'PATH': 'C:/fake/bin',
               'HOME': 'C:/fake/home',
               'SPARK_QWEN_KEY': 'sk-invented-for-this-test',
               'CLAUDE_CODE_DISABLE_CLAUDE_MDS': '0',      # the account's own setting
               'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '0',
               'ARCHEUS_HOME': 'C:/core/run',
               'ARCHEUS_HOOK_TOKEN': 'brk_invented',
               'PYTEST_CURRENT_TEST': 'tests/v1/unit/test_gaps3_harnesses_calls.py::x'}

#: the two names a tool-less Claude call must impose (calls.py:112)
DISABLE = ('CLAUDE_CODE_DISABLE_CLAUDE_MDS', 'CLAUDE_CODE_DISABLE_AUTO_MEMORY')

#: the T-086 hidden-source fence exactly as calls.py:110-111 builds it
NO_TOOLS_TAIL = ['--strict-mcp-config', '--disable-slash-commands',
                 '--setting-sources', 'user', '--safe-mode']

#: a Claude-shaped answer that says everything an answer needs — and everything a
#: lying CLI would like Core to believe
TEMPTING = json.dumps({'is_error': False, 'result': '{"decisions": ["stolen"]}',
                       'structured_output': {'decisions': ['stolen']},
                       'usage': {'input_tokens': 9999, 'output_tokens': 9999},
                       'total_cost_usd': 0.0})

#: the invented account home every spec here carries unless it says otherwise
HOME = 'acct-home'

_SPEC = dict(route_decision_id='rte_3', purpose='brain', prompt='P', workdir='.',
             schema=None, model=None, limits={}, no_tools=False)


def _spec(home=HOME, **kw):
    return base.CallSpec(**dict(dict(_SPEC, account=base.AccountRef('acc', home)), **kw))


def _result(rc=0, stdout='', reason='', error='', timed_out=False):
    return llmcall.Result(rc, stdout, reason, error, timed_out)


class Runner:
    """`llmcall.run_headless` and `config.account_env` in one stand-in.

    `account` is ONE mapping handed out to every call, which is what a memoizing
    `account_env` would do: an adapter that wrote into it would change every later
    call's environment, so `test_a_tool_less_claude_call_*` asserts it comes back
    untouched. `seen` records every (argv, stdin, kwargs) the adapters spawn."""

    def __init__(self, result=None):
        self.result, self.seen, self.env_calls = result, [], []
        self.account = dict(ACCOUNT_ENV)

    def __call__(self, cmd, input_text=None, **kw):
        self.seen.append((cmd, input_text, kw))
        return self.result

    def account_env(self, home=None, harness=None):
        self.env_calls.append((home, harness))
        return self.account


@pytest.fixture
def spawn(monkeypatch, tmp_path):
    """Every seam the two adapters reach the OS through, stood in one place."""
    r = Runner(_result(stdout='{}'))
    monkeypatch.setattr(llmcall, 'run_headless', r)
    monkeypatch.setattr(llmcall, 'budget_args', lambda: [])
    monkeypatch.setattr(config, 'account_env', r.account_env)
    monkeypatch.setattr(config, 'get_claude_exe', lambda: str(tmp_path / 'claude.exe'))
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: str(tmp_path / 'pi.exe'))
    monkeypatch.setattr(harnesses, 'disabled', lambda: set())
    return r


# ── denial: an account that may not be spent, and a call that may not have tools ──

def test_an_account_that_cannot_be_spent_is_refused_at_its_own_home(spawn, monkeypatch):
    """calls.py:91-94 `return quota.reason(account.home_ref)`. Inverted to
    `quota.reason()` — the obvious edit, since `reason` defaults its argument — the
    adapter answers for whichever account happens to be ACTIVE, so a spent account
    keeps being elected and keeps spending, and a healthy one is blocked by another
    account's rate limit. No existing test calls this method at all: the only
    `why_not` any test reads is pi's, at
    `tests/v1/unit/test_knowledge_units.py:238`, and pi's is a constant ''
    (calls.py:166-167), so the Claude denial channel is entirely unasserted."""
    seen = []

    def reason(cfgdir=None):
        seen.append(cfgdir)
        return 'account rate-limited by Claude' if cfgdir == 'spent-home' else ''

    monkeypatch.setattr(quota, 'reason', reason)
    spent = calls.ClaudeCodeCaller().why_not(base.AccountRef('acc_s', 'spent-home'))
    free = calls.ClaudeCodeCaller().why_not(base.AccountRef('acc_f', 'free-home'))
    assert spent == 'account rate-limited by Claude' and bool(spent)
    assert free == ''
    assert seen == ['spent-home', 'free-home']


def test_a_tool_less_claude_call_drops_every_hidden_source_even_without_a_shape(spawn):
    """calls.py:100-101 + calls.py:110-111: `extra = (…) if spec.schema is None` and
    then `extra = ('--tools', '', …, '--safe-mode') + extra`. Written as an
    assignment instead of a join — or with the tool-less flags only added when a
    shape was asked — the argv keeps one half and `--tools ""`, `--strict-mcp-config`
    or `--safe-mode` silently disappears, which puts MCP servers, skills, project
    settings (their hooks), the user's plugins/agents and every ancestor CLAUDE.md
    back into a call whose prompt carries data Core must not let it read.
    `tests/v1/integration/test_deputies.py:390` inspects only a call WITH a schema
    (its `_call` defaults `schema={'type': 'object'}`, that file:362) and
    `tests/v1/unit/test_gaps_harnesses_calls.py:393` (G19) only a call with both, so
    the no-shape half of this join is unasserted."""
    calls.ClaudeCodeCaller().call(_spec(no_tools=True, schema=None))
    (cmd, stdin, kw), = spawn.seen
    assert cmd.count('--tools') == 1 and cmd[cmd.index('--tools') + 1] == ''
    i = cmd.index('--strict-mcp-config')
    assert cmd[i - 2:i] == ['--tools', ''] and cmd[i:i + len(NO_TOOLS_TAIL)] == NO_TOOLS_TAIL
    assert cmd.count('--strict-mcp-config') == 1
    for flag in ('--mcp-config', '--allowedTools', '--plugin-dir', '--session-id'):
        assert flag not in cmd
    assert '--output-format' not in cmd and '--json-schema' not in cmd   # none was asked
    assert {k: kw['env'][k] for k in DISABLE} == {k: '1' for k in DISABLE}
    # the same call asked for its shape: both halves of the join are still there
    calls.ClaudeCodeCaller().call(_spec(no_tools=True, schema={'type': 'object',
                                                               'properties': {'a': {}}}))
    cmd2 = spawn.seen[1][0]
    assert cmd2.count('--tools') == 1 and cmd2[cmd2.index('--tools') + 1] == ''
    j = cmd2.index('--json-schema')
    assert cmd2[j - 2:j] == ['--output-format', 'json']
    assert cmd2[j + 1] == json.dumps({'properties': {'a': {}}, 'type': 'object'},
                                     sort_keys=True)
    assert cmd2[i - 2:i] == ['--tools', ''] and cmd2.count('--safe-mode') == 1
    assert len(spawn.seen) == 2                                   # one spawn per call


def test_a_tool_less_claude_env_overrides_the_account_and_writes_nowhere_it_shared(spawn):
    """calls.py:102 `env = _env(spec.account.home_ref, self.id)` and calls.py:112
    `env.update(CLAUDE_CODE_DISABLE_CLAUDE_MDS='1', CLAUDE_CODE_DISABLE_AUTO_MEMORY='1')`.
    Two inversions are caught: `update` becoming `setdefault` (the account's own
    `'0'` then re-enables CLAUDE.md and auto-memory for a call that must not read
    them), and `_env` handing the caller the mapping `config.account_env` gave it —
    the tool-less flags then stick to every later call, including the user's own.
    `tests/v1/integration/test_deputies.py:402` and :428 delete those two names from
    the environment before the call, so they can only ever see them absent, never
    overridden by the account's own value, and
    `tests/v1/unit/test_gaps_harnesses_calls.py:393` (G19) makes one call, so nothing
    pins the order of a tool-less call and the call after it."""
    home = HOME                                            # the spec's own account home
    calls.ClaudeCodeCaller().call(_spec(home=home, no_tools=True))
    first = spawn.seen[0][2]['env']
    assert {k: first[k] for k in DISABLE} == {k: '1' for k in DISABLE}
    assert first['SPARK_QWEN_KEY'] == 'sk-invented-for-this-test' and first['PATH']
    assert not [k for k in first if k.startswith(('ARCHEUS_', 'PYTEST_'))]
    calls.ClaudeCodeCaller().call(_spec(home=home, no_tools=False))
    second = spawn.seen[1][2]['env']
    # Core never imposes the fence on a call that needs its context…
    assert {k: second[k] for k in DISABLE} == {k: '0' for k in DISABLE}
    assert second is not first
    # …and nothing of the tool-less call leaked into the shared account mapping
    assert spawn.account == ACCOUNT_ENV
    assert spawn.env_calls == [(home, 'claude_code'), (home, 'claude_code')]


def test_a_tool_less_pi_call_is_tool_less_whether_or_not_a_shape_was_asked(spawn,
                                                                            tmp_path):
    """calls.py:174-175 `llmcall.build_headless_args(…, harness='pi',
    no_tools=spec.no_tools)`. Read as `no_tools=spec.schema is not None` — or with
    the flag dropped for the no-schema branch, which is what the shape of the two
    `spec.schema is not None` gates invites — a tool-less pi call that asked for no
    shape comes back with `--tools read,grep,find,ls`, and `--no-tools` alone (no
    `--no-extensions`, claude_sessions/pi.py:311) lets an extension add one back.
    `tests/v1/integration/test_deputies.py:410` again asks with a schema, and
    `tests/v1/unit/test_knowledge_units.py:226` (test_l14) only ever runs an ordinary
    call, so no existing test holds both halves of this keyword."""
    exe = str(tmp_path / 'pi.exe')
    calls.PiCaller().call(_spec(no_tools=True, schema=None))
    (cmd, stdin, kw), = spawn.seen
    assert cmd == [exe, '-p', '--no-session', '--no-tools', '--no-extensions']
    assert 'JSON Schema' not in stdin                       # nothing was asked for
    calls.PiCaller().call(_spec(no_tools=True, schema={'type': 'object'}))
    cmd2, stdin2, kw2 = spawn.seen[1]
    assert cmd2 == cmd and 'matching this JSON Schema' in stdin2
    calls.PiCaller().call(_spec(no_tools=False, schema=None))
    assert spawn.seen[2][0] == [exe, '-p', '--no-session', '--tools',
                                'read,grep,find,ls']
    # pi is not Claude Code: a tool-less pi call never writes Claude's private names,
    # it only passes on whatever the account itself carries
    for env in (kw['env'], kw2['env'], spawn.seen[2][2]['env']):
        assert all(env.get(k) == ACCOUNT_ENV[k] for k in DISABLE)
        assert not [k for k in env if k.startswith(('ARCHEUS_', 'PYTEST_'))]
    assert spawn.env_calls == [(HOME, 'pi'), (HOME, 'pi'), (HOME, 'pi')]


# ── an answer is only ever what a run that succeeded printed ────────────────

@pytest.mark.parametrize('stdout, returncode, reason, want', [
    (TEMPTING, 1, 'provider exploded', 'provider exploded'),
    ('   ', 0, '', 'the call produced no output'),
], ids=['exit-one-with-an-answer-in-its-mouth', 'exit-zero-with-nothing-but-blank'])
def test_a_failed_pi_run_hands_back_neither_its_stdout_nor_its_figures(spawn, stdout,
                                                                       returncode,
                                                                       reason, want):
    """calls.py:179-180 `if r.returncode != 0 or not r.stdout.strip(): return
    _failed(r)`, whose `_failed` (calls.py:49-58) answers with `error`/`detail` and
    the defaults of `base.CallResult` (archeus/harnesses/base.py:205-209) —
    `text=''`, `parsed=None`, `usage={}`. Drop the guard and the runner's merged
    stderr is read as the answer: the blank case, because `run_headless` strips,
    becomes an empty "ok" with no
    reason anywhere, and the crashed CLI's last words — here a whole Claude-shaped
    envelope — become `parsed` and the ledger's figures.
    `tests/v1/unit/test_gaps_harnesses_calls.py:126` (G04) asserts this for Claude
    Code only, its :149 (G05) parametrises pi over cases whose `stdout` is always `''`
    (the `_result` default), and `tests/v1/integration/test_deputies.py:483` prints
    only blanks, so a failed pi run that printed something tempting is unasserted."""
    spawn.result = _result(rc=returncode, stdout=stdout, reason=reason)
    got = calls.PiCaller().call(_spec(schema={'type': 'object'}))
    assert (got.error, got.detail, got.text, got.parsed, got.usage) == (
        'failed', want, '', None, {})
    assert len(spawn.seen) == 1                               # one spawn, no retry
    # and the same envelope on a run that DID succeed still reports no figures: pi
    # declares no usage measure (calls.py:150-155), so nothing it prints is a ledger
    spawn.result = _result(rc=0, stdout=TEMPTING)
    ok = calls.PiCaller().call(_spec(schema={'type': 'object'}))
    assert (ok.error, ok.usage) == (None, {})
    assert ok.parsed == json.loads(TEMPTING)                   # parse_json, never unwrapped


def test_an_error_envelope_is_refused_whole_and_feeds_neither_answer_nor_ledger(spawn):
    """calls.py:125-127 `if isinstance(envelope, dict) and envelope.get('is_error')
    is True: return base.CallResult(error='failed', detail=str(envelope.get('result')
    or 'the call reported an error')[:500])` — a return that happens BEFORE
    calls.py:128-134 builds `raw`, `parsed`, `usage` and `cost_usd`. Move it below
    them, or drop it, and an error the CLI reported with exit 0 still puts its
    `structured_output` in front of Core as an answer and its `usage`/`total_cost_usd`
    in the ledger. `tests/v1/integration/test_deputies.py:489` asserts the
    (error, detail) pair of a minimal envelope only, so nothing there proves the rest
    of the envelope died with it."""
    envelope = {'is_error': True, 'result': 'credit balance is too low',
                'structured_output': {'decisions': ['accepted-anyway']},
                'usage': {'input_tokens': 9999, 'output_tokens': 9999},
                'total_cost_usd': 1.0}
    spawn.result = _result(rc=0, stdout=json.dumps(envelope))
    got = calls.ClaudeCodeCaller().call(_spec(schema={'type': 'object'}))
    assert (got.error, got.detail) == ('failed', 'credit balance is too low')
    assert (got.text, got.parsed, got.usage) == ('', None, {})
    assert len(spawn.seen) == 1


# ── boundaries: where a call runs, and what an adapter may claim ────────────

@pytest.mark.parametrize('caller', [calls.ClaudeCodeCaller, calls.PiCaller],
                         ids=['claude', 'pi'])
def test_an_own_call_runs_where_the_spec_sends_it_and_nowhere_else(spawn, tmp_path,
                                                                  caller):
    """calls.py:115 `cwd=spec.workdir` and calls.py:176 `cwd=spec.workdir`. With the
    keyword gone (or `cwd=None`) the child inherits Core's own working directory, so
    a tool-less call resolves its config, its CLAUDE.md and its relative paths
    against wherever Core happens to be rather than the workspace the route decided
    on — the confinement half of ADR-0022 that no flag can put back. No existing
    test reads the `cwd` the stand-in spawn was given:
    `tests/v1/unit/test_knowledge_units.py:202`/:226 (test_l13/test_l14) assert argv,
    stdin and env, and `tests/v1/integration/test_deputies.py:374` builds every spec
    with `workdir='.'`, the same value all its cases use."""
    one, two = tmp_path / 'ws-one', tmp_path / 'ws-two'
    one.mkdir()
    two.mkdir()
    home = str(tmp_path / 'acct-home')
    caller().call(_spec(home=home, workdir=str(one)))
    caller().call(_spec(home=home, workdir=str(two)))
    assert [kw['cwd'] for _, _, kw in spawn.seen] == [str(one), str(two)]
    for _, _, kw in spawn.seen:
        assert kw['cwd'] != str(home) and kw['cwd'] != os.getcwd()
    assert spawn.env_calls == [(home, caller.id), (home, caller.id)]


def test_no_adapter_declares_a_capability_its_own_call_cannot_honour(monkeypatch):
    """calls.py:72-78 (`ClaudeCodeCaller.capabilities`) and calls.py:150-155
    (`PiCaller.capabilities`). `tests/v1/unit/test_own_call_no_tools.py:132` and
    `tests/v1/unit/test_gaps_harnesses_calls.py:342` (G16) assert membership
    (`'no_tools' in …`, enforcement, `structured_output`), so an adapter that ADDS a
    capability is never caught: `shell` or `code_edit` on pi would let the router
    elect the pi own call for work its argv (`--tools read,grep,find,ls`, or
    `--no-tools`) cannot do, and a `cost` measure would let Core budget in dollars a
    harness that reports none (ADR-0048 §3)."""
    monkeypatch.setattr(calls, 'claude_models', lambda: ())
    monkeypatch.setattr(calls, 'pi_offers', lambda account=None: ((), 'stand-in'))
    c = calls.ClaudeCodeCaller().capabilities()
    p = calls.PiCaller().capabilities(base.AccountRef('acc_p', 'pi-home'))
    assert c.capabilities == frozenset({'headless', 'structured_output', 'interactive',
                                        'resume', 'code_edit', 'shell', 'no_tools'})
    assert p.capabilities == frozenset({'headless', 'structured_output', 'interactive',
                                        'no_tools'})
    assert not {'shell', 'code_edit', 'resume', 'web', 'mcp'} & p.capabilities
    assert tuple(p.usage_measures) == () and 'cost' not in c.usage_measures
    assert (c.enforcement, c.structured_output) == ('hook', 'native')
    assert (p.enforcement, p.structured_output) == ('none', 'prompted')


# ── error paths: naming a failure is a routing decision ────────────────────

@pytest.mark.parametrize('result, want', [
    (_result(rc=None, error='could not start: model "claude-opus-9" does not exist'),
     'unavailable'),
    (_result(rc=None, error='timed out after 600s: the model was never available',
             timed_out=True), 'timeout'),
    (_result(rc=1, reason='Model "claude-opus-9" is unknown to this account'),
     'model_unavailable'),
], ids=['no-exit-code-says-model', 'timeout-says-model', 'a-real-refusal-says-model'])
def test_a_failure_with_no_exit_code_is_never_named_a_refused_model(spawn, result, want):
    """calls.py:51-58: `if r.timed_out`, then `if r.returncode is None`, both before
    `_MODEL_REFUSED.search(why) and _MODEL_WHY.search(why)`. In that order the CLI
    that never started stays `unavailable` (this harness is not there) instead of
    `model_unavailable` (this MODEL is not there): inverted, one broken install
    retires a healthy model for every account in the routing state, and a wedged
    spawn — which never had an exit code at all — is reported as a policy refusal.
    `tests/v1/unit/test_gaps_harnesses_calls.py:149` (G05) covers the two guards and
    the naming, but every case there that names a model carries `rc=1`, so the two
    earlier `return`s are never met by a model-shaped `why`."""
    spawn.result = result
    got = calls.ClaudeCodeCaller().call(_spec(schema={'type': 'object'}))
    assert (got.error, got.detail, got.text, got.parsed, got.usage) == (
        want, result.reason or result.error, '', None, {})


def test_a_truncated_warning_prefixed_answer_fabricates_neither_shape_nor_figures(spawn):
    """calls.py:119-124 `try: envelope = json.loads(r.stdout)` /
    `except ValueError: envelope = llmcall.parse_json(r.stdout) if spec.schema is not
    None else None`, with the `isinstance(envelope, dict)` guards of calls.py:125,
    :128 and :131 on the recovery that is not recoverable. `run_headless` merges
    stderr into stdout, so a CLI that dies mid-envelope leaves a warning line and a
    half object: the call is not a crash, its text is exactly what was printed, and
    `parsed` is None — not `{}`, which Core's schema would accept as a well-formed
    empty answer — while `usage` stays empty rather than reading figures out of the
    prose. `tests/v1/integration/test_deputies.py:456` covers a warning ahead of a
    WHOLE envelope, and `tests/v1/unit/test_gaps_harnesses_calls.py:206` (G08) covers
    unparsable output only for a call that asked for no shape, so nothing runs a
    shape-requested call through a broken one."""
    truncated = ('warning: stale cache, retrying\n{"usage": {"input_tokens": 9}, '
                 '"total_cost_usd": 2.5, "result": "par')
    spawn.result = _result(rc=0, stdout=truncated)
    got = calls.ClaudeCodeCaller().call(_spec(schema={'type': 'object'}))
    assert got.error is None and got.text == truncated
    assert got.parsed is None and got.usage == {}
    # the control: the same warning ahead of a whole envelope costs neither its
    # figures nor its shape (the `parse_json` side of the same except)
    whole = ('warning: stale cache, retrying\n'
             + json.dumps({'result': 'ok', 'structured_output': {'decisions': []},
                           'usage': {'input_tokens': 9}, 'total_cost_usd': 2.5}))
    spawn.result = _result(rc=0, stdout=whole)
    ok = calls.ClaudeCodeCaller().call(_spec(schema={'type': 'object'}))
    assert (ok.error, ok.parsed) == (None, {'decisions': []})
    assert ok.usage == {'tokens_in': 9, 'cost_usd': 2.5}
    assert len(spawn.seen) == 2
