"""pi as a third harness: its sessions, its projects, and what it cannot do.

Everything here is built against a session pi actually wrote on this machine —
`~/.pi/agent/sessions/--C--Users-mab-AppData-Local-Temp-piprobe--/<ts>_<uuid>
.jsonl`, whose first line is `{"type":"session","version":3,"id":…,"cwd":…}`
followed by `model_change`, `thinking_level_change` and `message` entries. The
fixture is a fake; the schema is the one in the package's own
`docs/session-format.md`, checked against that file.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox
from claude_sessions import harnesses, pi, sessions, store


def _session(path, cwd, sid, turns=2, model='claude-sonnet-4-5',
             usage=None, version=3):
    """One pi session file. The two entries before the first message are real:
    pi writes `model_change` and `thinking_level_change` at startup."""
    recs = [
        {'type': 'session', 'version': version, 'id': sid,
         'timestamp': '2026-09-14T21:38:10.048Z', 'cwd': cwd},
        {'type': 'model_change', 'id': 'aaaa0001', 'parentId': None,
         'timestamp': '2026-09-14T21:38:10.081Z',
         'provider': 'anthropic', 'modelId': model},
        {'type': 'thinking_level_change', 'id': 'aaaa0002',
         'parentId': 'aaaa0001', 'timestamp': '2026-09-14T21:38:10.081Z',
         'thinkingLevel': 'medium'},
    ]
    for i in range(turns):
        recs.append({
            'type': 'message', 'id': 'u%06d' % i, 'parentId': 'aaaa0002',
            'timestamp': '2026-09-14T21:39:%02d.000Z' % i,
            'message': {'role': 'user',
                        'content': [{'type': 'text', 'text': 'do it %d' % i}],
                        'timestamp': 1789421890086}})
        recs.append({
            'type': 'message', 'id': 'a%06d' % i, 'parentId': 'u%06d' % i,
            'timestamp': '2026-09-14T21:39:%02d.500Z' % i,
            'message': {'role': 'assistant',
                        'content': [{'type': 'text', 'text': 'done'}],
                        'api': 'anthropic-messages', 'provider': 'anthropic',
                        'model': model, 'stopReason': 'stop',
                        'usage': dict(usage or {'input': 10, 'output': 5,
                                                'cacheRead': 3, 'cacheWrite': 2,
                                                'totalTokens': 20})}})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r) + '\n')
    return path


def pi_home(root, sessions_spec=(), exe=True):
    """A pi home under *root*. *sessions_spec* is [(sid, cwd, turns)].

    The directory name is pi's own encoding — every separator and the drive
    colon mapped to `-`, wrapped in `--` — and it is written here precisely so
    the reader can be caught decoding it.
    """
    home = os.path.join(str(root), '.pi', 'agent')
    for i, (sid, cwd, turns) in enumerate(sessions_spec):
        name = '--%s--' % ''.join(
            c if c.isalnum() else '-' for c in cwd)
        _session(os.path.join(home, 'sessions', name,
                              '2026-09-14T21-38-%02d-000Z_%s.jsonl' % (i, sid)),
                 cwd, sid, turns)
    os.makedirs(home, exist_ok=True)
    if exe:
        b = os.path.join(str(root), 'AppData', 'Roaming', 'npm')
        os.makedirs(b, exist_ok=True)
        for name in ('pi.cmd', 'pi.exe', 'pi'):
            open(os.path.join(b, name), 'w').close()
    return home


# ── the registry ─────────────────────────────────────────────

def test_pi_is_a_home_with_two_components(monkeypatch, tmp_path):
    """`~/.pi` is not the home — `~/.pi/agent` is, and `~/.pi` holds other
    things beside it. Every other harness's home is one level down, which is
    exactly why `home_rel` was a tuple from the start."""
    sb = Sandbox(monkeypatch, tmp_path)
    pi_home(sb.root)
    assert harnesses.home_dir('pi') == os.path.join(str(sb.root), '.pi', 'agent')
    assert harnesses.descriptor('pi')['home_env'] == 'PI_CODING_AGENT_DIR'


def test_a_pi_home_with_no_binary_is_not_offered(monkeypatch, tmp_path):
    """A home with no CLI is a leftover, not an installation — the same rule
    Codex gets, and the reason `instances()` asks `exe()` at all."""
    sb = Sandbox(monkeypatch, tmp_path)
    pi_home(sb.root, [('s1', 'C:\\work\\alpha', 1)], exe=False)
    assert 'pi' not in [h for _n, _d, h in harnesses.instances()]
    pi_home(sb.root, [], exe=True)
    assert 'pi' in [h for _n, _d, h in harnesses.instances()]


def test_a_pi_session_file_is_placed_by_its_path(monkeypatch, tmp_path):
    """`of_path` is what keeps `_parse_session`'s signature alone. A pi
    transcript lives under the pi home, so the file itself says which reader
    folds it."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\alpha', 1)])
    got = [p for d in pi._dirs(home) for _m, p in pi._files(d)]
    assert harnesses.of_path(got[0])['id'] == 'pi'
    assert harnesses.of_path(str(tmp_path / 'elsewhere.jsonl'))['id'] == 'claude'


# ── the directory name is never decoded ──────────────────────

def test_the_working_directory_is_read_not_decoded(monkeypatch, tmp_path):
    r"""pi maps every non-alphanumeric character to `-`, so `C:\work\a-b` and
    `C:\work\a\b` name the SAME directory. Decoding it is guesswork; the header
    of every session file carries the real `cwd`, which is exact.
    """
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\a-b', 1)])
    assert [p for _m, p, _e in pi.projects(home)] == ['C:\\work\\a-b']
    # the same session, renamed to something the encoding could never produce
    d = pi._dirs(home)[0]
    moved = os.path.join(os.path.dirname(d), '--totally-unrelated--')
    os.rename(d, moved)
    assert [p for _m, p, _e in pi.projects(home)] == ['C:\\work\\a-b']


def test_a_session_directory_with_no_sessions_is_not_a_project(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [])
    os.makedirs(os.path.join(home, 'sessions', '--C--work--empty--'))
    assert pi.projects(home) == []


# ── the session list ─────────────────────────────────────────

def test_a_turn_is_a_user_or_assistant_message_and_nothing_else(tmp_path):
    """Seven roles share the `message` entry type. A tool result, a bash line
    typed at the prompt, an extension's note and a compaction summary are the
    transcript's machinery — counting them reports a dozen turns for a session
    in which the user said one thing."""
    p = _session(str(tmp_path / 'a' / '2026_s1.jsonl'), 'C:\\w', 's1', turns=1)
    noise = [{'type': 'message', 'id': 'n%d' % i, 'parentId': None,
              'timestamp': '2026-09-14T21:40:00.000Z',
              'message': {'role': r, 'content': [{'type': 'text', 'text': 'x'}]}}
             for i, r in enumerate(('toolResult', 'bashExecution', 'custom',
                                    'branchSummary', 'compactionSummary'))]
    with open(p, 'a', encoding='utf-8') as f:
        for r in noise:
            f.write(json.dumps(r) + '\n')
    s = {'preview': '', 'count': 0}
    for obj in _iter(p):
        pi._turn(obj, s)
    assert s['count'] == 2
    assert s['preview'] == 'do it 0'


def _iter(p):
    with open(p, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def test_the_session_list_reads_the_same_tuple(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\alpha', 2),
                             ('s2', 'C:\\work\\alpha', 1)])
    folder = os.path.join(home, 'projects', pi.projects(home)[0][2])
    rows = sessions.scan_sessions(folder)
    assert [r[1] for r in rows] == ['s2', 's1']     # newest first
    assert [r[3] for r in rows] == [2, 4]
    assert rows[0][2] == 'do it 0'


def test_the_id_comes_from_the_header_not_the_file_name(monkeypatch, tmp_path):
    """The file name carries the uuid and the header carries the id, and they
    are the same today. Reading the name is what stops being true the first
    time a file is copied, renamed or migrated in place."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\alpha', 1)])
    d = pi._dirs(home)[0]
    old = pi._files(d)[0][1]
    new = os.path.join(d, '2026-09-14T21-38-00-000Z_not-the-id.jsonl')
    os.rename(old, new)
    folder = os.path.join(home, 'projects', pi.projects(home)[0][2])
    assert [r[1] for r in sessions.scan_sessions(folder)] == ['s1']
    assert store.transcript_path(folder, 's1') == new


def test_a_file_with_no_header_falls_back_to_its_name(monkeypatch, tmp_path):
    """Every entry in a pi session carries an `id`, and only the header's is
    the SESSION's — the rest are 8-char hex entry ids linking the tree. A
    truncated file whose first line is a message would otherwise be listed
    under one of those, and `transcript_path` would never find it again."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\alpha', 1)])
    d = pi._dirs(home)[0]
    p = pi._files(d)[0][1]
    lines = open(p, encoding='utf-8').read().splitlines()
    headless = os.path.join(d, '2026-09-14T21-38-09-000Z_from-the-name.jsonl')
    with open(headless, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines[1:]) + '\n')       # the header dropped
    assert pi._sid(headless) == 'from-the-name'
    assert pi.header(headless) == {}


def test_pi_has_no_archive(monkeypatch, tmp_path):
    """An archived listing is empty rather than the whole corpus — a harness
    that cannot archive must not answer the archived question with everything
    it has."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\alpha', 1)])
    folder = os.path.join(home, 'projects', pi.projects(home)[0][2])
    assert pi.scan(folder, archived=True) == []
    assert harnesses.cap('pi', 'archive')[0] is False
    assert harnesses.cap('pi', 'archive')[1]


# ── tokens ───────────────────────────────────────────────────

def test_the_four_token_fields_map_one_to_one(monkeypatch, tmp_path):
    """Unlike Codex, pi records a full four-way split per message, and the
    names line up with archeus's own: input/output/cacheRead/cacheWrite. There
    is nothing to reconstruct and nothing cumulative to difference."""
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\alpha', 3)])
    folder = os.path.join(home, 'projects', pi.projects(home)[0][2])
    st = sessions.get_session_stats(store.transcript_path(folder, 's1'))
    assert st['usage_by_model'] == {'claude-sonnet-4-5': {
        'in': 30, 'out': 15, 'cache_read': 9, 'cache_create': 6}}
    assert st['cwd'] == 'C:\\work\\alpha'
    assert st['count'] == 6


def test_a_refused_call_is_counted_as_an_error(tmp_path):
    """The 401 a session gets from a bad key is an assistant message with
    `stopReason: error`. It is the session's own record of a failed turn, and
    the sessions list already has a column for it."""
    s = dict(sessions._EMPTY_STATS)
    s['usage_by_model'], s['models'] = {}, []
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:38:10.306Z',
             'message': {'role': 'assistant', 'content': [], 'model': 'm',
                         'stopReason': 'error',
                         'errorMessage': '401 authentication_error'}}, s)
    assert s['api_errors'] == 1


def test_spend_a_tool_did_on_its_own_behalf_is_still_spend(tmp_path):
    """A `toolResult` carries `usage` for nested LLM work — a subagent-ish tool
    that called a model itself. It is not a turn, so it is not counted as one,
    but it is real tokens spent by this session."""
    s = dict(sessions._EMPTY_STATS)
    s['usage_by_model'], s['models'] = {}, []
    pi.fold({'type': 'model_change', 'modelId': 'm'}, s)
    pi.fold({'type': 'message',
             'message': {'role': 'toolResult', 'toolName': 'task',
                         'content': [], 'isError': False,
                         'usage': {'input': 7, 'output': 3,
                                   'cacheRead': 0, 'cacheWrite': 0}}}, s)
    assert s['count'] == 0
    assert s['usage_by_model']['m'] == {
        'in': 7, 'out': 3, 'cache_read': 0, 'cache_create': 0}


def test_the_fold_adds_no_field_the_cache_would_reject(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    home = pi_home(sb.root, [('s1', 'C:\\work\\alpha', 1)])
    folder = os.path.join(home, 'projects', pi.projects(home)[0][2])
    st = sessions.get_session_stats(store.transcript_path(folder, 's1'))
    assert st.keys() == sessions._EMPTY_STATS.keys()


# ── the shared surfaces ──────────────────────────────────────

def test_pi_projects_reach_the_one_walk(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    pi_home(sb.root, [('s1', actual, 1)])
    assert actual in [p for _m, p, _e, _h in store.all_projects()]


def test_pi_spend_reaches_the_usage_table(monkeypatch, tmp_path):
    """The corpus walk is `stats.iter_all_sessions`, and it goes through
    `scan_sessions` + `transcript_path` — so a harness whose transcripts are
    not `<folder>/<sid>.jsonl` is counted by all three consumers at once."""
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import stats as stats_mod
    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    home = pi_home(sb.root, [('s1', actual, 2)])
    enc = pi.projects(home)[0][2]
    rows = stats_mod.assemble_project_usage([(0, actual, enc, home)])
    assert len(rows) == 1
    assert rows[0]['sessions'] == 1
    assert rows[0]['usage'] == {'in': 20, 'out': 10,
                                'cache_read': 6, 'cache_create': 4}


def test_a_pi_print_run_is_an_inference_call():
    """`quota.preflight` gates on argv rather than on the caller, so a harness
    whose headless mode it does not recognise silently stops being gated."""
    assert harnesses.is_inference(['pi', '-p', 'do it'])
    assert harnesses.is_inference(['C:\\x\\pi.cmd', '--print', 'do it'])
    assert not harnesses.is_inference(['pi', 'list'])
    assert not harnesses.is_inference(['pi'])


def test_every_capability_pi_declares_is_a_real_one():
    """A descriptor naming a key `CAPS` does not have is a typo that would
    otherwise read as 'supported'."""
    assert set(harnesses.descriptor('pi')['caps']) <= set(harnesses.CAPS)
    for key in harnesses.descriptor('pi')['caps']:
        ok, why = harnesses.cap('pi', key)
        assert ok is False and why.strip(), key


def test_pi_keeps_the_skills_claude_code_has():
    """Not a gap: `~/.claude/skills` is one of the roots pi discovers, so a
    skill archeus installs for Claude Code is already loaded by pi. Greying the
    page would be wrong, and it is the only one of the six shared surfaces that
    is true of."""
    assert harnesses.cap('pi', 'skills')[0] is True
    for gone in ('mcp', 'hooks', 'agents', 'plugins'):
        assert harnesses.cap('pi', gone)[0] is False, gone


# ── launching pi ─────────────────────────────────────────────

def test_the_argv_is_pis_own_vocabulary():
    """From `pi --help` on the installed binary (0.85.1). pi takes a session by
    path OR partial uuid on `--session`/`--fork`, so the id archeus already
    holds is enough for both."""
    assert pi.launch_argv('pi.cmd', 'new', {}, 'D:/p') == ['pi.cmd']
    assert pi.launch_argv('pi.cmd', 'continue', {}, '')[1:] == ['-c']
    assert pi.launch_argv('pi.cmd', 'resume:abc', {}, '')[1:] == ['--session', 'abc']
    assert pi.launch_argv('pi.cmd', 'fork:abc', {}, '')[1:] == ['--fork', 'abc']
    assert pi.launch_argv('pi.cmd', 'resume-named::abc::x', {}, '')[1:] \
        == ['--session', 'abc']


def test_the_working_directory_is_not_a_flag():
    """pi has no `-C`. It works in the process's working directory, which is
    what `_direct_launch` already sets — passing one would be inventing a flag.
    """
    assert 'D:/p' not in pi.launch_argv('pi.cmd', 'new', {}, 'D:/p')


def test_effort_becomes_a_thinking_level_and_an_unknown_one_is_dropped():
    """pi's scale is a LEVEL, not a token budget: off/minimal/low/medium/high/
    xhigh/max. An effort archeus offers that pi does not have is dropped rather
    than rounded, so pi uses its own default — the honest answer to "this CLI
    does not have that setting"."""
    assert pi.launch_argv('pi.cmd', 'new', {'effort': 'high'}, '')[1:] \
        == ['--thinking', 'high']
    for orphan in ('ultrathink', 'auto', ''):
        assert '--thinking' not in pi.launch_argv('pi.cmd', 'new', {'effort': orphan}, '')


def test_a_name_is_only_for_a_new_session():
    assert pi.launch_argv('pi.cmd', 'new', {'name': 'x'}, '')[1:] == ['-n', 'x']
    assert '-n' not in pi.launch_argv('pi.cmd', 'resume:a', {'name': 'x'}, '')


def test_a_prompt_is_behind_the_option_terminator():
    """`--` is what stops a prompt beginning with a dash being read as a flag.
    pi's own help documents it for exactly this."""
    argv = pi.launch_argv('pi.cmd', 'new', {'prompt': '--not-a-flag'}, '')
    assert argv[-2:] == ['--', '--not-a-flag']


def test_the_launch_path_asks_the_harness_for_its_argv(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import main as main_mod
    home = pi_home(sb.root, [('s1', 'C:/work/alpha', 1)])
    args, env, _folder = main_mod.build_launch_command(
        'C:/work/alpha', 'C--work-alpha', 'resume:s1',
        {'cfgdir': home, 'effort': 'high', 'model': 'anthropic/claude-sonnet-5',
         'perm': 'default', 'name': 'x', 'worktree': '*'})
    assert os.path.basename(args[0]).startswith('pi')
    assert args[1:3] == ['--session', 's1']
    assert '--permission-mode' not in args and '-w' not in args
    assert env['PI_CODING_AGENT_DIR'] == home


# ── the catalogue pi ships, which is what fills a fresh install's picker ──────

def _fake_pkg(root, files):
    """An npm tree shaped like pi's, with a bin shim beside its node_modules.

    Built rather than pointed at the real installation for the reason the whole
    Sandbox exists: a test that reads the developer's own node_modules passes on
    this machine and nowhere else, and would have nothing to say when npm
    changes where it hoists a dependency.
    """
    binq = os.path.join(root, 'npm')
    data = os.path.join(binq, 'node_modules', '@earendil-works', 'pi-ai',
                        'dist', 'providers', 'data')
    os.makedirs(data, exist_ok=True)
    for name, obj in files.items():
        with open(os.path.join(data, name), 'w', encoding='utf-8') as f:
            json.dump(obj, f)
    shim = os.path.join(binq, 'pi.cmd')
    with open(shim, 'w') as f:
        f.write('@echo off\n')
    return shim


def _with_pkg(monkeypatch, root, files):
    shim = _fake_pkg(root, files)
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: shim if hid == 'pi' else None)
    pi._CAT.clear()
    return shim


_TWO = {
    'openai-codex.json': {'openai-codex-responses': {
        'gpt-5.5': {'id': 'gpt-5.5', 'name': 'GPT-5.5', 'provider': 'openai-codex',
                    'cost': {'input': 5, 'output': 30},
                    'contextWindow': 400000,
                    'thinkingLevelMap': {'minimal': 'minimal', 'xhigh': 'xhigh'}}}},
    'google.json': {'google-generative-ai': {
        'gemini-3.1-flash-lite': {'id': 'gemini-3.1-flash-lite',
                                  'name': 'Gemini 3.1 Flash Lite',
                                  'provider': 'google',
                                  'cost': {'input': 0.25, 'output': 1.5},
                                  'contextWindow': 1000000,
                                  'thinkingLevelMap': {'off': None}}}},
}


def test_the_catalogue_is_read_out_of_the_install(monkeypatch, tmp_path):
    """Not a list typed into this repo. `pi update` rewrites these files, so a
    static copy would be wrong the first time the user updated — the same
    argument `models()` makes for reading the CLI's own session history."""
    _with_pkg(monkeypatch, str(tmp_path), _TWO)
    rows = {r['id']: r for r in pi.catalogue()}
    assert set(rows) == {'openai-codex/gpt-5.5', 'google/gemini-3.1-flash-lite'}
    assert rows['openai-codex/gpt-5.5']['label'] == 'GPT-5.5'
    assert rows['openai-codex/gpt-5.5']['cost']['input'] == 5
    assert rows['google/gemini-3.1-flash-lite']['thinking'] == ['off']


def test_every_preset_names_a_model_the_catalogue_publishes():
    """A quick start whose model 404s on the first turn is worse than no button.
    Checked against the REAL installed catalogue, so this is the gate that fires
    the day a provider renames an id — which is the only way archeus would ever
    find out."""
    known = {r['id'] for r in pi.catalogue()}
    if not known:
        return                      # pi not installed here; nothing to check
    for _name, _blurb, fields in harnesses.HARNESSES['pi']['presets']:
        assert fields['model'] in known, fields['model']
        assert fields['effort'] in harnesses.HARNESSES['pi']['efforts']


def test_no_install_is_an_empty_catalogue_not_a_crash(monkeypatch):
    """The model field is free text. With pi absent there are no suggestions,
    which is a quieter picker and not a broken one."""
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: None)
    pi._CAT.clear()
    assert pi.catalogue() == []
    assert pi._data_dir() == ''


def test_one_unreadable_provider_file_does_not_lose_the_other_37(
        monkeypatch, tmp_path):
    """This tree is npm's, not archeus's, so a bad file there is not the fault
    `jsonstore` treats a corrupt file of OUR own as — the other providers are
    still the answer."""
    shim = _with_pkg(monkeypatch, str(tmp_path), _TWO)
    data = os.path.join(os.path.dirname(shim), 'node_modules', '@earendil-works',
                        'pi-ai', 'dist', 'providers', 'data')
    with open(os.path.join(data, 'broken.json'), 'w') as f:
        f.write('{not json')
    pi._CAT.clear()
    assert len(pi.catalogue()) == 2


def test_a_scalar_beside_the_catalogues_is_skipped(monkeypatch, tmp_path):
    """A provider file's top level is keyed by API name, and at least one ships
    a schema version alongside. Iterating it as a dict of models raised."""
    files = dict(_TWO)
    files['weird.json'] = {'version': 3, 'some-api': {
        'm1': {'id': 'm1', 'name': 'M1', 'provider': 'weird',
               'cost': {'input': 1, 'output': 2}}}}
    _with_pkg(monkeypatch, str(tmp_path), files)
    assert {r['id'] for r in pi.catalogue()} >= {'weird/m1'}


def test_the_catalogue_prices_a_model_no_anthropic_table_knows(
        monkeypatch, tmp_path):
    """The point of reading it at all. A gpt-5.5 session counted its tokens
    correctly and priced them at nothing, because every pattern in
    COST_PER_MTOK is an Anthropic id."""
    from claude_sessions import stats
    _with_pkg(monkeypatch, str(tmp_path), _TWO)
    stats._HARNESS_RATES.clear()
    cost, exact = stats.estimate_cost(
        {'gpt-5.5': {'in': 1_000_000, 'out': 1_000_000,
                     'cache_read': 0, 'cache_create': 0}})
    assert exact and cost == 35.0          # 1M x $5 in + 1M x $30 out
    stats._HARNESS_RATES.clear()


def test_a_model_nothing_publishes_a_price_for_stays_unpriced(
        monkeypatch, tmp_path):
    """No guess. An opus-tier fallback on a gpt-5.6-luna session would be wrong
    by a factor of fifty, and `n/a` is the honest cell."""
    from claude_sessions import stats
    _with_pkg(monkeypatch, str(tmp_path), _TWO)
    stats._HARNESS_RATES.clear()
    cost, exact = stats.estimate_cost(
        {'some-local-llama': {'in': 1_000_000, 'out': 1_000_000,
                              'cache_read': 0, 'cache_create': 0}})
    assert not exact and cost == 0.0
    assert stats.fmt_cost(cost, exact) == 'n/a'
    stats._HARNESS_RATES.clear()


def test_an_exact_id_beats_a_substring_pattern():
    """COST_PER_MTOK is matched by SUBSTRING, so merging a thousand catalogue
    ids into it would let a short key like `gpt-5` claim `gpt-5.6-terra`. The
    two tables are separate and the exact lookup runs first."""
    from claude_sessions import stats
    table = {'sonnet': {'in': 3.0, 'out': 15.0},
             'claude-sonnet-5': {'in': 1.0, 'out': 2.0}}
    rates, known = stats._rates_for('claude-sonnet-5', table)
    assert known and rates['in'] == 1.0            # exact, not the substring


# ── a machine with only pi and a local model ─────────────────────────────────

def _settings(sb, **kw):
    from claude_sessions import config
    s = dict(config._DEFAULT_SETTINGS)
    s.update(kw)
    sb.settings.write_text(json.dumps(s), encoding='utf-8')


def test_a_quick_resume_does_not_hand_pi_claude_defaults(monkeypatch, tmp_path):
    """Quick resume sends Claude Code's default model and effort. pi cannot
    resolve a bare Claude id (`Model "claude-opus-5" is ambiguous across
    providers`) and exits, so the session never reopened."""
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import main as main_mod
    home = pi_home(sb.root, [('s1', 'C:/work/alpha', 1)])
    args, _env, _f = main_mod.build_launch_command(
        'C:/work/alpha', 'C--work-alpha', 'resume:s1',
        {'cfgdir': home, 'effort': 'ultracode', 'model': 'claude-opus-5'})
    assert '--model' not in args and '--thinking' not in args
    # pi's own provider/id form is a real choice and survives
    args, _env, _f = main_mod.build_launch_command(
        'C:/work/alpha', 'C--work-alpha', 'resume:s1',
        {'cfgdir': home, 'effort': 'high', 'model': 'spark/qwen3.8'})
    assert args[args.index('--model') + 1] == 'spark/qwen3.8'
    assert args[args.index('--thinking') + 1] == 'high'


def _headless(monkeypatch, fn, *a, **kw):
    from claude_sessions import memory, gui_api
    seen = {}

    def fake(args, **k):
        seen['args'], seen['input'], seen['env'] = args, k.get('input_text'), k.get('env')
        return seen.get('reply', '')
    monkeypatch.setattr(gui_api, '_run_cancellable', fake)
    memory._tls.silent = True
    try:
        seen['out'] = fn(*a, **kw)
    finally:
        memory._tls.silent = False
    return seen


def test_memory_runs_on_pi_when_claude_is_not_installed(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import config, memory
    home = pi_home(sb.root)
    monkeypatch.setattr(config, 'get_claude_exe', lambda: None)
    _settings(sb, headless_harness_model='spark/qwen3.8')
    assert memory.headless_harness() == 'pi'
    seen = _headless(monkeypatch, memory._claude_stdin, 'hello', cwd='.',
                     model='claude-haiku-4-5', extra_args=('--json-schema', '{}'))
    args = seen['args']
    assert os.path.basename(args[0]).startswith('pi')
    assert args[1:] == ['-p', '--no-session', '--tools', 'read,grep,find,ls',
                        '--model', 'spark/qwen3.8']
    assert seen['input'].startswith('hello')
    assert seen['env']['PI_CODING_AGENT_DIR'] == home


def test_an_explicit_choice_beats_an_installed_claude(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import config, memory
    pi_home(sb.root)
    monkeypatch.setattr(config, 'get_claude_exe', lambda: r'C:\fake\claude.exe')
    assert memory.headless_harness() == 'claude'
    _settings(sb, headless_harness='pi')
    assert memory.headless_harness() == 'pi'


def test_nothing_installed_says_so(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import config, memory
    monkeypatch.setattr(config, 'get_claude_exe', lambda: None)
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: None)
    _settings(sb, headless_harness='pi')
    seen = _headless(monkeypatch, memory._claude_stdin, 'hello', cwd='.')
    assert seen['out'] == '' and 'args' not in seen
    assert 'pi' in memory.why_failed()


def test_structured_calls_on_pi_ask_for_the_shape_in_words(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import config, memory, gui_api
    pi_home(sb.root)
    monkeypatch.setattr(config, 'get_claude_exe', lambda: None)
    _settings(sb)
    sent = {}
    monkeypatch.setattr(gui_api, '_run_cancellable', lambda args, **k: (
        sent.update(args=args, prompt=k['input_text']),
        'Here you go:\n{"entities": [{"name": "x"}]}')[1])
    memory._tls.silent = True
    try:
        got = memory._claude_json('extract', '.', {'type': 'object', 'title': 'GRAPH'})
    finally:
        memory._tls.silent = False
    assert got == {'entities': [{'name': 'x'}]}
    assert '"title": "GRAPH"' in sent['prompt']
    assert '--json-schema' not in sent['args']


def test_a_hand_off_to_pi_launches_pi_with_the_pointer(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    from claude_sessions import config, gui_api, proc
    from claude_sessions.paths import encode_component
    from harness import make_jsonl
    home = pi_home(sb.root)
    actual = str(tmp_path / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = encode_component(actual)
    folder = os.path.join(str(sb.projects), enc)
    os.makedirs(folder, exist_ok=True)
    sid = 'aaaa0000-0000-0000-0000-000000000000'
    make_jsonl(os.path.join(folder, sid + '.jsonl'), title='Fix the bug')
    monkeypatch.setattr(config, 'get_claude_exe', lambda: None)
    spawned = []
    monkeypatch.setattr(proc, 'spawn_terminal',
                        lambda args, **k: (spawned.append((args, k)), (object(), ''))[1])
    r = gui_api.api_inject_launch({}, {'path': actual, 'enc': enc, 'cfgdir': str(sb.cfg),
                                       'sid': sid, 'account': 'default',
                                       'target_cfgdir': home})
    assert r == {'ok': True}
    args, k = spawned[0]
    assert os.path.basename(args[0]).startswith('pi')
    assert args[-2] == '--' and 'injected-context.md' in args[-1]
    assert k['env']['PI_CODING_AGENT_DIR'] == home
    assert os.path.isfile(os.path.join(actual, '.archeus', 'injected-context.md'))


def test_project_setup_reports_a_count_not_a_crash(monkeypatch, tmp_path):
    """`_memfn` already counts the entities; `len()` of that int was the
    `TypeError: object of type 'int' has no len()` the setup job died on."""
    Sandbox(monkeypatch, tmp_path)
    from claude_sessions import gui_api, memory, claude_md
    monkeypatch.setattr(claude_md, 'scaffold_claude_md', lambda p, f: True)
    monkeypatch.setattr(memory, 'refresh_memory',
                        lambda p, f, n: {'entities': [{'name': 'a'}, {'name': 'b'}]})
    ran = {}
    monkeypatch.setattr(gui_api, 'start_job',
                        lambda label, fn: ran.setdefault('r', fn()) and 'j1')
    gui_api.api_job_start({}, {'kind': 'project_setup', 'path': str(tmp_path),
                               'folder': str(tmp_path), 'name': 'p'})
    assert ran['r'] == {'claude_md': True, 'entities': 2}
