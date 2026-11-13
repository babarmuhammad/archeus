"""T-1320 · Close the highest-risk test gaps in claude_sessions/codex.py (123-321).

Exact source range: ``claude_sessions/codex.py`` lines 123-321 inclusive at the
current tip. That range is now ``scan`` (125), ``transcript_path`` (151),
``_count`` (160), ``fold`` (183), ``_split`` (241) and ``_spend`` (249), and the
first lines of ``launch_argv`` (278-321); the card's line numbers came from an
older tip and were re-located by reading the source. No source file is edited
here; no new dependency.

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. codex.py:325-326  resume launch: a prompt starting with ``--`` is data, not a flag
                      (no ``--`` terminator before the prompt)               (strict xfail)
 2. codex.py:325-326  fork launch: a prompt ``-m evil`` is one argv element and never
                      a model override; the terminator defect is kept as strict xfail
 3. codex.py:299-322  a prompt ``--`` with model/cwd/add_dirs/perm/sandbox: every
                      option flag sits before the prompt
 4. codex.py:135-146  NULL rollout_path among good rows: count 0, good sessions kept
 5. codex.py:176-177  a truthy list payload in an event_msg is ignored by _count and
                      the next valid event still counts
 6. codex.py:176-177  a truthy string payload and a numeric payload: neither crashes
                      _count, the valid event after them still counts
 7. codex.py:200-202  fold: a non-dict session_meta payload cannot set cwd or crash
                      (crash at codex.py:202, strict xfail)
 8. codex.py:210-216  fold: a non-dict turn_context payload cannot invent a model or
                      reorder models (crash at codex.py:210, strict xfail)
 9. codex.py:218-228  fold: a non-dict event_msg payload stops the later valid error
                      event being counted (crash at codex.py:218, strict xfail)
10. codex.py:154-157  transcript_path NULL -> ''; a missing rollout file counts 0
                      without reading the ambient home

The defects in 1, 2, 7, 8 and 9 are source defects, not fixture mistakes: the
prompt is appended with no terminator at codex.py:325-326, and fold reads
``payload`` with ``.get`` at codex.py:200-218 without a dict check. Each
xfail is strict, so a fix turns it into a visible XPASS.

Every rollout and index is built under tmp_path; no ambient CODEX_HOME, no real
home, no subprocess, no network.
"""

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                     # noqa: E402

from claude_sessions import codex                 # noqa: E402

_COLS = ('id', 'rollout_path', 'cwd', 'preview', 'first_user_message',
         'model', 'tokens_used', 'git_branch', 'archived', 'updated_at_ms',
         'created_at_ms')


def _home(tmp_path):
    home = tmp_path / 'codex-home'
    home.mkdir()
    return str(home)


def _index(home, rows):
    con = sqlite3.connect(os.path.join(home, 'state_5.sqlite'))
    con.execute('CREATE TABLE threads (%s)' % ', '.join(_COLS))
    for r in rows:
        vals = {c: None for c in _COLS}
        vals.update({'archived': 0, 'tokens_used': 0, 'git_branch': ''})
        vals.update(r)
        con.execute('INSERT INTO threads (%s) VALUES (%s)'
                    % (', '.join(_COLS), ', '.join('?' * len(_COLS))),
                    [vals[c] for c in _COLS])
    con.commit()
    con.close()


def _rollout(path, *objs):
    with open(path, 'w', encoding='utf-8') as f:
        for o in objs:
            f.write(json.dumps(o) + '\n')
    return str(path)


def _user(text='hi'):
    return {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': text}}


def _stats():
    return {'preview': '', 'count': 0, 'title': '', 'usage_by_model': {},
            'models': [], 'first_ts': None, 'last_ts': None, 'branch': '',
            'cwd': '', 'api_errors': 0, 'headless': False}


def _launch(choice, **opts):
    return codex.launch_argv('codex', choice, opts, None)


# ── 4. NULL rollout among good rows ───────────────────────────────────────

def test_null_rollout_row_counts_zero_and_keeps_good_sessions(tmp_path):
    home = _home(tmp_path)
    proj = str(tmp_path / 'proj')
    good = _rollout(tmp_path / 'good.jsonl', _user('a'), _user('b'))
    _index(home, [
        {'id': 'good', 'rollout_path': good, 'cwd': proj,
         'first_user_message': 'hello', 'updated_at_ms': 2000},
        {'id': 'null', 'rollout_path': None, 'cwd': proj,
         'first_user_message': 'second', 'updated_at_ms': 1000},
    ])
    folder = os.path.join(home, 'projects', codex._enc(proj))

    assert codex.scan(folder) == [(2.0, 'good', 'hello', 2),
                                  (1.0, 'null', 'second', 0)]


# ── 5 and 6. non-dict payloads in _count ──────────────────────────────────

def test_list_payload_in_event_msg_is_ignored_and_next_event_counts(tmp_path):
    path = _rollout(tmp_path / 'r.jsonl',
                    {'type': 'event_msg', 'payload': [1, 2]}, _user())
    assert codex._count(path) == 1


def test_string_and_numeric_payloads_do_not_crash_count(tmp_path):
    path = _rollout(tmp_path / 'r.jsonl',
                    {'type': 'event_msg', 'payload': 'user_message'},
                    {'type': 'event_msg', 'payload': 7},
                    _user(), _user())
    assert codex._count(path) == 2


# ── 7, 8, 9. non-dict payloads in fold ────────────────────────────────────

@pytest.mark.xfail(strict=True, reason=(
    'codex.py:200-202 fold reads payload with .get and no dict check; a string '
    'session_meta payload raises AttributeError instead of being ignored'))
def test_non_dict_session_meta_cannot_set_cwd_or_crash(tmp_path):
    s = _stats()
    codex.fold({'type': 'session_meta', 'payload': '/invented/dir'}, s)

    assert s['cwd'] == ''


@pytest.mark.xfail(strict=True, reason=(
    'codex.py:210 fold calls .get on a non-dict turn_context payload; a string '
    'payload raises AttributeError and the model list is left half-processed'))
def test_non_dict_turn_context_cannot_invent_or_reorder_models(tmp_path):
    s = _stats()
    s['models'] = ['gpt-a', 'gpt-b']
    codex.fold({'type': 'turn_context', 'payload': 'gpt-invented'}, s)

    assert s['models'] == ['gpt-a', 'gpt-b']


@pytest.mark.xfail(strict=True, reason=(
    'codex.py:218 fold calls .get on a non-dict event_msg payload; the raise '
    'stops the later valid error event from being counted'))
def test_malformed_event_payload_does_not_stop_a_later_error(tmp_path):
    s = _stats()
    codex.fold({'type': 'event_msg', 'payload': 'oops'}, s)
    codex.fold({'type': 'event_msg', 'payload': {'type': 'error'}}, s)

    assert s['api_errors'] == 1


# ── 10. NULL transcript path and a missing rollout file ───────────────────

def test_null_transcript_path_is_empty_and_missing_file_counts_zero(tmp_path):
    home = _home(tmp_path)
    proj = str(tmp_path / 'proj')
    _index(home, [{'id': 'sid-1', 'rollout_path': None, 'cwd': proj}])
    folder = os.path.join(home, 'projects', codex._enc(proj))

    assert codex.transcript_path(folder, 'sid-1') == ''
    assert codex._count('') == 0
    assert codex._count(str(tmp_path / 'never-written.jsonl')) == 0


# ── 1, 2, 3. launch argv: prompts and options ─────────────────────────────

def test_resume_prompt_is_one_argv_element(tmp_path):
    prompt = '--dangerously-bypass-approvals-and-sandbox'
    args = _launch('resume:sid-1', prompt=prompt)

    assert args[-1] == prompt
    assert args[1:3] == ['resume', 'sid-1']


@pytest.mark.xfail(strict=True, reason=(
    'codex.py:325-326 appends the prompt with no -- terminator, so a resume '
    'prompt beginning with a dash is read by codex as a flag'))
def test_resume_prompt_follows_a_terminator(tmp_path):
    prompt = '--dangerously-bypass-approvals-and-sandbox'
    args = _launch('resume:sid-1', prompt=prompt)

    assert args[-2:] == ['--', prompt], args


def test_fork_prompt_that_looks_like_a_model_flag_is_data(tmp_path):
    args = _launch('fork:sid-2', prompt='-m evil')

    assert args == ['codex', 'fork', 'sid-2', '-m evil'], args
    assert '-m' not in args


@pytest.mark.xfail(strict=True, reason=(
    'codex.py:325-326 appends the prompt with no -- terminator, so a fork '
    'prompt beginning with a dash is read by codex as a flag'))
def test_fork_prompt_follows_a_terminator(tmp_path):
    args = _launch('fork:sid-2', prompt='-m evil')

    assert args[-2:] == ['--', '-m evil'], args


def test_option_flags_precede_a_dash_dash_prompt(tmp_path):
    add = str(tmp_path / 'extra')
    cwd = str(tmp_path / 'work')
    args = codex.launch_argv('codex', 'continue',
                             {'model': 'gpt-x', 'effort': 'high',
                              'perm': 'bypassPermissions', 'sandbox': 'read-only',
                              'add_dirs': [add], 'prompt': '--'},
                             cwd)

    assert args[-1] == '--'
    assert args[:4] == ['codex', 'resume', '--last', '-m']
    assert args[4] == 'gpt-x'
    assert args.index('-a') < len(args) - 1
    assert args.index('-s') < len(args) - 1
    assert args.index('--add-dir') < len(args) - 1
    assert args.index('-C') < len(args) - 1
    assert args[args.index('-C') + 1] == cwd
    assert args[args.index('--add-dir') + 1] == add
    assert args[args.index('-a') + 1] == 'never'
