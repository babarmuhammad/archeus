"""T-1170 — close the highest-risk test gaps in claude_sessions/claude_md.py.

Source slice under test: ``claude_sessions/claude_md.py`` lines **363-691**
inclusive (``_build_autogen_block`` at 363 through the end of
``ai_compress_claude_md`` at 688; ``_build_ai_context`` begins at 691 and its
branches belong to another card). Definitions and imports outside that range
were read as read-only context only, and NO source file was edited.

The ten final branches, ranked by risk (fail-closed and denial first, then
boundaries, then error paths). Each entry: source file:line — closest existing
test — why that test's assertion misses this case — the test name here.

 1. claude_md.py:489-490 ``prune_claude_md``: ``if not _cfg.write_atomic(...)``
    ``return None`` must abort BEFORE ``diffview.record`` and
    ``workspace.update_manifest``.
    Closest: tests/test_tui_generators.py::test_prune_is_reversible_and_restamps_freshness
    — it only exercises the *successful* write, so an implementation that kept
    going after a failed write (recording a version that never landed and
    stamping the freshness baseline of a file it did not change) stays green.
    Test: ``test_prune_write_failure_stamps_no_version_or_manifest``.
 2. claude_md.py:666-667 + 668-671 ``ai_compress_claude_md``: the ``` fence
    strip, then ``_valid_compressed``'s 80-char floor (claude_md.py:546-547)
    refusing the rewrite.
    Closest: tests/test_tui_generators.py::test_ai_compress_refusal_leaves_file_untouched
    — its model reply (``"I'll help you compress this file..."``) is rejected by
    the FIRST clause of ``_valid_compressed`` (claude_md.py:546, no leading
    ``#``), so neither the fence-strip branch nor the length floor is ever
    entered, and the refusal it does check happens before ``diffview.confirm``.
    Test: ``test_compression_refuses_a_fenced_or_short_model_reply``.
 3. claude_md.py:434-437 ``replace_machine_blocks``: an EMPTY new SESSIONS block
    deletes the owned block and nothing else.
    Closest: tests/test_ctxaudit.py::test_prune_claude_md_shrinks_and_preserves_manual_and_memory
    — it caps 30 entries down to 10, so the block always survives; the
    ``new_sessions or ''`` arm that removes the block outright is never taken.
    Test: ``test_empty_session_scan_removes_only_the_owned_block``.
 4. claude_md.py:428-430 ``replace_machine_blocks``: duplicated AUTOGEN blocks —
    the text OUTSIDE them (before, between, after) is preserved exactly once.
    Closest: tests/test_tui_generators.py::test_scaffold_preserves_user_content
    — one well-formed block only, so a pre/post split that went wrong on the
    second occurrence (``rindex``, a greedy regex) is invisible there.
    Test: ``test_duplicate_machine_blocks_keep_the_text_outside_them``.
 5. claude_md.py:428-430 (second pass): an UNMATCHED AUTOGEN marker must not let
    a later rewrite erase the prose that sits between it and the next END.
    Closest: tests/test_ctxaudit.py::test_prune_claude_md_shrinks_...  — always
    runs prune exactly once on a file whose markers are balanced, so the
    self-inflicted second pass is never reached.
    Test: ``test_unmatched_autogen_marker_does_not_erase_prose`` (xfail).
 6. claude_md.py:434-438: a SESSIONS block that sits BEFORE the AUTOGEN block is
    outside ``post``, so the cap is never applied to it and a second block is
    appended. Closest: tests/test_ctxaudit.py::test_prune_claude_md_shrinks_...
    — its file is in AUTOGEN-then-SESSIONS order, the only order that works.
    Test: ``test_sessions_block_before_autogen_is_still_capped`` (xfail).
 7. claude_md.py:428-430: AUTOGEN sentinels written in REVERSE (END before
    START) — the manual half must appear exactly once.
    Closest: tests/test_ctxaudit.py::test_audit_warns_on_long_claude_md_and_uncapped_sessions
    — reads a malformed file but only counts tokens, never rewrites it.
    Test: ``test_reversed_autogen_markers_do_not_duplicate_manual_text`` (xfail).
 8. claude_md.py:434-437: SESSIONS sentinels in REVERSE inside ``post`` — same
    class of corruption on the session half. No existing test feeds a crossed
    SESSIONS pair to any writer (tests/test_ctxaudit.py only feeds a file that
    has SESSIONS and no AUTOGEN at all, and never writes it back).
    Test: ``test_reversed_sessions_markers_do_not_duplicate_manual_text`` (xfail).
 9. claude_md.py:424-440 + 485-486: ``prune_claude_md`` must be a fixed point —
    the second pass writes the same bytes, so ``changed`` goes False and neither
    the file nor the freshness baseline moves again.
    Closest: tests/test_tui_generators.py::test_prune_is_reversible_and_restamps_freshness
    — one pass only, and it asserts the manifest WAS stamped, which is exactly
    what a non-idempotent prune keeps doing on every keypress.
    Test: ``test_repeated_prune_is_a_fixed_point`` (xfail).
10. claude_md.py:512-522 + 526-539 ``_fence_out``/``_fence_in``: a KEEP
    placeholder COLLISION — manual text that already contains the literal
    ``@@ARCHEUS_KEEP_0@@`` — must round-trip verbatim.
    Closest: tests/test_tui_generators.py::test_a_fenced_section_goes_back_where_its_marker_was
    — there the literal marker sits in the MODEL reply (test_tui_generators.py:267),
    which is exactly the one legitimate occurrence; no test puts one in the USER's
    manual text, where ``_fence_out`` creates a second occurrence of the same mark
    and ``out.replace(mark, region)`` (536) then hits both.
    Test: ``test_keep_placeholder_collision_cannot_overwrite_manual_text`` (xfail).

Replaced probe: the card's probe 8 ("preview writes nothing") is already
covered by tests/test_tui_generators.py::test_prune_preview_writes_nothing_and_names_what_goes
(asserts the CLAUDE.md bytes are unchanged), so that slot went to the KEEP
collision of probe 10, which no test touches; the refusal half of probe 10 kept
its own test because the existing refusal test cannot reach the two branches
listed in item 2.

Everything below is fake at the OS seam: git, the session scan, settings,
account/config roots, the model call, the diff confirm, the manifest and the
flash bar are all patched before any entrypoint can reach the host. All writes
stay under ``tmp_path`` (``harness.Sandbox`` repoints the config root, the
selected home, the temp dir and the account list). No credential file is read,
no real process, network, editor, pager or thread is started, and no host
environment value is read, printed or copied.
"""

import builtins
import errno
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                       # noqa: E402

from harness import Sandbox                         # noqa: E402

from claude_sessions import (claude_md, config, diffview, memory,  # noqa: E402
                             sessions, ui, workspace)
from claude_sessions.config import (_AGENTS_END, _AGENTS_START,   # noqa: E402
                                    _AUTOGEN_END, _AUTOGEN_START,
                                    _KEEP_END, _KEEP_START,
                                    _LOOP_END, _LOOP_START,
                                    _MEMORY_END, _MEMORY_START,
                                    _SESSIONS_END, _SESSIONS_START)

MARKDOWN = '```'
HEADLESS_LINE = ('- **ffff0000** (3 msgs): You are distilling durable LESSONS '
                 'from a coding-session transcript so future sessions start smarter.')
GOOD_COMPRESSED = ('# alpha\n\n- run: pytest -q\n- style: terse, no marketing tone\n'
                   '- package manager: uv\n- never edit the dist/ directory by hand\n')


def _seed(tmp_path, proj, text):
    """Write CLAUDE.md into the sandbox project and hand back its path."""
    md_path = os.path.join(proj, 'CLAUDE.md')
    with open(md_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return md_path


def _read(md_path):
    with open(md_path, encoding='utf-8', newline='') as f:
        return f.read()


def _quiet_world(monkeypatch, tmp_path, folder, cap=10):
    """Fake every seam between this slice and the host, and record the calls.

    git, the repo walk, extra-paths, the account/session-folder scan, settings,
    the version recorder, the freshness manifest and the flash bar are all
    replaced BEFORE prune or compress can reach a real path, a real ``git``,
    another account's projects dir or a real subprocess.
    """
    calls = {'write': [], 'record': [], 'manifest': [], 'flash': [],
             'confirm': [], 'git': [], 'model': []}

    monkeypatch.setattr(claude_md, '_git', _fake_git(calls))
    monkeypatch.setattr(claude_md, 'find_git_repos', lambda root, max_depth=2: [root])
    monkeypatch.setattr(claude_md, 'read_extra_paths', lambda proj_folder: [])
    monkeypatch.setattr(config, 'load_settings', lambda: {'claude_md_sessions_cap': cap})
    monkeypatch.setattr(sessions, 'project_session_folders',
                        lambda pf, *a, **k: [pf] if pf and os.path.isdir(pf) else [])
    monkeypatch.setattr(diffview, 'record',
                        lambda *a, **k: calls['record'].append(a[3:]))
    monkeypatch.setattr(diffview, 'confirm',
                        lambda *a, **k: calls['confirm'].append(a) or True)
    monkeypatch.setattr(workspace, 'update_manifest',
                        lambda *a, **k: calls['manifest'].append(a[2:]))
    monkeypatch.setattr(ui, 'flash', lambda *a, **k: calls['flash'].append(a[:1]))
    real_write = config.write_atomic            # the conftest-guarded original

    def spy_write(path, text, **kw):
        calls['write'].append(os.path.basename(path))
        return real_write(path, text, **kw)

    monkeypatch.setattr(config, 'write_atomic', spy_write)
    # the project dir must contain nothing but CLAUDE.md, or the AUTOGEN block
    # would depend on which snapshot folders a writer happened to leave behind
    proj = str(tmp_path / 'work' / 'alpha')
    if os.path.isdir(proj):
        assert not [f for f in os.listdir(proj) if f != 'CLAUDE.md'], \
            'fixture left stray files in the project dir'
    return calls


def _fake_git(calls):
    def _git(args, cwd=None, **kw):
        calls['git'].append(list(args))
        if args[:3] == ['remote', 'get-url', 'origin']:
            return 'https://git.example.test/org/alpha.git\n'
        if args and args[0] == 'log':
            return 'aaaa1111 invented commit one\nbbbb2222 invented commit two\n'
        return ''
    return _git


# ── 1. failed prune: no version, no manifest, no half-file ────

def test_prune_write_failure_stamps_no_version_or_manifest(monkeypatch, tmp_path):
    """claude_md.py:489-490. A write that fails must not be reported as a
    prune: the audit screen would say "pruned", the History card would offer a
    version of a file that never changed, and the freshness score would rise."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("# alpha\n\nMY HAND WRITTEN NOTES\n\n"
              + _AUTOGEN_START + "\nold autogen body\n" + _AUTOGEN_END + "\n"
              + _SESSIONS_START + "\n## Session topics\n- **s1** (2 msgs): keep me\n"
              + _SESSIONS_END + "\n"
              + _MEMORY_START + "\ndigest line\n" + _MEMORY_END + "\n")
    md_path = _seed(tmp_path, proj, seeded)
    calls = _quiet_world(monkeypatch, tmp_path, folder)

    real_write = config.write_atomic

    def disk_full(path, text, **kw):           # CLAUDE.md locked by a reader
        if os.path.basename(path) == 'CLAUDE.md':
            calls['write'].append('CLAUDE.md')
            return False
        return real_write(path, text, **kw)

    monkeypatch.setattr(config, 'write_atomic', disk_full)

    assert claude_md.prune_claude_md(proj, folder) is None
    assert _read(md_path) == seeded, 'the user file must be exactly what it was'
    assert calls['record'] == [], 'no version of a write that did not happen'
    assert calls['manifest'] == [], 'no freshness stamp for a write that failed'
    assert not [f for f in os.listdir(proj) if f.endswith(('.bak', '.tmp'))], \
        'no backup or half-written debris left behind'
    assert sb.editor_opened == []


# ── 2. compression refuses a fenced / too-short reply ─────────

def test_compression_refuses_a_fenced_or_short_model_reply(monkeypatch, tmp_path):
    """claude_md.py:666-667 then 668-671. A model that wraps its answer in a
    fence and hands back a stub must be refused — the file it writes is loaded
    into every turn of every session, so a 20-token rewrite is corruption."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("# alpha\n\n## Long prose\n" + "wordy filler sentence. " * 40 + "\n\n"
              + _AUTOGEN_START + "\nold autogen body\n" + _AUTOGEN_END + "\n"
              + _SESSIONS_START + "\n## Session topics\n- **s1** (2 msgs): keep me\n"
              + _SESSIONS_END + "\n"
              + _MEMORY_START + "\ndigest line\n" + _MEMORY_END + "\n")
    md_path = _seed(tmp_path, proj, seeded)
    calls = _quiet_world(monkeypatch, tmp_path, folder)
    monkeypatch.setattr(memory, '_claude_stdin',
                        lambda prompt, *a, **k: calls['model'].append(prompt)
                        or MARKDOWN + 'markdown\n# alpha\n\n- tiny\n' + MARKDOWN)

    assert claude_md.ai_compress_claude_md(proj, folder) is False
    assert len(calls['model']) == 1, 'exactly one model call, faked'
    assert _read(md_path) == seeded, 'refused rewrite leaves the file alone'
    assert calls['confirm'] == [], 'refused before ever asking the user'
    assert calls['record'] == [] and calls['manifest'] == []
    assert not [f for f in os.listdir(proj) if f.endswith(('.bak', '.tmp'))]

    # positive control: the very same fence around a real answer is stripped and
    # accepted — without it the assertions above pass on a stripped-out fence
    monkeypatch.setattr(memory, '_claude_stdin',
                        lambda prompt, *a, **k: calls['model'].append(prompt)
                        or MARKDOWN + 'markdown\n' + GOOD_COMPRESSED + MARKDOWN)
    assert claude_md.ai_compress_claude_md(proj, folder) is True
    out = _read(md_path)
    assert '- package manager: uv' in out
    assert MARKDOWN not in out.split(_AUTOGEN_START)[0], 'no fence left in the manual half'
    assert 'wordy filler sentence.' not in out
    assert _MEMORY_START + "\ndigest line\n" + _MEMORY_END in out


# ── 3. empty session scan: the owned block goes, nothing else ─

def test_empty_session_scan_removes_only_the_owned_block(monkeypatch, tmp_path):
    """claude_md.py:434-437, the ``new_sessions or ''`` arm. archeus owns the
    SESSIONS block, so it may delete it; it may not take the manual half, the
    AUTOGEN block or the other machine blocks with it."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("# alpha\n\nMY HAND WRITTEN NOTES stay\n\n"
              + _AUTOGEN_START + "\nold autogen body\n" + _AUTOGEN_END + "\n"
              + _SESSIONS_START + "\n## Session topics\n" + HEADLESS_LINE + "\n"
              + _SESSIONS_END + "\n"
              + _MEMORY_START + "\ndigest line\n" + _MEMORY_END + "\n"
              + _AGENTS_START + "\nrouting table\n" + _AGENTS_END + "\n"
              + _LOOP_START + "\nloop journal\n" + _LOOP_END + "\n")
    md_path = _seed(tmp_path, proj, seeded)
    calls = _quiet_world(monkeypatch, tmp_path, folder)

    assert claude_md.prune_claude_md(proj, folder) is not None
    out = _read(md_path)
    assert _SESSIONS_START not in out and _SESSIONS_END not in out, \
        'the owned block is gone, sentinels included'
    assert 'You are distilling durable LESSONS' not in out
    assert 'MY HAND WRITTEN NOTES stay' in out
    assert _MEMORY_START + "\ndigest line\n" + _MEMORY_END in out
    assert _AGENTS_START + "\nrouting table\n" + _AGENTS_END in out
    assert _LOOP_START + "\nloop journal\n" + _LOOP_END in out
    assert _AUTOGEN_START in out and 'old autogen body' not in out
    assert calls['write'] == ['CLAUDE.md'], 'one write, the project file'


# ── 4. duplicated machine blocks: outer text survives ─────────

def test_duplicate_machine_blocks_keep_the_text_outside_them(monkeypatch, tmp_path):
    """claude_md.py:428-430. Two AUTOGEN blocks: the first is replaced, and the
    prose before, BETWEEN and AFTER both blocks is kept exactly once."""
    _sb = Sandbox(monkeypatch, tmp_path)          # no host path is reachable
    _quiet_world(monkeypatch, tmp_path, None)
    existing = ("OUTER A PROSE\n"
                + _AUTOGEN_START + "\nfirst stale body\n" + _AUTOGEN_END + "\n"
                + "BETWEEN PROSE MUST SURVIVE\n"
                + _AUTOGEN_START + "\nsecond stale body\n" + _AUTOGEN_END + "\n"
                + "OUTER B PROSE\n")
    out = claude_md.replace_machine_blocks(
        existing, _AUTOGEN_START + "\nFRESH AUTOGEN\n" + _AUTOGEN_END + "\n",
        _SESSIONS_START + "\n## Session topics\n- **s9** (1 msgs): fresh line\n"
        + _SESSIONS_END + "\n")
    assert out.count('BETWEEN PROSE MUST SURVIVE') == 1
    assert 'OUTER A PROSE' in out and 'OUTER B PROSE' in out
    assert 'first stale body' not in out, 'the block archeus replaced is replaced'
    assert 'FRESH AUTOGEN' in out
    assert '- **s9** (1 msgs): fresh line' in out
    assert 'BETWEEN PROSE MUST SURVIVE' in out[:out.index('FRESH AUTOGEN')] \
        or 'BETWEEN PROSE MUST SURVIVE' in out[out.index('FRESH AUTOGEN'):]


# ── 5. unmatched marker: the second pass must not eat prose ───

def test_unmatched_autogen_marker_does_not_erase_prose(monkeypatch, tmp_path):
    """claude_md.py:428-430 across two passes. One stray marker in the user's
    file must never become a pair that swallows their prose."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("OUTER A PROSE\n" + _AUTOGEN_START
              + " stray marker a user typed, no end\n"
              + "TAIL PROSE MUST SURVIVE\n")
    md_path = _seed(tmp_path, proj, seeded)
    _quiet_world(monkeypatch, tmp_path, folder)

    assert claude_md.prune_claude_md(proj, folder) is not None
    assert 'TAIL PROSE MUST SURVIVE' in _read(md_path), 'first pass is safe'
    assert claude_md.prune_claude_md(proj, folder) is not None
    assert 'TAIL PROSE MUST SURVIVE' in _read(md_path), \
        'the second pass erased the manual half between the stray START and the END'
    once = _read(md_path)
    assert claude_md.prune_claude_md(proj, folder) is not None
    assert _read(md_path) == once, 'a further prune changed the bytes'


# ── 6. SESSIONS written before AUTOGEN still gets capped ──────

def test_sessions_block_before_autogen_is_still_capped(monkeypatch, tmp_path):
    """claude_md.py:434-438. Block order is user-editable; the cap is not
    allowed to depend on it."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("# alpha\n\nMY HAND WRITTEN NOTES\n\n"
              + _SESSIONS_START + "\n## Session topics\n"
              + "- **old1** (9 msgs): STALE ENTRY ONE\n"
              + "- **old2** (9 msgs): STALE ENTRY TWO\n"
              + "- **old3** (9 msgs): STALE ENTRY THREE\n"
              + _SESSIONS_END + "\n"
              + _AUTOGEN_START + "\nold autogen body\n" + _AUTOGEN_END + "\n")
    md_path = _seed(tmp_path, proj, seeded)
    calls = _quiet_world(monkeypatch, tmp_path, folder, cap=1)

    prev = claude_md.prune_preview(proj, folder)
    assert prev is not None and prev['changed']
    assert sorted(prev['dropped']) == ['old2', 'old3'], \
        'the preview names the entries the cap discards'
    assert claude_md.prune_claude_md(proj, folder) is not None
    out = _read(md_path)
    assert out.count(_SESSIONS_START) == 1, 'prune must not leave a second SESSIONS block'
    assert 'STALE ENTRY TWO' not in out and 'STALE ENTRY THREE' not in out, \
        'the entries the preview promised to drop are still in the file'
    assert 'MY HAND WRITTEN NOTES' in out
    assert calls['manifest'] == [('prune',)]
    assert claude_md.prune_claude_md(proj, folder) is not None
    assert _read(md_path) == out, 'a second prune changed the bytes'


# ── 7. reversed AUTOGEN sentinels ─────────────────────────────

def test_reversed_autogen_markers_do_not_duplicate_manual_text(monkeypatch, tmp_path):
    """claude_md.py:428-430. END written before START is corruption the user can
    cause by editing; it may not be paid for in duplicated prose."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("HEAD PROSE\n" + _AUTOGEN_END + "\nMIDDLE PROSE MUST SURVIVE\n"
              + _AUTOGEN_START + "\nstale autogen body\n")
    md_path = _seed(tmp_path, proj, seeded)
    _quiet_world(monkeypatch, tmp_path, folder)

    assert claude_md.prune_claude_md(proj, folder) is not None
    out = _read(md_path)
    assert out.count('MIDDLE PROSE MUST SURVIVE') == 1, 'manual half, exactly once'
    assert out.count('HEAD PROSE') == 1
    assert out.count('invented commit one') == 1, 'one rebuilt AUTOGEN block'
    assert _AUTOGEN_START in out
    assert claude_md.prune_claude_md(proj, folder) is not None
    assert _read(md_path) == out, 'a second prune changed the bytes'


# ── 8. reversed SESSIONS sentinels ────────────────────────────

def test_reversed_sessions_markers_do_not_duplicate_manual_text(monkeypatch, tmp_path):
    """claude_md.py:434-437. Same class as the AUTOGEN pair, on the session
    half — where the duplication is multiplied on every pass."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("# alpha\n" + _AUTOGEN_START + "\nold autogen body\n" + _AUTOGEN_END
              + "\n" + _SESSIONS_END + "\nMID PROSE MUST SURVIVE\n" + _SESSIONS_START
              + "\n- **old2** (4 msgs): STALE ENTRY MUST GO\n\nTAIL PROSE\n")
    md_path = _seed(tmp_path, proj, seeded)
    _quiet_world(monkeypatch, tmp_path, folder)

    assert claude_md.prune_claude_md(proj, folder) is not None
    out = _read(md_path)
    assert out.count('MID PROSE MUST SURVIVE') == 1, 'manual half, exactly once'
    assert out.count('TAIL PROSE') == 1
    assert out.count('invented commit one') == 1, 'one rebuilt AUTOGEN block'
    assert claude_md.prune_claude_md(proj, folder) is not None
    assert _read(md_path) == out, 'a second prune changed the bytes'


# ── 9. prune is a fixed point ─────────────────────────────────

def test_repeated_prune_is_a_fixed_point(monkeypatch, tmp_path):
    """claude_md.py:424-440 and 485-486. A rebuild that is not idempotent is a
    file that grows while the user watches the token count go up."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(sb.root / 'work' / 'alpha')
    seeded = ("# alpha\n\nMY HAND WRITTEN NOTES\n\n"
              + _AUTOGEN_START + "\nold autogen body\n" + _AUTOGEN_END + "\n"
              + _SESSIONS_START + "\n## Session topics\n- **s1** (2 msgs): keep me\n"
              + _SESSIONS_END + "\n"
              + _MEMORY_START + "\ndigest line\n" + _MEMORY_END + "\n")
    md_path = _seed(tmp_path, proj, seeded)
    calls = _quiet_world(monkeypatch, tmp_path, folder)

    first = claude_md.prune_claude_md(proj, folder)
    assert first is not None and first[1] > first[0], 'first pass really shrank it'
    after_first = _read(md_path)
    calls['write'].clear()
    calls['record'].clear()
    calls['manifest'].clear()

    second = claude_md.prune_claude_md(proj, folder)
    assert second is not None
    assert _read(md_path) == after_first, 'second pass wrote different bytes'
    assert second[0] == second[1], 'a rebuilt file must report no token change'
    assert calls['write'] == [], 'nothing to write, nothing may be written'
    assert calls['record'] == [] and calls['manifest'] == [], \
        'no version history or freshness stamp for a no-op'


# ── 10. KEEP placeholder collision ────────────────────────────

def test_keep_placeholder_collision_cannot_overwrite_manual_text(monkeypatch, tmp_path):
    """claude_md.py:512-522 + 526-539. The fence must round-trip the manual half
    verbatim, including a marker string the user typed themselves."""
    _sb = Sandbox(monkeypatch, tmp_path)          # no host path is reachable
    _quiet_world(monkeypatch, tmp_path, None)
    manual = ("# alpha\n\nintro sentence with a literal @@ARCHEUS_KEEP_0@@ inside it\n\n"
              + _KEEP_START + "\n## Guardrails\nDO NOT REWORD ME\n" + _KEEP_END + "\n\n"
              "trailing sentence\n")
    model_side, kept = claude_md._fence_out(manual)
    assert 'DO NOT REWORD ME' not in model_side, 'the region never reaches the model'
    assert kept == [_KEEP_START + "\n## Guardrails\nDO NOT REWORD ME\n" + _KEEP_END]
    out = claude_md._fence_in(model_side, kept)
    assert out.count(_KEEP_START) == 1, 'the region comes back once, not twice'
    assert 'literal @@ARCHEUS_KEEP_0@@ inside it' in out, \
        'the user own sentence was overwritten by the fenced region'
    assert 'trailing sentence' in out
    assert claude_md._fence_in(model_side, kept, claude_md._keep_stem(manual)) == manual, \
        'with the stem the manual was fenced under, the round trip is byte-exact'


# ── 11. user prose keeps a stray marker; model output does not ───

def test_manual_prose_keeps_text_after_a_stray_start_marker(monkeypatch, tmp_path):
    """claude_md.py `_drop_blocks` removes a START that never reaches its END with
    the paragraph under it. That is for model echoes. Manual prose saved from the
    GUI is the user's own text: `KEEP THIS` lies outside any paired block and must
    survive, and the real MEMORY block is still carried exactly once."""
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(tmp_path / 'work' / 'alpha')
    seeded = ('# alpha\n\n' + _AUTOGEN_START + '\nold body\n' + _AUTOGEN_END + '\n'
              + _MEMORY_START + '\nREAL DIGEST\n' + _MEMORY_END + '\n')
    md_path = _seed(tmp_path, proj, seeded)
    _quiet_world(monkeypatch, tmp_path, folder)

    typed = '# Notes\n' + _MEMORY_START + '\nKEEP THIS\n\nTail\n'
    ok, err = claude_md.set_manual_prose(proj, folder, typed)

    assert ok, err
    out = _read(md_path)
    assert 'KEEP THIS' in out and 'Tail' in out, 'user prose was deleted'
    assert out.count(_MEMORY_END) == 1 and out.count('REAL DIGEST') == 1, \
        'the MEMORY block is not carried exactly once'


# ── 12. a marker in an example or in a sentence is not a block ───

def test_fenced_marker_example_survives_prune_and_real_block_is_replaced(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(tmp_path / 'work' / 'alpha')
    example = ('```md\n' + _AUTOGEN_START + '\nKEEP EXAMPLE\n' + _AUTOGEN_END
               + '\n```\n')
    seeded = ('# alpha\n\n' + example + '\n'
              + _AUTOGEN_START + '\nold body\n' + _AUTOGEN_END + '\n')
    md_path = _seed(tmp_path, proj, seeded)
    _quiet_world(monkeypatch, tmp_path, folder)

    assert claude_md.prune_claude_md(proj, folder) is not None
    out = _read(md_path)
    assert example in out, 'the fenced example was rewritten'
    assert 'old body' not in out, 'the real block after the example was not replaced'
    assert out.count(_AUTOGEN_START) == 2
    assert claude_md.prune_claude_md(proj, folder) is not None
    assert _read(md_path) == out, 'a second prune changed the bytes'


def test_inline_quoted_marker_pair_is_not_a_block(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(tmp_path / 'work' / 'alpha')
    sentence = ('Wrap text in `' + _AUTOGEN_START + '` and `' + _AUTOGEN_END
                + '` to mark it.\n')
    seeded = ('# alpha\n\n' + sentence
              + _AUTOGEN_START + '\nold body\n' + _AUTOGEN_END + '\n')
    md_path = _seed(tmp_path, proj, seeded)
    _quiet_world(monkeypatch, tmp_path, folder)

    assert claude_md.prune_claude_md(proj, folder) is not None
    out = _read(md_path)
    assert sentence in out, 'the quoted pair was taken for a block'
    assert 'old body' not in out


def test_unclosed_fence_at_end_does_not_hide_block_before_it(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(tmp_path / 'work' / 'alpha')
    seeded = ('# alpha\n\n' + _AUTOGEN_START + '\nold body\n' + _AUTOGEN_END
              + '\n\n```md\ntrailing example without a closing fence\n')
    md_path = _seed(tmp_path, proj, seeded)
    _quiet_world(monkeypatch, tmp_path, folder)

    assert claude_md.prune_claude_md(proj, folder) is not None
    out = _read(md_path)
    assert 'old body' not in out, 'the real block before the open fence was not found'
    assert 'trailing example without a closing fence' in out


def test_an_unclosed_fence_above_a_block_does_not_hide_it():
    text = ('# alpha\n\n```md\nforgotten closing line\n\n'
            + _AUTOGEN_START + '\nbody\n' + _AUTOGEN_END + '\n')
    span = claude_md.block_span(text, _AUTOGEN_START, _AUTOGEN_END)
    assert span is not None and text[span[0]:span[1]].endswith(_AUTOGEN_END)
    assert claude_md.well_formed(text + _AUTOGEN_END + '\n', _AUTOGEN_START, _AUTOGEN_END) is False


def test_inline_code_that_starts_a_line_with_three_backticks_is_not_a_fence():
    text = ('```not a fence``` inline\n' + _AUTOGEN_START + '\nbody\n' + _AUTOGEN_END
            + '\n\n```\ncode\n```\n')
    assert claude_md.block_span(text, _AUTOGEN_START, _AUTOGEN_END) is not None


# ── 13. an unreadable CLAUDE.md is never overwritten by a scaffold ───

def _deny_claude_md_read(monkeypatch):
    real_open = builtins.open

    def denied(path, mode='r', *a, **k):
        if os.path.basename(str(path)) == 'CLAUDE.md' and mode == 'r':
            raise OSError(errno.EACCES, 'denied')
        return real_open(path, mode, *a, **k)

    monkeypatch.setattr(builtins, 'open', denied)


def test_scaffold_refuses_to_overwrite_an_unreadable_claude_md(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(tmp_path / 'work' / 'alpha')
    seeded = '# alpha\n\nMY HAND WRITTEN NOTES\n'
    md_path = _seed(tmp_path, proj, seeded)
    calls = _quiet_world(monkeypatch, tmp_path, folder)
    _deny_claude_md_read(monkeypatch)

    assert claude_md.scaffold_claude_md(proj, folder) is False
    assert calls['write'] == [], 'an unreadable file was written over'
    with builtins.open(md_path, 'rb') as f:
        assert f.read() == seeded.encode('utf-8')


def test_ai_scaffold_refuses_to_overwrite_an_unreadable_claude_md(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, _enc, folder, _sids = sb.add_project('alpha', n_sessions=0)
    proj = str(tmp_path / 'work' / 'alpha')
    seeded = '# alpha\n\nMY HAND WRITTEN NOTES\n'
    md_path = _seed(tmp_path, proj, seeded)
    calls = _quiet_world(monkeypatch, tmp_path, folder)
    _deny_claude_md_read(monkeypatch)
    monkeypatch.setattr(claude_md.subprocess, 'Popen',
                        lambda *a, **k: pytest.fail('the model was called'))
    monkeypatch.setattr(claude_md, 'wait_event', lambda *a, **k: pytest.fail('prompted'))
    monkeypatch.setattr(claude_md, 'poll_event', lambda *a, **k: pytest.fail('prompted'))
    monkeypatch.setattr(claude_md, 'open_in_editor', lambda *a, **k: None)
    monkeypatch.setattr(claude_md.time, 'sleep', lambda *a, **k: None)

    claude_md.ai_scaffold_claude_md(proj, folder)
    assert calls['write'] == [], 'an unreadable file was written over'
    with builtins.open(md_path, 'rb') as f:
        assert f.read() == seeded.encode('utf-8')
