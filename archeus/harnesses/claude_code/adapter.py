"""The Claude Code execution adapter (execution-architecture §3; p11-design-gate §9.2).

    claude -p --output-format stream-json --verbose --session-id <uuid>
           [--model m] [--effort e] --max-turns N --settings <exec dir>/res/settings.json
           --setting-sources <opted in> --strict-mcp-config [--mcp-config <exec dir>/res/mcp.json]
           [--disable-slash-commands] [--plugin-dir <dir>]...
           --tools <mapped tools> [--disallowedTools <mcp patterns>]
           [--resume <session uuid>]                    (prompt on stdin)

The settings file installs the Archeus hook (harnesses/hook.py) for this
execution only — as its PreToolUse command, and (P12) as its PreCompact command,
the context-pressure backstop — and never touches the user's settings.json
(ADR-0019). What the account's, the project's and the local settings sources
would load besides is excluded unless opted in, and recorded (ADR-0049, P20 D6:
harnesses/sources.py); the flags are read from the recorded inventory. The
tools the process may call at all are the task's action classes mapped to
Claude Code's names (ADR-0052, P20 slice F: tools.py), beneath the hook. The
account is its home: `CLAUDE_CONFIG_DIR` from the account's `home_ref`, with any API key popped so it cannot shadow the login (the current
product's `config.account_env` rule). An isolated execution never gets the home:
its `CLAUDE_CONFIG_DIR` is its own `ExecPaths.config` (ADR-0053 A2), which
base.spawn creates for the first process and keeps for a resume. Nothing else of
the inherited environment is relocated here, and no login is put there (that is
R3-B's broker). The process I/O contract is the shared one
(base.spawn): the stream is stream-json on stdout, tailed from a file.

Normalisation (`normalise`) maps stream-json lines to the vocabulary Core
reads: assistant, tool, tool_result, usage, result, limit, error, stderr. A
limit is recognised by the current product's `quota.is_limit_error`.
"""

import os
import shutil
import uuid
from dataclasses import replace

from claude_sessions import config, proc, quota

from .. import base, sources
from ..calls import claude_models
from . import tools

#: turns per task size (p11-design-gate §18): a bounded agent
MAX_TURNS = {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}
_ERR = {'error_during_execution': 'resource', 'error_max_turns': 'task'}
#: Claude Code's own limit on the hook (seconds). The hook answers `halt` at
#: its own deadline (ARCHEUS_HOOK_WAIT, 60 s) well before this one, because a
#: hook Claude Code times out is not documented to block the call
HOOK_TIMEOUT_S = 120


def normalise(raw):
    """One stream-json object -> the normalised events it carries."""
    t = raw.get('type')
    if t == 'stderr':
        return [raw]
    out = []
    # a subagent's turn names the tool call that spawned it: its sidechain lane
    # (p21-design-gate D14); the main conversation has none
    lane = raw.get('parent_tool_use_id')
    if t == 'assistant':
        msg = raw.get('message') or {}
        for block in msg.get('content') or ():
            if block.get('type') == 'text':
                out.append({'type': 'assistant', 'text': block.get('text', ''), 'lane': lane})
            elif block.get('type') == 'tool_use':
                out.append({'type': 'tool', 'name': block.get('name'),
                            'input': block.get('input'), 'id': block.get('id'), 'lane': lane})
        if isinstance(msg.get('usage'), dict):
            out.append({'type': 'usage', 'usage': msg['usage']})
        if isinstance(msg.get('model'), str) and msg['model'] not in ('', '<synthetic>'):
            # the model that answered, as the transcript reports it (SERVED, ADR-0031 §6)
            out.append({'type': 'model', 'model': msg['model']})
    elif t == 'user':
        for block in (raw.get('message') or {}).get('content') or ():
            if isinstance(block, dict) and block.get('type') == 'tool_result':
                out.append({'type': 'tool_result', 'is_error': bool(block.get('is_error')),
                            'tool_use_id': block.get('tool_use_id'), 'lane': lane})
    elif t == 'result':
        text = str(raw.get('result') or '')
        usage = dict(raw.get('usage') or {})
        if raw.get('total_cost_usd') is not None:
            usage['total_cost_usd'] = raw['total_cost_usd']
        if raw.get('is_error') and quota.is_limit_error(text):
            out.append({'type': 'limit', 'window': quota.is_window_limit(text), 'text': text})
        billed = raw.get('modelUsage')
        out.append({'type': 'result', 'summary': text[:2000], 'is_error': bool(raw.get('is_error')),
                    'subtype': raw.get('subtype'), 'session_id': raw.get('session_id'),
                    'usage': usage,
                    # the models the usage is attributed to (BILLED, ADR-0031 §6)
                    'billed': sorted(billed) if isinstance(billed, dict) else []})
    elif t == 'system':
        out.append({'type': 'system', 'subtype': raw.get('subtype'),
                    'session_id': raw.get('session_id')})
    return out


class ClaudeCodeAdapter:
    id = 'claude_code'

    def __init__(self, exe=None):
        self._exe = exe
        self._children = {}
        self._stopped = set()

    def _find(self):
        return self._exe or shutil.which('claude')

    def discover(self):
        exe = self._find()
        return base.HarnessInfo(self.id, bool(exe), None, exe)

    def capabilities(self, account=None):
        return base.Capabilities(
            frozenset({'code_edit', 'shell', 'web', 'headless', 'interactive', 'resume',
                       'structured_output'}), 'hook', claude_models(),
            structured_output='native', efforts=('low', 'medium', 'high'),
            usage_measures=frozenset({'tokens'}))

    def default_account(self):
        """The active Claude config dir, fixed (ADR-0048 D-25.1), with its home,
        so a task's process runs on it rather than on whatever Core inherited."""
        from claude_sessions import config
        return base.default_ref(self.id, config.resolve_config_dir(None))

    def authenticate(self, account):
        from claude_sessions import usage
        ok = bool(usage._creds(account.home_ref))
        return base.AuthStatus(ok, '' if ok else 'no Claude login in %s' % account.home_ref)

    def _settings(self, spec):
        # Core-authored spawn configuration: class 2, readable by the execution and
        # never writable by it (PV-20 §7.5, A2)
        path = os.path.join(base.ExecPaths(spec.execution_id).res, 'settings.json')
        hooks = {}
        if spec.hook_settings:
            cmd = ' '.join('"%s"' % a for a in spec.hook_settings)
            hooks = {'PreToolUse': [{'matcher': '*', 'hooks': [
                {'type': 'command', 'command': cmd, 'timeout': HOOK_TIMEOUT_S}]}],
                     'PreCompact': [{'hooks': [
                         {'type': 'command', 'command': cmd, 'timeout': 30}]}]}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        config.write_json_atomic(path, {'hooks': hooks}, indent=None)
        return path

    def argv(self, spec, session):
        a = [self._find(), '-p', '--output-format', 'stream-json', '--verbose',
             '--max-turns', str(MAX_TURNS.get(int(spec.task_contract.get('estimate', 3)), 60)),
             '--settings', self._settings(spec)]
        a += sources.flag_argv((spec.inventory or {}).get('flags') or sources.DEFAULT_FLAGS,
                               home=self._home(spec),
                               workdir=spec.workdir,
                               exec_dir=base.ExecPaths(spec.execution_id).res)
        a += tools.tool_argv(spec.task_contract.get('action_classes') or (), spec.inventory)
        a += ['--resume', session] if spec.resume_ref else ['--session-id', session]
        if spec.model:
            a += ['--model', spec.model]
        if spec.effort:
            a += ['--effort', spec.effort]
        return a

    def inventory(self, spec, *, isolated=False):
        """What this execution's settings sources load and what becomes of it
        (ADR-0049): taken before the spawn, recorded by Core, read by argv."""
        return sources.take(self._home(spec), spec.workdir, spec.opt_ins, isolated=isolated)

    @staticmethod
    def _home(spec):
        home = spec.account.home_ref if spec.account else None
        return os.path.expanduser(home) if home else None

    def _env(self, spec):
        env = dict(spec.env)
        home = spec.account.home_ref if spec.account else None
        if spec.isolation is not None:
            env['CLAUDE_CONFIG_DIR'] = base.ExecPaths(spec.execution_id).config
        elif home:
            env['CLAUDE_CONFIG_DIR'] = os.path.expanduser(home)
        for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
            env.setdefault(k, None)
        return env

    def start(self, spec):
        from claude_sessions.sessions import HEADLESS_MARK
        session = spec.resume_ref or str(uuid.uuid4())
        spec = replace(spec, env=self._env(spec), prompt=spec.prompt + '\n\n' + HEADLESS_MARK)
        handle, child = base.spawn(spec, self.argv(spec, session))
        self._children[spec.execution_id] = child
        self._stopped.discard(spec.execution_id)
        return handle

    def resume(self, spec, state):
        session = (state or {}).get('session')
        if not session:
            raise base.SpawnFailed('no Claude session to resume')
        return self.start(replace(spec, resume_ref=session,
                                  prompt='Continue the task from where you stopped.'))

    def send(self, handle, message):
        raise NotImplementedError('a headless execution reads its prompt from stdin')

    def pause(self, handle):
        return base.PauseResult(halted=False)       # the PAUSE flag, at the next tool call

    def status(self, handle):
        child = self._children.get(handle.execution_id)
        if child is not None and child.pid == handle.pid:
            code = child.poll()
            return base.ProcStatus('running' if code is None else 'exited', code)
        if handle.create_time is not None and \
                proc.process_create_time(handle.pid) == handle.create_time:
            return base.ProcStatus('running')
        ended = base.read_json(os.path.join(handle.exec_dir, 'ended')) or {}
        code = ended.get('exit_code')
        if code is None:
            res = [e for e in self.inspect(handle).events if e.get('type') == 'result']
            if res:
                code = 1 if res[-1].get('is_error') else 0
        return base.ProcStatus('exited', code)

    def inspect(self, handle, offset=0):
        raw, offset = base.read_stream(os.path.join(handle.exec_dir, 'stream.jsonl'), offset)
        return base.Snapshot(tuple(ev for r in raw for ev in normalise(r)), offset)

    def stop(self, handle, *, grace_s=0.0):
        if not proc.kill_pid_tree(handle.pid, handle.create_time):
            if proc.process_create_time(handle.pid) is not None:
                raise base.StopRefused('pid %d is not the process this execution started'
                                       % handle.pid)
            return
        self._stopped.add(handle.execution_id)

    def collect_result(self, handle):
        st = self.status(handle)
        events = self.inspect(handle).events
        results = [e for e in events if e.get('type') == 'result']
        last = results[-1] if results else {}
        session = last.get('session_id') or next(
            (e.get('session_id') for e in events if e.get('session_id')), None)
        failure = None
        if any(e.get('type') == 'limit' for e in events):
            failure = 'limit'
        elif last.get('is_error'):
            failure = _ERR.get(last.get('subtype'), 'task')
        halted = os.path.exists(base.halted_path(handle.exec_dir))
        reason = 'killed' if handle.execution_id in self._stopped else (
            'ok' if st.exit_code == 0 and not last.get('is_error') else 'error')
        return base.ExecutionResult(
            exit_reason=reason, exit_code=st.exit_code, reported_summary=last.get('summary', ''),
            usage=last.get('usage') or {}, usage_total=bool(results), session_ref=session,
            transcript_path=os.path.join(handle.exec_dir, 'stream.jsonl'), failure=failure,
            halted=halted, adapter_state={'session': session} if session else None)

