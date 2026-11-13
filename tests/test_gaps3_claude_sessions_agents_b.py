"""T-1177 — the highest-risk uncovered branches of claude_sessions/agents.py.

Slice under test: ``claude_sessions/agents.py`` lines **421-795 inclusive** (the
card's tip ``56d53504``; the checkout in this container is ``c40a3e318f97``, and
every line number below was read off this working tree) — ``sync_project_agents``
and the library / routing helpers inside the slice: ``find_library_agent``
(:473-479), ``routing_table`` (:719), ``write_agent_index`` (:757) and
``write_routing_block`` (:774, which crosses the upper endpoint at :795).
Definitions and imports outside the slice are read-only context; no source file
is edited.

Focus, as the card names it: **the managed manifest cannot delete foreign
files.** ``.claude/agents/.archeus-managed.json`` (``agents._MANIFEST``,
agents.py:584) is the ownership record ``sync_project_agents`` uses to decide
what it may ``os.remove`` (agents.py:632-640), and the file lives INSIDE the
project directory — so it is data a cloned repository supplies, not state
archeus alone owns.

Final ten selected branches (probe 4 "unlisted user files survive" was already
covered by tests/test_tui_agents.py::test_sync_project_agents, so it was
replaced; evidence, closest existing test and the reason its assertion misses
are in /work/QWEN-DONE-T-1177.md):

 1. agents.py:632-640  manifest entry ``../../victim.md`` — traversal out of dest   (xfail)
 2. agents.py:632-640  manifest entry with an absolute path — join returns it as-is (xfail)
 3. agents.py:616-617  ``if not isinstance(prev, list)`` — a JSON object gets no
                       removal authority
 4. agents.py:614-619  unparseable manifest — nothing is deleted, the unreadable
                       record survives, ownership is re-established on retry
 5. agents.py:623-626  an unresolvable selected ref is not counted, not created,
                       and does not stop the cleanup pass
 6. agents.py:646-666  ``shutil.copyfile`` failure is not a managed success
 7. agents.py:652-659  routed strip touches ``model:`` inside the frontmatter only
                       (indentation, near-miss keys)
 8. agents.py:655-661  a ``model:`` line in the BODY is preserved byte-for-byte
 9. agents.py:668-671  a failed manifest write must not be reported as managed
                       installs                                                      (xfail)
10. agents.py:649-665  a failure inside the routed strip cannot inflate the count

Everything the tested code writes stays under ``tmp_path``. The OS touches that
are not plain project files are seam-faked (``builtins.open``,
``shutil.copyfile``); config roots, settings, the account dir, the agent
library root, the editor and the Claude binary path are faked before entry, and
the credential readers are pinned to raise so a reach is a failure, not a read.
No network, no subprocess, no real home, no environment values, no sleeps.
"""

import builtins
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                        # noqa: E402

from harness import Sandbox                          # noqa: E402

from claude_sessions import agents                   # noqa: E402
from claude_sessions import clientstate, config as cfg, usage as usage_mod


# ── sandbox: invented state only, host state pinned out first ───────────────

@pytest.fixture
def env(monkeypatch, tmp_path):
    """A Sandbox (the neighbouring pattern) plus the fakes this slice needs.

    ``sync_project_agents(..., routed=None)`` imports ``config.active_provider``
    AT CALL TIME (agents.py:605-608), so provider state — which in the real app
    is the user's routed backend and its credential — is pinned here rather than
    left for the lazy import to resolve."""
    sb = Sandbox(monkeypatch, tmp_path)

    def _no_provider(s=None):
        return None                                    # Anthropic-direct, invented

    monkeypatch.setattr(cfg, 'active_provider', _no_provider)
    monkeypatch.setattr(cfg, 'load_settings',
                        lambda: {'providers': [], 'provider_active': ''})
    monkeypatch.setattr(cfg, 'all_config_dirs',
                        lambda: [('default', str(sb.cfg))])

    def _never_read_credentials(*a, **k):
        raise AssertionError('a test reached a real credential reader')

    monkeypatch.setattr(usage_mod, '_creds', _never_read_credentials)
    monkeypatch.setattr(usage_mod, '_read_token', _never_read_credentials)
    monkeypatch.setattr(clientstate, 'client_json', _never_read_credentials)
    # no process may be started from this slice, at all
    monkeypatch.setattr(subprocess, 'Popen', _never_read_credentials)
    return sb


# ── small portable helpers ──────────────────────────────────────────────────

def _write(path, text):
    """Write exact bytes: explicit \\n, never the platform's own newline."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return path


def _read(path):
    with open(path, 'rb') as f:
        return f.read().decode('utf-8')


def _proj(tmp_path, name='proj'):
    p = tmp_path / name
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _dest(proj):
    return os.path.join(proj, '.claude', 'agents')


def _manifest_path(proj):
    return os.path.join(_dest(proj), agents._MANIFEST)


def _read_manifest(proj):
    p = _manifest_path(proj)
    if not os.path.isfile(p):
        return None
    return json.loads(_read(p))


def _seed(sb, category, name, text=None):
    """One library agent at <library>/<category>/<name>.md, exact bytes."""
    p = os.path.join(str(sb.agents_lib), category, name + '.md')
    return _write(p, text if text is not None
                  else '---\nname: %s\ndescription: Use PROACTIVELY when x.\n---\n\n'
                       'Body for %s.\n' % (name, name))


def _fail_writes(monkeypatch, path, note='simulated disk failure'):
    """Seam-fake the file layer: opening `path` for writing raises OSError."""
    real_open = builtins.open
    target = os.path.normcase(os.path.abspath(path))

    def fake_open(file, mode='r', *a, **kw):
        if not isinstance(file, int) and ('w' in mode or 'a' in mode or 'x' in mode):
            if os.path.normcase(os.path.abspath(str(file))) == target:
                raise OSError(note + ': ' + os.path.basename(target))
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, 'open', fake_open)


def _fail_reads(monkeypatch, path, note='simulated read failure'):
    """Seam-fake the file layer: opening `path` for reading raises OSError."""
    real_open = builtins.open
    target = os.path.normcase(os.path.abspath(path))

    def fake_open(file, mode='r', *a, **kw):
        if not isinstance(file, int) and 'w' not in mode and 'a' not in mode \
                and 'x' not in mode:
            if os.path.normcase(os.path.abspath(str(file))) == target:
                raise OSError(note + ': ' + os.path.basename(target))
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, 'open', fake_open)


# ── 1+2 · the manifest is project-supplied data, not an authority to delete ──

XFALL_TRAVERSAL = (
    'claude_sessions/agents.py:635 joins every manifest entry to dest with '
    'os.path.join(dest, fn) and os.remove()s the result at :638 with no '
    'containment check, so a .archeus-managed.json naming ../../* deletes a '
    'file archeus never placed — the contract at agents.py:590-591 says only '
    'files archeus previously placed are removed.')

XFALL_ABSOLUTE = (
    'claude_sessions/agents.py:635 — os.path.join(dest, fn) returns fn verbatim '
    'when fn is absolute, so the isfile/remove at :636-638 acts on any path the '
    'manifest names; contract at agents.py:590-591.')


@pytest.mark.xfail(strict=True, reason=XFALL_TRAVERSAL)
def test_manifest_traversal_entry_cannot_delete_outside(env, tmp_path):
    """agents.py:632-640 — a manifest naming `../../victim.md` must not be a
    licence to delete it. Closest existing test:
    test_tui_agents.py::test_sync_project_agents, whose manifest is always
    written by sync itself (basenames only), so the join is never given a
    parent segment and the escape is never attempted.

    The attacker in this scenario is a cloned project: `.claude/agents/` — and
    therefore the manifest — is part of the repository.
    """
    _seed(env, '01-core', 'rev')
    proj = _proj(tmp_path)
    dest = _dest(proj)
    os.makedirs(dest, exist_ok=True)
    victim = os.path.join(proj, 'victim.md')          # dest/../../victim.md
    _write(victim, 'user file, never placed by archeus\n')
    _write(_manifest_path(proj), json.dumps(['../../victim.md']))

    n = agents.sync_project_agents(proj, ['01-core/rev'])

    assert os.path.isfile(victim), 'manifest entry walked out of the agents dir'
    assert _read(victim) == 'user file, never placed by archeus\n'
    assert os.path.isfile(os.path.join(dest, 'rev.md')), 'the install still happens'
    assert _read_manifest(proj) == ['rev.md']
    assert n == 1


@pytest.mark.xfail(strict=True, reason=XFALL_ABSOLUTE)
def test_manifest_absolute_entry_cannot_delete_foreign(env, tmp_path):
    """agents.py:632-640 — same missing containment check, second entry shape.
    The absolute path is built from tmp_path so the test says nothing about
    POSIX-vs-Windows path syntax; on both, join(dest, <absolute>) IS the
    absolute argument. Closest existing test:
    test_tui_agents.py::test_sync_project_agents — it only ever asserts that
    files sync itself placed disappear.
    """
    _seed(env, '01-core', 'rev')
    proj = _proj(tmp_path)
    dest = _dest(proj)
    os.makedirs(dest, exist_ok=True)
    victim = os.path.join(str(tmp_path), 'victim-absolute.md')
    _write(victim, 'not an archeus file\n')
    _write(_manifest_path(proj), json.dumps([victim]))

    agents.sync_project_agents(proj, ['01-core/rev'])

    assert os.path.isfile(victim), 'an absolute manifest entry deleted a foreign file'
    assert _read(victim) == 'not an archeus file\n'


# ── 3+4 · no parse, no authority: fail closed on the removal half ────────────

def test_manifest_json_object_grants_no_removal_authority(env, tmp_path):
    """agents.py:616-617 — the ``isinstance(prev, list)`` guard. If it goes, the
    removal loop iterates the object's KEYS, which is the traversal of test 1
    arriving without any hostile content beyond a dict. The closest existing
    test (test_tui_agents.py::test_sync_project_agents) only ever feeds sync's
    own list output back in, so the guard is never exercised.
    """
    _seed(env, '01-core', 'rev')
    proj = _proj(tmp_path)
    dest = _dest(proj)
    os.makedirs(dest, exist_ok=True)
    victim = os.path.join(proj, 'victim-obj.md')
    _write(victim, 'mine\n')
    _write(os.path.join(dest, 'stale.md'), 'still installed, unprovable owner\n')
    _write(_manifest_path(proj), json.dumps({'../../victim-obj.md': True,
                                             'stale.md': True}))

    n = agents.sync_project_agents(proj, ['01-core/rev'])

    assert os.path.isfile(victim), 'a non-list manifest was used as a delete list'
    assert os.path.isfile(os.path.join(dest, 'stale.md')), \
        'ownership could not be established, so nothing may be removed'
    assert n == 1 and _read_manifest(proj) == ['rev.md'], \
        'the install and a fresh, well-formed record are still owed'


def test_unparseable_manifest_deletes_nothing_and_keeps_its_record(env, tmp_path):
    """agents.py:614-619 (parse failure) + :628-629 (early return) + :668-673
    (record only rewritten from a record we could read).

    A half-written manifest is the common real case — an AV scan or a crash
    during the last write. archeus must (a) delete nothing it cannot prove it
    placed, (b) not destroy the unreadable record, which is the only evidence of
    what it owns, and (c) re-establish ownership on the next successful sync so
    the files do not become permanent orphans. No existing test corrupts the
    manifest: the only other manifest reference in the suite,
    test_migration.py:97, asserts the file exists.
    """
    _seed(env, '01-core', 'rev')
    proj = _proj(tmp_path)
    dest = _dest(proj)
    os.makedirs(dest, exist_ok=True)
    _write(os.path.join(dest, 'orphan.md'), 'installed by an earlier sync\n')
    _write(os.path.join(dest, 'user.md'), 'the user wrote this\n')
    victim = os.path.join(proj, 'victim-parse.md')
    _write(victim, 'user file\n')
    broken = '["orphan.md", {"half'
    _write(_manifest_path(proj), broken)

    assert agents.sync_project_agents(proj, []) == 0
    assert os.path.isfile(os.path.join(dest, 'orphan.md')), \
        'a manifest archeus could not parse is not a delete list'
    assert os.path.isfile(os.path.join(dest, 'user.md'))
    assert os.path.isfile(victim)
    assert _read(_manifest_path(proj)) == broken, \
        'the unreadable ownership record was overwritten by a no-op sync'

    # retry: one good sync must put ownership back on disk
    assert agents.sync_project_agents(proj, ['01-core/rev']) == 1
    assert _read_manifest(proj) == ['rev.md']
    assert agents.sync_project_agents(proj, []) == 0
    assert not os.path.isfile(os.path.join(dest, 'rev.md')), \
        'the re-established record must actually own what it names'
    assert _read_manifest(proj) is None
    assert os.path.isfile(os.path.join(dest, 'orphan.md')), \
        'a file never named by a parsed record is never deleted'


# ── 5 · an unresolvable selection is not an install ─────────────────────────

def test_unresolvable_ref_is_not_counted_or_created(env, tmp_path):
    """agents.py:623-626 — ``if src:`` is the only thing between a ref that no
    longer resolves (library entry deleted, renamed category, a stale session
    record replayed by main.py:808) and an empty phantom agent file Claude Code
    would load. test_build_agents_json_skips_missing covers the same shape in a
    DIFFERENT function (build_agents_json), and test_sync_project_agents only
    ever passes refs that resolve, so this branch has never run.
    """
    _seed(env, '01-core', 'rev')
    proj = _proj(tmp_path)
    dest = _dest(proj)
    os.makedirs(dest, exist_ok=True)
    _write(os.path.join(dest, 'old.md'), 'managed, now deselected\n')
    _write(os.path.join(dest, 'user.md'), 'user owned\n')
    _write(_manifest_path(proj), json.dumps(['old.md']))

    n = agents.sync_project_agents(proj, ['01-core/ghost', 'nosep', '01-core/rev'])

    assert n == 1, n
    assert _read_manifest(proj) == ['rev.md']
    assert not os.path.exists(os.path.join(dest, 'ghost.md')), \
        'an unresolvable ref installed an empty agent Claude Code would route to'
    assert not os.path.exists(os.path.join(dest, 'nosep.md'))
    assert os.path.isfile(os.path.join(dest, 'rev.md'))
    assert not os.path.isfile(os.path.join(dest, 'old.md')), \
        'the cleanup pass must still run when a ref fails to resolve'
    assert os.path.isfile(os.path.join(dest, 'user.md'))


# ── 6 · a failed copy is not a managed success ──────────────────────────────

def test_copyfile_failure_is_not_counted_or_recorded(env, tmp_path, monkeypatch):
    """agents.py:646-666 — the copy is inside the try, ``written.append(fn)``
    sits AFTER it (:664) and the manifest is written from ``written``, not from
    ``desired``. Move the append above the copy, or build the manifest from the
    selection, and this goes red: the count is what gui_api.py:1884 shows the
    user, and a manifest naming a file that is not there makes the next sync
    delete, or fail to delete, the wrong thing. No existing test makes a copy
    fail; test_sync_project_agents always copies successfully.
    """
    _seed(env, '01-core', 'rev')
    _seed(env, '01-core', 'backend')
    proj = _proj(tmp_path)
    dest = _dest(proj)
    os.makedirs(dest, exist_ok=True)
    gone = os.path.join(dest, 'old.md')
    _write(gone, 'managed, now deselected\n')
    _write(_manifest_path(proj), json.dumps(['old.md']))

    real_copyfile = shutil.copyfile
    seen = []

    def fake_copyfile(src, dst, *a, **kw):
        # removal must already have happened before the first copy
        seen.append(os.path.isfile(gone))
        if str(dst).endswith('backend.md'):
            raise OSError('simulated copy failure')
        return real_copyfile(src, dst, *a, **kw)

    monkeypatch.setattr(shutil, 'copyfile', fake_copyfile)

    n = agents.sync_project_agents(proj, ['01-core/rev', '01-core/backend'])

    assert seen and not any(seen), 'the copy ran before the deselected file was removed'
    assert n == 1, n
    assert _read_manifest(proj) == ['rev.md'], \
        'a file whose copy failed must not be claimed as managed'
    assert not os.path.exists(os.path.join(dest, 'backend.md'))
    assert os.path.isfile(os.path.join(dest, 'rev.md'))
    assert not os.path.isfile(gone)
    md_path = os.path.join(proj, 'CLAUDE.md')
    md = _read(md_path) if os.path.isfile(md_path) else ''
    assert 'backend' not in md, 'the routing table advertises an absent agent'


# ── 7+8 · the routed strip is scoped to the frontmatter, and no wider ───────

def test_routed_strip_touches_only_frontmatter_model_keys(env, tmp_path):
    """agents.py:652-659 — the filter is ``l.strip().startswith('model:')`` over
    ``content[3:end]`` only. The closest existing test is
    test_providers.py:309 (``test_synced_agents_lose_their_model_field_on_a_routed_session``,
    one flat frontmatter line and a one-word body), so ``.strip()``
    can be dropped (an indented key survives and the subagent 401s anyway) and
    ``'model:'`` can loosen to ``'model'`` (a real key such as ``model_name`` is
    silently eaten) without moving it.
    """
    _seed(env, '01-core', 'mixed', text=(
        '---\n'
        'name: mixed\n'
        'description: Use PROACTIVELY when reviewing.\n'
        '  model: claude-indented-haiku\n'
        'model: claude-haiku-4-5\n'
        'model_name: keep-me\n'
        'models: keep-me-too\n'
        '---\n\n'
        'Body text.\n'))
    proj = _proj(tmp_path)
    dest = _dest(proj)

    assert agents.sync_project_agents(proj, ['01-core/mixed'], routed=True) == 1
    out = _read(os.path.join(dest, 'mixed.md'))

    assert 'claude-haiku-4-5' not in out, 'frontmatter model: survived on a routed sync'
    assert 'claude-indented-haiku' not in out, \
        'the indented model: key survived — the filter lost its .strip()'
    assert 'model_name: keep-me' in out, 'a near-miss key was eaten by the strip'
    assert 'models: keep-me-too' in out
    assert 'name: mixed' in out
    assert 'description: Use PROACTIVELY when reviewing.' in out
    assert 'Body text.' in out


@pytest.mark.xfail(strict=True, reason=(
    "possible source defect, claude_sessions/agents.py:650 and :660: the routed copy reads and "
    "writes in text mode, so on Windows the body comes back with CRLF line endings and is not "
    "carried byte-for-byte as the docstring promises. Cosmetic in effect; kept as the contract."))
def test_routed_strip_preserves_a_body_model_line(env, tmp_path):
    """agents.py:655-661 — ``fm`` is ``content[3:end]``; the body is carried
    through by ``body = content[end + 4:]`` and re-emitted untouched. The
    closest existing test is test_providers.py:309, which uses the
    literal body ``body``, so applying the filter to the WHOLE file — which
    rewrites what the agent IS while "fixing" which model it calls — passes it.
    Agent bodies in this library carry example frontmatter, so this is the
    common case, not a corner.
    """
    body = ('When configuring the subagent, write:\n\n'
            '    model: claude-body-marker\n\n'
            '    model_name: also-a-marker\n\n'
            'Then save it as .claude/agents/x.md.\n')
    _seed(env, '01-core', 'writer', text=(
        '---\nname: writer\ndescription: Use PROACTIVELY when writing docs.\n'
        'model: claude-haiku-4-5\n---\n\n' + body))
    proj = _proj(tmp_path)
    assert agents.sync_project_agents(proj, ['01-core/writer'], routed=True) == 1
    out = _read(os.path.join(_dest(proj), 'writer.md'))
    assert 'claude-haiku-4-5' not in out
    assert 'model: claude-body-marker' in out, 'the body was rewritten, not the frontmatter'
    assert out.endswith('\n---\n\n' + body), 'the body is not carried byte-for-byte'


# ── 9 · an unrecorded install may not be reported as one ────────────────────

XFALL_MANIFEST_WRITE = (
    'claude_sessions/agents.py:668-671 swallows the manifest write failure in '
    'the same `except Exception: pass` that guards the success path, and '
    'agents.py:684 returns len(written) regardless, so the caller (gui_api.py'
    ':1884) reports N installed agents that no manifest names — files the user '
    'can never remove through archeus, because the removal loop at :632 only '
    'follows the manifest.')


@pytest.mark.xfail(strict=True, reason=XFALL_MANIFEST_WRITE)
def test_failed_manifest_write_is_not_reported_as_managed(env, tmp_path):
    """agents.py:668-675 + :684 — the count returned must never exceed what the
    ownership record backs. Fail-closed either way: roll the copies back, or
    report 0; the assertion does not prescribe which, it only refuses a number
    archeus cannot honour later. test_sync_project_agents only exercises the
    manifest on a write that succeeds.
    """
    _seed(env, '01-core', 'rev')
    proj = _proj(tmp_path)
    dest = _dest(proj)
    _fail_writes(env.mp, _manifest_path(proj))

    n = agents.sync_project_agents(proj, ['01-core/rev'])

    assert os.path.isfile(os.path.join(dest, 'rev.md')), \
        'precondition: the copy itself still succeeded'
    recorded = _read_manifest(proj) or []
    assert n == len(recorded), \
        'returned %r while the manifest names %r: untracked agents are ' \
        'unremovable agents' % (n, recorded)


# ── 10 · a routing-path failure cannot inflate the count ────────────────────

def test_routed_read_failure_cannot_inflate_the_count(env, tmp_path):
    """agents.py:649-665, :684 — the routed branch reads the source itself
    (:650) instead of delegating to shutil, so it has its own failure surface
    (a library file locked by an editor on Windows, or removed between
    find_library_agent and the copy). test_providers's routed test has one
    readable source and no manifest assertion, so an exception that skipped
    ``written.append`` but still returned ``len(desired)`` — or one that leaked
    the failed name into the manifest — stays green there.
    """
    _seed(env, '01-core', 'a', text=(
        '---\nname: a\ndescription: Use PROACTIVELY when a.\n'
        'model: claude-haiku-4-5\n---\n\nBody a.\n'))
    bad = _seed(env, '01-core', 'b', text=(
        '---\nname: b\ndescription: Use PROACTIVELY when b.\n---\n\nBody b.\n'))
    proj = _proj(tmp_path)
    dest = _dest(proj)
    _fail_reads(env.mp, bad)

    n = agents.sync_project_agents(proj, ['01-core/a', '01-core/b'], routed=True)

    assert n == 1, n
    assert _read_manifest(proj) == ['a.md'], 'the failed agent was claimed as managed'
    assert not os.path.exists(os.path.join(dest, 'b.md')), \
        'a failed routed copy left a file Claude Code will discover'
    a_out = _read(os.path.join(dest, 'a.md'))
    assert 'claude-haiku-4-5' not in a_out, \
        'the agent that did copy never went through the routed strip'
    assert 'Body a.' in a_out
