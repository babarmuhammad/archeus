"""T-1169: the ten highest-risk uncovered branches of claude_sessions/claude_md.py
lines 1-362 inclusive (tip 56d53504; every line number here was read from this
checkout — `git` is not available in the container to re-confirm the tip) —
fail-closed and denial first, then boundaries, then error paths.

Slice owned here (definitions/imports above line 40 are read-only context):
`upsert_block` 40-85, `write_memory_block` 88-115, `_preserve_block` 129-139,
`_parse_existing_sessions` 248-260, `_build_sessions_block` 273-360. Functions
that cross the 362 endpoint stay owned; `_build_autogen_block` (363) does not.

Final ten (ranked by risk; each name, source line and evidence in the report):

  1. unreadable instructions file must not be overwritten            :53-57, :73-75   XFAIL
  2. inconsistent sentinels (END before START) must not corrupt prose :58-68           XFAIL
  3. model-forged unterminated block must not outlive the real one    :137-139         XFAIL
  4. failed atomic write returns the OLD text and touches nothing     :82-84
  5. first instructions file failing still writes the second          :108-115
  6. duplicate pairs: only the first is replaced, prose between stays :58-60
  7. empty section removes only the owned block; writes nothing       :58-70
  8. unpaired start keeps the user's tail when a block is appended    :71-72
  9. session cap exact boundary (fresh scan, merge, no-folder)        :297-300, :356-357
 10. malformed session row survives, manual tail does not move        :251-259, :58-68

Seams: `builtins.open` (the pattern of tests/v1/unit/test_pv20_isolation.py:1030-1036
and test_gaps_core_world_inspection.py: faking an OS denial with our own errno, so
no test reads an OS error message), `config.write_atomic` (the choke point every
writer of this file uses, already wrapped by tests/conftest.py),
`harnesses.instructions_files`, and `sessions.project_session_folders` — so
account discovery never runs against the host. No real network, no subprocess, no
credential reader, no HOME read; every file the tested code writes lives under
tmp_path. Three assertions are kept as strict xfails because the source disagrees
with a justified premise; none was weakened to make the file green.
"""

import errno
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                    # noqa: E402

from harness import Sandbox, make_jsonl          # noqa: E402

from claude_sessions import claude_md            # noqa: E402
from claude_sessions import config as _c         # noqa: E402
from claude_sessions import harnesses as _h      # noqa: E402
from claude_sessions import sessions             # noqa: E402
from claude_sessions.config import (_MEMORY_START, _MEMORY_END, _AGENTS_START,
                                    _AGENTS_END, _SESSIONS_START, _SESSIONS_END)


# ── seams ───────────────────────────────────────────────────────────────────

def _write(root, name, text):
    """One file, exactly these bytes, identical on Linux and Windows."""
    p = os.path.join(str(root), name)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return p


def _read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def _deny_read(monkeypatch, name):
    """`open` says no to reads of `name`. The gate is a dict the test closes
    again afterwards, so the same test can still inspect the file on disk.
    Our own errno and message: no assertion ever matches OS error text."""
    gate = {'on': True}
    real = open

    def deny(file, *a, **k):
        base = os.path.basename(os.fspath(file)) if isinstance(
            file, (str, bytes, os.PathLike)) else ''
        mode = a[0] if a else k.get('mode', 'r')
        if gate['on'] and base == name and 'r' in mode and '+' not in mode:
            raise PermissionError(errno.EACCES, 'synthetic denial', base)
        return real(file, *a, **k)

    monkeypatch.setattr('builtins.open', deny)
    return gate


def _spy_write_atomic(monkeypatch, fail=()):
    """Record every `config.write_atomic` call; optionally refuse the ones whose
    path ends with a name in `fail`. The rest go to the real (sandbox-guarded)
    helper, so a refusal is the only thing standing between the test and a write."""
    real = _c.write_atomic
    calls = []

    def spy(path, text, **kw):
        calls.append((str(path), text))
        if str(path).endswith(tuple(fail)):
            return False
        return real(path, text, **kw)

    monkeypatch.setattr(_c, 'write_atomic', spy)
    return calls


def _rows(block):
    return [ln for ln in (block or '').splitlines() if ln.startswith('- ')]


# ── 1 · denial: an unreadable file is never overwritten ─────────────────────

@pytest.mark.xfail(strict=True, reason=(
    "claude_md.py:53-57 turns an unreadable CLAUDE.md into old='' and :73-75 "
    "then writes a header-only file over prose it never read; the contract at "
    "claude_md.py:41-43 ('leaving everything else ... intact') requires a "
    "refusal, not a guess"))
def test_an_instructions_file_that_cannot_be_read_is_never_overwritten(tmp_path,
                                                                        monkeypatch):
    """`except Exception: old = ''` (claude_md.py:56-57) is the one place in this
    slice that can destroy text archeus never saw: with `old` wiped the writer
    takes the brand-new-file branch (:73-75) and replaces a locked, in-use or
    permission-denied CLAUDE.md — full of hand-written rules — with a title line
    plus one generated block. Fail-closed means ok=False and no write at all;
    the function cannot know the text, so nothing is claimed about `new`.

    Nearest existing coverage: `tests/test_harnesses.py:488
    (test_a_second_file_that_cannot_be_written_is_a_failure)` refuses a WRITE and
    checks `ok`; no test anywhere calls `harnesses.read_instructions`, and no test
    calls `upsert_block` directly at all — it is only ever reached through
    `write_memory_block` (`tests/test_harnesses.py:473-517`,
    `tests/test_memauto.py:52-88`, `tests/test_persisted_scrub.py:72`), so the read
    side of :53-57 is unexercised and this assertion could not have been made there.

    Catches: removal of the guard's effect at :82-83 (with the read failure allowed
    to reach the writer the file is replaced), and a handler that re-raises
    instead of refusing. The fix (return ok=False without writing) satisfies it.
    """
    _write(tmp_path, 'CLAUDE.md',
           '# proj\n\nHAND-WRITTEN RULE: never deploy on Friday.\n')
    before = _read(os.path.join(str(tmp_path), 'CLAUDE.md'))
    calls = _spy_write_atomic(monkeypatch)
    gate = _deny_read(monkeypatch, 'CLAUDE.md')

    ok, _old, _new = claude_md.upsert_block(
        str(tmp_path), _MEMORY_START, _MEMORY_END,
        _MEMORY_START + '\nMEMO line\n' + _MEMORY_END + '\n')
    gate['on'] = False
    assert ok is False, 'an unreadable file was accepted as an empty one'
    assert calls == [], 'a write was attempted over a file that could not be read'
    assert _read(os.path.join(str(tmp_path), 'CLAUDE.md')) == before


# ── 2 · fail-closed: sentinels that disagree are not a block ────────────────

@pytest.mark.xfail(strict=True, reason=(
    "claude_md.py:58-60 splices on the FIRST index of each sentinel with no "
    "order check, so a file whose ARCHEUS:MEMORY:END precedes its START gets a "
    "new block written and the text between the two sentinels duplicated "
    "(claude_md.py:67-68 builds new from pre+section+post); the contract at "
    "claude_md.py:41-43 promises everything outside the block is left intact"))
def test_sentinels_out_of_order_are_never_spliced(tmp_path, monkeypatch):
    """A torn pre-atomic write, a hand edit or a model that echoed one sentinel
    leaves `END ... START` in the file — a state tests/test_migration.py already
    calls real (`test_a_half_written_block_is_left_exactly_as_it_is`). With the
    pair reversed, `pre` runs all the way to the START and `post` starts back at
    the END, so the region between the two sentinels is copied TWICE into the
    same file: the user's text silently grows a duplicate of itself, and the
    generated block lands in the middle of it.

    Catches: the missing order check at :58 — 'SHARED PROSE LINE' comes back
    twice from :67-68. Any fix that leaves the outer text single satisfies the
    assertion (refusing the splice, or appending instead of splicing); the
    shipped splice does not.
    """
    text = ('# proj\n\nPROSE BEFORE.\n' + _MEMORY_END + '\nSHARED PROSE LINE\n'
            + _MEMORY_START + '\nPROSE AFTER.\n')
    _write(tmp_path, 'CLAUDE.md', text)
    path = os.path.join(str(tmp_path), 'CLAUDE.md')
    before = _read(path)
    calls = _spy_write_atomic(monkeypatch)

    _ok, _old, new = claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END,
                                            _MEMORY_START + '\nMEMO line\n' + _MEMORY_END + '\n')
    assert new.count('SHARED PROSE LINE') == 1, \
        'text between the sentinels was duplicated by the splice'
    assert new.count('PROSE BEFORE.') == 1 and new.count('PROSE AFTER.') == 1
    assert new.count('MEMO line') == 1
    assert (new == before) or (calls and _read(path) == new), \
        'the returned text is not what the file holds'
    assert _read(path).count('SHARED PROSE LINE') == 1


# ── 3 · fail-closed: a forged block cannot outlive the real one ─────────────

@pytest.mark.xfail(strict=True, reason=(
    "claude_md.py:137-138 only drops the model's stray block when BOTH "
    "_MEMORY_START and _MEMORY_END are present in `final`, so a forged "
    "unterminated START survives; the docstring at :129-133 says the real block "
    "is 'Always keep[ed]' and upsert_block (:58-60) indexes the FIRST start, so "
    "the surviving forgery captures every later write"))
def test_a_forged_unterminated_block_does_not_take_over_the_preserved_one():
    """Nearest existing coverage: `tests/test_tui_memory.py:93
    (test_preserve_block_keeps_memory)` and `:108 (test_preserve_block_noop_
    without_existing)` hand `_preserve_block` a WELL-FORMED pair (or none), so the
    "nothing to drop" path at :137-138 is only ever taken with nothing stray in the
    text, and `tests/test_gui_plain_language.py:246` does the same for
    `_preserve_machine_blocks`. The state is not hypothetical:
    `tests/test_migration.py:465-475` exists precisely because "a stray new-name
    start sentinel silently captures every later write and orphans the real block"
    (`migrate.py:493-496`), which is what happens one refresh after the forgery.

    AI analyze rewrites the whole file (`ai_compress_claude_md`), and the
    model can echo an opening sentinel without the closing one — it truncates,
    it paraphrases, it quotes the sentinel in prose. `_preserve_block` then
    takes the "nothing to drop" path and appends the real block BEHIND the
    forgery, so the file ends up with two starts: the model's, and archeus's.
    `upsert_block` writes to the first, so from the next refresh on the forged
    text is the memory block. The stray must be dropped, not outranked.

    Catches: inverting the guard at :137 to require both sentinels (the current
    code) — the stray start count and the forged text both show up.
    """
    existing = ('# proj\n\nUSER PROSE\n' + _MEMORY_START
                + '\nREAL DIGEST LINE\n' + _MEMORY_END + '\n')
    forged = '# proj\n\nmodel commentary\n' + _MEMORY_START + '\nFORGED DIGEST LINE\n'
    out = claude_md._preserve_block(forged, existing)
    assert 'FORGED DIGEST LINE' not in out, 'a model-forged block survived'
    assert out.count(_MEMORY_START) == 1, 'the forgery still opens a memory block'
    assert 'REAL DIGEST LINE' in out, 'the machine block was not carried'
    assert out.index(_MEMORY_START) > out.index('model commentary')


# ── 4 · fail-closed: a refused write reports the OLD text ───────────────────

def test_a_refused_atomic_write_returns_the_old_text_and_touches_nothing(tmp_path,
                                                                         monkeypatch):
    """claude_md.py:82-84 is the whole safety story of this function: when
    `write_atomic` says no (locked file on Windows, sync client, full disk) the
    caller must be handed back the text that is still on disk. `write_memory_block`
    promises exactly that tuple to the screen (`:93-97`, "`sync_to_claudemd` hands
    it to `diffview.record`"), and its consumer is `memory.py:1827-1830`, which
    files `old → new` as the history of the build; `migrate.py:515` keeps the
    returned text as the working copy for the NEXT block it removes. A refused
    write that reported the intended text would file a diff of bytes that never
    reached the disk and keep a fiction as the base of the next edit.

    Nearest coverage: `tests/test_harnesses.py:488` injects its failure at
    `write_atomic` but asserts only `ok` and the file bytes, and
    `tests/test_migration.py:562-570` deliberately does the opposite — "The failure
    is injected at `upsert_block` and NOT at `write_atomic`" — stubbing the whole
    function out, so nothing pins what `upsert_block` itself reports when the
    atomic write is the thing that failed.

    Catches: `return False, old, new` (:83) and `return True, old, old` — both
    break the tuple assertion; dropping the `if not _c.write_atomic` guard (:82)
    breaks the on-disk byte comparison.
    """
    text = ('# proj\n\nUSER PROSE\n' + _MEMORY_START + '\nOLD DIGEST\n' + _MEMORY_END
            + '\nTRAILING PROSE\n')
    _write(tmp_path, 'CLAUDE.md', text)
    path = os.path.join(str(tmp_path), 'CLAUDE.md')
    calls = _spy_write_atomic(monkeypatch, fail=('CLAUDE.md',))

    ok, old, new = claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END,
                                          _MEMORY_START + '\nNEW DIGEST\n' + _MEMORY_END + '\n')
    assert len(calls) == 1, 'the write was never attempted'
    assert ok is False
    assert old == text
    assert new == text, 'a write that failed reported new text to the diff screen'
    assert _read(path) == text, 'the file changed although the write was refused'


# ── 5 · fail-closed: the fan-out is not cut short by the first failure ──────

def test_the_first_instructions_file_failing_still_writes_the_second(tmp_path,
                                                                     monkeypatch):
    """`tests/test_harnesses.py:488
    (test_a_second_file_that_cannot_be_written_is_a_failure)` refuses the SECOND
    file and asserts `ok is False`; nothing refuses the
    first, which is where the loop's shape matters. `first` (claude_md.py:113-114)
    is the tuple the CLAUDE.md tab diffs, `ok` (:112) is the AND over every file,
    and the loop (:109-114) must keep going after a failure — a `break`/early
    `return got` there leaves AGENTS.md on a stale digest while the run reports
    having finished, exactly the half-written state :99-101 says is unacceptable.

    Catches: `ok = got[0]` instead of `ok = ok and got[0]` (ok comes back True),
    an early exit after the first failure (AGENTS.md never written), and
    `first = got` outside the `is None` guard — the tuple handed back would then
    be AGENTS.md's (`old == ''`, `new` carrying the digest), not CLAUDE.md's.
    """
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(_h, 'instructions_files', lambda: ['CLAUDE.md', 'AGENTS.md'])
    first_text = '# proj\n\nFIRST FILE USER PROSE\n'
    _write(tmp_path, 'CLAUDE.md', first_text)
    calls = _spy_write_atomic(monkeypatch, fail=('CLAUDE.md',))

    ok, old, new = claude_md.write_memory_block(str(tmp_path), 'MEMO retries bounded')
    assert ok is False, 'a half-written fan-out reported success'
    assert [os.path.basename(p) for p, _t in calls] == ['CLAUDE.md', 'AGENTS.md'], \
        'the fan-out stopped at the file that failed'
    # the tuple is CLAUDE.md's OWN (ok, old, new) — and because its write was
    # refused, upsert_block (:83-84) reports the old text as `new`, not the text
    # that never reached the disk. AGENTS.md's tuple would be ('', header+digest)
    assert (old, new) == (first_text, first_text), \
        'the returned tuple is not the refused CLAUDE.md write'
    assert _read(os.path.join(str(tmp_path), 'CLAUDE.md')) == first_text
    agents = _read(os.path.join(str(tmp_path), 'AGENTS.md'))
    assert 'MEMO retries bounded' in agents
    assert _MEMORY_START in agents and _MEMORY_END in agents


# ── 6 · boundary: duplicate pairs, the prose between them is not ours ───────

def test_replacing_one_of_two_blocks_keeps_the_prose_between_them(tmp_path, monkeypatch):
    """Two identical pairs in one file is a state the repo already handles:
    `tests/test_migration.py:436-440` describes a rename that "APPENDED a second
    block beside it" and asserts `text.count(START) == 1, 'two blocks, one
    renderer'` at `:458`, and `migrate.py:493-496` is written around "`upsert_block`
    indexes the FIRST occurrence". The splice at
    claude_md.py:58-60 therefore has to take the first START and the first END
    and nothing else: `pre` must stop at the first START (an `rindex` there eats
    PROSE A) and `post` must start right after the first END (an `rindex` there
    swallows UNRELATED PROSE B and the second block, which is user-owned text
    until something rewrites it). Nearest coverage of the splice itself: nothing
    calls `upsert_block` directly, and
    `tests/test_harnesses.py:503 (test_the_block_writer_takes_a_filename_rather_
    than_being_copied)` only rewrites ONE pair with no text after it, so neither
    the first/first rule nor the seam is asserted anywhere.

    Catches: `old.rindex(start)`/`old.rindex(end)` at :59-60, and dropping the
    seam normalisation at :67 (the `\\n\\n` leak the comment at :61-66 warns
    about) is caught by the idempotence assertion on the second call.
    """
    text = ('# proj\n\nPROSE A\n' + _MEMORY_START + '\nBLOCK ONE\n' + _MEMORY_END
            + '\nUNRELATED PROSE B\n' + _MEMORY_START + '\nBLOCK TWO\n' + _MEMORY_END
            + '\nPROSE C\n')
    _write(tmp_path, 'CLAUDE.md', text)
    path = os.path.join(str(tmp_path), 'CLAUDE.md')
    calls = _spy_write_atomic(monkeypatch)
    section = _MEMORY_START + '\nREPLACED DIGEST\n' + _MEMORY_END + '\n'

    ok, old, new = claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END, section)
    assert ok is True and len(calls) == 1
    assert old == text
    for keep in ('PROSE A', 'UNRELATED PROSE B', 'PROSE C', 'BLOCK TWO'):
        assert new.count(keep) == 1, '%r lost or duplicated by the splice' % keep
    assert 'BLOCK ONE' not in new
    assert 'REPLACED DIGEST' in new
    assert new.count(_MEMORY_START) == 2, 'a third block appeared'

    # the seam stays idempotent, or the blank-line leak of :61-66 comes back
    claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END, section)
    once = _read(path)
    claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END, section)
    assert _read(path) == once, 'the file grows on every rewrite'
    assert '\n\n\n' not in once


# ── 7 · boundary: an empty section removes ONLY the block it owns ───────────

def test_an_empty_section_removes_only_its_own_block_and_writes_nothing(tmp_path,
                                                                        monkeypatch):
    """`section=''` is the removal call every machine block's owner makes
    (`agents.py:781`, `loops.py:512`, `migrate.py:515`, all removing a machine
    block). Two branches carry it:
    the splice at :58-68 must leave the AGENTS block and both prose runs
    untouched, and the "nothing to remove" return at :69-70 must be a true no-op
    — removing it drops the file into :71-72, which `rstrip`s and appends a
    blank-line-bearing no-change and *writes it*, churning a file nobody asked
    to change.

    Nearest coverage: `tests/test_migration.py:570` patches `claude_md.upsert_block`
    out entirely (to inject a failure, so its behaviour is never observed), and
    `tests/test_ctxaudit.py:48 (test_prune_claude_md_shrinks_and_preserves_manual_
    and_memory)` goes through `prune_claude_md`, which only rewrites the SESSIONS
    block and asserts the MEMORY block is still there — never that removing one
    machine block leaves the other one, its sentinels and the prose seams alone.

    Catches: deleting the :69-70 branch (the second half fails: a write is
    attempted and `new is not old`), and letting the removal splice also strip
    neighbouring blocks (the first half fails).
    """
    text = ('# proj\n\nPROSE A\n' + _MEMORY_START + '\nMINE\n' + _MEMORY_END + '\n'
            + _AGENTS_START + '\nROUTING TABLE ROW\n' + _AGENTS_END + '\nPROSE C\n')
    _write(tmp_path, 'CLAUDE.md', text)
    calls = _spy_write_atomic(monkeypatch)

    ok, old, new = claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END, '')
    assert ok is True
    assert old == text
    assert 'MINE' not in new and _MEMORY_START not in new and _MEMORY_END not in new
    assert new.count(_AGENTS_START + '\nROUTING TABLE ROW\n' + _AGENTS_END) == 1, \
        'another machine block was taken with it'
    assert new.count('PROSE A') == 1 and new.count('PROSE C') == 1

    # and with no block at all there is nothing to remove: no write, same text
    plain = '# proj\n\nONLY USER PROSE HERE\n'
    _write(tmp_path, 'CLAUDE.md', plain)
    calls.clear()
    ok, old, new = claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END, '')
    assert ok is True and old == plain and new == plain, 'a no-op removal changed the text'
    assert calls == [], 'a no-op removal still wrote the file'
    assert _read(os.path.join(str(tmp_path), 'CLAUDE.md')) == plain


# ── 8 · boundary: an unpaired start keeps the user's tail ───────────────────

def test_appending_to_a_file_with_an_unpaired_start_keeps_the_users_tail(tmp_path,
                                                                          monkeypatch):
    """A start sentinel with no end (hand edit, torn write, model echo — the state
    `tests/test_migration.py:465
    (test_a_half_written_block_is_left_exactly_as_it_is)` exists to protect) fails
    the :58 test, so the file reaches :71-72 and the block is
    APPENDED. That branch is `old.rstrip('\\n') + '\\n\\n' + section`: the user's
    half-block text is the only thing standing between their prose and the new
    block, and it is exactly what a `new = section` rewrite of that line would
    drop. (Reported separately: appending beside an orphan START makes the
    orphan the first index, so later writes land in the wrong region — that is
    branch 3's xfail; this test asserts the tail, which the source does get right.)

    Catches: inverting :71 (`elif old.strip()` -> the brand-new-file branch at
    :73-75 loses the tail) or replacing :72 with `new = section`.
    """
    text = ('# proj\n\nOUTER PROSE\n' + _MEMORY_START + '\nORPHAN TAIL TEXT\n')
    _write(tmp_path, 'CLAUDE.md', text)
    path = os.path.join(str(tmp_path), 'CLAUDE.md')
    calls = _spy_write_atomic(monkeypatch)

    ok, old, new = claude_md.upsert_block(str(tmp_path), _MEMORY_START, _MEMORY_END,
                                          _MEMORY_START + '\nNEW DIGEST\n' + _MEMORY_END + '\n')
    assert ok is True and len(calls) == 1
    assert old == text
    assert new.startswith(old.rstrip('\n')), 'the existing file was not kept as the prefix'
    assert new.count('ORPHAN TAIL TEXT') == 1, 'the user tail was lost or duplicated'
    assert new.count('OUTER PROSE') == 1
    assert 'NEW DIGEST' in new
    assert _read(path) == new


# ── 9 · boundary: the session cap, measured at the edge ────────────────────

def test_the_session_cap_is_measured_at_its_exact_boundary(tmp_path, monkeypatch):
    """claude_md.py:356-357 (`ordered = ordered[:cap]`) and the no-folder twin at
    :299-300 are both one-line slices. The only existing test of this function's
    caps, `tests/test_ctxaudit.py:29 (test_sessions_block_capped_to_setting)`, takes
    15 sessions down to the default 10, then to 3, then to 0 — it never sits ON the
    and starts being the behaviour), and it never merges: it always passes
    `existing={}`. So the merged path — `existing` non-empty AND a real folder, the
    branch where the cap is applied AFTER the merge at :357 — is entered by no test
    anywhere (`tests/test_ctxaudit.py:33,41,44` and
    `tests/test_multiaccount_memory.py:80` all pass `{}`). The no-folder slice at
    :300 is run once, by `tests/test_ctxaudit.py:273
    (test_headless_lines_already_in_the_file_are_dropped)`, with three rows and the
    DEFAULT cap — far above the row count, where `kept[:cap]`, `kept[:cap-1]` and
    no slice at all are indistinguishable. The merged ordering at
    :350-351 is the other half: new sessions first, old entries last, so an
    off-by-one silently deletes the user's oldest remembered topic.

    Catches: `ordered[:cap]` -> `[:cap - 1]` (four become three), `[:cap + 1]`
    (three become four), reversing `ordered` (the newest would be the one
    dropped), `if cap:` -> `if cap is not None:` (cap 0 empties the merge path),
    and `kept[:cap]` -> `kept[:cap - 1]` in the no-folder branch.
    """
    Sandbox(monkeypatch, tmp_path)
    folder = tmp_path / 'enc-folder'
    folder.mkdir()
    # four transcripts, one minute apart, newest = the last one written
    keys = []
    for i in range(4):
        sid = 'row%d0000-0000-0000-0000-000000000000' % i
        keys.append(sid[:8])                       # the key claude_md.py:340 builds
        make_jsonl(os.path.join(str(folder), sid + '.jsonl'),
                   preview='remembered topic %d' % i)
        stamp = 1700000000 + i * 60
        os.utime(os.path.join(str(folder), sid + '.jsonl'), (stamp, stamp))
    # account discovery never runs against the host: one folder, this one
    monkeypatch.setattr(sessions, 'project_session_folders',
                        lambda pf: [str(folder)] if pf else [])
    old_entry = {'oldkey': '- **oldkey** (9 msgs): the oldest remembered topic'}

    assert len(_rows(claude_md._build_sessions_block(str(folder), {}, cap=4))) == 4
    assert len(_rows(claude_md._build_sessions_block(str(folder), {}, cap=0))) == 4, \
        'cap 0 must stay unlimited on the merge path too (0 is falsy at :356)'
    three = _rows(claude_md._build_sessions_block(str(folder), {}, cap=3))
    assert len(three) == 3, 'the cap is not exact at its edge'
    assert 'remembered topic 3' in '\n'.join(three), 'the newest was not kept'
    assert 'topic 0' not in '\n'.join(three), 'the oldest was not dropped'

    merged = _rows(claude_md._build_sessions_block(str(folder), dict(old_entry), cap=5))
    assert len(merged) == 5, 'the merge does not reach the cap exactly'
    assert merged[-1] == old_entry['oldkey'], 'old entries are not last'
    assert merged[0].startswith('- **%s**' % keys[3]), 'new entries are not first'

    capped = _rows(claude_md._build_sessions_block(str(folder), dict(old_entry), cap=4))
    assert len(capped) == 4
    assert 'the oldest remembered topic' not in '\n'.join(capped), \
        'the merged entry survived a cap of exactly the new-session count'

    # the no-folder branch has its own slice (:299-300): same edge, other line
    existing = {('k%d' % i): '- **k%d** (2 msgs): plain remembered line %d' % (i, i)
                for i in range(3)}
    assert len(_rows(claude_md._build_sessions_block('', existing, cap=3))) == 3
    two = _rows(claude_md._build_sessions_block('', existing, cap=2))
    assert len(two) == 2, 'the no-folder cap is not exact at its edge'
    assert len(_rows(claude_md._build_sessions_block('', existing, cap=0))) == 3, \
        'cap 0 must stay unlimited'


# ── 10 · boundary: a malformed row, and the manual text behind the block ────

def test_a_malformed_session_row_survives_and_the_manual_tail_still_moves(
        tmp_path, monkeypatch):
    """`_parse_existing_sessions` (:248-260) reads back what the previous pass
    wrote, and a row whose `**bold**` key was broken by hand or by a torn write
    takes the `key = line[:20]` path at :258 — a truncated key. No test in the
    repo calls `_parse_existing_sessions` at all: every sessions-block test either
    passes `{}` (`tests/test_ctxaudit.py:33,41,44`,
    `tests/test_multiaccount_memory.py:80`) or hand-writes the dict
    (`tests/test_ctxaudit.py:273`), so what the parser does to a row that is not
    well formed has never been observed. The row text must
    still come back whole (it is the value, and it is what gets re-emitted), the
    non-dash lines must stay out, a half pair must yield nothing at all (:251),
    and the whole round-trip has to leave the user's manual text after
    `SESSIONS:END` byte-identical, because the rebuilt block is written through
    the same splice the memory block uses.

    Catches: `entries[key] = line` -> `entries[key] = line[:20]` (the row is
    truncated), dropping the :256 dash filter (a `*` bullet becomes a topic),
    checking only one sentinel at :251, and a splice at :58-60 that eats the
    manual tail.
    """
    row_bad = '- plain row with no bold key at all'
    text = ('# proj\n\n' + _SESSIONS_START + '\n## Session topics\n'
            '- **goodkey** (3 msgs): a well formed topic\n'
            + row_bad + '\n* a bullet that is not a row\n- \n'
            + _SESSIONS_END + '\nMY MANUAL NOTES stay here.\n')
    entries = claude_md._parse_existing_sessions(text)
    assert entries.get('goodkey') == '- **goodkey** (3 msgs): a well formed topic'
    assert entries.get(row_bad[:20]) == row_bad, 'the malformed row was truncated'
    assert not any(ln.startswith('* ') for ln in entries.values()), \
        'a non-dash line was taken for a session row'
    assert claude_md._parse_existing_sessions(
        _SESSIONS_END + '\n- **a** (1 msgs): x\n') == {}, 'a half pair was parsed'
    assert claude_md._parse_existing_sessions(
        _SESSIONS_START + '\n- **a** (1 msgs): x\n') == {}, \
        'a block with no closing sentinel was parsed'

    content = claude_md._build_sessions_block('', entries, cap=0)
    assert content.count(row_bad) == 1, 'the malformed row did not survive the rebuild'
    assert 'a well formed topic' in content
    # wrapped exactly the way prune_claude_md:462 wraps it before the upsert
    block = '%s\n%s%s\n' % (_SESSIONS_START, content, _SESSIONS_END)

    _write(tmp_path, 'CLAUDE.md', text)
    path = os.path.join(str(tmp_path), 'CLAUDE.md')
    calls = _spy_write_atomic(monkeypatch)
    ok, old, new = claude_md.upsert_block(str(tmp_path), _SESSIONS_START, _SESSIONS_END,
                                          block)
    assert ok is True and len(calls) == 1
    assert old == text
    assert new.endswith('MY MANUAL NOTES stay here.\n'), 'the manual tail moved or went'
    assert new.count('MY MANUAL NOTES stay here.') == 1
    assert new.count(row_bad) == 1
    assert new.count(_SESSIONS_START) == 1 and new.count(_SESSIONS_END) == 1
    assert _read(path) == new
