"""C-22: pi's offers are what ONE pi home can run, in pi's own words
(`pi --list-models`), never the catalogue pi ships (domain-model §8.3: an offer
is an account's; ADR-0022; ADR-0031: discovery is not authorisation).

No real pi runs here: `proc.run` is replaced by a scripted `--list-models`
that answers per `PI_CODING_AGENT_DIR`, so every test is about the home it
names and nothing reads the user's configuration."""

import json
import os
import subprocess

import pytest

from archeus.core.application import resources
from archeus.core.routing import router as R
from archeus.harnesses import base
from archeus.harnesses import calls as real
from archeus.harnesses import sessions as SA
from claude_sessions import harnesses, pi, proc

HEADER = 'provider  model                  context  max-out  thinking  images'


def table(*rows):
    return '\n'.join([HEADER] + ['%s  %s  262.1K  32.8K  no  no' % r for r in rows]) + '\n'


class FakePi:
    """`pi --list-models`, scripted per home; counts every spawn."""

    def __init__(self):
        self.answers, self.calls = {}, []

    def __call__(self, args, *, env=None, **kw):
        assert args[1:] == ['--list-models']
        home = env['PI_CODING_AGENT_DIR']
        self.calls.append(home)
        rc, out = self.answers.get(home, (1, ''))
        if rc is None:
            return None
        return subprocess.CompletedProcess(args, rc, out, 'boom' if rc else '')


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakePi()
    monkeypatch.setattr(proc, 'run', f)
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: str(tmp_path / 'pi.cmd'))
    monkeypatch.setattr(pi, '_version', lambda exe: '0.85.1')
    monkeypatch.setattr(pi, 'catalogue', lambda home=None: [
        {'id': 'anthropic/claude-z', 'label': 'Z', 'provider': 'anthropic', 'cost': {},
         'context': 200000, 'thinking': []},
        {'id': 'openai/gpt-y', 'label': 'Y', 'provider': 'openai', 'cost': {},
         'context': 400000, 'thinking': []}])
    monkeypatch.setattr(pi, '_CONFIGURED', {})
    return f


def home(tmp_path, name, models_json=None):
    h = tmp_path / name
    h.mkdir()
    if models_json is not None:
        (h / 'models.json').write_text(json.dumps(models_json), encoding='utf-8')
    return str(h)


SPARK = {'providers': {'spark': {'baseUrl': 'http://example.invalid/v1', 'apiKey': 'k',
                                 'models': [{'id': 'qwen-x', 'contextWindow': 262144}]}}}


def ids(offers):
    return [m.id for m in offers]


# ── account isolation ────────────────────────────────────────────────────────

def test_each_home_offers_only_what_pi_lists_for_it(fake, tmp_path):
    a, b = home(tmp_path, 'a', SPARK), home(tmp_path, 'b')
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    fake.answers[b] = (0, table(('openai', 'gpt-y')))
    assert ids(real.pi_models(a)) == ['spark/qwen-x']
    assert ids(real.pi_models(b)) == ['openai/gpt-y']
    assert sorted(fake.calls) == sorted([a, b])        # queried independently


def test_the_shipped_catalogue_is_never_an_offer(fake, tmp_path):
    a, b = home(tmp_path, 'a', SPARK), home(tmp_path, 'b')
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    fake.answers[b] = (0, table(('openai', 'gpt-y')))
    for h in (a, b):
        assert 'anthropic/claude-z' not in ids(real.pi_models(h))
    # the catalogue is still there, as catalogue
    assert 'anthropic/claude-z' in [c['id'] for c in pi.catalogue()]
    assert 'anthropic/claude-z' not in [m['id'] for m in pi.configured(a)['models']]


def test_one_home_failing_leaves_the_other_untouched(fake, tmp_path):
    a, b = home(tmp_path, 'a', SPARK), home(tmp_path, 'b')
    fake.answers[a] = (1, '')
    fake.answers[b] = (0, table(('openai', 'gpt-y')))
    offers, note = real.pi_offers(base.AccountRef('acc_a', a))
    assert offers == () and 'exited 1' in note and 'boom' in note
    assert ids(real.pi_models(b)) == ['openai/gpt-y']


def test_the_cache_is_per_home_and_never_leaks(fake, tmp_path):
    a, b = home(tmp_path, 'a', SPARK), home(tmp_path, 'b')
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    fake.answers[b] = (0, table(('openai', 'gpt-y')))
    real.pi_models(a), real.pi_models(b), real.pi_models(a), real.pi_models(b)
    assert sorted(fake.calls) == sorted([a, b])        # one spawn per home
    assert ids(real.pi_models(a)) == ['spark/qwen-x']  # A's answer, still A's


# ── cache invalidation ───────────────────────────────────────────────────────

def test_unchanged_version_and_config_reuse_the_answer(fake, tmp_path):
    a = home(tmp_path, 'a', SPARK)
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    real.pi_models(a), real.pi_models(a)
    assert fake.calls == [a]


def test_a_config_change_invalidates(fake, tmp_path):
    a = home(tmp_path, 'a', SPARK)
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    real.pi_models(a)
    p = os.path.join(a, 'auth.json')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('{"openai": {"key": "x"}}')
    fake.answers[a] = (0, table(('openai', 'gpt-y'), ('spark', 'qwen-x')))
    assert ids(real.pi_models(a)) == ['openai/gpt-y', 'spark/qwen-x']
    assert fake.calls == [a, a]
    st = os.stat(os.path.join(a, 'models.json'))
    os.utime(os.path.join(a, 'models.json'), ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
    real.pi_models(a)
    assert fake.calls == [a, a, a]


def test_a_version_change_invalidates(fake, tmp_path, monkeypatch):
    a = home(tmp_path, 'a', SPARK)
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    real.pi_models(a)
    monkeypatch.setattr(pi, '_version', lambda exe: '0.86.0')
    real.pi_models(a)
    assert fake.calls == [a, a]


def test_a_failure_is_retried_after_its_ttl_and_not_before(fake, tmp_path, monkeypatch):
    a = home(tmp_path, 'a', SPARK)
    clock = [1000.0]
    monkeypatch.setattr(pi, '_now', lambda: clock[0])
    fake.answers[a] = (1, '')
    assert pi.configured(a)['ok'] is False
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    clock[0] += pi._FAIL_TTL_S - 1
    assert pi.configured(a)['ok'] is False and fake.calls == [a]     # still the cached miss
    clock[0] += 1
    assert ids(real.pi_models(a)) == ['spark/qwen-x'] and fake.calls == [a, a]
    clock[0] += 10 ** 6
    real.pi_models(a)
    assert fake.calls == [a, a]                                       # a success never expires


# ── ids and context windows ──────────────────────────────────────────────────

def test_ids_are_provider_slash_model_and_context_comes_from_models_json(fake, tmp_path):
    a = home(tmp_path, 'a', SPARK)
    fake.answers[a] = (0, table(('spark', 'qwen-x'), ('openai', 'gpt-y'), ('xai', 'grok-q')))
    got = {m.id: m for m in real.pi_models(a)}
    assert all('/' in i and i.split('/', 1)[0] and i.split('/', 1)[1] for i in got)
    assert got['spark/qwen-x'].context_window == 262144      # models.json, exact
    assert got['openai/gpt-y'].context_window == 400000      # catalogue fact, same id
    assert got['xai/grok-q'].context_window is None          # known nowhere: unknown
    assert all(m.tier is None for m in got.values())         # no tier assigned here


# ── failures: unknown capability is never available ─────────────────────────

@pytest.mark.parametrize('answer, why', [
    ((1, ''), 'exited 1'),
    ((None, ''), 'could not be run'),
    ((0, 'something else entirely\n'), 'unrecognised table'),
    ((0, HEADER + '\nonly-one-cell\n'), 'unrecognised row'),
    ((0, ''), 'printed nothing'),
])
def test_a_failed_or_unreadable_answer_offers_nothing(fake, tmp_path, answer, why):
    a = home(tmp_path, 'a', SPARK)
    fake.answers[a] = answer
    got = pi.configured(a)
    assert got['ok'] is False and got['models'] == [] and why in got['why']
    offers, note = real.pi_offers(base.AccountRef('acc_a', a))
    assert offers == () and why in note


def test_pi_saying_none_is_an_empty_answer_not_a_failure(fake, tmp_path):
    a = home(tmp_path, 'a')
    fake.answers[a] = (0, 'No models available. Use /login or set an API key.\n')
    got = pi.configured(a)
    assert got == {'ok': True, 'models': [], 'why': ''}
    assert real.pi_offers(base.AccountRef('acc_a', a)) == (
        (), 'pi lists no model this home can run')


def test_missing_executable_and_missing_home(fake, tmp_path, monkeypatch):
    assert 'no pi home' in pi.configured(str(tmp_path / 'nowhere'))['why']
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: None)
    got = pi.configured(home(tmp_path, 'a'))
    assert got['ok'] is False and 'not installed' in got['why']
    assert fake.calls == []


def test_no_provider_is_special(fake, tmp_path):
    """A self-hosted provider and a hosted one go through the same path."""
    import inspect
    src = inspect.getsource(pi.configured) + inspect.getsource(pi._list_models) + \
        inspect.getsource(real.pi_offers)
    for word in ('spark', 'localhost', '127.0.0.1', '192.168', 'self_hosted', 'local'):
        assert word not in src


# ── the adapters and the snapshot carry per-account offers ──────────────────

def test_both_pi_adapters_answer_per_account(fake, tmp_path):
    a, b = home(tmp_path, 'a', SPARK), home(tmp_path, 'b')
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    fake.answers[b] = (1, '')
    for adapter in (real.PiCaller(), SA.PiSessions()):
        ca = adapter.capabilities(base.AccountRef('acc_a', a))
        cb = adapter.capabilities(base.AccountRef('acc_b', b))
        assert ids(ca.models) == ['spark/qwen-x'] and ca.models_note is None
        assert cb.models == () and 'exited 1' in cb.models_note


def test_the_snapshot_gives_each_account_its_own_offers(fake, tmp_path):
    a, b = home(tmp_path, 'a', SPARK), home(tmp_path, 'b')
    fake.answers[a] = (0, table(('spark', 'qwen-x')))
    fake.answers[b] = (0, table(('openai', 'gpt-y')))
    hs = [{'id': 'pi', 'installed': True}]
    accounts = [{'id': 'acc_a', 'ref': a, 'home_ref': a, 'harness': 'pi'},
                {'id': 'acc_b', 'ref': b, 'home_ref': b, 'harness': 'pi'}]
    resources._account_offers(accounts, [real.PiCaller()], hs)
    assert [m['id'] for m in accounts[0]['models']] == ['spark/qwen-x']
    assert [m['id'] for m in accounts[1]['models']] == ['openai/gpt-y']


# ── the router elects among each account's own offers ───────────────────────

def _snap(accounts):
    h = {'id': 'pi', 'installed': True, 'capabilities': ['headless', 'structured_output'],
         'enforcement': 'none', 'structured_output': 'prompted', 'efforts': [],
         # the harness-level list: the default home's answer, never the account's
         'models': [{'id': 'anthropic/claude-z', 'tier': None, 'context_window': None}],
         'exempt': True}
    return {'now': '2026-10-01T10:00:00.000Z', 'harnesses': [h], 'accounts': accounts,
            'terms': {}, 'affinity': None, 'approved_fallbacks': []}


def _acct(id_, models, note=None, priority=1):
    return {'id': id_, 'ref': id_, 'harness': 'pi', 'label': id_, 'auth_kind': 'api_key',
            'registered': True, 'health': 'AVAILABLE', 'why_not': None,
            'policy': {'priority': priority, 'allocation_pct': 80, 'reserve_pct': 10,
                       'brain_reserve_pct': 10, 'fallback': 'ask', 'budgets': {},
                       'project_allow': [], 'project_deny': []},
            'usage': {'windows': {'5h': 0.0}, 'age_s': 0, 'resets_at': {}},
            'ledger': {'tokens_today': 0, 'cost_today': 0, 'running': 0},
            'models': [{'id': m, 'tier': None, 'context_window': None} for m in models],
            'models_note': note}


def _call(**kw):
    return dict({'subject': 'archeus_call', 'purpose': 'brain', 'capabilities': ['headless'],
                 'structured_output': True, 'min_model_tier': None, 'models': {},
                 'model_required': False, 'effort': None, 'effort_required': False,
                 'preferred': {}, 'forbidden': {}, 'required': {}, 'size': None,
                 'policy': None}, **kw)


def test_a_model_only_another_account_offers_is_not_this_accounts():
    s = _snap([_acct('acc_a', ['spark/qwen-x'], priority=1),
               _acct('acc_b', ['openai/gpt-y'], priority=2)])
    d = R.route(_call(models={'pi': 'openai/gpt-y'}, model_required=True), s)
    by = {c['resource']: c for c in d['candidates']}
    assert d['selected'] == 'acc_b' and d['model'] == 'openai/gpt-y'
    assert by['acc_a']['eliminated_at_step'] == 'model'
    # the harness-level (catalogue-shaped) list lends nothing to either account
    d = R.route(_call(models={'pi': 'anthropic/claude-z'}, model_required=True), s)
    assert d['result'] != 'selected'


def test_an_account_whose_discovery_found_nothing_is_not_electable():
    s = _snap([_acct('acc_a', [], note='pi --list-models exited 1: boom')])
    d = R.route(_call(), s)
    (c,) = d['candidates']
    assert d['result'] != 'selected'
    assert c['eliminated_at_step'] == 'model' and 'exited 1' in c['reason']


def test_a_snapshot_recorded_before_c22_replays_on_the_harness_list():
    a = _acct('acc_a', [])
    del a['models'], a['models_note']
    d = R.route(_call(), _snap([a]))
    assert d['selected'] == 'acc_a'


# ── legacy: auth_state and the launch modal ─────────────────────────────────

def test_auth_state_honours_a_keyed_models_json_per_home(tmp_path):
    a = home(tmp_path, 'a', SPARK)
    b = home(tmp_path, 'b', {'providers': {'spark': {'models': [{'id': 'qwen-x'}]}}})
    c = home(tmp_path, 'c')
    with open(os.path.join(c, 'auth.json'), 'w', encoding='utf-8') as f:
        f.write('{}')
    assert pi.auth_state(a) == 'ok'          # models.json provider with its own key
    assert pi.auth_state(b) == 'missing'     # declared, but no key: not a login
    assert pi.auth_state(c) == 'missing'     # fresh install
