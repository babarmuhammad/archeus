"""P6, the pure half (p6-design-gate §12, L01–L16): the pre-router election and
the provider-terms gate as a function, vocabulary rules, the generated
explanation, knowledge identity, Core's validation of an answer, the legacy
seams, the real adapters' argv against a stand-in runner, and the import
boundaries. No database, no real CLI."""

import json
import os
import subprocess
import sys

import pytest

from archeus.core import calls as K
from archeus.core import ports
from archeus.core.application import knowledge as AK
from archeus.core.application import resources
from archeus.core.routing import router
from archeus.core.domain import entities, shapes
from archeus.core.knowledge import passes
from archeus.harnesses import base
from archeus.harnesses import calls as real
from archeus.harnesses.fake import FakeCaller, is_fake_caller

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
NONE = ports.OwnCallPreference()


class Real(FakeCaller):
    """Gated like a real adapter (not FakeCaller itself)."""


def terms(**states):
    return {h: {'headless': v, 'rotation': 'unknown'} for h, v in states.items()}


def picked(callers, terms_=None, pref=NONE):
    """P10: the router over the own-call snapshot (the pre-router election is
    gone). Returns (harness or None, {resource: step}, gated)."""
    hs = [resources.harness_view(a, is_fake_caller(a)) for a in sorted(callers,
                                                                      key=lambda a: a.id)]
    accts = [{'id': None, 'ref': 'fake:%s' % h['id'], 'harness': h['id'], 'label': h['id'],
              'registered': False, 'why_not': None, 'policy': None, 'usage': None}
             for h in hs if h['installed'] and 'headless' in h['capabilities']]
    req = {'subject': 'archeus_call', 'capabilities': ['headless'], 'structured_output': True,
           'models': {}, 'preferred': {'harnesses': [pref.harness] if pref.harness else []}}
    d = router.route(req, {'harnesses': hs, 'accounts': accts, 'terms': terms_ or {}})
    gated = d['result'] == 'blocked' and any(c['eliminated_at_step'] == 'provider_terms'
                                             for c in d['candidates'])
    return d['harness_id'] if d['selected'] else None, {
        c['resource']: c['eliminated_at_step'] for c in d['candidates']}, gated


# ── L01–L05 routing an own call (P6's election, now the router's, P10) ──

def test_l01_only_installed_headless_harnesses_are_eligible():
    got = picked([FakeCaller('b'), FakeCaller('a', installed=False),
                  FakeCaller('c', headless=False)])
    assert got == ('b', {'a': 'installed', 'b': None, 'c': 'headless'}, False)


def test_l02_your_choice_then_the_first_by_id_and_no_harness_by_name():
    """P10: the pre-router's "else Claude Code" rule is gone — the router has no
    rule naming a harness (ADR-0022: it replaced the pre-router election)."""
    fakes = [FakeCaller('zeta'), FakeCaller('claude_code'), FakeCaller('alpha')]
    assert picked(fakes, pref=ports.OwnCallPreference(harness='zeta'))[0] == 'zeta'
    assert picked(fakes)[0] == 'alpha'
    assert picked(fakes, pref=ports.OwnCallPreference(harness='missing'))[0] == 'alpha'
    assert picked(fakes)[1] == {'alpha': None, 'claude_code': 'election', 'zeta': 'election'}


def test_l03_a_real_adapter_needs_permitted_terms_and_a_fake_never_does():
    """ADR-0021. Mutation: dropping the scripted exemption fails the fake row;
    dropping the terms check fails the real rows."""
    assert picked([Real('pi')]) == (None, {'pi': 'provider_terms'}, True)
    assert picked([Real('pi')], terms(pi='refused'))[1] == {'pi': 'provider_terms'}
    assert picked([Real('pi')], terms(pi='permitted'))[0] == 'pi'
    assert picked([FakeCaller('pi')])[0] == 'pi'
    # gated only when the terms are what stopped it
    assert picked([Real('pi', headless=False)])[2] is False


def test_l04_the_fake_exemption_is_class_identity():
    assert is_fake_caller(FakeCaller('x'))
    assert not is_fake_caller(Real('x')) and not is_fake_caller(real.PiCaller())

    class Impostor:
        id = 'fake'
    assert not is_fake_caller(Impostor())


def test_l05_a_model_is_the_chosen_harness_vocabulary_or_nothing():
    p = ports.OwnCallPreference(harness='pi', model='spark/qwen3.8', claude_model='haiku-x')
    assert p.model_for('pi') == 'spark/qwen3.8'
    assert p.model_for('codex') is None                     # set for pi: dropped, not moved
    assert p.model_for('claude_code') == 'haiku-x'
    assert ports.OwnCallPreference(model='m').model_for('anything') == 'm'


def test_l06_the_legacy_setting_is_read_and_mapped(monkeypatch):
    from claude_sessions import config
    monkeypatch.setattr(config, 'load_settings', lambda: {
        'headless_harness': 'claude', 'headless_harness_model': ' ', 'extract_model': 'h'})
    got = ports.LegacyOwnCallPreference().get()
    assert (got.harness, got.model, got.claude_model) == ('claude_code', None, 'h')


def test_l07_the_explanation_is_generated_from_the_record():
    hs = [resources.harness_view(a, True) for a in (FakeCaller('a', headless=False),
                                                     FakeCaller('b'))]
    req = {'subject': 'archeus_call', 'capabilities': ['headless'], 'models': {}}
    d = router.route(req, {'harnesses': hs, 'accounts': [
        {'id': None, 'ref': 'fake:b', 'harness': 'b', 'label': 'b', 'registered': False}]})
    assert router.explain(d, req) == (
        "I used b (b, its default model) because it is b's own account. Not used: a — does "
        "not declare headless (it cannot make a tool-less call).")
    assert router.explain(router.route(req, {'harnesses': []}), req).startswith(
        'Nothing could run this')


# ── L08–L10 knowledge identity and Core's checks ──

def test_l08_the_same_claim_is_equality_of_the_normalised_title_never_similarity():
    assert AK.key('  Retry  ONCE\n') == AK.key('retry once')
    assert AK.key('retry once') != AK.key('retry twice')
    assert AK.key('use tabs') != AK.key("don't use tabs")


def test_l09_an_answer_is_checked_beyond_its_schema():
    ok = {'entities': [{'name': 'a', 'kind': 'module', 'summary': 's'}]}
    shapes.validate(ok, passes.KNOWLEDGE_SCHEMA)
    assert passes.check_knowledge(ok) == []
    assert passes.check_knowledge({'entities': [{'name': ' ', 'kind': 'module',
                                                 'summary': 's'}]})
    dup = {'entities': [dict(ok['entities'][0]), dict(ok['entities'][0], name='A ')]}
    assert 'listed twice' in passes.check_knowledge(dup)[0]
    big = {'entities': [{'name': 'a', 'kind': 'module', 'summary': 'é' * 1500}]}
    assert 'bytes' in passes.check_knowledge(big)[0]           # 1500 chars, 3000 bytes
    with pytest.raises(shapes.Invalid):
        shapes.validate({'entities': [{'name': 'a', 'kind': 'guess', 'summary': 's'}]},
                        passes.KNOWLEDGE_SCHEMA)
    with pytest.raises(shapes.Invalid):
        shapes.validate({'entities': [ok['entities'][0]] * 101}, passes.KNOWLEDGE_SCHEMA)
    assert passes.check_lessons({'lessons': [{'title': '', 'text': 't', 'outcome': 'worked'}]})
    assert passes.check_decisions({'decisions': [{'statement': ' '}]})


def test_l10_no_answer_and_a_prose_answer_are_invalid_not_empty():
    assert K._problems(None, passes.KNOWLEDGE_SCHEMA, passes.check_knowledge) == [
        'the answer carried no JSON']
    assert K._problems({'entities': [{'name': 'x'}]}, passes.KNOWLEDGE_SCHEMA,
                       passes.check_knowledge)


# ── L11–L12 the fake's two mechanisms ──

def _spec(**kw):
    return base.CallSpec(route_decision_id='rte_x', purpose='knowledge_extraction',
                         prompt='P', workdir='.', account=base.AccountRef('a'),
                         schema=passes.DECISIONS_SCHEMA, **kw)


def test_l11_a_prompted_harness_asks_in_the_prompt_and_a_native_one_does_not():
    reply = {'knowledge_extraction': [{'parsed': {'decisions': []}}]}
    native, prompted = FakeCaller('n', replies=reply), FakeCaller('p', structured='prompted',
                                                                  replies=reply)
    assert native.call(_spec()).parsed == {'decisions': []}
    assert prompted.call(_spec()).parsed == {'decisions': []}
    assert native.sent[0][1] == 'P'
    assert prompted.sent[0][1].startswith('P\n\nAnswer with ONLY one JSON object')
    assert json.dumps(passes.DECISIONS_SCHEMA, sort_keys=True) in prompted.sent[0][1]
    assert native.capabilities().structured_output == 'native'
    assert prompted.capabilities().structured_output == 'prompted'


def test_l12_the_legacy_parse_seam_is_one_implementation():
    from claude_sessions import llmcall, memory
    assert memory._parse_json is llmcall.parse_json
    assert llmcall.parse_json('ok:\n```json\n{"a": 1}\n```') == {'a': 1}
    env = json.dumps({'structured_output': {'a': 1}, 'total_cost_usd': 0.25})
    assert llmcall.unwrap_structured(env) == ({'a': 1}, 0.25)
    assert llmcall.unwrap_structured(json.dumps({'result': 'x {"b": 2} y'})) == ({'b': 2},
                                                                                None)


# ── L13–L14 the real adapters, against a stand-in runner ──

class Runner:
    def __init__(self, result):
        self.result, self.seen = result, []

    def __call__(self, cmd, input_text=None, **kw):
        self.seen.append((cmd, input_text, kw))
        return self.result


def _result(rc=0, stdout='', reason='', error='', timed_out=False):
    from claude_sessions import llmcall
    return llmcall.Result(rc, stdout, reason, error, timed_out)


def test_l13_claude_code_calls_read_only_ephemeral_and_native(monkeypatch, tmp_path):
    from claude_sessions import config, llmcall
    from claude_sessions.sessions import HEADLESS_MARK
    env = json.dumps({'structured_output': {'decisions': []}, 'total_cost_usd': 0.01,
                      'usage': {'input_tokens': 7, 'output_tokens': 3}})
    run = Runner(_result(stdout=env))
    monkeypatch.setattr(llmcall, 'run_headless', run)
    monkeypatch.setattr(llmcall, 'budget_args', lambda: [])
    monkeypatch.setattr(config, 'get_claude_exe', lambda: 'C:/x/claude.exe')
    spec = _spec(model='claude-haiku-4-5')
    spec = base.CallSpec(**dict(spec.__dict__, account=base.AccountRef('a', str(tmp_path))))
    got = real.ClaudeCodeCaller().call(spec)
    (cmd, stdin, kw), = run.seen
    assert cmd[:6] == ['C:/x/claude.exe', '-p', '--max-turns', '20', '--disallowedTools',
                       'Write,Edit,NotebookEdit,Bash']
    assert cmd[cmd.index('--model') + 1] == 'claude-haiku-4-5'
    assert cmd[cmd.index('--output-format') + 1] == 'json' and '--json-schema' in cmd
    assert stdin.endswith(HEADLESS_MARK)
    assert os.path.normcase(kw['env']['CLAUDE_CONFIG_DIR']) == os.path.normcase(str(tmp_path))
    assert (got.error, got.parsed) == (None, {'decisions': []})
    assert got.usage == {'tokens_in': 7, 'tokens_out': 3, 'cache_read': 0, 'cache_write': 0,
                         'cost_usd': 0.01}


def test_l14_pi_calls_with_its_own_flags_vocabulary_and_home(monkeypatch, tmp_path):
    from claude_sessions import harnesses, llmcall
    run = Runner(_result(stdout='here: {"decisions": []}'))
    monkeypatch.setattr(llmcall, 'run_headless', run)
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: 'C:/x/pi.exe')
    monkeypatch.setattr(harnesses, 'disabled', lambda: set())
    home = str(tmp_path / '.pi' / 'agent')
    os.makedirs(home)
    real_home = harnesses.home_dir
    monkeypatch.setattr(harnesses, 'home_dir',
                        lambda hid=None: home if hid == 'pi' else real_home(hid))
    account, why_not = real.PiCaller().account(rotation=False)
    assert (account.home_ref, why_not) == (home, '')
    spec = base.CallSpec(**dict(_spec(model='spark/qwen3.8').__dict__, account=account))
    got = real.PiCaller().call(spec)
    (cmd, stdin, kw), = run.seen
    assert cmd == ['C:/x/pi.exe', '-p', '--no-session', '--tools', 'read,grep,find,ls',
                   '--model', 'spark/qwen3.8']
    assert 'matching this JSON Schema' in stdin
    assert os.path.normcase(kw['env']['PI_CODING_AGENT_DIR']) == os.path.normcase(home)
    assert got.parsed == {'decisions': []}


@pytest.mark.parametrize('result,error', [
    (_result(rc=None, timed_out=True, error='timed out'), 'timeout'),
    (_result(rc=1, reason='Model "claude-opus-5" is ambiguous across providers'),
     'model_unavailable'),
    (_result(rc=1, reason='You have hit your session limit'), 'failed'),
    (_result(rc=None, error='could not start'), 'unavailable'),
])
def test_l15_a_run_that_did_not_succeed_is_named_never_parsed(monkeypatch, result, error):
    from claude_sessions import harnesses, llmcall
    monkeypatch.setattr(llmcall, 'run_headless', Runner(result))
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: 'pi.exe')
    monkeypatch.setattr(harnesses, 'disabled', lambda: set())
    got = real.PiCaller().call(_spec())
    assert (got.error, got.parsed) == (error, None)


def test_l16_the_knowledge_path_reaches_no_legacy_ui_memory_or_router():
    """The call path may reach the P0.5 runner (llmcall) and the legacy account
    helpers the real adapters use; never `memory`, `recall`, the UI, and no
    P10 router exists to reach. P5's closure (test_context_units C16) is
    unchanged by P6. Mutation: `from claude_sessions import memory` in
    harnesses/calls.py fails here."""
    banned = ('claude_sessions.memory', 'claude_sessions.recall', 'claude_sessions.gui_api',
              'claude_sessions.ui', 'claude_sessions.main', 'claude_sessions.gui',
              'archeus.core.router')
    code = ('import sys\n'
            'import archeus.core.calls, archeus.core.knowledge.worker\n'
            'import archeus.core.knowledge.passes, archeus.harnesses.calls\n'
            'import archeus.core.application.knowledge, archeus.core.knowledge.ingest\n'
            'print([m for m in %r if m in sys.modules])' % (banned,))
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=ROOT,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == '[]', r.stdout
    assert not os.path.exists(os.path.join(ROOT, 'archeus', 'core', 'router.py'))
