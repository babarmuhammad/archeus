"""The provider layer: named backend profiles, the migration onto them, the one
seam every routed launch goes through, and the bugs the rename uncovered.

Every test here was mutation-verified: revert the change it covers and it goes
red. That matters more than usual for the migration, because the failure mode is
silent (a user's settings quietly reverting to defaults on upgrade).
"""
import os

from claude_sessions import config as c
from claude_sessions import stats


def _legacy(**over):
    """A settings dict as it looked BEFORE profiles: flat provider_* keys at the
    top level, which is where the omniroute_* rename left them."""
    s = dict(c._DEFAULT_SETTINGS)
    s.update(over)
    return s


# ── the omniroute_* -> provider_* rename ─────────────────────────

def test_migration_carries_the_old_omniroute_keys_forward():
    """load_settings() parks unrecognised keys in _unknown, so by the time
    migrate_settings runs the old names are THERE and not at the top level.
    Reading the top level instead finds nothing and silently resets a
    configured user to defaults."""
    s = dict(c._DEFAULT_SETTINGS)
    s[c._UNKNOWN_KEYS] = {'omniroute_base_url': 'http://box:20128',
                          'omniroute_api_key': 'sk-old',
                          'omniroute_exec_model': 'auto/coding'}
    out, changed = c.migrate_settings(s)
    assert changed
    prof, = out['providers']
    assert prof['base_url'] == 'http://box:20128'
    assert prof['api_key'] == 'sk-old'
    assert prof['model'] == 'auto/coding'


def test_migration_infers_the_kind_from_a_configured_exec_model():
    """Before there was a kind, "routing is on" WAS "an exec model is set" --
    so that is the only signal available to migrate from."""
    s = dict(c._DEFAULT_SETTINGS)
    s[c._UNKNOWN_KEYS] = {'omniroute_exec_model': 'auto/coding'}
    out, _ = c.migrate_settings(s)
    prof, = out['providers']
    assert prof['kind'] == 'omniroute'


def test_migration_leaves_a_user_who_never_used_omniroute_on_anthropic():
    """No kind meant nothing to route to. An empty list is the honest result --
    NOT a profile pointing at the placeholder localhost URL the old default
    carried, which would offer a backend that was never configured."""
    out, _ = c.migrate_settings(dict(c._DEFAULT_SETTINGS))
    assert out['providers'] == []
    assert out['provider_active'] == ''


# ── flat keys -> one named profile ───────────────────────────────

def test_the_one_configured_backend_becomes_one_named_profile():
    out, changed = c.migrate_settings(_legacy(
        provider_kind='omniroute', provider_base_url='http://localhost:20128',
        provider_api_key='sk-x', provider_exec_model='auto/coding',
        provider_keys_migrated=True))
    assert changed
    prof, = out['providers']
    assert prof['name'] == 'OmniRoute'
    assert prof['kind'] == 'omniroute'
    assert prof['api_key'] == 'sk-x'
    assert out['provider_active'] == prof['id']


def test_a_generic_backend_is_named_after_its_host():
    """A profile needs a name and the old shape had none, so one is derived. The
    host is the only thing on hand that distinguishes two of them."""
    out, _ = c.migrate_settings(_legacy(
        provider_kind='generic', provider_base_url='http://10.0.0.5:8000',
        provider_exec_model='Qwen', provider_keys_migrated=True))
    prof, = out['providers']
    assert prof['name'] == '10.0.0.5'


def test_the_failover_list_moves_into_the_profile_that_serves_it():
    """The candidates are MODEL IDS. A global list applied to whichever backend
    happened to be configured was already wrong; it only looked right while
    there could be exactly one."""
    out, _ = c.migrate_settings(_legacy(
        provider_kind='omniroute', provider_exec_model='auto/coding',
        failover_models=['gemini/flash', 'nvidia/pro'],
        provider_keys_migrated=True))
    prof, = out['providers']
    assert prof['failover_models'] == ['gemini/flash', 'nvidia/pro']
    assert 'failover_models' not in out


def test_every_migrated_flat_key_lands_somewhere():
    """The census, as a gate: a key that is neither mapped into the profile nor
    deliberately dropped is one a user had configured and silently loses."""
    mapped = {old for old, _new in c._FLAT_TO_PROFILE}
    assert mapped | set(c._FLAT_DROPPED) >= {
        'provider_kind', 'provider_base_url', 'provider_api_key',
        'provider_exec_model', 'provider_context_tokens', 'provider_tool_search',
        'gateway_kind', 'gateway_port', 'gateway_target_base_url',
        'gateway_target_api_key', 'failover_models', 'failover_port',
        'failover_quiet', 'headless_provider'}


def test_migration_drops_the_dead_names_so_they_are_not_rewritten_forever():
    """save_settings layers _unknown back over its output, so a legacy key left
    in that bucket is written to disk on every save for the rest of time."""
    s = dict(c._DEFAULT_SETTINGS)
    s[c._UNKNOWN_KEYS] = {'omniroute_api_key': 'sk-old', 'future_key': 1}
    out, _ = c.migrate_settings(s)
    assert 'omniroute_api_key' not in out[c._UNKNOWN_KEYS]
    assert 'provider_api_key' not in out
    assert 'provider_api_key' not in out[c._UNKNOWN_KEYS]
    # a key from a NEWER archeus is not ours to delete
    assert out[c._UNKNOWN_KEYS]['future_key'] == 1


def test_migration_is_idempotent():
    out, first = c.migrate_settings(_legacy(
        provider_kind='generic', provider_base_url='http://box:20128',
        provider_exec_model='m', provider_keys_migrated=True))
    out2, second = c.migrate_settings(out)
    assert first and not second
    assert len(out2['providers']) == 1
    assert out2['providers'][0]['base_url'] == 'http://box:20128'


def test_a_second_run_does_not_undo_a_user_who_deleted_the_profile():
    """The flag is what makes it one-time. Without it, deleting the migrated
    profile is overruled on the next start."""
    out, _ = c.migrate_settings(_legacy(
        provider_kind='omniroute', provider_exec_model='auto/coding',
        provider_keys_migrated=True))
    out['providers'] = []
    out['provider_active'] = ''
    out, changed = c.migrate_settings(out)
    assert not changed and out['providers'] == []


# ── schema discipline ────────────────────────────────────────────

def test_the_profile_list_is_declared_so_the_gui_cannot_wipe_it():
    """/api/settings does load -> mutate -> save and load_settings drops what it
    does not know, so an undeclared key is written once and deleted by the very
    next save."""
    for k in ('providers', 'provider_active', 'headless_provider_id',
              'provider_profiles_migrated', 'provider_keys_migrated'):
        assert k in c._DEFAULT_SETTINGS, k


def test_the_profile_list_is_not_writable_by_the_generic_settings_loop():
    """`gui._api_settings` writes every key NOT in INTERNAL_SETTINGS straight
    off the wire. A profile carries two credentials, a base URL and a port that
    two detached daemons connect to, so one POST could otherwise rewrite every
    endpoint archeus forwards to."""
    from claude_sessions import gui
    assert 'providers' in c.INTERNAL_SETTINGS
    assert 'providers' not in gui._SETTING_KEYS


def test_no_credential_ever_reaches_the_page():
    """The payload is readable by anything that reaches the port. A boolean says
    whether a key is set; the key itself is never sent."""
    from claude_sessions import gui
    prof = c.new_profile(id='p1', name='x', api_key='sk-secret',
                         gateway_target_api_key='sk-gw')
    pub = gui._public_profile(prof)
    assert 'sk-secret' not in repr(pub) and 'sk-gw' not in repr(pub)
    assert pub['api_key_set'] is True and pub['gateway_target_api_key_set'] is True


# ── the accessors ────────────────────────────────────────────────

def test_a_profile_is_never_resolved_to_a_different_one():
    """A caller that asked for a specific backend and is handed another is the
    exact failure this layer exists to remove."""
    a = c.new_profile(id='a', name='A', port=20129)
    b = c.new_profile(id='b', name='B', port=20131)
    s = {'providers': [a, b], 'provider_active': 'a'}
    assert c.provider_profile('b', s)['name'] == 'B'
    assert c.provider_profile('gone', s) is None
    assert c.provider_profile('', s) is None
    assert c.active_provider(s)['name'] == 'A'


def test_two_profiles_never_share_a_port_pair():
    """Each owns failover on `port` and its gateway on `port + 1`, so they step
    by two — one daemon per profile is the whole reason concurrent backends are
    possible, and a shared port is two daemons racing for one bind."""
    s = {'providers': []}
    ports = []
    for i in range(4):
        p = c.new_profile(id='p%d' % i, name='p', port=c.free_profile_port(s))
        s['providers'].append(p)
        ports.append(p['port'])
    assert len(set(ports)) == 4
    gws = [c.gateway_port_of(p) for p in s['providers']]
    assert not (set(ports) & set(gws)), 'a gateway port collides with a failover port'


def test_a_profile_stored_by_an_older_version_is_filled_in():
    """Read sites index these without a default, so a missing field would
    KeyError at the first request rather than at save time."""
    s = {'providers': [{'id': 'p1', 'name': 'old'}]}
    prof, = c.provider_profiles(s)
    assert set(prof) == set(c.PROFILE_FIELDS)


# ── the env the seam produces ────────────────────────────────────

def test_anthropic_direct_is_untouched():
    """The default path must add no env at all -- not a base URL, not a
    disabled-feature flag. Anything else changes every existing user's session."""
    assert c.provider_env(None) == {}
    assert c.provider_env(c.active_provider({'providers': []})) == {}


def test_adaptive_thinking_is_disabled_for_every_routed_backend():
    """Including an Anthropic-SHAPED one. A thinking block carries a signature
    that must round-trip byte-for-byte to the infrastructure that minted it, so
    a local server cannot produce one -- and Claude Code sends
    thinking:{"type":"adaptive"} unconditionally, which a backend that does not
    know the field answers with 400. That fails the whole turn, not the
    thinking."""
    for kind in ('omniroute', 'generic'):
        prof = c.new_profile(id='p', kind=kind, model='m', base_url='http://h')
        assert c.provider_env(prof)['CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING'] == '1'


def test_the_failover_proxy_still_wins_the_base_url():
    prof = c.new_profile(id='p', kind='generic', model='m',
                         base_url='http://upstream', failover_models=['b'],
                         port=20129)
    assert c.provider_env(prof)['ANTHROPIC_BASE_URL'] == 'http://127.0.0.1:20129'


def test_each_profile_points_its_sessions_at_its_OWN_proxy():
    """Two live backends, two proxies. Sharing one is how a session's turns
    reached the other profile's upstream with the other profile's key."""
    a = c.new_profile(id='a', model='m', base_url='http://a', failover_models=['x'],
                      port=20129)
    b = c.new_profile(id='b', model='m', base_url='http://b', failover_models=['y'],
                      port=20131)
    assert c.provider_env(a)['ANTHROPIC_BASE_URL'] != c.provider_env(b)['ANTHROPIC_BASE_URL']


def test_the_gateway_takes_the_provider_slot_for_its_own_profile():
    prof = c.new_profile(id='p', kind='generic', model='m', base_url='http://real',
                         gateway_kind='openai',
                         gateway_target_base_url='http://lm:1234/v1', port=20129)
    assert c.provider_upstream(prof) == 'http://127.0.0.1:%d' % c.gateway_port_of(prof)


# ── the two daemons ──────────────────────────────────────────────

def test_two_profiles_daemons_share_no_lock_file_and_no_marker():
    """A bare connectivity check on a port would happily trust whatever is
    squatting it — including the OTHER profile's proxy."""
    from claude_sessions import failover, gateway
    a, b = c.new_profile(id='a', port=20129), c.new_profile(id='b', port=20131)
    for mod in (failover, gateway):
        da, db = mod._daemon(a), mod._daemon(b)
        assert da.lock_path() != db.lock_path()
        assert da.marker_path != db.marker_path
        assert da.marker != db.marker
    # and a failover daemon must not answer for the gateway of the same profile
    assert failover._daemon(a).marker != gateway._daemon(a).marker


def test_a_daemon_whose_profile_is_gone_refuses_to_start(monkeypatch, capsys):
    """Never a fall back to the active profile. These processes are dispatched
    BEFORE migrate_settings runs, so they can be looking at a settings file that
    predates the profile list — guessing there would route a session at an
    upstream nobody chose."""
    from claude_sessions import failover, gateway
    monkeypatch.setattr(c, 'load_settings',
                        lambda: {'providers': [], 'provider_active': ''})
    assert failover.serve_cli(0, 'nope') == 1
    assert gateway.serve_cli(0, 'nope') == 1
    assert 'no such provider profile' in capsys.readouterr().out


def test_the_daemon_is_pinned_to_its_profile_at_spawn(monkeypatch):
    """The id travels in the child's argv. Looking it up after the child starts
    would let an edit landing between the spawn and the first request hand it a
    different backend."""
    from claude_sessions import failover
    seen = {}
    prof = c.new_profile(id='abc123', name='x', port=20129)
    monkeypatch.setattr(failover._proxy.Daemon, 'is_ready', lambda *a, **k: False)
    monkeypatch.setattr(failover._proxy.Daemon, 'claim_spawn', lambda *a, **k: True)
    monkeypatch.setattr(failover._proxy.Daemon, 'read_lock', lambda *a, **k: None)

    import subprocess
    monkeypatch.setattr(subprocess, 'Popen',
                        lambda cmd, **kw: seen.setdefault('cmd', cmd))
    failover.ensure_running(prof)
    assert seen['cmd'][-1] == 'abc123'
    assert '--failover-serve' in seen['cmd']


# ── the subagent frontmatter bug ─────────────────────────────────

def test_synced_agents_lose_their_model_field_on_a_routed_session(tmp_path, monkeypatch):
    """A bare Anthropic id in agent frontmatter cannot be resolved by a routed
    backend: the subagent 401s, or the proxy answers "Ambiguous model". Three of
    the four call sites never passed the flag, so GUI-launched and
    suggestion-accepted agents kept it and broke on every routed session --
    which is why the default is derived here instead of asked of callers."""
    from claude_sessions import agents
    lib = tmp_path / 'lib'
    lib.mkdir()
    (lib / 'a.md').write_text('---\nname: a\nmodel: claude-haiku-4-5\n---\nbody\n',
                              encoding='utf-8')
    monkeypatch.setattr(agents, 'find_library_agent', lambda ref: str(lib / 'a.md'))
    proj = tmp_path / 'proj'
    proj.mkdir()
    prof = c.new_profile(id='p1', name='x', kind='generic', base_url='http://h')
    monkeypatch.setattr(c, 'load_settings',
                        lambda: {'providers': [prof], 'provider_active': 'p1'})
    agents.sync_project_agents(str(proj), ['a'])
    out = (proj / '.claude' / 'agents' / 'a.md').read_text(encoding='utf-8')
    assert 'model:' not in out
    assert 'name: a' in out


def test_synced_agents_keep_their_model_field_on_anthropic(tmp_path, monkeypatch):
    from claude_sessions import agents
    lib = tmp_path / 'lib'
    lib.mkdir()
    (lib / 'a.md').write_text('---\nname: a\nmodel: claude-haiku-4-5\n---\nbody\n',
                              encoding='utf-8')
    monkeypatch.setattr(agents, 'find_library_agent', lambda ref: str(lib / 'a.md'))
    proj = tmp_path / 'proj'
    proj.mkdir()
    monkeypatch.setattr(c, 'load_settings', lambda: dict(c._DEFAULT_SETTINGS))
    agents.sync_project_agents(str(proj), ['a'])
    out = (proj / '.claude' / 'agents' / 'a.md').read_text(encoding='utf-8')
    assert 'model: claude-haiku-4-5' in out


# ── the cost bug ─────────────────────────────────────────────────

def test_an_unpriced_model_reads_as_not_tracked_never_as_zero():
    """A routed model may be a paid OpenRouter or self-hosted one. `~$0.00` told
    that user their spend was approximately nothing."""
    cost, exact = stats.estimate_cost({'qwen3-coder': {'in': 100000, 'out': 50000}})
    assert not exact
    assert stats.fmt_cost(cost, exact) == 'n/a'


def test_a_priced_model_still_shows_its_number():
    cost, exact = stats.estimate_cost({'claude-sonnet-5': {'in': 1000000, 'out': 0}})
    assert exact and cost > 0
    assert stats.fmt_cost(cost, exact).startswith('3') or '.' in stats.fmt_cost(cost, exact)


def test_a_mixed_rollup_still_quotes_the_part_it_knows():
    """cost>0 with exact=False is a real, useful number for the Anthropic half --
    only a rollup with NOTHING priced becomes n/a."""
    cost, exact = stats.estimate_cost({'claude-sonnet-5': {'in': 1000000, 'out': 0},
                                       'qwen3-coder': {'in': 999999, 'out': 999999}})
    assert cost > 0 and not exact
    assert stats.fmt_cost(cost, exact).startswith('~')


def test_the_gui_renders_the_same_two_cases():
    """Two renderers of one rule is two chances to disagree about it, so the
    JS helper is asserted to exist rather than trusted."""
    js = open(os.path.join(os.path.dirname(__file__), '..', 'claude_sessions',
                           'web', 'app.js'), encoding='utf-8').read()
    assert 'function costCell(' in js
    assert "'n/a'" in js.split('function costCell(')[1][:200]
    assert '?.exact' not in js  # no stray old-style inline render left behind
    assert "exact?'':'~'}$${" not in js


# ── the launcher round-trip ──────────────────────────────────

def _opts(**over):
    o = {'effort': '', 'model': '', 'perm': '', 'name': '', 'worktree': '',
         'cfgdir': 'C:/x', 'agent': '', 'agents_json': '', 'max_thinking': '',
         'subagent_model': '', 'provider': '', 'provider_model': ''}
    o.update(over)
    return o


def test_the_choice_line_carries_the_backend_AND_the_model():
    """The bat launcher writes the whole launch to a file and re-reads it in a
    second process, so a field the line cannot carry is silently dropped -- the
    picker said one backend and the session ran on another, with nothing
    anywhere saying so. v7 carried a model id and no backend identity, which is
    the same hole one level up."""
    from claude_sessions import main
    line = main.build_choice_line('C:/p', 'C--p', 'new',
                                  _opts(provider='p1', provider_model='Qwen'))
    _path, _enc, _choice, back = main.parse_choice_line(line)
    assert back['provider'] == 'p1'
    assert back['provider_model'] == 'Qwen'


def test_a_v7_line_still_parses_as_the_active_profile(monkeypatch):
    """A v7 line can be sitting in %TEMP% at upgrade time. Its field 14 was a
    MODEL with no backend named, which is what it meant when it was written."""
    from claude_sessions import main
    prof = c.new_profile(id='act', name='A')
    monkeypatch.setattr(c, 'load_settings',
                        lambda: {'providers': [prof], 'provider_active': 'act'})
    v7 = 'v7|C:/p|C--p|new|-|-|-|-|-|C:/x|-|-|-|-|auto/coding'
    _p, _e, _ch, opts = main.parse_choice_line(v7)
    assert opts['provider_model'] == 'auto/coding'
    assert opts['provider'] == 'act'


def test_older_choice_lines_still_parse():
    """A v6 line predates routing entirely — it must land on Anthropic, not on
    whatever profile happens to be active."""
    from claude_sessions import main
    v6 = 'v6|C:/p|C--p|new|-|claude-sonnet-5|-|-|-|C:/x|-|-|-|-'
    path, enc, choice, opts = main.parse_choice_line(v6)
    assert (path, enc, choice) == ('C:/p', 'C--p', 'new')
    assert opts['model'] == 'claude-sonnet-5'
    assert opts['provider'] == '' and opts['provider_model'] == ''


# ── archeus's OWN headless calls ───────────────────────────────

def _headless_call(monkeypatch, sb, profiles=(), **settings):
    """Run _claude_stdin in silent mode against a fake exe and return the
    (argv, env) it built. Returns env=None when the call stayed on Anthropic."""
    import json
    from claude_sessions import gui_api, memory, omniroute
    s = dict(c._DEFAULT_SETTINGS)
    s['providers'] = list(profiles)
    s.update(settings)
    sb.settings.write_text(json.dumps(s), encoding='utf-8')
    seen = {}

    def fake_cancel(args, **kw):
        seen['args'], seen['env'] = args, kw.get('env')
        return '{}'

    monkeypatch.setattr(c, 'get_claude_exe', lambda: r'C:\fake\claude.exe')
    monkeypatch.setattr(gui_api, '_run_cancellable', fake_cancel)
    monkeypatch.setattr(omniroute, 'is_reachable', lambda *a, **k: True)
    memory._tls.silent = True
    try:
        memory._claude_stdin('hello', cwd='.')
    finally:
        memory._tls.silent = False
    return seen.get('args', []), seen.get('env')


def test_headless_calls_stay_on_anthropic_by_default(monkeypatch, tmp_path):
    """A configured provider is for SESSIONS. Memory extraction and code review
    run unattended, from a hook and from background threads, so moving them to
    another model -- and another bill -- has to be asked for."""
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    prof = c.new_profile(id='p1', name='local', kind='generic',
                         base_url='http://localhost:11434', model='qwen3-coder:30b')
    args, env = _headless_call(monkeypatch, sb, profiles=[prof],
                               provider_active='p1')
    assert env is None                      # inherit archeus's own environment
    assert args[args.index('--model') + 1] == c._DEFAULT_SETTINGS['extract_model']


def test_headless_calls_follow_their_OWN_setting_not_the_active_profile(monkeypatch, tmp_path):
    """`headless_provider_id` names the backend, and it is deliberately not
    `provider_active`: what you last launched a session on must not silently
    become what your memory extraction bills."""
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    a = c.new_profile(id='a', name='A', kind='generic', base_url='http://a',
                      model='model-a')
    b = c.new_profile(id='b', name='B', kind='generic', base_url='http://b',
                      model='model-b')
    args, env = _headless_call(monkeypatch, sb, profiles=[a, b],
                               provider_active='a', headless_provider_id='b')
    assert env['ANTHROPIC_BASE_URL'] == 'http://b'
    assert args[args.index('--model') + 1] == 'model-b'


def test_headless_provider_routes_the_call_and_swaps_the_model(monkeypatch, tmp_path):
    """The model has to move WITH the base URL: extract_model names an
    Anthropic model, and a local backend answers 404 for it."""
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    prof = c.new_profile(id='p1', name='local', kind='generic',
                         base_url='http://localhost:11434', model='qwen3-coder:30b')
    args, env = _headless_call(monkeypatch, sb, profiles=[prof],
                               headless_provider_id='p1')
    assert env['ANTHROPIC_BASE_URL'] == 'http://localhost:11434'
    assert env['CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING'] == '1'
    assert 'PATH' in env                      # merged onto the real environment
    assert args[args.index('--model') + 1] == 'qwen3-coder:30b'


def test_headless_provider_without_a_model_stays_on_anthropic(monkeypatch, tmp_path):
    """A profile's model is what a routed call would ASK for. Without it there
    is nothing to send, and inheriting extract_model would put an Anthropic id
    in front of a local server."""
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    prof = c.new_profile(id='p1', name='local', kind='generic',
                         base_url='http://h', model='')
    _args, env = _headless_call(monkeypatch, sb, profiles=[prof],
                                headless_provider_id='p1')
    assert env is None


def test_a_deleted_profile_leaves_no_dangling_pointer(monkeypatch, tmp_path):
    """A setting naming something that no longer exists reads as Anthropic --
    the right failure, the wrong state: it would reappear the moment an id was
    reused."""
    from harness import Sandbox
    from claude_sessions import gui
    Sandbox(monkeypatch, tmp_path)
    prof = c.new_profile(id='p1', name='x', kind='generic', base_url='http://h')
    s = dict(c._DEFAULT_SETTINGS, providers=[prof], provider_active='p1',
             headless_provider_id='p1')
    monkeypatch.setattr(c, 'load_settings', lambda: dict(s))
    saved = {}
    monkeypatch.setattr(c, 'save_settings', lambda d: saved.update(d) or True)
    monkeypatch.setattr(gui, 'load_settings', c.load_settings)
    monkeypatch.setattr(gui, 'save_settings', c.save_settings)
    gui._api_provider_delete({}, {'id': 'p1'})
    assert saved['providers'] == []
    assert saved['provider_active'] == '' and saved['headless_provider_id'] == ''


def test_an_unreachable_provider_fails_the_call_instead_of_billing_anthropic(monkeypatch, tmp_path):
    """Falling back would spend the account the user just routed away from,
    silently. The seam raises; _claude_stdin returns '' and the caller reports
    no output."""
    from harness import Sandbox
    from claude_sessions import gui_api, memory, omniroute
    import json
    sb = Sandbox(monkeypatch, tmp_path)
    prof = c.new_profile(id='p1', name='x', kind='generic',
                         base_url='http://127.0.0.1:1', model='m')
    s = dict(c._DEFAULT_SETTINGS, providers=[prof], headless_provider_id='p1')
    sb.settings.write_text(json.dumps(s), encoding='utf-8')
    called = []
    monkeypatch.setattr(c, 'get_claude_exe', lambda: r'C:\fake\claude.exe')
    monkeypatch.setattr(gui_api, '_run_cancellable', lambda *a, **k: called.append(1) or '{}')
    monkeypatch.setattr(omniroute, 'is_reachable', lambda *a, **k: False)
    memory._tls.silent = True
    try:
        assert memory._claude_stdin('hello', cwd='.') == ''
    finally:
        memory._tls.silent = False
    assert not called


# ── which backend a session ran on is recorded, not guessed ──────────────────
# `_used_provider` reads it back off the transcript's model ids, and sessions.py
# already admits that cannot tell an Anthropic model served THROUGH a provider
# from a direct run. The launcher knows, so it writes it down.

def _launch(monkeypatch, sb, choice, opts=None, provider=''):
    from claude_sessions import main as main_mod
    monkeypatch.setattr(main_mod, 'get_claude_exe', lambda: r'C:\fake\claude.exe')
    folder = sb.projects / 'X--work-proj'
    folder.mkdir(exist_ok=True)
    o = {'effort': '', 'model': '', 'perm': '', 'name': '', 'worktree': '',
         'agent': '', 'provider': provider}
    o.update(opts or {})
    args, env, proj = main_mod.build_launch_command(str(sb.root), 'X--work-proj',
                                                    choice, o)
    return args, str(folder)


def test_a_new_session_records_the_backend_it_was_launched_on(monkeypatch, tmp_path):
    from claude_sessions import config as C
    from claude_sessions.sessions import load_session_providers
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    s = C.load_settings()
    prof = C.new_profile(name='Local', kind='generic',
                         base_url='http://127.0.0.1:8000', model='m1', port=20129)
    s['providers'] = [prof]
    C.save_settings(s)
    monkeypatch.setattr('claude_sessions.omniroute.prepare_launch',
                        lambda m, p, ctx_bytes=0: ({'ANTHROPIC_BASE_URL': p['base_url']}, ''))
    args, folder = _launch(monkeypatch, sb, 'new', provider=prof['id'])
    sid = args[args.index('--session-id') + 1]
    assert load_session_providers(folder)[sid] == prof['id']


def test_an_anthropic_launch_records_that_too_rather_than_nothing(monkeypatch, tmp_path):
    from claude_sessions.sessions import load_session_providers
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    args, folder = _launch(monkeypatch, sb, 'new')
    sid = args[args.index('--session-id') + 1]
    rec = load_session_providers(folder)
    # present and empty: "launched on Anthropic direct" is an answer, and an
    # absent key is what makes the reader fall back to guessing
    assert sid in rec and rec[sid] == ''


def test_a_resume_records_under_the_id_it_resumed(monkeypatch, tmp_path):
    from claude_sessions.sessions import load_session_providers
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    _args, folder = _launch(monkeypatch, sb, 'resume:abc-123')
    assert 'abc-123' in load_session_providers(folder)


def test_a_fork_records_nothing_because_its_id_is_not_ours(monkeypatch, tmp_path):
    from claude_sessions.sessions import load_session_providers
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    _args, folder = _launch(monkeypatch, sb, 'fork:abc-123')
    # --fork-session mints a new id we never see; claiming the source id here
    # would label the ORIGINAL session with the fork's backend
    assert load_session_providers(folder) == {}


def test_the_record_beats_the_model_id_guess_in_both_directions(monkeypatch, tmp_path):
    from claude_sessions.sessions import resolve_provider
    anthropic_stats = {'models': ['claude-sonnet-5']}
    other_stats = {'models': ['gpt-5-codex']}
    # an Anthropic model served THROUGH a provider: the guess says "direct"
    assert resolve_provider({'s1': 'p1'}, 's1', anthropic_stats) is True
    # and a non-Anthropic id on a session archeus launched on Anthropic
    assert resolve_provider({'s2': ''}, 's2', other_stats) is False
    # no record at all -> the guess, unchanged
    assert resolve_provider({}, 's3', other_stats) is True
    assert resolve_provider({}, 's4', anthropic_stats) is False


def test_one_model_flag_and_it_is_the_backends(monkeypatch, tmp_path):
    """Both used to be emitted, and the right one won only because Claude
    Code's parser takes the later occurrence. An Anthropic id is not resolvable
    on a routed backend, so which one survives is not a detail."""
    from claude_sessions import config as C
    from harness import Sandbox
    sb = Sandbox(monkeypatch, tmp_path)
    s = C.load_settings()
    prof = C.new_profile(name='Local', kind='generic',
                         base_url='http://127.0.0.1:8000', model='m1', port=20129)
    s['providers'] = [prof]
    C.save_settings(s)
    monkeypatch.setattr('claude_sessions.omniroute.prepare_launch',
                        lambda m, p, ctx_bytes=0: ({}, ''))
    args, _folder = _launch(monkeypatch, sb, 'new',
                            opts={'model': 'claude-sonnet-5'}, provider=prof['id'])
    assert args.count('--model') == 1
    assert args[args.index('--model') + 1] == 'm1'


def test_no_daemon_job_calls_its_proxy_without_a_profile():
    """`failover_stop` called `failover.stop_running()` with no argument for the
    whole life of the per-profile conversion: a TypeError raised on the job
    thread, where nothing logs it and the job just never finishes. A signature
    is not a gate, so this walks the dispatch itself."""
    import ast
    import inspect
    from claude_sessions import gui_api
    tree = ast.parse(inspect.getsource(gui_api.api_job_start))
    bad = [n.func.attr for n in ast.walk(tree)
           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
           and n.func.attr in ('stop_running', 'ensure_running') and not n.args]
    assert not bad, 'called with no profile: %s' % bad
