"""Output styles, checkpoints and the OTEL launch env.

Two of these three read or write files that belong to Claude Code, so the tests
that matter are the ones about restraint:

  · `select()` must carry every other key in settings.json through untouched.
  · `checkpoints` must return "not recognised" rather than a guess when the
    undocumented store stops looking the way it looks today.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import checkpoints, outputstyles, statusline


# ── output styles ─────────────────────────────────────────────

def _proj(tmp_path):
    p = tmp_path / 'proj'
    (p / '.claude' / 'output-styles').mkdir(parents=True)
    return str(p)


def test_builtins_are_offered_even_though_they_are_not_on_disk(tmp_path):
    styles = outputstyles.listing(_proj(tmp_path), str(tmp_path / 'cfg'))
    names = [s['name'] for s in styles]
    assert names[:3] == ['default', 'Explanatory', 'Learning']
    assert all(s['builtin'] for s in styles[:3])


def test_a_custom_style_is_read_from_its_frontmatter(tmp_path):
    proj = _proj(tmp_path)
    (tmp_path / 'proj' / '.claude' / 'output-styles' / 'reviewer.md').write_text(
        '---\nname: Reviewer\ndescription: Reviews, never writes.\n---\n\nBody.\n',
        encoding='utf-8')
    styles = outputstyles.listing(proj, str(tmp_path / 'cfg'))
    s = [x for x in styles if x['name'] == 'Reviewer'][0]
    assert s['description'] == 'Reviews, never writes.'
    assert s['scope'] == 'project'
    assert outputstyles.read('Reviewer', proj, str(tmp_path / 'cfg')) == 'Body.'


def test_selecting_a_style_preserves_every_other_settings_key(tmp_path):
    """THE test for this module. settings.json belongs to Claude Code and holds
    hooks, permissions and env; writing one key must not cost the others."""
    proj = _proj(tmp_path)
    sp = os.path.join(proj, '.claude', 'settings.json')
    with open(sp, 'w', encoding='utf-8') as fh:
        json.dump({'hooks': {'Stop': [{'x': 1}]},
                   'permissions': {'allow': ['Bash(ls:*)']},
                   'env': {'FOO': 'bar'}}, fh)
    ok, _ = outputstyles.select('Explanatory', proj)
    assert ok
    after = json.load(open(sp, encoding='utf-8'))
    assert after['outputStyle'] == 'Explanatory'
    assert after['hooks'] == {'Stop': [{'x': 1}]}
    assert after['permissions'] == {'allow': ['Bash(ls:*)']}
    assert after['env'] == {'FOO': 'bar'}


def test_default_clears_the_key_instead_of_pinning_it(tmp_path):
    """'default' means "no override". Writing it as a value would freeze the
    behaviour against a future change in what default means."""
    proj = _proj(tmp_path)
    sp = os.path.join(proj, '.claude', 'settings.json')
    outputstyles.select('Learning', proj)
    assert json.load(open(sp, encoding='utf-8'))['outputStyle'] == 'Learning'
    outputstyles.select('default', proj)
    assert 'outputStyle' not in json.load(open(sp, encoding='utf-8'))


def test_project_settings_shadow_user_settings(tmp_path):
    proj = _proj(tmp_path)
    cfg = tmp_path / 'cfg'
    cfg.mkdir()
    (cfg / 'settings.json').write_text('{"outputStyle": "Learning"}', encoding='utf-8')
    assert outputstyles.current(None, str(cfg)) == 'Learning'
    outputstyles.select('Explanatory', proj)
    assert outputstyles.current(proj, str(cfg)) == 'Explanatory'


def test_a_builtin_cannot_be_deleted(tmp_path):
    ok, msg = outputstyles.delete('Explanatory', _proj(tmp_path))
    assert ok is False and 'ships with Claude Code' in msg


def test_a_saved_style_round_trips(tmp_path):
    proj = _proj(tmp_path)
    ok, _ = outputstyles.save('Code Review', 'Reviews only.', 'Be terse.', proj)
    assert ok
    # the name is slugged for the filename but kept verbatim in frontmatter
    assert os.path.isfile(os.path.join(proj, '.claude', 'output-styles',
                                       'Code-Review.md'))
    names = [s['name'] for s in outputstyles.listing(proj, str(tmp_path / 'c'))]
    assert 'Code Review' in names


def test_viewing_a_builtin_explains_itself_instead_of_showing_nothing(tmp_path):
    """`read()` returned '' for anything not on disk, and all three built-ins
    are not on disk — so the view button rendered "(empty)" on the styles most
    people have, which reads as a dead button rather than as an empty file."""
    text = outputstyles.read('Explanatory', _proj(tmp_path), str(tmp_path / 'cfg'))
    assert text and 'ships inside Claude Code' in text
    assert 'Explains its reasoning' in text, 'the description is the useful half'


def test_every_starter_is_a_usable_style(tmp_path):
    """A starter is offered as something you can read and copy, so it has to
    hold up as a document — an empty or nameless one would install a file that
    changes nothing."""
    rows = outputstyles.starters()
    assert len(rows) >= 4
    for s in rows:
        assert s['name'] and s['description']
        assert len(s['body'].splitlines()) >= 5, s['name']
        assert s['scope'] == 'starter' and not s['builtin']
    names = {s['name'].lower() for s in rows}
    builtin = {n.lower() for n, _d in outputstyles.BUILTIN}
    assert not (names & builtin), 'a starter must not shadow a built-in'


def test_a_starter_can_be_read_before_it_is_installed(tmp_path):
    body = outputstyles.read('Terse', None, str(tmp_path / 'cfg'))
    assert 'No preamble' in body


def test_installing_a_starter_produces_an_ordinary_style(tmp_path):
    """Nothing stays linked to archeus: what lands on disk is a normal
    markdown style the user owns, listed like any other."""
    cfg = str(tmp_path / 'cfg')
    ok, msg = outputstyles.install_starter('Reviewer', None, cfg)
    assert ok, msg
    assert os.path.isfile(os.path.join(cfg, 'output-styles', 'Reviewer.md'))
    row = next(s for s in outputstyles.listing(None, cfg) if s['name'] == 'Reviewer')
    assert row['scope'] == 'user' and not row['builtin']
    ok, _ = outputstyles.delete('Reviewer', None, cfg)
    assert ok


def test_an_unknown_starter_is_refused(tmp_path):
    ok, msg = outputstyles.install_starter('nope', None, str(tmp_path / 'cfg'))
    assert not ok and 'nope' in msg


def test_the_active_scope_says_which_file_won(tmp_path):
    """Two settings.json files can both name a style and only one is in force.
    Without this the page could show the winner but not where it came from —
    so a user changing the wrong file saw nothing happen."""
    proj = _proj(tmp_path)
    cfg = str(tmp_path / 'cfg')
    assert outputstyles.active_scope(proj, cfg) == ''
    outputstyles.select('Learning', None, cfg)
    assert outputstyles.active_scope(proj, cfg) == 'user'
    outputstyles.select('Explanatory', proj, cfg)
    assert outputstyles.active_scope(proj, cfg) == 'project'
    assert outputstyles.current(proj, cfg) == 'Explanatory'


# ── checkpoints ───────────────────────────────────────────────

def _px(name):
    """An absolute path shaped like the host platform's own.

    These fixtures used a literal `D:\\x\\...`, but checkpoints derives the
    display name with os.path.basename, and '\\' is an ordinary filename
    character on POSIX — so the whole string came back as the basename there.
    """
    return os.path.join('D:\\x' if os.name == 'nt' else '/x', name)


def _ckpt(tmp_path, paths, versions=2):
    """A file-history store built the way the real one is named."""
    cfg = tmp_path / 'cfg'
    sdir = cfg / 'file-history' / 'sid1'
    sdir.mkdir(parents=True)
    for i, p in enumerate(paths):
        key = hashlib.sha256(p.encode()).hexdigest()[:16]
        for v in range(1, versions + 1):
            (sdir / f'{key}@v{v}').write_text(f'line {i}\nv{v}\n', encoding='utf-8')
    jsonl = tmp_path / 't.jsonl'
    with open(jsonl, 'w', encoding='utf-8') as fh:
        for p in paths:
            fh.write(json.dumps({'message': {'content': [
                {'type': 'tool_use', 'name': 'Edit',
                 'input': {'file_path': p}}]}}) + '\n')
    return str(cfg), str(jsonl)


def test_snapshots_are_matched_to_the_files_the_session_edited(tmp_path):
    cfg, jsonl = _ckpt(tmp_path, [_px('a.py'), _px('b.py')])
    h = checkpoints.history('sid1', jsonl, cfg)
    assert h['recognised'] is True and h['orphans'] == 0
    assert sorted(f['name'] for f in h['files']) == ['a.py', 'b.py']
    assert [v['v'] for v in h['files'][0]['versions']] == [1, 2]


def test_an_unrecognised_store_says_so_rather_than_guessing(tmp_path):
    """The load-bearing safety property. The naming scheme is undocumented; if
    it moves, the honest answer is "I can't read this", not an arbitrary
    pairing of snapshots to filenames."""
    cfg, jsonl = _ckpt(tmp_path, [_px('a.py')])
    sdir = tmp_path / 'cfg' / 'file-history' / 'sid1'
    for f in sdir.iterdir():                     # rename to a scheme we can't map
        f.rename(sdir / ('ffffffffffffffff@v' + f.name.rsplit('v', 1)[1]))
    h = checkpoints.history('sid1', jsonl, cfg)
    assert h['recognised'] is False
    assert h['files'] == []


def test_unmatched_snapshots_are_counted_not_invented(tmp_path):
    cfg, jsonl = _ckpt(tmp_path, [_px('a.py'), _px('b.py')])
    # a transcript that only remembers one of the two files
    with open(jsonl, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps({'message': {'content': [
            {'type': 'tool_use', 'name': 'Edit',
             'input': {'file_path': _px('a.py')}}]}}) + '\n')
    h = checkpoints.history('sid1', jsonl, cfg)
    assert h['recognised'] is True
    assert len(h['files']) == 1
    assert h['orphans'] == 1


def test_a_session_with_no_store_is_empty_not_an_error(tmp_path):
    h = checkpoints.history('nope', str(tmp_path / 'missing.jsonl'), str(tmp_path))
    assert h == {'recognised': True, 'files': [], 'orphans': 0, 'store': False}


def test_versions_diff_against_each_other(tmp_path):
    cfg, jsonl = _ckpt(tmp_path, [_px('a.py')])
    d = checkpoints.diff_versions('sid1', _px('a.py'), 1, 2, cfg)
    assert '-v1' in d and '+v2' in d


def test_nothing_here_writes(tmp_path):
    """Read-only is a promise, not a convention: /rewind stays the only thing
    that restores, so this module must not contain a write path at all."""
    import inspect
    src = inspect.getsource(checkpoints)
    for w in ("open(full, 'w'", 'os.remove', 'os.rename', 'shutil.copy',
              'shutil.rmtree', 'os.unlink'):
        assert w not in src, w


def test_only_edit_tools_contribute_paths(tmp_path):
    """A Read of a file leaves no snapshot; counting it would produce phantom
    rows that never resolve and inflate the orphan count."""
    cfg, jsonl = _ckpt(tmp_path, [_px('a.py')])
    with open(jsonl, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps({'message': {'content': [
            {'type': 'tool_use', 'name': 'Read',
             'input': {'file_path': _px('never-edited.py')}}]}}) + '\n')
    assert checkpoints._edited_paths(jsonl) == [_px('a.py')]


# ── statusline preview / OTEL ─────────────────────────────────

def test_the_gui_preview_carries_no_terminal_escapes():
    line = statusline.plain(statusline.render(
        {'model': {'display_name': 'Opus 5'},
         'workspace': {'current_dir': os.getcwd()}}))
    assert '\x1b' in statusline.render(
        {'model': {'display_name': 'Opus 5'},
         'workspace': {'current_dir': os.getcwd()}}), 'terminal output lost colour'
    assert '\x1b' not in line and 'Opus 5' in line


def test_otel_env_is_empty_unless_both_enabled_and_pointed_somewhere():
    from claude_sessions import config
    assert config.otel_env({'otel_enabled': False,
                            'otel_endpoint': 'http://x:4318'}) == {}
    assert config.otel_env({'otel_enabled': True, 'otel_endpoint': ''}) == {}


def test_otel_never_turns_on_prompt_logging_by_itself():
    """The first question anyone asks about telemetry. The toggle exports
    metrics; it must not opt you into shipping prompt text."""
    from claude_sessions import config
    env = config.otel_env({'otel_enabled': True,
                           'otel_endpoint': 'http://localhost:4318',
                           'otel_protocol': 'http/protobuf',
                           'otel_headers': 'Authorization=Bearer t'})
    assert env['CLAUDE_CODE_ENABLE_TELEMETRY'] == '1'
    assert env['OTEL_EXPORTER_OTLP_ENDPOINT'] == 'http://localhost:4318'
    assert 'OTEL_LOG_USER_PROMPTS' not in env
