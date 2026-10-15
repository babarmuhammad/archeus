"""The interactive launch argv (p12-design-gate §4, §13.3): moved out of
`main`, which imports the whole TUI at module level, so a caller that only
needs a command line — the V1 session adapters, the GUI — does not pay for a
terminal UI it never shows. `main` re-exports it under the same name, so every
legacy caller and the harness descriptor's `main.build_launch_command` keep
working unchanged.
"""

import os

from . import config as _c
from . import harnesses as _harnesses
from . import store
from .config import get_claude_exe, load_settings


def build_launch_command(path, encoded_name, choice, opts):
    """Pure launch assembly shared by the TUI and GUI paths. Returns
    (args, env, proj_folder): the claude.exe argv, the child environment,
    and the account project folder. args is None when choice == 'terminal'
    (caller opens a plain shell) — and raises RuntimeError if claude.exe
    can't be found."""
    from .sessions import read_extra_paths, load_add_dirs

    # config dir: from the choice line (bat path) else whichever account the
    # rotation policy elects — which is the active one unless it has run out, so
    # with rotation off, or nothing spent, this is the module default it always
    # was. An EXPLICIT cfgdir always wins: picking an account in the launch
    # window is a decision, not a preference to be second-guessed.
    from . import rotate
    cfgdir = opts.get('cfgdir') or rotate.elect()
    proj_folder = store.project_folder(cfgdir, encoded_name) if encoded_name else None

    # Pins the home explicitly — overriding any ambient one archeus itself was
    # launched under — and pops the key that would shadow that home's login.
    # Both are per harness, which is why this is `account_env` and not two
    # lines: `CLAUDE_CONFIG_DIR` means nothing to Codex, and clearing
    # `ANTHROPIC_API_KEY` for it would be clearing the wrong one.
    from .config import account_env
    env = account_env(cfgdir)
    # OpenTelemetry export, if configured. archeus already owns the launch
    # environment, so this is the natural place for it — and it is the step from
    # a personal tool to one a team can point at a shared backend.
    from .config import otel_env
    # one read, two consumers: otel_env() would otherwise load it again, and the
    # fallback/autocompact flags below need the same dict
    settings = load_settings()
    env.update(otel_env(settings))
    extra = read_extra_paths(proj_folder)
    if extra:
        env['PATH'] = ';'.join(extra) + ';' + env.get('PATH', '')

    if choice == 'terminal':
        return None, env, proj_folder

    # ── which CLI is being launched ───────────────────────────
    # Everything ABOVE this line is archeus's: the project folder, the extra
    # PATH, the telemetry, the home. Everything BELOW it is Claude Code's flag
    # vocabulary, down to the last one — so a second harness gets its own short
    # builder rather than a branch per flag through a hundred and forty lines.
    #
    # The project's extra directories are archeus's too, and they were on the
    # wrong side of it: `load_add_dirs` ran a hundred lines below this return,
    # so `codex.launch_argv` read an `add_dirs` nothing ever set. A project's
    # extra dirs applied under Claude Code and vanished under Codex, silently.
    # The same argument covers the per-project system prompt, which pi takes as
    # `--append-system-prompt`.
    opts = dict(opts)
    opts.setdefault('add_dirs',
                    [x for x in load_add_dirs(proj_folder) if os.path.isdir(x)])
    _sp = os.path.join(proj_folder, 'system-prompt.txt') if proj_folder else ''
    if _sp and os.path.exists(_sp):
        opts.setdefault('system_prompt_file', _sp)
    d = _harnesses.of(cfgdir)
    if d['id'] != _harnesses.DEFAULT:
        exe = _harnesses.exe(d['id'])
        if not exe:
            raise RuntimeError('%s not found' % d['label'])
        # Quick resume (GUI and TUI) sends Claude Code's DEFAULT model and
        # effort. This CLI cannot resolve a bare Claude id — pi answers `Model
        # "claude-opus-5" is ambiguous across providers` and exits, which is
        # what "resuming a pi session does nothing" was — and `max`/`ultracode`
        # are not Codex levels. `provider/id` stays: that is pi's own form.
        from .sessions import _is_anthropic_model
        m = opts.get('model') or ''
        if '/' not in m and _is_anthropic_model(m):
            opts['model'] = ''
        if opts.get('effort') not in d['efforts']:
            opts['effort'] = ''
        argv = _harnesses.impl('launch_argv', d['id'])(exe, choice, opts, path)
        return argv, env, proj_folder

    env['CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'] = '1'
    # launch-economy env: cap thinking tokens / route subagents to a cheap model
    if opts.get('max_thinking'):
        env['MAX_THINKING_TOKENS'] = str(opts['max_thinking'])
    if opts.get('subagent_model'):
        env['CLAUDE_CODE_SUBAGENT_MODEL'] = opts['subagent_model']

    claude = get_claude_exe()
    if not claude:
        raise RuntimeError('claude.exe not found')

    args = [claude]
    if choice == 'continue':
        args += ['-c']
    elif choice.startswith('resume:'):
        args += ['-r', choice[7:]]
    elif choice.startswith('resume-named::'):
        args += ['-r', choice[14:].split('::', 1)[0]]
    elif choice.startswith('fork:'):
        args += ['-r', choice[5:], '--fork-session']
    # 'new' → no extra args

    if opts['effort']:
        args += ['--effort', opts['effort']]
    # Routed session: merge this PROFILE's env overrides + use the picked model.
    # The profile is resolved from the id the picker chose, never from whatever
    # is globally active — two sessions may be running on two backends.
    prof = _c.provider_profile(opts.get('provider', ''), settings)
    provider_model = (opts.get('provider_model') or
                      (prof or {}).get('model') or '') if prof else ''
    if prof:
        from .omniroute import prepare_launch
        pv_env, _warn = prepare_launch(provider_model, prof)
        env.update(pv_env)
    # ONE --model flag. The provider's model wins when there is one: it names a
    # model that backend serves, while opts['model'] is an Anthropic id the
    # backend cannot resolve. Both used to be emitted and the right one won only
    # because Claude Code's parser takes the later occurrence.
    launch_model = provider_model or opts['model']
    if launch_model:
        args += ['--model', launch_model]
    # Which backend a session ran on is RECORDED, not inferred. _used_provider
    # reads it back off the transcript's model ids, which cannot tell an
    # Anthropic model served THROUGH a provider from a direct run — sessions.py
    # says so itself. We know the answer here.
    #
    # A new session's id is ours to choose (`--session-id`), which is the only
    # way to have one before Claude Code has written a line; a resume keeps the
    # id it is resuming. A fork mints its own and `-c` picks one we have not
    # seen, so those two keep falling back to the inference.
    launched_sid = ''
    if choice == 'new':
        import uuid
        launched_sid = str(uuid.uuid4())
        args += ['--session-id', launched_sid]
    elif choice.startswith('resume:'):
        launched_sid = choice[7:]
    elif choice.startswith('resume-named::'):
        launched_sid = choice[14:].split('::', 1)[0]
    if launched_sid and proj_folder:
        from .sessions import save_session_provider
        save_session_provider(proj_folder, launched_sid,
                              prof['id'] if prof else '')
    # `auto` is dropped where the classifier cannot run — with a provider in
    # play the model is whatever that backend served, and the classifier is a
    # SEPARATE request that would go to the same base URL. The model check reads
    # the provider model when there is one, because that is the model the
    # session will actually be on.
    from .config import effective_perm
    perm = effective_perm(opts['perm'], provider_model or opts['model'],
                          provider_model)
    if perm:
        args += ['--permission-mode', perm]
    # Model fallback chain for an overloaded primary. Unrelated to failover.py,
    # which retries a DIFFERENT free-tier model through archeus's own proxy;
    # this is Claude Code's own retry against the Anthropic API.
    fbs = [m for m in (settings.get('launch_fallback_models') or []) if m]
    if fbs:
        args += ['--fallback-model', ','.join(fbs)]
    if settings.get('launch_autocompact'):
        args += ['--autocompact', settings['launch_autocompact']]
    if opts.get('agent'):
        args += ['--agent', opts['agent']]
    # Selected library agents are NOT passed inline (--agents JSON overruns the
    # Windows command line). They're copied into <project>/.claude/agents/ by
    # sync_project_agents at selection time, where Claude auto-discovers them.
    if choice == 'new':
        if opts['name']:
            args += ['-n', opts['name']]
        if opts['worktree'] == '*':
            args += ['-w']
        elif opts['worktree']:
            args += ['-w', opts['worktree']]
    # both resolved above the harness dispatch, so every CLI gets them
    if opts.get('system_prompt_file'):
        args += ['--system-prompt-file', opts['system_prompt_file']]
    if opts.get('add_dirs'):
        args += ['--add-dir', *opts['add_dirs']]
    # An opening message for an INTERACTIVE session — `claude "<text>"` submits
    # it as the first turn and leaves you in the session. It is last because it
    # is the CLI's positional argument, and it is the whole mechanism behind
    # starting a `/loop` from archeus: a loop is session-scoped, so there is
    # nothing to start except a session that begins by typing it.
    if opts.get('prompt'):
        args += [str(opts['prompt'])]
    return args, env, proj_folder
