"""T-1186 — the ten highest-risk uncovered branches of pi's reader.

Slice under test: ``claude_sessions/pi.py`` lines **1-327 inclusive** at tip
``56d53504`` — the pi reader: ``_dirs``, ``_files``, ``header``, ``_sid``,
``_cwd_of``, ``projects``, ``has_project``, ``_home_of``, ``_dir_for``,
``scan``, ``transcript_path``, ``_text``, ``_turn``, ``fold``,
``launch_argv``, ``headless_argv``. Definitions and imports past line 327 are
read-only context; the two functions that cross the endpoint (``launch_argv``
ends at 299, ``headless_argv`` at 313, ``models`` starts at 328) stay owned by
this slice because their branches begin inside it.

The ten branches this file pins, in risk order (fail-closed and denial first,
then boundaries, then error paths), plus one extra at the end. Evidence for
"uncovered": a line/arc trace of ``tests/test_pi.py`` (the existing coverage
the card names) over this slice, confirmed per branch by running
``tests/test_pi.py`` against the mutated source — mutating the branch and its
neighbour (``or``→``and``, dropping a guard, inverting an ordering) left
``tests/test_pi.py`` green apart from its one environment-dependent test,
while the test named here failed on the same mutation:

 1. ``pi.py:40``  ``_dirs`` joins ``home or ''`` — an UNNAMED home reads
    ``<cwd>/sessions`` (closest: ``test_pi.py::test_a_session_directory_with_no_
    sessions_is_not_a_project``, which always names a real home).
 2. ``pi.py:138-142, 167-170``  ``_dir_for``/``transcript_path`` answer ``''``
    (closest: ``test_pi.py::test_the_id_comes_from_the_header_not_the_file_name``,
    which only ever asks for an id that exists).
 3. ``pi.py:311``  ``headless_argv(no_tools=True)`` — the ``--no-extensions``
    half of the tool fence (closest: ``test_pi.py::test_memory_runs_on_pi_when_
    claude_is_not_installed``, which only ever takes the ``no_tools=False`` arm).
 4. ``pi.py:252-261``  a NON-NUMERIC usage figure raises out of ``fold`` and
    kills the corpus walk (closest: ``test_pi.py::test_the_four_token_fields_map_
    one_to_one``, whose numbers are all well-formed).
 5. ``pi.py:252-255``  absent/empty usage creates no accounting row, and the
    ``'pi'`` key only for a record that really carries usage (closest:
    ``test_pi.py::test_the_fold_adds_no_field_the_cache_would_reject``, which
    compares key NAMES and would pass with a phantom row of zeros).
 6. ``pi.py:228-236``  ``model_change`` re-ordering — the line ``s['models']
    .remove(m)`` (234) is never executed (closest: ``test_pi.py::test_a_refused_call_
    is_counted_as_an_error``, which folds one model change).
 7. ``pi.py:247-248``  the error counter per record, the ``errorMessage``-only
    arm of the ``or``, and a non-``message`` record that must never count
    (closest: ``test_pi.py::test_a_refused_call_is_counted_as_an_error``, whose
    single record carries BOTH fields, so ``or`` and ``and`` read the same).
 8. ``pi.py:80, 90-91``  a first line that parses to NOTHING (a truncated
    file) — ``header``'s second ``return {}`` (80) and the whole-name ``_sid``
    fallback (91), for a name with no ``_`` at all (closest: ``test_pi.py::
    test_a_file_with_no_header_falls_back_to_its_name``, whose first line is a
    well-formed ``model_change`` — so ``iter_json`` still yields an object, and
    whose every file name carries a timestamp — so ``rest or base`` never has
    to reach ``base``). The companion assertion that a directory of only
    unreadable files is no project (pi.py:112-113) is shared with
    ``test_a_session_directory_with_no_sessions_is_not_a_project``.
 9. ``pi.py:295-298``  ``--append-system-prompt`` composed with a prompt: the
    terminator must still be the last option (closest: ``test_pi.py::test_a_
    prompt_is_behind_the_option_terminator``, which never sets
    ``system_prompt_file`` — line 296 is never executed at all).
10. ``pi.py:61-67``  one unreadable session file is dropped, not the whole
    directory, and a stray non-``.jsonl`` entry is ignored (closest:
    ``test_pi.py::test_a_session_directory_with_no_sessions_is_not_a_project``,
    whose directory holds nothing at all).

 11. beyond the ten, ``pi.py:176-177, 201-202``  ``_text``'s plain-string fast
     path and the ``if txt:`` guard on the preview — a user message whose
     ``content`` is a string, and an empty user turn that must not blank the
     preview the previous turn set (closest: ``test_pi.py::
     test_a_turn_is_a_user_or_assistant_message_and_nothing_else``, which only
     ever builds list-of-blocks content and always has something to say).

Replaced probes: "toolResult usage without a conversational turn" is already
pinned by ``test_pi.py::test_spend_a_tool_did_on_its_own_behalf_is_still_spend``
and "an unsupported effort is omitted" by ``test_pi.py::
test_effort_becomes_a_thinking_level_and_an_unknown_one_is_dropped``; both were
swapped for genuinely uncovered branches (5 and 10 above). The effort boundary
is still re-pinned here, in the argv test, as a composition with the terminator.

Everything the reader could reach outside this file is faked before it is
entered — config roots, settings, the selected pi homes, account discovery, the
credential reader, the model/picker readers, the editor, the job scheduler and
every process runner (``pytest`` raises from all of them here). Inputs are
invented; nothing under the real user home is opened.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                        # noqa: E402

from claude_sessions import config, gui_api, harnesses, paths, pi, proc, sessions  # noqa: E402
from harness import Sandbox                          # noqa: E402

JSONL_NEWLINE = b'\n'


# ── the sealed world ─────────────────────────────────────────────────────

@pytest.fixture
def world(tmp_path, monkeypatch):
    """A pi home under tmp_path and nothing outside it that can be reached.

    Every seam that could read the machine is pinned BEFORE the reader is
    entered: the selected homes and account discovery (`homes`/`instances`),
    the binary probe (`exe`), the credential reader (`auth_state`, which reads
    `auth.json`), the picker readers (`models`, `catalogue`, `configured`,
    `_declared_*`), the process runners (`proc.run`, `proc.spawn_terminal`),
    the editor and the job scheduler. Each of the last group raises, so a test
    that quietly grows a privileged side effect fails here rather than passing
    while reading the developer's own `~/.pi`.
    """
    sb = Sandbox(monkeypatch, tmp_path)
    state = {'homes': [], 'spawned': [], 'edited': []}

    def _boom(what):
        def go(*a, **k):
            raise AssertionError('T-1186 must not reach %s: %r' % (what, a[:1]))
        return go

    # no pi binary is installed on this machine as far as the reader knows, so
    # nothing can probe PATH or spawn the real CLI by accident
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: None)
    # the selected homes are THESE, invented ones, for every harness probe
    monkeypatch.setattr(harnesses, 'homes',
                        lambda hid=None: (list(state['homes']) if hid == 'pi' else []))
    monkeypatch.setattr(harnesses, 'instances',
                        lambda: [(n, d, 'pi') for n, d in state['homes']])
    # an unnamed home must land inside the sandbox, never on the real profile
    monkeypatch.setattr(harnesses, 'home_dir', lambda hid=None: str(tmp_path / 'no-home'))
    for name in ('auth_state', 'configured', 'doctor', 'catalogue', 'models',
                 '_declared_models', '_declared_contexts', '_list_models',
                 '_version', '_data_dir'):
        monkeypatch.setattr(pi, name, _boom('pi.' + name))
    for name in ('run', 'spawn_terminal'):
        monkeypatch.setattr(proc, name, _boom('proc.' + name))
    monkeypatch.setattr(gui_api, 'start_job', _boom('gui_api.start_job'))
    monkeypatch.setattr(config, 'open_in_editor',
                        lambda p: (state['edited'].append(p), True)[1])
    # an empty directory to run FROM: a test that hands the reader no home at
    # all must not be answered out of whatever the real cwd happens to hold
    quiet = os.path.join(str(tmp_path), 'quiet')
    os.makedirs(quiet, exist_ok=True)
    state['quiet'] = quiet
    state['tmp'] = tmp_path
    state['sb'] = sb
    return state


# ── invented session pieces (nothing here is read from a real home) ──────

def _line(obj):
    return json.dumps(obj, sort_keys=True).encode('utf-8')


def _write(path, raw_lines):
    """One session file, written with explicit newline BYTES."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        for raw in raw_lines:
            f.write(raw + JSONL_NEWLINE)
    return path


def _header(sid, cwd, ts='2026-09-14T21:38:10.048Z'):
    return _line({'type': 'session', 'version': 3, 'id': sid,
                  'timestamp': ts, 'cwd': cwd})


def _message(role, text='', model=None, usage=None, **kw):
    m = {'role': role, 'content': [{'type': 'text', 'text': text}]}
    if model is not None:
        m['model'] = model
    if usage is not None:
        m['usage'] = usage
    m.update(kw)
    return _line({'type': 'message', 'id': 'm' + role[:4], 'parentId': None,
                  'timestamp': '2026-09-14T21:39:00.000Z', 'message': m})


def _home(root, name, sessions_dir):
    """`<root>/<name>` as a pi home whose `sessions/` holds *sessions_dir*.

    *sessions_dir* is {encoded directory name: [(file name, [raw line, ...])]}.
    """
    home = os.path.join(str(root), name)
    for dname, files in sessions_dir.items():
        d = os.path.join(home, 'sessions', dname)
        for fname, raw in files:
            _write(os.path.join(d, fname), raw)
    os.makedirs(os.path.join(home, 'sessions'), exist_ok=True)
    return home


def _dir_name(cwd):
    """pi's own directory name for *cwd*: every non-alphanumeric to `-`,
    wrapped in `--`. Written here, never decoded by the reader."""
    return '--' + ''.join(c if c.isalnum() else '-' for c in cwd) + '--'


def _stats():
    return {'preview': '', 'count': 0, 'title': '', 'usage_by_model': {},
            'models': [], 'first_ts': None, 'last_ts': None, 'branch': '',
            'cwd': '', 'api_errors': 0, 'headless': False}


# ── 1. an unnamed home must read NOTHING, not the working directory ─────

def test_an_unnamed_home_reads_no_store_from_the_working_directory(world, monkeypatch):
    """A folder that names no home is a DENIAL, not a fallback to `.`.

    `_dirs` is the only reader of the store's existence, and `os.path.join('',
    'sessions')` is `sessions`: whoever starts archeus with a `sessions`
    directory beside it — a checkout, a tmp run dir, any harness whose cwd is a
    project — becomes a pi home the user never selected, and its sessions are
    listed, priced and opened. The two fakes in `world` prove the test is not
    leaning on a real `~/.pi`; this asserts the other half.
    """
    tmp = world['tmp']
    foreign = os.path.join(str(tmp), 'cwdwithstore')
    victim = 'C:\\victim'
    # a store that belongs to no home this test ever named, sitting in the
    # directory the process happens to run from
    d = os.path.join(foreign, 'sessions', _dir_name(victim))
    _write(os.path.join(d, '2026-09-14T21-38-00-000Z_foreign-1.jsonl'),
           [_header('foreign-1', victim)])
    monkeypatch.chdir(foreign)

    assert pi._dirs('') == []
    assert pi._dirs(None) == []
    assert pi.projects('') == []
    assert pi.projects(None) == []
    assert pi.has_project('', paths.encode_component(victim)) is False
    # and the store is still there, so the emptiness above is a denial and not
    # an artefact of a fixture that built nothing
    assert pi.projects(foreign) != []


# ── 2. a folder that matches nothing denies, and never the other home ───

def test_a_folder_that_matches_nothing_denies_without_another_home(world, monkeypatch):
    """`_dir_for`/`transcript_path` answering `''` is the whole denial.

    Two homes, one session each, and a sidecar folder in home A whose encoded
    name belongs to home B's project. `projects()` is asked of the session
    store (the sidecar folder is created lazily), so the answer must come from
    home A alone: an empty listing, no transcript path, and never B's row read
    as if it were A's.
    """
    tmp = world['tmp']
    cwd_a, cwd_b = 'C:\\work\\alpha', 'C:\\work\\beta'
    home_a = _home(tmp, 'homeA', {_dir_name(cwd_a): [
        ('2026-09-14T21-38-00-000Z_sid-a.jsonl',
         [_header('sid-a', cwd_a), _message('user', 'alpha said')])]})
    home_b = _home(tmp, 'homeB', {_dir_name(cwd_b): [
        ('2026-09-14T21-38-01-000Z_sid-b.jsonl',
         [_header('sid-b', cwd_b), _message('user', 'beta said')])]})
    world['homes'] = [('A', home_a), ('B', home_b)]
    monkeypatch.chdir(world['quiet'])            # no relative fallback

    # the control: the same code, holding the right name, does answer
    folder_a = os.path.join(home_a, 'projects', paths.encode_component(cwd_a))
    assert pi._dir_for(folder_a) == os.path.join(home_a, 'sessions', _dir_name(cwd_a))
    assert [r[1] for r in pi.scan(folder_a)] == ['sid-a']
    assert pi.transcript_path(folder_a, 'sid-a').endswith('sid-a.jsonl')
    assert pi.has_project(home_a, paths.encode_component(cwd_a)) is True

    # home A's folder, asked for B's project: nothing, and not B's answer
    folder_wrong = os.path.join(home_a, 'projects', paths.encode_component(cwd_b))
    assert pi._dir_for(folder_wrong) == ''
    assert pi.scan(folder_wrong) == []
    assert pi.transcript_path(folder_wrong, 'sid-b') == ''
    assert pi.transcript_path(folder_a, 'no-such-session') == ''
    assert pi.has_project(home_a, paths.encode_component(cwd_b)) is False
    # a home that is not there at all denies the same way
    assert pi._dir_for(os.path.join(str(tmp), 'gone', 'projects', 'x')) == ''
    assert pi.scan(os.path.join(str(tmp), 'gone', 'projects', 'x')) == []
    assert pi.has_project(os.path.join(str(tmp), 'gone'), 'x') is False
    assert world['spawned'] == [] and world['edited'] == []


# ── 3. the tool fence ────────────────────────────────────────────────────

def test_no_tools_without_no_extensions_is_not_a_fence(world):
    """`--no-tools` alone only changes pi's DEFAULT tool.

    `headless_argv(no_tools=True)` is the argv archeus puts on its OWN
    one-shot calls; the docstring at pi.py:302-310 says the reason
    `--no-extensions` rides with it is that an extension can bring a tool back.
    Dropping that second flag is invisible to every existing test, because the
    only pi headless argv the suite asserts is the read-only-tools one.
    """
    argv = pi.headless_argv('pi.cmd', '', no_tools=True)
    assert argv[:3] == ['pi.cmd', '-p', '--no-session']      # print, no memory
    assert '--no-tools' in argv and '--no-extensions' in argv, argv
    assert '--tools' not in argv                             # no whitelist at all
    assert '--model' not in argv                             # none named, none invented
    assert 'read,grep,find,ls' not in argv

    # the other arm: the read-only fence, and it must not look like no-tools
    rows = pi.headless_argv('pi.cmd', 'spark/qwen3.8')
    assert rows[:3] == ['pi.cmd', '-p', '--no-session']
    assert rows[3:5] == ['--tools', 'read,grep,find,ls']
    assert '--no-tools' not in rows and '--no-extensions' not in rows
    assert rows[-2:] == ['--model', 'spark/qwen3.8']         # model last
    assert world['spawned'] == []


# ── 4. accounting must survive a hostile number ─────────────────────────

def test_a_hostile_token_count_must_not_take_the_walk_down(world):
    """One bad record may not stop the walk: fold must not raise on it.

    `fold` runs inside the corpus walk (`sessions.get_session_stats` ->
    `stats.iter_all_sessions`), and a transcript pi wrote after a provider
    returned a count as a string — or a hand-edited file, which is exactly the
    input this reader has to treat as hostile — currently raises out of the
    walk. The fail-closed answer is the one `header` and `_files` already use
    for a bad file: drop the figure, keep the session.
    """
    s = _stats()
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:00.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'usage': {'input': '10', 'output': None}}}, s)
    # the bogus figure is not banked as spend ...
    assert s['usage_by_model'] == {}, s['usage_by_model']
    # ... and the walk reaches the record after it
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:01.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'usage': {'input': 4, 'output': 2}}}, s)
    assert s['usage_by_model'] == {'m': {'in': 4, 'out': 2,
                                         'cache_read': 0, 'cache_create': 0}}
    assert s['count'] == 2


# ── 5. usage pi never reported is never banked ───────────────────────────

def test_usage_pi_never_reported_is_never_banked(world):
    """`if not u: return` (pi.py:252-254) is what keeps a turn free.

    A user message has no `usage`; a `model_change` has no `usage`; a message
    whose `usage` is `{}` or `null` reported nothing. Banking any of them
    invents a model row in the usage table that pi never charged for — and the
    `'pi'` fallback key (pi.py:255) then turns one unnamed message into a
    permanent line item. The existing fold test compares field NAMES only, so
    a row of zeros passes there.
    """
    s = _stats()
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:00.000Z',
             'message': {'role': 'user', 'content': 'say something'}}, s)
    pi.fold({'type': 'model_change', 'modelId': 'm', 'timestamp': '2026-09-14T21:39:01.000Z'}, s)
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:02.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'usage': {}}}, s)
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:03.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'usage': None}}, s)
    assert s['usage_by_model'] == {}, s['usage_by_model']
    assert s['count'] == 3                      # every conversational message

    # a record that DOES carry usage banks under the session's own model ...
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:04.000Z',
             'message': {'role': 'toolResult', 'content': [],
                         'usage': {'input': 7, 'output': 1, 'cacheRead': 2,
                                   'cacheWrite': 3}}}, s)
    assert s['usage_by_model'] == {'m': {'in': 7, 'out': 1,
                                         'cache_read': 2, 'cache_create': 3}}
    assert s['count'] == 3                      # ... and still is not a turn

    # ... and only the LAST resort is the harness id: a home with no model
    # recorded at all must not lose the spend and must not invent a model
    bare = _stats()
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:05.000Z',
             'message': {'role': 'assistant', 'content': [],
                         'usage': {'input': 1}}}, bare)
    assert bare['usage_by_model'] == {'pi': {'in': 1, 'out': 0,
                                             'cache_read': 0, 'cache_create': 0}}
    assert bare['models'] == []                 # banking is not a model record


# ── 6. A, B, A ends on A ─────────────────────────────────────────────────

def test_a_session_that_went_a_b_a_ends_on_a(world):
    """The `model_change` re-ordering branch at pi.py:228-236 has never run.

    The comment there names the case: a session that went A, B, A must not
    leave B looking like the model it ended on — the picker sorts on the LAST
    entry and the usage table labels the session with it. The message-level
    twin (pi.py:242-245) is reached by the token tests; this one is not, so
    `remove`/`append` could be inverted here and nothing would notice until a
    user launched the wrong model.
    """
    s = _stats()
    for mid in ('A', 'B', 'A'):
        pi.fold({'type': 'model_change', 'modelId': mid,
                 'timestamp': '2026-09-14T21:38:10.000Z'}, s)
    assert s['models'] == ['B', 'A']
    assert s['count'] == 0 and s['api_errors'] == 0      # a change is not a turn

    # the spend a tool did on its own follows the model the session ENDED on
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:00.000Z',
             'message': {'role': 'toolResult', 'content': [],
                         'usage': {'input': 5}}}, s)
    assert list(s['usage_by_model']) == ['A'], s['usage_by_model']

    # a change that names nothing changes nothing
    before = list(s['models'])
    for junk in ({'type': 'model_change'}, {'type': 'model_change', 'modelId': ''},
                 {'type': 'model_change', 'modelId': None}):
        pi.fold(junk, s)
    assert s['models'] == before


# ── 7. one error record, one count, and only a message can be one ───────

def test_every_error_record_counts_once_and_only_messages_count(world):
    """The `or` at pi.py:247 has two arms and the tests have one.

    `test_a_refused_call_is_counted_as_an_error` folds ONE record carrying
    BOTH `stopReason: error` and `errorMessage`, so `or` and `and` answer the
    same, one refusal and a hundred refusals answer the same, and an error
    field sitting on a `session` or `model_change` record — which pi does
    write — answers `api_errors` the screen then charges the model for.
    """
    s = _stats()
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:00.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'stopReason': 'stop', 'errorMessage': '401 dead key'}}, s)
    assert s['api_errors'] == 1, 'errorMessage alone is a failed turn'
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:01.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'stopReason': 'error'}}, s)
    assert s['api_errors'] == 2, 'stopReason alone is a failed turn'
    # PER RECORD: a second clean turn must not lift it, and a third refusal
    # must not be swallowed by the first
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:02.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'stopReason': 'stop'}}, s)
    assert s['api_errors'] == 2
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:03.000Z',
             'message': {'role': 'assistant', 'model': 'm', 'content': [],
                         'stopReason': 'error', 'errorMessage': 'overloaded'}}, s)
    assert s['api_errors'] == 3
    # a machine record carrying the same field is not a failed turn
    for junk in ({'type': 'session', 'errorMessage': 'not a turn'},
                 {'type': 'model_change', 'modelId': 'm', 'errorMessage': 'no'},
                 {'type': 'thinking_level_change', 'stopReason': 'error'},
                 {'errorMessage': 'no type at all'}):
        pi.fold(junk, s)
    assert s['api_errors'] == 3


# ── 8. a truncated first line invents neither id nor cwd ─────────────────

def test_a_truncated_header_invents_no_id_and_no_cwd(world, monkeypatch):
    """`header` has a SECOND `return {}` (pi.py:80) no test reaches.

    The existing test drops the header line, leaving a well-formed
    `model_change` first — `iter_json` still yields an object. The shape that
    happens on a crash mid-write is a first line that parses to NOTHING: then
    the id must come from the file name (pi.py:90-91, including a name with no
    `_` at all), the cwd must not be read off the directory name (pi.py:96-100,
    112-113), and a directory of only unreadable files is not a project — while
    one unreadable file must not hide the good session beside it.
    """
    tmp = world['tmp']
    good_cwd = 'C:\\work\\good'
    cut = b'{"type":"session","version":3,"id":"tru'          # cut mid-write
    home = _home(tmp, 'half', {
        # a directory whose every file is unreadable: not a project
        _dir_name('C:\\never'): [
            ('2026-09-14T21-38-00-000Z_only-cut.jsonl', [cut]),
            ('2026-09-14T21-38-01-000Z_blank.jsonl', []),
            ('lonelyname.jsonl', [cut]),         # a name with no `_` at all
        ],
        # one cut file beside one good one: the project is still there
        _dir_name(good_cwd): [
            ('2026-09-14T21-38-02-000Z_broken.jsonl',
             [cut, _line({'type': 'message', 'id': 'entry-9',
                          'message': {'role': 'user', 'content': 'x'}})]),
            ('2026-09-14T21-38-03-000Z_good-7.jsonl',
             [_header('good-7', good_cwd), _message('user', 'real ask')]),
        ],
    })
    world['homes'] = [('half', home)]
    # the order of a listing is the file's mtime, so it is SET here rather than
    # inherited from however fast this machine writes
    os.utime(os.path.join(home, 'sessions', _dir_name(good_cwd),
                          '2026-09-14T21-38-02-000Z_broken.jsonl'),
             (1700000200, 1700000200))
    os.utime(os.path.join(home, 'sessions', _dir_name(good_cwd),
                          '2026-09-14T21-38-03-000Z_good-7.jsonl'),
             (1700000300, 1700000300))
    monkeypatch.chdir(world['quiet'])

    def pick(cwd):
        want = _dir_name(cwd)
        return [d for d in pi._dirs(home) if os.path.basename(d) == want][0]

    broken, kept = pick('C:\\never'), pick(good_cwd)

    # the unreadable directory: no id, no cwd, no project
    assert pi.header(os.path.join(broken, '2026-09-14T21-38-00-000Z_only-cut.jsonl')) == {}
    assert pi.header(os.path.join(broken, '2026-09-14T21-38-01-000Z_blank.jsonl')) == {}
    assert pi._cwd_of(broken) == ''
    assert [p[1] for p in pi.projects(home)] == [good_cwd]

    # the cut file keeps its OWN identity from the name, and an id that is not
    # a session id never becomes one: `entry-9` belongs to a message
    cut_p = os.path.join(kept, '2026-09-14T21-38-02-000Z_broken.jsonl')
    assert pi.header(cut_p) == {}
    assert pi._sid(cut_p) == 'broken'
    # a file name pi never wrote (no timestamp separator) still answers itself
    assert pi._sid(os.path.join(broken, 'lonelyname.jsonl')) == 'lonelyname'
    assert pi._sid(os.path.join(kept, '2026-09-14T21-38-03-000Z_good-7.jsonl')) == 'good-7'

    # and the session listing for the good directory holds both files by their
    # own right, newest first — and never the 8-char id of a message record
    folder = os.path.join(home, 'projects', paths.encode_component(good_cwd))
    ids = [r[1] for r in pi.scan(folder)]
    assert ids == ['good-7', 'broken']
    assert 'entry-9' not in ids
    assert [r[3] for r in pi.scan(folder)] == [1, 1]


# ── 9. the prompt is the last thing after the terminator ────────────────

def test_the_prompt_is_the_last_thing_after_the_terminator(world):
    """`--append-system-prompt` (pi.py:295-296) has never met a prompt.

    Line 296 is never executed in the existing suite, so the option that lands
    AFTER `--` would send the prompt file's path to the model as its first
    message — and a prompt that is not a str reaches `subprocess` as an int and
    dies there. The terminator is only a terminator if nothing follows it.
    """
    prompt = '--append-system-prompt /etc/passwd'
    prompt_file = str(world['tmp'] / 'P.md')
    argv = pi.launch_argv('pi.cmd', 'new', {
        'model': 'spark/qwen3.8', 'effort': 'high', 'name': 'probe',
        'system_prompt_file': prompt_file, 'prompt': prompt}, 'D:\\p')
    assert argv[0] == 'pi.cmd'
    assert argv[-2:] == ['--', prompt]
    i = argv.index('--')
    assert argv[i - 2:i] == ['--append-system-prompt', prompt_file]
    assert '--model' in argv[:i] and '--thinking' in argv[:i] and '-n' in argv[:i]
    assert prompt not in argv[:i]
    # cwd is still not a flag (pi has no -C): the working directory stays out
    assert 'D:\\p' not in argv

    # a prompt that is not a string is still one argv entry the child can take
    typed = pi.launch_argv('pi.cmd', 'continue', {'prompt': 7}, '')
    assert typed[-2:] == ['--', '7'] and isinstance(typed[-1], str)
    # and no prompt at all means no terminator either
    assert '--' not in pi.launch_argv('pi.cmd', 'continue', {'prompt': ''}, '')
    assert '--' not in pi.launch_argv('pi.cmd', 'continue', {'prompt': 0}, '')
    # an effort pi has no word for is dropped, and never reaches argv as free text
    assert '--thinking' not in pi.launch_argv('pi.cmd', 'new', {'effort': 'ultrathink'}, '')


# ── 10. one unreadable file does not lose the directory ─────────────────

def test_one_unreadable_session_file_does_not_lose_the_directory(world, monkeypatch):
    """`_files` answers per FILE (pi.py:61-67).

    Two branches here have never executed: the `continue` that skips a name
    that is not `.jsonl`, and the `except OSError` around `getmtime` for the
    file that vanishes between `listdir` and the stat — a session ending while
    the screen refreshes. Losing the one file is fine; losing the directory is
    the sessions screen going empty on a live run.
    """
    tmp = world['tmp']
    cwd = 'C:\\work\\flaky'
    d = os.path.join(str(tmp), 'flaky', 'sessions', _dir_name(cwd))
    keep_old = _write(os.path.join(d, '2026-09-14T21-38-01-000Z_keep-old.jsonl'),
                      [_header('keep-old', cwd)])
    keep_new = _write(os.path.join(d, '2026-09-14T21-39-01-000Z_keep-new.jsonl'),
                      [_header('keep-new', cwd), _message('user', 'still here')])
    vanishing = _write(os.path.join(d, '2026-09-14T21-38-02-000Z_gone.jsonl'),
                       [_header('gone', cwd)])
    _write(os.path.join(d, 'notes.txt'), [b'not a session'])            # pi.py:61-62
    _write(os.path.join(d, 'side.jsonl.bak'), [b'{"type":"session"}'])  # not .jsonl
    os.utime(keep_old, (1700000000, 1700000000))
    os.utime(keep_new, (1700000600, 1700000600))
    os.utime(vanishing, (1700000300, 1700000300))
    world['homes'] = [('flaky', os.path.join(str(tmp), 'flaky'))]
    monkeypatch.chdir(world['quiet'])

    real = os.path.getmtime

    def flaky_getmtime(path):
        if os.path.basename(path) == '2026-09-14T21-38-02-000Z_gone.jsonl':
            raise OSError(2, 'ended between listdir and stat')
        return real(path)

    monkeypatch.setattr(os.path, 'getmtime', flaky_getmtime)
    got = pi._files(d)
    assert [os.path.basename(p) for _m, p in got] == [
        '2026-09-14T21-39-01-000Z_keep-new.jsonl',
        '2026-09-14T21-38-01-000Z_keep-old.jsonl']          # newest first
    assert got[0][0] > got[1][0]

    folder = os.path.join(str(tmp), 'flaky', 'projects', paths.encode_component(cwd))
    assert [r[1] for r in pi.scan(folder)] == ['keep-new', 'keep-old']
    rows = pi.scan(folder)
    assert [r[3] for r in rows] == [1, 0]          # the unreadable one is gone, not zeroed
    assert pi.transcript_path(folder, 'gone') == ''
    assert world['spawned'] == [] and world['edited'] == []


# ── the preview is the only thing the list shows ────────────────────────

def test_a_plain_string_prompt_still_becomes_the_preview(world):
    """`_text`'s fast path (pi.py:176-177) has never been taken.

    pi writes `content` as a plain string for a user message it did not have to
    structure — the normal shape for a typed prompt. If that arm is lost the
    sessions list shows an empty preview column for every session on the
    machine, and an empty user message must not wipe the preview the previous
    turn set.
    """
    s = _stats()
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:00.000Z',
             'message': {'role': 'user', 'content': '  fix the thing  '}}, s)
    assert s['preview'] == 'fix the thing'          # the plain string, stripped
    assert s['count'] == 1
    # a newline in a prompt is folded to a space: the row is one line (pi.py:202)
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:01.000Z',
             'message': {'role': 'user', 'content': 'first\nsecond'}}, s)
    assert s['preview'] == 'first second'
    # the 200-character cap is a display contract, not a truncation of content
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:01.500Z',
             'message': {'role': 'user', 'content': 'x' * 300}}, s)
    assert len(s['preview']) == 200 and s['preview'].endswith('x')
    # an empty user turn says nothing and must not blank what came before
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:02.000Z',
             'message': {'role': 'user', 'content': '   '}}, s)
    assert s['preview'] == 'x' * 200
    assert s['count'] == 4
    # junk blocks are read as no text, never as str(dict)
    blank = _stats()
    pi.fold({'type': 'message', 'timestamp': '2026-09-14T21:39:03.000Z',
             'message': {'role': 'user', 'content': [None, 'junk', {'type': 'code'}]}}, blank)
    assert blank['preview'] == '' and blank['count'] == 1
    assert sessions._EMPTY_STATS.keys() == s.keys()
