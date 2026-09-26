"""The real adapters' `call()` — Archeus's own tool-less calls (ADR-0022).

Two harnesses declare `headless` today, as on main (94b90f9): Claude Code and
pi. Each keeps the call read-only and ephemeral in its own flags and asks for
structured output its own way; both run on the shared P0.5 runner
(`llmcall.run_headless`). Codex declares no `headless`: `codex exec` logs
progress on stderr, which the runner merges into the answer.

Nothing here decides whether a call may happen. The provider-terms gate
(ADR-0021) and the election are Core's (archeus/core/calls.py), and a real
adapter never enters the P1 AdapterRegistry, whose gate refuses real
tool-using execution (`start()`) until P9. These adapters have no `start()`.
"""

import json
import re

from claude_sessions import config, llmcall

from . import base

_MODEL_REFUSED = re.compile(r'model', re.I)
_MODEL_WHY = re.compile(r'not found|does not exist|invalid|ambiguous|unknown|not available', re.I)


def _usage(envelope):
    u = envelope.get('usage') if isinstance(envelope, dict) else None
    if not isinstance(u, dict):
        return {}
    n = lambda k: u.get(k) if isinstance(u.get(k), int) else 0  # noqa: E731
    return {'tokens_in': n('input_tokens'), 'tokens_out': n('output_tokens'),
            'cache_read': n('cache_read_input_tokens'),
            'cache_write': n('cache_creation_input_tokens')}


def _failed(r):
    """A CallResult for a run that did not succeed."""
    if r.timed_out:
        return base.CallResult(error='timeout', detail=r.error)
    if r.returncode is None:
        return base.CallResult(error='unavailable', detail=r.error)
    why = r.reason or r.error
    if _MODEL_REFUSED.search(why or '') and _MODEL_WHY.search(why or ''):
        return base.CallResult(error='model_unavailable', detail=why)
    return base.CallResult(error='failed', detail=why)


class ClaudeCodeCaller:
    """`claude -p` with the write tools disallowed, `--max-turns`, the budget
    cap and, for a schema, `--output-format json --json-schema` (native). The
    prompt leaves with HEADLESS_MARK, so the transcript Claude Code writes is
    never listed back to the user as a session they had."""
    id = 'claude_code'

    def discover(self):
        exe = config.get_claude_exe()
        return base.HarnessInfo(self.id, bool(exe), None, exe)

    def capabilities(self, account=None):
        return base.Capabilities(
            frozenset({'headless', 'structured_output', 'interactive', 'resume', 'code_edit',
                       'shell'}), 'hook', claude_models(), structured_output='native')

    def authenticate(self, account):
        """Cheap, no inference: the home holds a Claude login."""
        from claude_sessions import usage
        ok = bool(usage._creds(account.home_ref))
        return base.AuthStatus(ok, '' if ok else 'no Claude login in %s' % account.home_ref)

    def account(self, *, rotation):
        """(AccountRef, why-not): legacy `rotate.elect()` when rotation across
        subscriptions is permitted (ADR-0021), else the active account; and
        `quota.reason()`, non-empty when that account cannot be spent."""
        from claude_sessions import quota, rotate
        cfg = rotate.elect() if rotation else config.resolve_config_dir(None)
        return base.AccountRef('claude_code:%s' % cfg, cfg), quota.reason(cfg)

    def call(self, spec):
        exe = self.discover().executable
        if not exe:
            return base.CallResult(error='unavailable', detail='Claude Code is not installed')
        extra = () if spec.schema is None else (
            '--output-format', 'json', '--json-schema', json.dumps(spec.schema, sort_keys=True))
        args, stdin = llmcall.build_headless_args(exe, spec.prompt, spec.model or '',
                                                  llmcall.budget_args(), extra)
        r = llmcall.run_headless(args, stdin, cwd=spec.workdir,
                                 env=config.account_env(spec.account.home_ref),
                                 timeout=spec.limits.get('timeout_s', 600))
        if r.returncode != 0:
            return _failed(r)
        try:
            envelope = json.loads(r.stdout)
        except ValueError:
            envelope = None
        parsed = llmcall.unwrap_structured(r.stdout)[0] if spec.schema is not None else None
        usage = _usage(envelope)
        cost = envelope.get('total_cost_usd') if isinstance(envelope, dict) else None
        if isinstance(cost, (int, float)) and not isinstance(cost, bool):
            usage['cost_usd'] = float(cost)
        return base.CallResult(text=r.stdout, parsed=parsed, usage=usage)


class PiCaller:
    """`pi -p --no-session --tools read,grep,find,ls [--model provider/id]`,
    the schema in the prompt (pi has no schema flag), on pi's own home. A model
    is pi's vocabulary or nothing: Core never hands it Claude Code's."""
    id = 'pi'

    def discover(self):
        from claude_sessions import harnesses
        exe = None if 'pi' in harnesses.disabled() else harnesses.exe('pi')
        return base.HarnessInfo(self.id, bool(exe), None, exe)

    def capabilities(self, account=None):
        return base.Capabilities(frozenset({'headless', 'structured_output', 'interactive'}),
                                 'none', pi_models(), structured_output='prompted')

    def authenticate(self, account):
        import os
        ok = bool(account.home_ref) and os.path.isdir(account.home_ref)
        return base.AuthStatus(ok, '' if ok else 'no pi home at %s' % account.home_ref)

    def account(self, *, rotation):
        from claude_sessions import harnesses
        home = harnesses.home_dir('pi')
        return base.AccountRef('pi:%s' % home, home), ''

    def call(self, spec):
        exe = self.discover().executable
        if not exe:
            return base.CallResult(error='unavailable', detail='pi is not installed')
        prompt = spec.prompt if spec.schema is None else base.prompted(spec.prompt, spec.schema)
        args, stdin = llmcall.build_headless_args(exe, prompt, spec.model or '', harness='pi')
        r = llmcall.run_headless(args, stdin, cwd=spec.workdir,
                                 env=config.account_env(spec.account.home_ref),
                                 timeout=spec.limits.get('timeout_s', 600))
        if r.returncode != 0:
            return _failed(r)
        return base.CallResult(text=r.stdout,
                               parsed=llmcall.parse_json(r.stdout) if spec.schema else None)


#: Claude model families by tier (resource-router §5 tier fit: plan authoring
#: and review large, well-specified implementation mid, mechanical small)
CLAUDE_TIERS = {'haiku': 'small', 'sonnet': 'mid', 'opus': 'large', 'fable': 'large'}


def claude_models():
    """Claude Code's offers, in its own vocabulary: the family aliases it
    accepts as `--model`, and the newest id of each family from the cached
    catalogue (a disk read, `models.roster`)."""
    from claude_sessions import models
    out = [base.ModelInfo(f, t) for f, t in CLAUDE_TIERS.items()]
    for r in models.roster():
        t = CLAUDE_TIERS.get(r.get('family'))
        if t is not None and r.get('id'):
            out.append(base.ModelInfo(models.alias(r['id']), t))
    return tuple(out)


def pi_models():
    """pi's offers, in its own vocabulary (`provider/id`): what this install
    has run and declared, and its catalogue with each context window. pi
    states no tier, so every one is unknown — the smallest (ADR-0022)."""
    from claude_sessions import harnesses, pi
    try:
        ctx = {c['id']: c.get('context') for c in pi.catalogue() if c.get('id')}
        ids_ = list(dict.fromkeys(list(pi.models(harnesses.home_dir('pi'))) + list(ctx)))
    except Exception:          # an unreadable pi state offers nothing, never crashes routing
        return ()
    return tuple(base.ModelInfo(m, None, ctx.get(m) if isinstance(ctx.get(m), int) else None)
                 for m in ids_)


def real_callers():
    """The adapters a Core offers for own calls when its ports name none."""
    return [ClaudeCodeCaller(), PiCaller()]
