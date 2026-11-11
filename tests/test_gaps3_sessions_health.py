"""T-1133 — the highest-risk uncovered branches of `claude_sessions/health.py`
lines 27-94 inclusive (check_project, settings_hygiene, _check_settings_hygiene)
at HEAD 56d53504 (2026-11-10). Read-only secret reporting: nothing here edits,
untracks or gitignores a file, and every test asserts that absence too.

FINAL SELECTED BRANCHES (one section of tests each, fail-closed first, then
boundaries, then error paths, then a forced ordering):

  B1  health.py:70-73   the report is decided on the RAW file line and the
                        `rule` label is looked up by the JSON spelling
                        (`kind_of[json.dumps(r)]`, health.py:65) — an escaped
                        value must not change either.
  B2  health.py:69-73   a PEM that reaches over several lines: the key body is
                        never handed back as a `sample`.
  B3  health.py:61-67   `json.loads(text).get(...)` on a top-level list /
                        scalar / null: AttributeError is the caught path, the
                        content scan still runs.
  B4  health.py:63-65   `permissions` and its values that are not lists:
                        `items if isinstance(items, list) else ()`.
  B5  health.py:54-58   a settings file that exists but cannot be read
                        (`except OSError: continue`) — it must not come back as
                        an inspected or committed file.
  B6  health.py:62,66-67 malformed JSON: `except (ValueError, AttributeError)`,
                        the raw keyed secret is still reported masked.
  B7  health.py:71-73   the 160-character sample limit clips AFTER masking, and
                        the finding is decided on the whole line.
  B8  health.py:49-51,72 a rule FILENAME carrying terminal controls.
  B9  health.py:74-80   a `git ls-files` row naming a path that was never
                        inspected cannot become a trusted exposure finding.
  B10 health.py:74-80,84-88  git unavailable / non-zero: no file mutation, the
                        already-found masked reports survive, and the git query
                        runs after the content scan (ordering forced with
                        threading.Events, never a sleep).

Three of these ten premises are contradicted by the source; those tests are
kept as `@pytest.mark.xfail(strict=True, ...)` with the defect line quoted in
the reason (B8 output hygiene, B9 row validation, B10 suppression by an
unlistable rules directory). Nothing is weakened to make them pass, and no
source file is edited.

Synthetic secrets only (`SYNTH…`); no real credential appears anywhere.
"""

import builtins
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import health, repos

S = 'SYNTHhunter2'
PEM_B1 = 'b3BlbnNzaC1rZXktdjEAAAAABG52aWUBAAA'
PEM_B2 = 'AAAAlwAAAAtzc2gtZWQyNTUxOAAAQkFsd2F5cwAAA'
PEM_B3 = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
GIT_ARGV = ['ls-files', '-t', '--cached', '--others', '--exclude-standard', '--']


def _write(root, parts, text):
    """One file under `.claude/`, with explicit newline bytes on every platform."""
    p = os.path.join(str(root), '.claude', *[str(x) for x in parts])
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return p


def _project(tmp_path, files):
    root = str(tmp_path)
    d = os.path.join(root, '.claude')
    if not os.path.isdir(d):
        os.makedirs(d)
    for parts, text in files.items():
        _write(root, parts, text)
    return root


def _tree(root):
    """Every file under the project, bytes included: the no-side-effect oracle."""
    out = {}
    for dirpath, _dirs, names in os.walk(str(root)):
        for n in names:
            p = os.path.join(dirpath, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, str(root))] = f.read()
    return out


@pytest.fixture
def git(monkeypatch):
    """The `_git` seam, as test_persisted_scrub.py uses it: no git is spawned.

    `git['out']` is what the next call answers, `git['calls']` the argv it was
    asked with. The default is '' (a clean repo, nothing to commit)."""
    state = {'out': '', 'calls': []}

    def fake(args, cwd, timeout=15):
        state['calls'].append([list(args), cwd, timeout])
        return state['out']

    monkeypatch.setattr(repos, '_git', fake)
    return state


def _allow(text):
    return json.dumps({'permissions': {'allow': [text]}}, indent=2)


# ── B1 — escaped JSON password value: raw bytes vs decoded command ─────────

def test_an_escaped_password_value_is_reported_with_its_permission_rule(tmp_path, git):
    """health.py:70-73 (decide) + 65 (label): the value reaches the file as
    `\\"`; the report and the `permissions.allow` label must not depend on the
    raw bytes looking like the decoded command."""
    cmd = 'curl -u "admin:%s" https://db.example.com' % S
    root = _project(tmp_path, {('settings.local.json',): _allow('Bash(%s)' % cmd)})
    before = _tree(root)
    found = health.settings_hygiene(root)
    hits = [f for f in found if f['line'] == 4]
    assert len(hits) == 1, found
    assert hits[0]['rule'] == 'permissions.allow', hits[0]
    assert S not in json.dumps(found, sort_keys=True)
    assert '[redacted]' in hits[0]['sample']
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.local.json']
    assert _tree(root) == before


def test_a_secret_in_a_one_line_settings_file_is_reported_though_no_rule_matches(
        tmp_path, git):
    """health.py:71-73: the decision is `redact(line) != line`, never "is this
    line one of the parsed permission entries". A minified file has one line
    holding a whole document, so `kind_of` cannot match and the default label
    must still be reported."""
    root = _project(tmp_path, {('settings.local.json',): json.dumps(
        {'permissions': {'allow': ['Bash(PGPASSWORD=%s psql)' % S]}})})
    found = [f for f in health.settings_hygiene(root) if f['line'] == 1]
    assert len(found) == 1, found
    assert found[0]['rule'] == 'setting', found[0]
    assert S not in json.dumps(found) and '[redacted]' in found[0]['sample']


# ── B2 — a PEM that reaches over several lines ────────────────────────────

def test_a_pem_in_a_settings_file_leaves_no_key_fragment_in_any_sample(tmp_path, git):
    """health.py:69-73: the key is one JSON string whose lines are literal
    `\\n`; every body line must be gone before the row is built."""
    pem = '-----BEGIN OPENSSH PRIVATE KEY-----\\n%s\\n%s\\n%s\\n' \
          '-----END OPENSSH PRIVATE KEY-----' % (PEM_B1, PEM_B2, PEM_B3)
    root = _project(tmp_path, {('settings.local.json',): json.dumps(
        {'permissions': {'allow': ['Bash(ssh -i "%s" host)' % pem,
                                   'Bash(PGPASSWORD=%s psql)' % S]}}, indent=2)})
    before = _tree(root)
    found = health.settings_hygiene(root)
    for body in (PEM_B1, PEM_B2, PEM_B3):
        assert body not in json.dumps(found), body[:12]
    assert S not in json.dumps(found)
    assert [f['line'] for f in found if f['line']] == [4, 5], found
    assert all('[redacted]' in f['sample'] for f in found if f['line']), found


def test_a_pem_in_a_memory_rule_and_the_secret_after_it_are_both_masked(tmp_path, git):
    """health.py:69-73 on a `.md` rule: the BEGIN line is redacted on its own,
    the raw base64 lines that follow must never be reported as samples, and the
    keyed secret on the line after the key still is."""
    text = '-----BEGIN OPENSSH PRIVATE KEY-----\n%s\n%s\n%s\n' \
           '-----END OPENSSH PRIVATE KEY-----\nconnect with db password=%s now\n' \
           % (PEM_B1, PEM_B2, PEM_B3, S)
    root = _project(tmp_path, {('rules', 'archeus-mem-db.md'): text})
    git['out'] = '? .claude/rules/archeus-mem-db.md\n'
    before = _tree(root)
    found = health.settings_hygiene(root)
    rel = os.path.join('.claude', 'rules', 'archeus-mem-db.md')
    assert [f['path'] for f in found] == [rel, rel, rel], found   # 2 rows + the git row
    assert [f['line'] for f in found] == [1, 6, 0], found
    for body in (PEM_B1, PEM_B2, PEM_B3):
        assert body not in json.dumps(found), body[:12]
    assert S not in json.dumps(found)
    assert 'BEGIN' not in json.dumps(found)
    assert 'password=[redacted]' in found[1]['sample']
    assert _tree(root) == before


# ── B3 — top-level list / scalar / null ───────────────────────────────────

def test_a_top_level_json_list_still_reports_its_secret_without_a_permission_label(
        tmp_path, git):
    """health.py:61-67: `json.loads(text).get` raises AttributeError on a list;
    the content scan is not allowed to stop with it."""
    root = _project(tmp_path, {('settings.json',): json.dumps(
        [{'env': 'Bash(PGPASSWORD=%s psql -h db.example.com)' % S}], indent=2)})
    before = _tree(root)
    found = [f for f in health.settings_hygiene(root) if f['line']]
    assert len(found) == 1, found
    assert found[0]['rule'] == 'setting', found[0]      # not permissions.allow
    assert '[redacted]' in found[0]['sample'] and S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.json']
    assert _tree(root) == before


@pytest.mark.parametrize('shape', ['null', 'scalar', 'string'], ids=('null', 'scalar',
                                                                     'string'))
def test_a_top_level_scalar_or_null_settings_file_never_crashes_the_card(tmp_path, git,
                                                                         shape):
    """health.py:63-67: the three other JSON shapes a settings file can have;
    none may take the check down (which is how a check is silently lost)."""
    body = {'null': 'null\n', 'scalar': '42\n',
            'string': json.dumps('nothing secret here') + '\n'}[shape]
    root = _project(tmp_path, {('settings.json',): body,
                               ('settings.local.json',): _allow('Bash(ls:*)')})
    found = health.settings_hygiene(root)
    assert found == [], found                     # no crash, and nothing invented
    assert git['calls'][0][0][:len(GIT_ARGV)] == GIT_ARGV      # asked about settings.local
    assert git['calls'][0][0][-1] == '.claude/settings.local.json'


# ── B4 — permissions and values that are not lists ────────────────────────

@pytest.mark.parametrize('doc', [
    pytest.param({'permissions': {'allow': 'Bash(PGPASSWORD=%s psql)' % S}},
                 id='allow-string'),
    pytest.param({'permissions': {'allow': {'cmd': 'Bash(PGPASSWORD=%s psql)' % S}}},
                 id='allow-dict'),
    pytest.param({'permissions': {'allow': 7, 'deny': None},
                  'env': 'Bash(PGPASSWORD=%s psql)' % S}, id='allow-int-and-null'),
    pytest.param({'permissions': 'Bash(PGPASSWORD=%s psql)' % S}, id='permissions-string'),
], ids=str)
def test_a_non_list_permissions_value_still_reports_its_secret(tmp_path, git, doc):
    """health.py:63-65: `items if isinstance(items, list) else ()` and the
    AttributeError half of the same try. A shape the parser does not understand
    must never read as "no secret here"."""
    root = _project(tmp_path, {('settings.json',): json.dumps(doc, indent=2)})
    before = _tree(root)
    found = [f for f in health.settings_hygiene(root) if f['line']]
    assert len(found) == 1, found
    assert found[0]['rule'] == 'setting', found[0]
    assert '[redacted]' in found[0]['sample'] and S not in json.dumps(found)
    assert _tree(root) == before


# ── B5 — a settings file that cannot be read ──────────────────────────────

def test_an_unreadable_settings_file_is_never_reported_as_inspected(tmp_path, monkeypatch,
                                                                    git):
    """health.py:54-58: `except OSError: continue`. The locked file must produce
    no row at all — neither a secret nor a git-exposure claim — while the file
    that COULD be read is still inspected, and nothing is written."""
    secret = _allow('Bash(PGPASSWORD=%s psql -h db.example.com)' % S)
    root = _project(tmp_path, {('settings.json',): secret,
                               ('settings.local.json',): secret})
    locked = os.path.join(root, '.claude', 'settings.local.json')
    git['out'] = 'H .claude/settings.json\n'
    real_open = builtins.open
    before = _tree(root)

    def guarded(file, *a, **k):
        if str(file) == locked:
            raise PermissionError(13, 'read denied by the test seam')
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, 'open', guarded)
    found = health.settings_hygiene(root)
    warns = health._check_settings_hygiene(root)
    assert [f['path'] for f in found] == [os.path.join('.claude', 'settings.json'),
                                          os.path.join('.claude', 'settings.json')], found
    assert [f['rule'] for f in found] == ['permissions.allow', 'tracked by git'], found
    assert not any(f['path'].endswith('settings.local.json') for f in found), found
    assert not any('settings.local.json' in w[1] for w in warns), warns
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.json']
    assert S not in json.dumps([found, warns])
    monkeypatch.undo()
    assert _tree(root) == before


# ── B6 — malformed JSON ───────────────────────────────────────────────────

def test_malformed_json_still_reports_the_raw_keyed_secret_masked(tmp_path, git):
    """health.py:62,66-67: `except (ValueError, AttributeError)` — a truncated
    document must not end the pass, and the report must not carry the bytes it
    was cut off around."""
    root = _project(tmp_path, {('settings.local.json',):
                               '{"permissions": {"allow": ["Bash(PGPASSWORD=%s psql)"]}' % S})
    before = _tree(root)
    found = [f for f in health.settings_hygiene(root) if f['line']]
    assert len(found) == 1, found
    assert found[0]['rule'] == 'setting', found[0]
    assert '[redacted]' in found[0]['sample'] and S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.local.json']
    assert _tree(root) == before


# ── B7 — the 160-character sample limit ───────────────────────────────────

def test_the_sample_is_masked_before_it_is_clipped_at_160(tmp_path, git):
    """health.py:71-73: `masked.strip()[:160]`. A credential whose closing `@`
    sits past column 160 is only recognised in the WHOLE line; clipping first
    would show the key instead of hiding it."""
    filler = 'Z' * 120
    cmd = 'curl https://admin:%s%s@internal.example.com/x' % (filler, S)
    root = _project(tmp_path, {('settings.local.json',): _allow('Bash(%s)' % cmd)})
    found = [f for f in health.settings_hygiene(root) if f['line']]
    assert len(found) == 1, found
    sample = found[0]['sample']
    assert len(sample) <= 160
    assert '[redacted]' in sample and S not in sample and filler[:24] not in sample
    assert 'admin:' not in sample


def test_a_secret_past_the_sample_limit_still_produces_the_finding(tmp_path, git):
    """health.py:71-73 again, the other half: the finding is decided on the
    whole line even when everything interesting is past the 160th column."""
    cmd = 'tool %s password=%s%s' % ('f' * 150, S, 'y' * 80)
    root = _project(tmp_path, {('settings.local.json',): _allow('Bash(%s)' % cmd)})
    found = [f for f in health.settings_hygiene(root) if f['line']]
    assert len(found) == 1, found
    assert found[0]['rule'] == 'permissions.allow', found[0]
    assert len(found[0]['sample']) == 160, found[0]
    assert S not in found[0]['sample'] and 'password=' not in found[0]['sample']


# ── B8 — a rule filename carrying terminal controls ───────────────────────

def _evil_rule_name():
    return 'archeus-mem-\x1b[31mEVIL.md'


@pytest.fixture
def control_named_rule(tmp_path, monkeypatch):
    """`.claude/rules` is real but lists one name carrying an ESC, whose bytes
    come from a file that is NOT in it. C0 characters cannot be created in a
    Windows filename, so the directory listing is emulated at the seam instead
    of the platform being replaced."""
    evil = _evil_rule_name()
    rules = os.path.join(str(tmp_path), '.claude', 'rules')
    os.makedirs(rules)
    backing = _write(tmp_path, ('backing.md',), 'token=%s renew it\n' % S)
    real_list, real_open = os.listdir, builtins.open

    def listed(path, *a, **k):
        if str(path) == rules:
            return [evil]
        return real_list(path, *a, **k)

    def opened(file, *a, **k):
        if str(file) == os.path.join(rules, evil):
            return real_open(backing, *a, **k)
        return real_open(file, *a, **k)

    monkeypatch.setattr(os, 'listdir', listed)
    monkeypatch.setattr(builtins, 'open', opened)
    return {'root': str(tmp_path), 'name': evil,
            'rel': os.path.join('.claude', 'rules', evil)}


def test_a_rule_file_named_with_a_terminal_control_is_still_reported_masked(
        control_named_rule, git):
    """health.py:49-51,72: an unreadable-to-the-eye name must not cost the
    finding — the file is scanned, labelled `memory rule` and masked. Asserted
    on the tail of the name, so the report staying honest and a later fix that
    sanitises the path are both compatible with this test."""
    root = control_named_rule['root']
    found = [f for f in health.settings_hygiene(root) if f['line']]
    assert len(found) == 1, found
    assert found[0]['path'].endswith('EVIL.md') and found[0]['path'].startswith(
        os.path.join('.claude', 'rules')), found[0]
    assert found[0]['rule'] == 'memory rule', found[0]
    assert '[redacted]' in found[0]['sample'] and S not in json.dumps(found)
    assert git['calls'][0][0] == GIT_ARGV + [found[0]['path'].replace(os.sep, '/')], \
        git['calls']


def test_health_output_carries_no_active_terminal_control(control_named_rule, git):
    """health.py:49-51,72,89: the card text a cloned repository can name."""
    root = control_named_rule['root']
    issues = health._check_settings_hygiene(root)
    assert issues, 'the finding itself must exist for the card to carry it'
    for sev, msg, hint in issues:
        for text in (msg, hint):
            assert not any(ord(c) < 0x20 for c in text), repr(text)


# ── B9 — a git row naming a path that was never inspected ─────────────────

def test_git_is_only_asked_about_the_files_that_were_inspected(tmp_path, git):
    """health.py:74-76: the pathspec list is the set of files this pass opened,
    slash-normalised, behind `--`."""
    root = _project(tmp_path, {('settings.json',):
                               _allow('Bash(PGPASSWORD=%s psql)' % S),
                               ('settings.local.json',): _allow('Bash(ls:*)'),
                               (('rules', 'archeus-mem-x.md')): 'plain text\n'})
    git['out'] = 'H .claude/settings.json\n? .claude/settings.local.json\n'
    before = _tree(root)
    found = health.settings_hygiene(root)
    assert git['calls'][0][0] == GIT_ARGV + ['.claude/settings.json',
                                             '.claude/settings.local.json']
    assert git['calls'][0][1] == root
    assert [f['rule'] for f in found] == ['permissions.allow', 'tracked by git',
                                          'not ignored by git'], found
    assert _tree(root) == before


@pytest.mark.xfail(strict=True,
                   reason='health.py:77-80 turns every row of the `_git` answer into a '
                          '"tracked by git" / "not ignored by git" finding with no check '
                          'that the path is one of the files this pass inspected, while '
                          'health.py:75-76 asks about them behind `--` and the docstring '
                          '(health.py:39-44) promises "which of those files git would '
                          'commit"; a stand-in git (a shim on PATH, a wrapper printed by '
                          'an alias) that answers other paths fabricates the finding')
def test_a_git_row_for_an_unrelated_path_is_not_a_finding(tmp_path, git):
    """health.py:77-80: rows must stay inside the inspected set."""
    root = _project(tmp_path, {('settings.json',): _allow('Bash(PGPASSWORD=%s psql)' % S)})
    git['out'] = ('H .claude/settings.json\nH .env\n? ../../outside/secret.txt\n'
                  'H src/settings.local.json\n')
    found = health.settings_hygiene(root)
    inspected = {os.path.join('.claude', 'settings.json')}
    rows = [f for f in found if not f['line']]
    assert {f['path'] for f in rows} <= inspected, found


# ── B10 — git unavailable or non-zero ─────────────────────────────────────

def test_git_answering_nothing_keeps_the_masked_reports_and_touches_nothing(tmp_path,
                                                                            git):
    """health.py:74-80 with the answer `proc.git` gives for a failed or absent
    git (None): the content findings survive, no git row is invented, and the
    project is byte-for-byte what it was."""
    root = _project(tmp_path, {('settings.local.json',):
                               _allow('Bash(PGPASSWORD=%s psql -h db.example.com)' % S)})
    git['out'] = None
    before = _tree(root)
    found = health.settings_hygiene(root)
    assert [f['rule'] for f in found] == ['permissions.allow'], found
    warns = health._check_settings_hygiene(root)
    assert len(warns) == 1 and warns[0][0] == 'warn', warns
    assert '[redacted]' in warns[0][1] and S not in repr(warns)
    assert 'never edits' in warns[0][2]
    assert _tree(root) == before


def test_the_git_query_runs_after_the_content_scan_so_a_late_file_is_not_claimed(
        tmp_path, monkeypatch):
    """health.py:52-76, the ordering: the pathspec list is built from what this
    pass READ, so a file that appears while git is still answering cannot join
    the report. Forced with Events — no sleep proves anything here."""
    root = _project(tmp_path, {('settings.local.json',):
                               _allow('Bash(PGPASSWORD=%s psql)' % S)})
    entered, release = threading.Event(), threading.Event()
    box = {'argv': None, 'found': None, 'exc': None}

    def fake(args, cwd, timeout=15):
        box['argv'] = list(args)
        entered.set()
        assert release.wait(5.0), 'the git seam was never released'
        return ''

    def work():
        try:
            box['found'] = health.settings_hygiene(root)
        except BaseException as exc:                      # reported, never swallowed
            box['exc'] = exc

    monkeypatch.setattr(repos, '_git', fake)
    t = threading.Thread(target=work, name='t1133-git')
    t.start()
    try:
        assert entered.wait(5.0), 'settings_hygiene never reached the git seam'
        _write(root, ('settings.json',), _allow('Bash(sshpass -p %s host)' % S))
    finally:
        release.set()
    t.join(10.0)
    assert not t.is_alive(), 'settings_hygiene hung behind the git seam'
    assert box['exc'] is None, box['exc']
    assert box['argv'] == GIT_ARGV + ['.claude/settings.local.json'], box['argv']
    assert {f['path'] for f in box['found']} == {os.path.join('.claude',
                                                             'settings.local.json')}, \
        box['found']
    assert S not in json.dumps(box['found'])


@pytest.mark.xfail(strict=True,
                   reason='health.py:50-51 lists the rules directory outside any handler, '
                          'so an OSError there reaches health.py:87-88 and _check_settings '
                          '_hygiene answers [] for the WHOLE pass: the masked secret '
                          'already collected from settings.local.json is dropped instead '
                          'of reported with the rules half missing')
def test_an_unlistable_rules_directory_does_not_suppress_the_reports_it_already_has(
        tmp_path, monkeypatch, git):
    """health.py:49-51 + 84-88: a directory that goes away or denies the listing
    between `isdir` and `listdir` costs the rules, not the secrets."""
    root = _project(tmp_path, {('rules', 'archeus-mem-x.md'):
                               'token=%s renew\n' % S,
                               ('settings.local.json',):
                               _allow('Bash(PGPASSWORD=%s psql)' % S)})
    real_list = os.listdir

    def listed(path, *a, **k):
        if str(path).endswith(os.path.join('.claude', 'rules')):
            raise PermissionError(13, 'the rules directory went away mid-scan')
        return real_list(path, *a, **k)

    monkeypatch.setattr(os, 'listdir', listed)
    before = _tree(root)
    warns = health._check_settings_hygiene(root)
    monkeypatch.undo()
    assert _tree(root) == before                       # report only, never a writer
    msgs = [m for _s, m, _h in warns]
    assert any('a secret in' in m and '[redacted]' in m and 'settings.local.json' in m
               for m in msgs), warns
    assert not any(S in m for m in msgs), warns


# ── the aggregation the GUI card reads (health.py:27-36) ──────────────────

def test_check_project_surfaces_the_secret_after_every_other_check(tmp_path, git):
    """health.py:30-35: settings hygiene is the last check appended and the only
    one that carries a secret; dropping that line takes the warning out of the
    card while every other check still passes."""
    root = _project(tmp_path, {('settings.local.json',):
                               _allow('Bash(PGPASSWORD=%s psql -h db.example.com)' % S)})
    git['out'] = '? .claude/settings.local.json\n'
    before = _tree(root)
    issues = health.check_project(root, root)
    secret_rows = [i for i in issues if 'a secret in' in i[1]]
    git_rows = [i for i in issues if 'is not ignored by git' in i[1]]
    assert [i[0] for i in secret_rows + git_rows] == ['warn', 'warn'], issues
    assert any('settings.local.json:4' in i[1] for i in secret_rows), issues
    assert any('never edits' in i[2] for i in secret_rows), issues
    assert issues[-1] in secret_rows + git_rows, issues      # hygiene rows come last
    assert S not in repr(issues)
    assert _tree(root) == before
