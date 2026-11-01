"""T-321: the uncovered branches of `archeus/harnesses/fake_agent.py`.

The fake agent is the stand-in every other test trusts (P20, ADR-0049 §3,
ADR-0052, PV-19 O4), so a branch of it that nothing exercises is a scripted
behaviour no test can rely on. This file takes the branches the existing tests
of the module leave alone — `test_settings_sources_units.py` E20/E23 (the exit
codes, `continue: false` with and without the deny) and
`test_tool_removal_units.py` F12-F14 (the tool flags), and
`contract/test_adapter_contract.py` (the process contract through the harness) —
in the order the risk falls: the deny and fail-closed paths first, then the
boundary values, then the error paths.

Everything runs the way the module's own tests run it: the scenario as argv[1],
the start step as argv[2], the spawn's flags after that, the prompt on stdin,
and every hook a script under `tmp_path` answered through `ARCHEUS_HOOK_CMD`
(the seam E20/E23/F12 use). Nothing here needs Windows or the Windows API, and
no fixture depends on case sensitivity, on an OS error text or on a path
separator: file names are ASCII without `?` or `:`, written bytes are compared
in binary, and the only sleep is 0.4 s of a hook that is killed at 0.05 s.
"""

import hashlib
import json
import os
import subprocess
import sys

import pytest

from archeus.harnesses import fake_agent as fa

AGENT = fa.__file__
EID = 'exe_' + 'A' * 26
ALLOW = json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                           'permissionDecision': 'allow'}})


def _tool(name=None, **inp):
    """One scripted tool call; `name=None` omits the key entirely."""
    ev = {'type': 'tool'}
    if name is not None:
        ev['name'] = name
    if inp:
        ev['input'] = inp
    return {'emit': ev}


def _hook(tmp_path, body, name='hook.py'):
    """An `ARCHEUS_HOOK_CMD` value: the JSON argv naming one script under
    tmp_path, exactly as E20, E23 and F12 build one."""
    script = tmp_path / name
    script.write_text(body, encoding='utf-8', newline='\n')
    return json.dumps([sys.executable, str(script)])


def _agent(steps, argv=(), start='0', cwd=None, env=None, stdin='', stdin_raw=None):
    """Run the fake agent as a foreign CLI is run: scenario, start step, flags,
    prompt on stdin. Returns (CompletedProcess, the events it printed)."""
    assert cwd is not None, 'the fake resolves everything against its cwd; name it'
    child = dict(os.environ)
    for k in ('ARCHEUS_HOOK_CMD', 'ARCHEUS_HOOK_TIMEOUT', 'ARCHEUS_EXECUTION_ID'):
        child.pop(k, None)                       # a host's value must not leak in
    child.update(env or {})
    raw = stdin_raw is not None
    r = subprocess.run([sys.executable, AGENT, json.dumps(steps), start] + list(argv),
                       input=stdin_raw if raw else stdin, capture_output=True,
                       text=not raw, cwd=str(cwd), env=child, timeout=60)
    out = r.stdout.decode('utf-8') if raw else r.stdout
    return r, [json.loads(line) for line in out.splitlines()]


def _kinds(evs):
    return [e['type'] for e in evs if isinstance(e, dict)]


# ── the denial and fail-closed paths ─────────────────────────────────────────

@pytest.mark.parametrize('stderr_text, reason', [('', ''), ('  denied now  \n', 'denied now')],
                         ids=['no-reason', 'padded-reason'])
def test_FA01_exit_code_2_denies_even_with_nothing_to_say(tmp_path, stderr_text, reason):
    """fake_agent.py:124-125. A deny that carries no reason is still the
    unconditional block: were the reason made the condition (`if r.stderr`), or
    were the strip dropped, the call would run, or carry a padded reason."""
    work = tmp_path / 'work'
    work.mkdir()
    cmd = _hook(tmp_path, 'import sys\nsys.stdin.read()\nsys.stderr.write(%r)\nsys.exit(2)\n'
                % stderr_text)
    steps = [_tool('Write', file_path='x.txt', content='x'),
             {'emit': {'type': 'assistant', 'text': 'after'}}]
    r, evs = _agent(steps, cwd=work, env={'ARCHEUS_HOOK_CMD': cmd})
    assert _kinds(evs) == ['started', 'tool_denied', 'exit']
    assert (evs[1]['name'], evs[1]['reason']) == ('Write', reason)
    assert (r.returncode, evs[-1]) == (3, {'type': 'exit', 'code': 3})
    assert not (work / 'x.txt').exists()             # the call never ran


def test_FA02_a_hook_that_cannot_run_at_all_is_a_non_blocking_error(tmp_path):
    """fake_agent.py:122-123 (the OSError side). A hook whose command cannot be
    executed is the documented worst case modelled, not a halt: the call
    PROCEEDS with a hook_error. Invert it (fail closed here) and the fake would
    hide a hook that is simply never installed."""
    work = tmp_path / 'work'
    work.mkdir()
    missing = str(tmp_path / 'no-such-hook-script.py')
    steps = [_tool('Read', file_path='a.txt')]
    r, evs = _agent(steps, cwd=work, env={'ARCHEUS_HOOK_CMD': json.dumps([missing])})
    assert _kinds(evs) == ['started', 'hook_error', 'tool', 'exit']
    assert evs[1]['reason'].startswith('the hook did not answer: ')
    assert evs[1]['reason'].endswith('Error')       # the exception's own type name
    assert (r.returncode, evs[-1]) == (0, {'type': 'exit', 'code': 0})


def test_FA03_a_hook_that_never_answers_hits_the_fake_own_timeout(tmp_path):
    """fake_agent.py:119-123 (the timeout side). ARCHEUS_HOOK_TIMEOUT is read
    from the environment and a hook over it is a non-blocking error, so the
    call runs. Drop the timeout= argument and this hangs; read no env and the
    call never runs, so the run never ends."""
    work = tmp_path / 'work'
    work.mkdir()
    cmd = _hook(tmp_path, 'import sys, time\nsys.stdin.read()\ntime.sleep(0.4)\n'
                'print("{}")\n')
    r, evs = _agent([_tool('Read', file_path='a.txt')], cwd=work,
                    env={'ARCHEUS_HOOK_CMD': cmd, 'ARCHEUS_HOOK_TIMEOUT': '0.05'})
    assert _kinds(evs) == ['started', 'hook_error', 'tool', 'exit']
    assert evs[1]['reason'] == 'the hook did not answer: TimeoutExpired'
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}


def test_FA04_a_json_deny_blocks_the_call_it_answers(tmp_path):
    """fake_agent.py:135 (the deny test only exists inside the `continue is
    False` branch). The fake is what catches a hook that fails open; reading a
    deny as no decision is the one fail-open it must not add itself. E20/E23
    only ever pair the deny with `continue: false`, so nothing covered the bare
    form — which is the form Claude Code documents."""
    work = tmp_path / 'work'
    work.mkdir()
    cmd = _hook(tmp_path, 'import sys\nsys.stdin.read()\nsys.stdout.write(%r)\n'
                % json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                                     'permissionDecision': 'deny',
                                                     'permissionDecisionReason': 'not today'}}))
    steps = [_tool('Write', file_path='x.txt', content='x'),
             {'emit': {'type': 'assistant', 'text': 'after'}}]
    r, evs = _agent(steps, cwd=work, env={'ARCHEUS_HOOK_CMD': cmd})
    assert _kinds(evs) == ['started', 'tool_denied', 'exit']
    assert evs[1]['reason'] == 'not today' and r.returncode == 3
    assert not (work / 'x.txt').exists()


@pytest.mark.parametrize('answer', [
    pytest.param(json.dumps({'permissionDecision': 'allow'}), id='decision-at-top-level'),
    pytest.param(json.dumps({'continue': True, 'hookSpecificOutput': None,
                             'permissionDecision': 'allow'}), id='null-hook-output'),
    pytest.param('[]', id='json-array'),
    pytest.param('"allow"', id='json-string'),
], ids=str)
def test_FA05_only_a_hook_specific_output_can_answer(tmp_path, answer):
    """fake_agent.py:132-133 and 138-140. The decision is read out of
    `hookSpecificOutput` and only from there, and only out of a JSON *object*:
    a top-level decision, a null `hookSpecificOutput` or a non-dict document is
    "the hook gave no decision", never an allow. Read the field at the top
    level and the first case would run the call unjudged; keep the JSON of a
    list and the second would crash the agent instead of answering."""
    work = tmp_path / 'work'
    work.mkdir()
    cmd = _hook(tmp_path, 'import sys\nsys.stdin.read()\nsys.stdout.write(%r)\n' % answer)
    r, evs = _agent([_tool('Read', file_path='a.txt')], cwd=work,
                    env={'ARCHEUS_HOOK_CMD': cmd})
    assert _kinds(evs) == ['started', 'hook_error', 'tool', 'exit']
    assert evs[1]['reason'] == 'the hook gave no decision'
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}


@pytest.mark.parametrize('answer, halts', [
    pytest.param(json.dumps({'continue': False}), True, id='boolean-false'),
    pytest.param(json.dumps({'continue': 'false', 'hookSpecificOutput': {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}), False,
        id='string-false'),
    pytest.param(json.dumps({'continue': 0, 'hookSpecificOutput': {
        'hookEventName': 'PreToolUse', 'permissionDecision': 'allow'}}), False, id='continue-zero'),
], ids=str)
def test_FA06_only_the_boolean_false_continues_stop_the_agent(tmp_path, answer, halts):
    """fake_agent.py:134 (`out.get('continue') is False`). A hook writing
    `"continue": "false"` or `0` means stop to a human and means nothing to
    Claude Code; read truthily (`if not out.get('continue')`) the fake would
    halt on a hook that in fact allowed the call."""
    work = tmp_path / 'work'
    work.mkdir()
    cmd = _hook(tmp_path, 'import sys\nsys.stdin.read()\nsys.stdout.write(%r)\n' % answer)
    steps = [_tool('Write', file_path='ran.txt', content='x'),
             {'emit': {'type': 'assistant', 'text': 'after'}}]
    r, evs = _agent(steps, cwd=work, env={'ARCHEUS_HOOK_CMD': cmd})
    kinds = _kinds(evs)
    assert ('halted' in kinds) is halts
    assert ('assistant' in kinds) is not halts
    assert 'tool' in kinds                          # PV-19 O4: the call runs first
    assert (work / 'ran.txt').exists()
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}


def test_FA07_the_call_the_fake_sends_the_hook_is_what_the_hook_reads(tmp_path):
    """fake_agent.py:115-117 and 188/198. The hook gets the PreToolUse JSON on
    stdin — the event name, the tool name, the input, the cwd and the
    execution id — and gets it for the tool calls only, never for an
    assistant line. Rename one key and archeus/harnesses/hook.py reads no
    tool, judges nothing, and the call runs; ask the hook about non-tool
    events and every emitted line becomes a round trip to it."""
    work = tmp_path / 'work'
    work.mkdir()
    log = tmp_path / 'calls.jsonl'
    cmd = _hook(tmp_path, 'import sys, json\n'
                'd = json.loads(sys.stdin.read())\n'
                'with open(%r, "a", encoding="utf-8") as f:\n'
                '    f.write(json.dumps(d) + "\\n")\n'
                'print(%r)\n' % (str(log), ALLOW))
    steps = [{'emit': {'type': 'assistant', 'text': 'thinking'}},
             _tool('Write', file_path='out.txt', content='body'),
             {'emit': {'type': 'result', 'summary': 'done'}}]
    r, evs = _agent(steps, cwd=work, env={'ARCHEUS_HOOK_CMD': cmd,
                                          'ARCHEUS_EXECUTION_ID': EID})
    assert r.returncode == 0
    calls = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert [c['tool_name'] for c in calls] == ['Write']            # only the tool call
    assert calls[0]['hook_event_name'] == 'PreToolUse'
    assert calls[0]['tool_input'] == {'file_path': 'out.txt', 'content': 'body'}
    assert calls[0]['session_id'] == EID
    assert os.path.isabs(calls[0]['cwd']) and os.path.samefile(calls[0]['cwd'], str(work))


# ── the scripted steps: resume, exit, the unknown ────────────────────────────

def test_FA08_a_tool_call_with_no_name_never_reaches_the_hook(tmp_path):
    """fake_agent.py:183-187 (`ev.get('name') or ''`, then the availability
    gate, before any hook). A scripted tool with no name cannot be matched to
    a tool the flags allow, so it is unavailable: it must not be offered to
    the hook (an empty name would match a hook that denies by name only) and
    must not run. Move the gate after the hook and an unnamed call is judged
    by whatever the hook happens to answer."""
    work = tmp_path / 'work'
    work.mkdir()
    log = tmp_path / 'asked.txt'
    cmd = _hook(tmp_path, 'import sys, json\nd = json.loads(sys.stdin.read())\n'
                'open(%r, "a").write(str(d["tool_name"]) + "\\n")\n'
                'print(%r)\n' % (str(log), ALLOW))
    steps = [_tool(), _tool('', file_path='a.txt'), {'emit': {'type': 'tool'}},
             {'emit': {'type': 'tool', 'name': '', 'input': {}}},
             _tool('Read', file_path='b.txt')]
    r, evs = _agent(steps, argv=['--tools', 'Read'], cwd=work,
                    env={'ARCHEUS_HOOK_CMD': cmd})
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}
    assert [e['type'] for e in evs][1:-1] == ['tool_unavailable', 'tool_unavailable',
                                              'tool_unavailable', 'tool_unavailable', 'tool']
    assert log.exists() and log.read_text().split() == ['Read']     # only the named one


def test_FA09_a_halt_names_the_step_a_resumed_process_starts_at(tmp_path):
    """fake_agent.py:193 with 177-179 and 158. The blocked call halts at ITS OWN
    step, so the resume asks the hook about it again instead of skipping a
    call that never ran; and every step before `start` is skipped, never
    re-run. Off-by-one either way and a resumed execution replays a side
    effect or silently drops a task."""
    work = tmp_path / 'work'
    work.mkdir()
    halt = _hook(tmp_path, 'import sys\nsys.stdin.read()\n'
                 'print(%r)\n' % json.dumps({'continue': False, 'stopReason': 'handoff',
                                             'hookSpecificOutput': {
                                                 'hookEventName': 'PreToolUse',
                                                 'permissionDecision': 'deny'}}))
    steps = [{'emit': {'type': 'assistant', 'text': 'before'}}, _tool('Bash', command='ls'),
             {'emit': {'type': 'assistant', 'text': 'after'}}]
    r, evs = _agent(steps, cwd=work, env={'ARCHEUS_HOOK_CMD': halt})
    # the call before the halt ran (step 0); the blocked call is step 1
    assert _kinds(evs) == ['started', 'assistant', 'halted', 'exit'] and r.returncode == 0
    assert evs[1]['text'] == 'before'
    assert evs[2] == {'type': 'halted', 'at': 1, 'reason': 'handoff'}
    assert evs[0]['at_step'] == 0

    asked = tmp_path / 'asked2.txt'
    allow = _hook(tmp_path, 'import sys, json\nd = json.loads(sys.stdin.read())\n'
                  'open(%r, "a").write(str(d["tool_name"]) + "\\n")\n'
                  'print(%r)\n' % (str(asked), ALLOW), name='allow.py')
    r, evs = _agent(steps, start='1', cwd=work, env={'ARCHEUS_HOOK_CMD': allow})
    assert evs[0]['at_step'] == 1
    assert _kinds(evs) == ['started', 'tool', 'assistant', 'exit']    # step 0 not replayed
    assert asked.read_text().split() == ['Bash']                    # the blocked call asked
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}


def test_FA10_a_halt_after_a_run_call_resumes_after_that_call(tmp_path):
    """fake_agent.py:201-202 (`halt_after` reports `i + 1`). With `continue: false`
    alone the call ran, so the resume must start at the NEXT step; report `i`
    and a resumed execution writes its file twice, report `i + 2` and it loses
    the step after the call."""
    work = tmp_path / 'work'
    work.mkdir()
    cmd = _hook(tmp_path, 'import sys\nsys.stdin.read()\nsys.stdout.write(%r)\n'
                % json.dumps({'continue': False, 'stopReason': 'stop after'}))
    steps = [_tool('Write', file_path='ran.txt', content='x'),
             {'emit': {'type': 'assistant', 'text': 'next'}}]
    r, evs = _agent(steps, cwd=work, env={'ARCHEUS_HOOK_CMD': cmd})
    assert _kinds(evs) == ['started', 'tool', 'halted', 'exit']
    assert evs[2] == {'type': 'halted', 'at': 1, 'reason': 'stop after'}
    assert (work / 'ran.txt').read_text(encoding='utf-8') == 'x'   # the call did run
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}


@pytest.mark.parametrize('given, code', [(3, 3), ('7', 7), (0, 0)], ids=['three', 'string-7', 'zero'])
def test_FA11_an_exit_step_ends_the_run_with_its_code(tmp_path, given, code):
    """fake_agent.py:206-207 and 168-170 (`done`). A crash is a non-zero exit,
    and the last line always says how it ended, for a Core that cannot ask the
    OS. Ignore the step's code, or emit the exit line before the other
    events, and a failed run reads as a clean one."""
    steps = [{'emit': {'type': 'assistant', 'text': 'last'}}, {'exit': given}]
    r, evs = _agent(steps, cwd=tmp_path)
    assert _kinds(evs) == ['started', 'assistant', 'exit']
    assert evs[-1] == {'type': 'exit', 'code': code} and r.returncode == code


def test_FA12_an_unknown_step_fails_loudly_and_ends_the_stream(tmp_path):
    """fake_agent.py:208-209 (the `else: raise SystemExit`). A step that is
    neither emit, sleep nor exit is a typo in a scenario and must not be
    swallowed: the process leaves non-zero, the steps after it never run, and
    the stream ends with no exit line at all, which is what tells a Core that
    the run did not finish. Ignore an unknown step instead and a truncated
    scenario looks like a finished one."""
    steps = [{'emit': {'type': 'assistant', 'text': 'one'}}, {'bogus': 1},
             {'emit': {'type': 'assistant', 'text': 'two'}}]
    r, evs = _agent(steps, cwd=tmp_path)
    assert r.returncode != 0
    assert _kinds(evs) == ['started', 'assistant']        # nothing after the bad step
    assert evs[1]['text'] == 'one'
    assert 'two' not in r.stdout and 'unknown step' in r.stderr


def test_FA13_a_step_that_carries_both_emit_and_exit_emits_first(tmp_path):
    """fake_agent.py:180 against 206 (the order of the elif chain). A malformed
    step holding both keys emits its event and does not exit before it: check
    exit first and the last event of a run is lost, which is exactly the event
    a verifier reads."""
    steps = [{'emit': {'type': 'result', 'summary': 'done'}, 'exit': 5}]
    r, evs = _agent(steps, cwd=tmp_path)
    assert _kinds(evs) == ['started', 'result', 'exit']
    assert evs[1]['summary'] == 'done'
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}


def test_FA14_a_sleep_step_waits_and_the_run_still_ends(tmp_path):
    """fake_agent.py:204-205. A sleep is a step, not an end: drop the branch
    and a scripted wait is the unknown step above, which every scenario that
    holds a process open (how a test stops something) would trip."""
    steps = [{'emit': {'type': 'assistant', 'text': 'one'}}, {'sleep': '0.05'},
             {'emit': {'type': 'assistant', 'text': 'two'}}]
    r, evs = _agent(steps, cwd=tmp_path)
    assert _kinds(evs) == ['started', 'assistant', 'assistant', 'exit']
    assert [e['text'] for e in evs[1:3]] == ['one', 'two']
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}


def test_FA15_an_emit_that_is_not_an_object_bypasses_the_hook_and_the_gate(tmp_path):
    """fake_agent.py:183, 188, 198 and 200 (the `isinstance(ev, dict)` guards).
    Only a JSON object can be a tool call; anything else is passed through
    verbatim, is never offered to the hook and never reaches the availability
    gate or the Write. It must also not stop the run. Drop the guard and a
    scripted string crashes the agent mid-stream, no exit line."""
    work = tmp_path / 'work'
    work.mkdir()
    asked = tmp_path / 'asked.txt'
    cmd = _hook(tmp_path, 'import sys, json\nd = json.loads(sys.stdin.read())\n'
                'open(%r, "a").write(str(d["tool_name"]) + "\\n")\n'
                'print(%r)\n' % (str(asked), ALLOW))
    steps = [{'emit': 'tool'}, {'emit': ['tool']}, {'emit': None}, {'emit': 4},
             {'emit': {'type': 'tool', 'name': 'Read', 'input': {}}}]
    r, evs = _agent(steps, argv=['--tools', 'Read'], cwd=work, env={'ARCHEUS_HOOK_CMD': cmd})
    assert evs[1:5] == ['tool', ['tool'], None, 4]                  # verbatim
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}
    assert _kinds(evs[5:-1]) == ['tool']                          # the real one went by
    assert asked.read_text().split() == ['Read']                    # and only it was asked


# ── the flags, the tool gate and the config ──────────────────────────────────

def test_FA16_a_valued_flag_left_hanging_is_a_switch_and_denies_everything():
    """fake_agent.py:66-71. A spawn whose last argument is `--tools` with no
    value after it holds the flag with no values, so nothing is available: an
    empty allow-list is no tool, never every tool. Read the missing value as
    no flag and the same argv would hand the execution every tool there is."""
    flags = fa.flags_of(['--setting-sources', '', '--tools'])
    assert flags['--tools'] == [] and '--x' not in flags
    assert fa.available(flags, 'Read') is False and fa.available(flags, 'Bash') is False
    # and a repeated valued flag keeps BOTH values, never only the last
    both = fa.flags_of(['--mcp-config', 'a', '--mcp-config', 'b'])
    assert both['--mcp-config'] == ['a', 'b']


def test_FA17_task_and_agent_are_one_tool_under_two_names_in_both_lists():
    """fake_agent.py:76 and 86 (ALIASES on both sides). `--tools Task` allows
    a scripted call named `Agent`, and `--disallowedTools Agent` denies `Task`;
    the alias must be applied to the scripted name AND to the list."""
    assert fa.available({'--tools': ['Task']}, 'Agent') is True
    assert fa.available({'--tools': ['Task']}, 'Task') is True
    assert fa.available({'--tools': ['Agent']}, 'Task') is True
    assert fa.available({'--disallowedTools': ['Agent']}, 'Task') is False
    assert fa.available({'--disallowedTools': ['Task']}, 'Agent') is False
    assert fa.available({}, 'Agent') is True
    assert fa._names(['Read,Task,Agent,']) == ['Read', 'Task', 'Task']


def test_FA18_a_tool_deny_is_exact_of_case_and_never_a_prefix():
    """fake_agent.py:87-90. `fnmatchcase`, so `bash` never denies `Bash` on
    any platform; a server deny `mcp__gh` takes `mcp__gh__x` (the `p + '__'`
    rule), NOT `mcp__ghx__y`, and the exactly-named `mcp__gh`; the empty
    entry denies nothing. A case-insensitive or prefix match here silently
    removes a tool the task was granted."""
    assert fa.available({'--disallowedTools': ['bash']}, 'Bash') is True
    assert fa.available({'--disallowedTools': ['Bash']}, 'Bash') is False
    assert fa.available({'--disallowedTools': ['']}, 'Bash') is True
    assert fa.available({'--disallowedTools': ['mcp__gh']}, 'mcp__gh__x') is False
    assert fa.available({'--disallowedTools': ['mcp__gh']}, 'mcp__ghx__y') is True
    assert fa.available({'--disallowedTools': ['mcp__gh']}, 'mcp__gh') is False  # exactly named
    assert fa.available({'--disallowedTools': ['mcp__*']}, 'mcp__gh__x') is False
    assert fa.available({'--disallowedTools': ['Read*']}, 'ReadWrite') is False
    assert fa.available({'--tools': ['Read']}, 'Bash') is False      # the allow-list wins


def test_FA19_an_mcp_server_is_named_as_the_cli_names_it_and_the_bare_prefix_is_no_server(
        tmp_path):
    """fake_agent.py:81 and 94-95. The loaded server name is normalised the way
    Claude Code normalises it, and the tool is matched by the CLI's name, so a
    scripted call that keeps the raw dot matches nothing and is unavailable; a
    name with one `__` has no server at all and is unavailable under strict
    too. Normalise both sides, or neither, and a server the user never opted
    in to is offered."""
    assert fa._server('mcp__a__b') == 'a' and fa._server('mcp__a__b__c') == 'a'
    assert fa._server('mcp__a') == '' and fa._server('Bash') == ''
    cfg = tmp_path / 'mcp.json'
    cfg.write_text(json.dumps({'mcpServers': {'pv_dot': {}, 'keep': {}, 'pv@at': {}}}),
                   encoding='utf-8', newline='\n')
    assert fa.mcp_servers({'--mcp-config': [str(cfg)]}) == ['pv_dot', 'keep', 'pv@at']
    strict = {'--strict-mcp-config': [], '--mcp-config': [str(cfg)]}
    assert fa.available(strict, 'mcp__pv_dot__t') is True
    assert fa.available(strict, 'mcp__pv_at__t') is True            # pv@at, as the CLI names it
    assert fa.available(strict, 'mcp__pv.dot__t') is False     # the raw name matches nothing
    assert fa.available(strict, 'mcp__pv@at__t') is False      # the same rule, one step earlier
    assert fa.available(strict, 'mcp__gone__t') is False
    assert fa.available(strict, 'mcp__a') is False                   # no server in the name
    assert fa.available({'--mcp-config': [str(cfg)]}, 'mcp__pv_dot__t') is True
    assert fa.available(dict(strict, **{'--disallowedTools': ['mcp__pv_dot']}),
                        'mcp__pv_dot__t') is False


def test_FA19b_an_unreadable_mcp_config_loads_nothing_and_the_run_still_ends(tmp_path):
    """fake_agent.py:104-109. A `--mcp-config` that cannot be opened is
    skipped, so its servers are simply not loaded and their tools are
    unavailable under --strict-mcp-config; the run still reports its started
    line and ends with the exit line. Let the OSError out and the whole
    process dies before `started`, with no exit line for the Core."""
    good = tmp_path / 'good.json'
    good.write_text(json.dumps({'mcpServers': {'keep': {}, 'pv.dot': {}}}), encoding='utf-8',
                    newline='\n')
    steps = [_tool('mcp__keep__ping'), _tool('mcp__gone__ping')]
    r, evs = _agent(steps, argv=['--strict-mcp-config', '--mcp-config', str(tmp_path / 'gone.json'),
                                 '--mcp-config', str(good)], cwd=tmp_path)
    assert r.returncode == 0 and evs[-1] == {'type': 'exit', 'code': 0}
    assert evs[0]['mcp_servers'] == ['keep', 'pv.dot']               # the read one only
    assert _kinds(evs[1:-1]) == ['tool', 'tool_unavailable']


# ── the writes and the prompt ────────────────────────────────────────────────

@pytest.mark.parametrize('spec', [
    pytest.param({'file_path': 'a.txt', 'content': 7}, id='content-not-text'),
    pytest.param({'file_path': 'a.txt', 'content': ['x']}, id='content-a-list'),
    pytest.param({'content': 'x'}, id='no-file-path'),
    pytest.param({'file_path': 5, 'content': 'x'}, id='path-not-text'),
    pytest.param(None, id='no-input-at-all'),
], ids=str)
def test_FA21_an_allowed_write_that_is_not_text_writes_nothing(tmp_path, spec):
    """fake_agent.py:147-149 (and 198-199's `ev.get('input') or {}`). A Write the
    hook allowed whose spec is not text writes nothing and does not stop the
    run: the event is still emitted, so the stream says what was asked while
    the workspace stays exactly as the verifier will judge it. Relax the two
    isinstance tests and open()/write() would raise on the same spec, or the
    content would land stringified as "7" and pass for a real write."""
    work = tmp_path / 'work'
    work.mkdir()
    call = {'type': 'tool', 'name': 'Write'}
    if spec is not None:
        call['input'] = spec
    steps = [{'emit': call}, {'emit': {'type': 'assistant', 'text': 'after'}}]
    r, evs = _agent(steps, argv=['--tools', 'Write'], cwd=work,
                    env={'ARCHEUS_HOOK_CMD': _hook(tmp_path, 'import sys\nsys.stdin.read()'
                                                   '\nprint(%r)\n' % ALLOW)})
    assert r.returncode == 0 and _kinds(evs) == ['started', 'tool', 'assistant', 'exit']
    assert os.listdir(str(work)) == []                               # nothing on disk


def test_FA22_an_allowed_write_lands_in_the_workdir_with_the_bytes_it_said(tmp_path):
    """fake_agent.py:150-153. The file is written under the process cwd, with
    its directories made for it, and its bytes are the content EXACTLY: no
    newline translation, so the same scenario judges the same workspace on
    Linux and on Windows. Drop newline='\\n' and the file the verifier reads
    differs from the content the agent asked for; resolve against anything but
    the cwd and P13 judges the wrong directory."""
    work = tmp_path / 'work'
    (work / 'deep').mkdir(parents=True)
    steps = [_tool('Write', file_path='deep/nested/report.txt', content='a\nb\r\nc\n'),
             _tool('Write', file_path='../outside/up.txt', content='up')]
    r, evs = _agent(steps, argv=['--tools', 'Write'], cwd=work,
                    env={'ARCHEUS_HOOK_CMD': _hook(tmp_path, 'import sys\nsys.stdin.read()'
                                                   '\nprint(%r)\n' % ALLOW)})
    assert r.returncode == 0 and _kinds(evs) == ['started', 'tool', 'tool', 'exit']
    made = work / 'deep' / 'nested' / 'report.txt'
    assert made.parent.is_dir() and made.read_bytes() == b'a\nb\r\nc\n'
    # a relative path is the cwd's, `..` and all: the fake confines nothing the
    # way a real agent's Write does not either, which is why P13 reads the
    # workspace and never the event.
    assert (tmp_path / 'outside' / 'up.txt').read_bytes() == b'up'


def test_FA23_a_prompt_that_is_not_text_is_still_read_whole_and_digested(tmp_path):
    """fake_agent.py:159 and 175. The fake reads its whole stdin as BYTES
    before it says anything, and reports the length and the sha256 of exactly
    what arrived: this is how a test proves the prompt got there intact. Read
    it as text and a non-UTF-8 prompt kills the process before `started`;
    digest something else and every test that trusts the digest trusts a
    number."""
    blob = b'\x00\xff\xfe title\n\xc3\xa9\xe2\x82\xac'      # 15 bytes, 12 characters
    r, evs = _agent([], cwd=tmp_path, stdin_raw=blob)
    assert _kinds(evs) == ['started', 'exit'] and r.returncode == 0
    assert blob.decode('utf-8', 'replace') != blob.decode('latin-1')   # not a text prompt
    assert len(blob) == 15 and len(blob.decode('utf-8', 'replace')) == 12
    assert evs[0]['stdin_bytes'] == 15
    assert evs[0]['stdin_sha256'] == hashlib.sha256(blob).hexdigest()
    assert evs[0]['argv'] == [] and evs[0]['execution_id'] is None


def test_FA24_the_started_line_reports_the_spawn_the_flags_asked_for(tmp_path):
    """fake_agent.py:172-176. The `started` line echoes the pid, the step it
    was told to start at, the execution id from the environment, the flags of
    the spawn and the servers its --mcp-config loads: a harness that cannot
    tell a resumed process from a fresh one, or a strict run from a loaded
    one, cannot tell what it is looking at later."""
    cfg = tmp_path / 'mcp.json'
    cfg.write_text(json.dumps({'mcpServers': {'gh': {}, 'pv@x': {}}}), encoding='utf-8',
                   newline='\n')
    r, evs = _agent([{'exit': 0}], start='4', cwd=tmp_path, stdin_raw=b'prompt\n',
                    env={'ARCHEUS_EXECUTION_ID': EID},
                    argv=['--strict-mcp-config', '--mcp-config', str(cfg), '--tools', 'Read'])
    started = evs[0]
    assert started['at_step'] == 4 and started['execution_id'] == EID
    assert started['stdin_bytes'] == 7 and r.returncode == 0
    assert started['stdin_sha256'] == hashlib.sha256(b'prompt\n').hexdigest()
    assert started['argv'] == ['--strict-mcp-config', '--mcp-config', str(cfg),
                               '--tools', 'Read']
    assert started['mcp_servers'] == ['gh', 'pv@x']           # as the file lists them
    assert isinstance(started['pid'], int) and started['pid'] > 0
