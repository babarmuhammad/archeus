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
    """The figures the envelope reports; an absent one is absent, never 0
    (ADR-0048 D-25.3)."""
    u = envelope.get('usage') if isinstance(envelope, dict) else None
    if not isinstance(u, dict):
        return {}
    names = {'input_tokens': 'tokens_in', 'output_tokens': 'tokens_out',
             'cache_read_input_tokens': 'cache_read',
             'cache_creation_input_tokens': 'cache_write'}
    return {ours: u[theirs] for theirs, ours in names.items()
            if isinstance(u.get(theirs), int) and not isinstance(u.get(theirs), bool)}


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
        # a cost figure is reported, but what it means differs by auth kind, so
        # no cost is declared and a cost budget is refused (ADR-0048 §3)
        return base.Capabilities(
            frozenset({'headless', 'structured_output', 'interactive', 'resume', 'code_edit',
                       'shell', 'no_tools'}), 'hook', claude_models(), structured_output='native',
            usage_measures=frozenset({'tokens'}))

    def authenticate(self, account):
        """Cheap, no inference: the home holds a Claude login."""
        from claude_sessions import usage
        ok = bool(usage._creds(account.home_ref))
        return base.AuthStatus(ok, '' if ok else 'no Claude login in %s' % account.home_ref)

    def default_account(self):
        """The active Claude config dir, fixed: no election here, because choosing
        among accounts is the router's, over registered ones (ADR-0048 D-25.1)."""
        return base.default_ref(self.id, config.resolve_config_dir(None))

    def why_not(self, account):
        """`quota.reason()`: non-empty when that account cannot be spent."""
        from claude_sessions import quota
        return quota.reason(account.home_ref)

    def call(self, spec):
        exe = self.discover().executable
        if not exe:
            return base.CallResult(error='unavailable', detail='Claude Code is not installed')
        extra = () if spec.schema is None else (
            '--output-format', 'json', '--json-schema', json.dumps(spec.schema, sort_keys=True))
        if spec.no_tools:
            # empty, never left out: no `--tools` at all means every tool
            # (claude_code/tools.py relies on the same form)
            extra = ('--tools', '') + extra
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
        models, note = pi_offers(account)
        # no `no_tools`: no pi form meaning NO tools is verified (call() refuses one)
        return base.Capabilities(frozenset({'headless', 'structured_output', 'interactive'}),
                                 'none', models, structured_output='prompted',
                                 models_note=note)

    def authenticate(self, account):
        import os
        ok = bool(account.home_ref) and os.path.isdir(account.home_ref)
        return base.AuthStatus(ok, '' if ok else 'no pi home at %s' % account.home_ref)

    def default_account(self):
        from claude_sessions import harnesses
        return base.default_ref(self.id, harnesses.home_dir('pi'))

    def why_not(self, account):
        return ''

    def call(self, spec):
        exe = self.discover().executable
        if not exe:
            return base.CallResult(error='unavailable', detail='pi is not installed')
        if spec.no_tools:
            # pi is known here only as `--tools read,grep,find,ls`; no form that
            # means NO tools has been verified, so refuse rather than run with those
            return base.CallResult(error='failed', detail='pi cannot be asked to run with no '
                                   'tools; this call needs a harness that can')
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


def pi_models(home=None):
    """pi's offers for ONE pi home, in its own vocabulary (`provider/id`): the
    models pi itself lists as runnable there (`pi.configured`), never the
    catalogue it ships (C-22; domain-model §8.3: an offer is an account's).
    pi states no tier, so every one is unknown — the smallest (ADR-0022)."""
    return pi_offers(base.AccountRef('pi', home) if home else None)[0]


def pi_offers(account=None):
    """(offers, note) for *account*'s pi home, or the default home without one.
    A failed discovery is ((), why): nothing is offered and nothing is guessed."""
    from claude_sessions import pi
    try:
        got = pi.configured(account.home_ref if account is not None else None)
    except Exception as e:     # an unreadable pi state offers nothing, never crashes routing
        return (), 'pi model discovery failed: %s: %s' % (type(e).__name__, e)
    if not got['ok']:
        return (), got['why']
    offers = tuple(base.ModelInfo(m['id'], None, m['context']) for m in got['models'])
    return offers, None if offers else 'pi lists no model this home can run'


def real_callers():
    """The adapters a Core offers for own calls when its ports name none."""
    return [ClaudeCodeCaller(), PiCaller()]
