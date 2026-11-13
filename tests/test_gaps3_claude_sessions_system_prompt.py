"""T-1180 — gap tests for `claude_sessions/system_prompt.py` lines 1-155.

Card: T-1180. Source range under test: `claude_sessions/system_prompt.py:1-155`
(the whole module, tip `56d53504`, MXC integration branch). This container is
Linux and the review runs the real suite on Windows, so every OS-specific
behaviour here is faked through a seam and never read off the host.

The slice holds three functions. The contract that matters most is the one in
the `merged_system_prompt` docstring (system_prompt.py:11-15): **prompt file
injection retains base instructions** — a project's own `system-prompt.txt`
must survive into the single file `--system-prompt-file` feeds every session,
with the pointer line appended after it. Losing that base silently is a
user-visible data loss no log reports, so it is what most of this file attacks.

FINAL SELECTED BRANCHES (ranked by risk; denial/fail-closed first, then
boundaries, then error paths; line numbers are
`claude_sessions/system_prompt.py`):

 1. :20-21    read error of an EXISTING base swallowed by `except Exception:
              pass` — the merged file carries the pointer only. Fail-open.
              test_merged_unreadable_base_must_not_silently_vanish
 2. :31-36    missing claude.exe — the denial must not reach the model, the
              pager, the writer or the editor.
              test_generate_denies_when_claude_exe_is_missing
 3. :93-95    cancelled generation must leave the prior prompt byte-identical.
              test_generate_cancel_keeps_prior_prompt_byte_identical
 4. :22,24-25 an option-like pointer stays FILE CONTENT and nothing spawns.
              test_merged_option_like_pointer_stays_file_content
 5. :17,19,22 a readable base is retained verbatim through UTF-8, pointer last.
              test_merged_preserves_utf8_base_instructions_and_pointer
 6. :19,22    whitespace-only base contributes no `\\n\\n` separator.
              test_merged_whitespace_only_base_adds_no_separator
 7. :17,22    missing / empty `sp_file` still writes the pointer alone.
              test_merged_missing_base_still_writes_pointer
 8. :23       `os.makedirs` failure propagates and creates nothing.
              test_merged_makedirs_failure_propagates_and_writes_nothing
 9. :24-25    out-file write failure has NO success path: no return, no file.
              test_merged_write_failure_has_no_success_path
10. :96,:119-123 timeout / truncated model output replaces nothing and reports
              the real reason.
              test_generate_timeout_or_truncated_output_replaces_nothing

Tests beyond the ten close the remaining uncovered branches of the same slice.
Evidence at `56d53504` (scratch sys.settrace probe run over the two existing
coverage files named by the card, `tests/test_tui_generators.py` +
`tests/test_tui_launch.py`): executed lines were 1-10, 29, 31-32, 39-41,
48-52, 54-55, 65-77, 88-97, 99-100, 105, 110-112, 114-118, 126-136, 139-140,
142-143 — so 16-26, 33-36, 42-45, 56-60, 101-104, 106-109, 113, 120-123, 137,
141, 146-147, 151-155 were never run. Repo-wide, `merged_system_prompt` is
never executed by any existing test at all: the only other mentions are
tests/test_plan_execute.py:288 and :302, which replace it with
`lambda *a, **k: None`, and tests/test_phase5_ux.py:96-97 / :105-106, which grep
the source TEXT of this module for 'fence_untrusted(claude_md)' and
'diffview.confirm(' without ever calling it. tests/test_tui_launch.py covers the
launch callers around it, not the merge. The extras cover the reject gate
:100-104, `write_atomic` False :105-109, the `diffview.record` fault
:110-113, `menu` ESC :136-137, manual create/open :145-155, the `CLAUDE.md`
read :41-45, `text_input` None :52, the unreadable PRIOR prompt :56-59, the
failed template write on the manual path :146-151, and the `project_path or
None` cwd handoff at :91 / :140-141.

Measured with a scratch sys.settrace probe over this file: every executable line
of the slice runs — the only lines the probe never reports are 11 and 30, the
two function docstrings, which are not executable statements.

Independence: no other `test_gaps3*` module is imported and no queue order is
assumed; every fake is built from `tests/harness.py` + `tmp_path` only, and all
writes, caches and fake homes stay under `tmp_path`.
"""
import builtins
import errno
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                                       # noqa: E402
from harness import CapturingStdout, Sandbox                        # noqa: E402

from claude_sessions import config as config_mod                    # noqa: E402
from claude_sessions import diffview, memory, system_prompt         # noqa: E402

#: The real `open`, captured before any test can replace the builtin, so the
#: assertions can always read what the code under test wrote.
_REAL_OPEN = open

PRIOR = '# System prompt / alpha\nKEEP ME — prior instructions, do not replace.\n'

#: side effects worth ordering, cheapest to most privileged
PRIVILEGED = ('text_input', 'claude_stdin', 'confirm', 'write_atomic', 'record', 'editor')


# ── seam fakes ───────────────────────────────────────────────

def _norm(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fsdecode(path))))


def write_file(path, text):
    """Write a fixture file with EXACT characters (no newline translation)."""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with _REAL_OPEN(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    return path


def read_bytes(path):
    with _REAL_OPEN(path, 'rb') as f:
        return f.read()


def read_text(path):
    """Decoded with newline translation OFF: CRLF on Windows, LF on Linux.
    Strict utf-8 — mojibake in the merged file raises here instead of passing."""
    with _REAL_OPEN(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def lf(s):
    """Normalize the one documented platform difference: the code writes with
    default newline translation, so its `\n\n` is CRLF on Windows, LF here."""
    return s.replace('\r\n', '\n')


class Spy:
    """One recording fake. Appends its tag to a shared ordered event log so a
    test can assert the ORDER of privileged side effects, not just their set."""

    def __init__(self, tag, ret=None, events=None, raises=None):
        self.tag = tag
        self.ret = ret
        self.raises = raises
        self.events = events if events is not None else []
        self.calls = []

    def __call__(self, *a, **kw):
        self.calls.append((a, kw))
        self.events.append(self.tag)
        if self.raises is not None:
            raise self.raises
        return self.ret() if callable(self.ret) else self.ret

    @property
    def called(self):
        return bool(self.calls)


class NoSpawn:
    """Tripwire for the `subprocess` name bound at system_prompt.py:2 and used
    nowhere in the slice. Attribute ACCESS trips, so even a capability check on
    the module fails the test."""

    def __init__(self, what):
        self.what = what

    def __getattr__(self, attr):
        raise AssertionError(f'{self.what}.{attr} must not be reached from T-1180 code')


def tripwire(what):
    """A callable that refuses to be the host: account discovery and the
    credential readers are pinned to this BEFORE any entrypoint or lazy import
    can run, and invented values are supplied by the test instead."""
    def _boom(*a, **kw):
        raise AssertionError(f'{what} must not be reached from T-1180 code')
    return _boom


class FakePath:
    """`os.path` for the merge: delegates to the real one, records the asks."""

    def __init__(self, fake):
        self._fake = fake
        self.sep = os.sep

    def isfile(self, p):
        self._fake.calls.append(('isfile', os.fsdecode(p)))
        return os.path.isfile(p)

    def exists(self, p):
        self._fake.calls.append(('exists', os.fsdecode(p)))
        return os.path.exists(p)

    def dirname(self, p):
        self._fake.calls.append(('dirname', os.fsdecode(p)))
        return os.path.dirname(p)

    def join(self, *a):
        return os.path.join(*a)


class FakeOs:
    """Stand-in for the `os` name `merged_system_prompt` uses (file access is
    faked separately, through the `open` seam — the code calls the builtin).

    Everything delegates to the real `os` unless a fault is armed for that call,
    so the fake cannot make a run green by construction: the error is ours
    (errno chosen here, never a localized OS message).
    """

    def __init__(self, makedirs_error=None):
        self.calls = []
        self.makedirs_error = makedirs_error
        self.path = FakePath(self)

    def makedirs(self, d, exist_ok=False):
        self.calls.append(('makedirs', os.fsdecode(d)))
        if self.makedirs_error is not None:
            raise self.makedirs_error
        return os.makedirs(d, exist_ok=exist_ok)

    def calls_of(self, name):
        return [c for c in self.calls if c[0] == name]


class Rig:
    """Sandbox + every seam the slice can touch, faked BEFORE the entrypoint runs.

    `Sandbox` repoints the config roots, the settings file, the fake homes and
    the temp dir into tmp_path and pins the background pollers. On top of it this
    rig pins the model runner, the pager, the history writer, the atomic writer,
    the editor and the UI primitives, and pins account discovery and the
    credential readers to tripwires — so no call below can reach host state, a
    credential or a process; every credential-shaped value used here is invented
    by the test and never read.

    `call()` is the only way in: it installs the stdout capture and the armed
    `open` faults AT CALL TIME (pytest installs its own global capture for the
    call phase, after fixtures, so a fixture-time capture swallows nothing).
    """

    def __init__(self, monkeypatch, tmp_path):
        mp = self.mp = monkeypatch
        self.sb = Sandbox(monkeypatch, tmp_path)
        _actual, _enc, folder, _sids = self.sb.add_project('alpha', n_sessions=0)
        self.folder = folder
        self.proj = str(self.sb.root / 'work' / 'alpha')
        self.sp = os.path.join(folder, 'system-prompt.txt')
        self.events = []
        self.caps = []
        self.read_faults = {}
        self.write_faults = {}

        # processes / editor discovery / executable lookup
        mp.setattr(system_prompt, 'subprocess', NoSpawn('subprocess'))
        mp.setattr(system_prompt, 'find_editor', tripwire('find_editor'))
        mp.setattr(system_prompt, 'get_claude_exe', lambda: r'C:\fake\claude.exe')

        # account discovery + credential readers: tripwires, not stubs, so a
        # leak fails the test instead of reading the developer's own account
        from claude_sessions import accounts as accounts_mod
        for name in ('accounts_menu', '_sync_accounts', '_login', '_env_for',
                     '_homes_menu', '_account_actions'):
            mp.setattr(accounts_mod, name, tripwire('accounts.' + name))

        # UI seams (imported by value at system_prompt.py:7)
        self.cls = self._spy('_cls')
        self.pause = self._spy('pause')
        self.flash = self._spy('flash')
        self.menu = self._spy('menu', ret='ai')
        self.text_input = self._spy('text_input', ret='')
        self.editor = self._spy('editor', ret=True)
        mp.setattr(system_prompt, '_cls', self.cls)
        mp.setattr(system_prompt, 'pause', self.pause)
        mp.setattr(system_prompt, 'flash', self.flash)
        mp.setattr(system_prompt, 'menu', self.menu)
        mp.setattr(system_prompt, 'text_input', self.text_input)
        mp.setattr(system_prompt, 'open_in_editor', self.editor)

        # model seams (`from . import memory` resolves at call time)
        self.claude_stdin = self._spy('claude_stdin',
                                      ret='You are a terse senior engineer.')
        mp.setattr(memory, '_claude_stdin', self.claude_stdin)
        mp.setattr(memory, 'last_call_cancelled', False)
        mp.setattr(memory, 'last_call_error', '')

        # pager + history seams
        self.confirm = self._spy('confirm', ret=True)
        self.record = self._spy('record')
        mp.setattr(diffview, 'confirm', self.confirm)
        mp.setattr(diffview, 'record', self.record)

        # atomic writer seam: faithful (writes real bytes) unless told otherwise
        self.write_atomic_ret = True
        self.write_atomic_writes = True
        self.write_atomic_calls = []

        def _wa(path, text, mode=None):
            self.events.append('write_atomic')
            self.write_atomic_calls.append((path, text, mode))
            if not self.write_atomic_ret:
                return False
            if self.write_atomic_writes:
                write_file(path, text)
            return True

        mp.setattr(config_mod, 'write_atomic', _wa)

    def _spy(self, tag, ret=None, raises=None):
        return Spy(tag, ret=ret, events=self.events, raises=raises)

    # -- seams --
    def use_os(self, fake):
        """Fake the `os` calls of the slice (path probes + makedirs)."""
        self.mp.setattr(system_prompt, 'os', fake)

    def set_exe(self, value):
        self.mp.setattr(system_prompt, 'get_claude_exe', lambda: value)

    def fail_read(self, path, exc=None):
        self.read_faults[_norm(path)] = exc or OSError(errno.EACCES, 'fake read denial')

    def fail_write(self, path, exc=None):
        self.write_faults[_norm(path)] = exc or OSError(errno.ENOSPC, 'fake disk full')

    def _opener(self, real):
        def opener(file, mode='r', *a, **kw):
            if isinstance(file, (str, bytes)):
                n = _norm(file)
                if 'w' in mode or 'a' in mode or 'x' in mode:
                    if n in self.write_faults:
                        raise self.write_faults[n]
                elif not isinstance(file, int) and n in self.read_faults:
                    raise self.read_faults[n]
            return real(file, mode, *a, **kw)
        return opener

    def call(self, fn, *a, **kw):
        """Run one entrypoint with stdout captured and the armed faults live."""
        cap = CapturingStdout()
        old_out, old_open = sys.stdout, builtins.open
        sys.stdout = cap
        builtins.open = self._opener(old_open)
        try:
            result = fn(*a, **kw)
        finally:
            sys.stdout = old_out
            builtins.open = old_open
        self.caps.append(cap)
        return result

    # -- assertions helpers --
    @property
    def printed(self):
        return ''.join(c.plain for c in self.caps)

    def side_effects(self):
        return [t for t in self.events if t in PRIVILEGED]

    def prompt_sent(self):
        """The prompt string handed to the model runner (or None)."""
        return self.claude_stdin.calls[0][0][0] if self.claude_stdin.calls else None

    def write_sp(self, text):
        return write_file(self.sp, text)

    def read_sp(self):
        return read_text(self.sp)


@pytest.fixture
def rig(monkeypatch, tmp_path):
    return Rig(monkeypatch, tmp_path)


def test_the_open_and_makedirs_faults_actually_fire(rig):
    """Guards the fakes themselves: an xfail is only worth anything if the fault
    it is dodging really fires, so the seams are proven live here — and an
    unarmed path still opens normally, so a passing suite is not an artefact of
    the fake."""
    base = write_file(os.path.join(rig.folder, 'system-prompt.txt'), 'RULE: keep\n')
    out = os.path.join(rig.folder, 'fault-check.txt')
    harmless = os.path.join(rig.folder, 'harmless.txt')
    rig.fail_read(base)
    rig.fail_write(out)
    rig.use_os(FakeOs(makedirs_error=OSError(errno.EACCES, 'fake mkdir denial')))

    def probe():
        with pytest.raises(OSError) as r_read:
            open(base, encoding='utf-8').read()
        assert r_read.value.errno == errno.EACCES
        with pytest.raises(OSError) as r_write:
            open(out, 'w', encoding='utf-8')
        assert r_write.value.errno == errno.ENOSPC
        assert not os.path.exists(out)
        with open(harmless, 'w', encoding='utf-8') as handle:
            handle.write('ok')
        assert read_text(harmless) == 'ok'

    rig.call(probe)


# ── the ten selected branches: denial / fail-closed first ────

@pytest.mark.xfail(strict=True, reason=(
    'fail-open source defect: system_prompt.py:20-21 swallows the read error of '
    'an EXISTING base prompt (`except Exception: pass`), merges the pointer alone '
    'and returns out_path as a success, so the instructions the docstring at '
    'system_prompt.py:11-15 promises to keep vanish from the file that '
    '--system-prompt-file feeds every session'))
def test_merged_unreadable_base_must_not_silently_vanish(rig):
    """:17-22 fail-closed. A base that exists but cannot be read is the dangerous
    case: today the merge reports success while producing a pointer-only file.
    Refusing to merge — and leaving the launch on the project's own prompt file —
    is the only safe answer, so the call must raise and write nothing.
    (test_the_open_and_makedirs_faults_actually_fire proves this fault fires.)"""
    base = write_file(os.path.join(rig.folder, 'system-prompt.txt'),
                      'RULE: never force-push. RULE: run pytest before commit.\n')
    out = os.path.join(rig.folder, 'merged-unreadable.txt')
    rig.fail_read(base)

    def attempt():
        with pytest.raises(OSError):
            system_prompt.merged_system_prompt(base, 'Read CTX.md first.', out)
        return not os.path.exists(out)

    assert rig.call(attempt) is True, 'a merged file was produced from an unreadable base'
    assert read_text(base).startswith('RULE: never force-push')


def test_generate_denies_when_claude_exe_is_missing(rig):
    """:31-36 denial. With no claude.exe the screen says so, pauses and touches
    nothing: no model call, no approval gate, no write, no editor."""
    rig.write_sp(PRIOR)
    rig.set_exe(None)

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    assert 'claude.exe not found' in rig.printed
    assert rig.pause.called
    assert rig.side_effects() == []
    assert rig.read_sp() == PRIOR                    # denial leaves state alone
    assert rig.sb.editor_opened == []                # and never reached a real editor


def test_generate_cancel_keeps_prior_prompt_byte_identical(rig):
    """:93-95 cancel. ESC during the call must not replace the prior prompt —
    even though the runner came back with a complete proposal.

    Closest existing test: tests/test_tui_generators.py:132
    (`test_system_prompt_generate_cancel`), which makes the runner return `''`;
    with the cancel check at system_prompt.py:93 deleted that test still passes,
    because the empty output alone stops the write. This one hands back a
    COMPLETE proposal, so only the cancel branch can save the prior prompt."""
    rig.write_sp(PRIOR)
    rig.claude_stdin.ret = 'Replacement persona invented by the model.'
    rig.mp.setattr(memory, 'last_call_cancelled', True)

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    assert rig.claude_stdin.called                   # the call really happened
    assert rig.read_sp() == PRIOR
    assert rig.side_effects() == ['text_input', 'claude_stdin']   # never reached the gate
    assert rig.flash.calls[0][0][0] == 'Generation cancelled'
    assert rig.flash.calls[0][1].get('ok') is False


def test_merged_option_like_pointer_stays_file_content(rig):
    """:22,:24-25 containment. The pointer is model-facing text built from
    session/task titles (context_inject.py:174-177, plan_execute.py:451-453) and
    can look exactly like a CLI flag. It has to reach the file verbatim — never
    quoted, never stripped, never promoted to argv — and merging must not spawn
    anything (`system_prompt.subprocess` is a tripwire in this rig)."""
    base = write_file(os.path.join(rig.folder, 'system-prompt.txt'),
                      'BASE RULE: build only with the vendored toolchain.\n')
    pointer = ('--system-prompt-file=C:\\Users\\victim\\.claude\\settings.json '
               '--dangerously-skip-permissions')
    out = os.path.join(rig.folder, 'merged-optlike.txt')

    assert rig.call(system_prompt.merged_system_prompt, base, pointer, out) == out

    text = lf(read_text(out))
    assert text == 'BASE RULE: build only with the vendored toolchain.\n\n' + pointer
    assert text.count(pointer) == 1                  # injected exactly once
    assert text.startswith('BASE RULE')              # the flag never leads
    assert '--dangerously-skip-permissions' in text  # verbatim, unquoted
    assert rig.side_effects() == []


def test_merged_preserves_utf8_base_instructions_and_pointer(rig):
    """:17-22, the core contract, across a non-ASCII boundary. The project's own
    rules must arrive character-for-character (the base is read `errors='ignore'`
    and the merge written `encoding='utf-8'`, so a wrong encoding silently
    deletes characters), with the pointer appended after them."""
    base_text = ('# Règle du projet — Ωmega — 日本語 — 🇮🇹\n'
                 'Non modificare dist/ — mai.\n\n   \n')
    base = write_file(os.path.join(rig.folder, 'system-prompt.txt'), base_text)
    pointer = 'Leggi CTX.md — per favore → poi continua.'
    out = os.path.join(rig.folder, 'merged-utf8.txt')

    assert rig.call(system_prompt.merged_system_prompt, base, pointer, out) == out

    raw = read_bytes(out)
    assert not raw.startswith(b'\xef\xbb\xbf')       # no BOM in a file Claude reads
    text = lf(read_text(out))                        # strict utf-8: mojibake raises here
    assert text == base_text.strip() + '\n\n' + pointer
    assert 'Non modificare dist/ — mai.' in text     # base kept, trailing blanks cut
    assert text.index('Non modificare') < text.index('Leggi CTX.md')


def test_merged_whitespace_only_base_adds_no_separator(rig):
    """:19,:22 boundary. `base + '\\n\\n' if base else ''` is guarded by the
    STRIPPED value: a whitespace-only prompt file must not buy the merged file a
    leading blank line (an empty rule block ahead of the pointer is noise Claude
    reads on every session), and neither must a zero-byte one."""
    base = write_file(os.path.join(rig.folder, 'system-prompt.txt'), '  \r\n\t\n \n')
    out = os.path.join(rig.folder, 'merged-ws.txt')
    assert rig.call(system_prompt.merged_system_prompt, base, 'POINTER LINE', out) == out
    assert lf(read_text(out)) == 'POINTER LINE'

    empty = write_file(os.path.join(rig.folder, 'ws-empty.txt'), '')
    out2 = os.path.join(rig.folder, 'merged-empty.txt')
    assert rig.call(system_prompt.merged_system_prompt, empty, 'POINTER LINE', out2) == out2
    assert lf(read_text(out2)) == 'POINTER LINE'


def test_merged_missing_base_still_writes_pointer(rig):
    """:17,:22 the pointer is never dropped for want of a base. Both halves of
    the `if sp_file and os.path.isfile(sp_file)` guard matter: the callers pass
    `''` when there is no project folder (context_inject.py:178,
    plan_execute.py:454) and a real path the moment a project deletes its file."""
    missing = os.path.join(rig.folder, 'no-such-system-prompt.txt')
    out1 = os.path.join(rig.folder, 'merged-missing.txt')
    assert rig.call(system_prompt.merged_system_prompt,
                    missing, 'Read PLAN.md first.', out1) == out1
    assert lf(read_text(out1)) == 'Read PLAN.md first.'

    out2 = os.path.join(rig.folder, 'merged-nofile.txt')
    assert rig.call(system_prompt.merged_system_prompt,
                    '', 'Read PLAN.md first.', out2) == out2
    assert lf(read_text(out2)) == 'Read PLAN.md first.'

    assert rig.side_effects() == []                  # a merge is not a model call


def test_merged_makedirs_failure_propagates_and_writes_nothing(rig):
    """:23 error path. When the merged file's directory cannot be created the
    merge has to fail loudly: the launch sites hand the returned path straight
    to `--system-prompt-file` (context_inject.py:180-181, plan_execute.py:455-458),
    so a swallowed mkdir error means launching Claude on a prompt file that does
    not exist."""
    base = write_file(os.path.join(rig.folder, 'system-prompt.txt'), 'BASE RULE\n')
    out = os.path.join(rig.folder, 'blocked', 'merged-mkdir.txt')
    fake = FakeOs(makedirs_error=OSError(errno.EACCES, 'fake mkdir denial'))
    rig.use_os(fake)

    def attempt():
        with pytest.raises(OSError) as caught:
            system_prompt.merged_system_prompt(base, 'POINTER', out)
        return caught.value.errno

    assert rig.call(attempt) == errno.EACCES
    assert fake.calls_of('makedirs') == [('makedirs', os.path.dirname(out))]
    assert not os.path.exists(os.path.join(rig.folder, 'blocked'))
    assert not os.path.exists(out)
    assert read_text(base) == 'BASE RULE\n'           # the base was not moved away


def test_merged_write_failure_has_no_success_path(rig):
    """:24-25 error path. A failed write must not return a path — the caller
    would hand a missing or half-written prompt file to Claude. And a failed
    rewrite of an existing merged file must leave the last good merge intact."""
    base = write_file(os.path.join(rig.folder, 'system-prompt.txt'), 'BASE RULE\n')
    out = os.path.join(rig.folder, 'merged-writefail.txt')
    rig.fail_write(out)

    def attempt_first():
        with pytest.raises(OSError) as caught:
            system_prompt.merged_system_prompt(base, 'POINTER', out)
        return caught.value.errno

    assert rig.call(attempt_first) == errno.ENOSPC
    assert not os.path.exists(out)
    assert rig.side_effects() == []

    prev = write_file(os.path.join(rig.folder, 'merged-prev.txt'), 'OLD MERGE\n')
    rig.fail_write(prev)

    def attempt_second():
        with pytest.raises(OSError):
            system_prompt.merged_system_prompt(base, 'POINTER', prev)

    rig.call(attempt_second)
    assert read_text(prev) == 'OLD MERGE\n'           # last good merge survives


def test_generate_timeout_or_truncated_output_replaces_nothing(rig):
    """:96,:119-123 error path. A timed-out, truncated or empty answer must leave
    the approved prompt in place and report WHY, through `memory.why_failed` —
    not the generic string, which is what hid rate limiting for a whole release.
    Three shapes of nothing: None, '', whitespace-only."""
    rig.write_sp(PRIOR)
    rig.mp.setattr(memory, 'last_call_error', 'claude: HTTP 429 rate limited (invented)')

    for nothing in (None, '', '   \n\t '):
        rig.claude_stdin.ret = nothing
        rig.call(system_prompt.ai_generate_system_prompt,
                 rig.sp, 'alpha', rig.proj, rig.folder)
        assert rig.read_sp() == PRIOR, nothing
        assert 'write_atomic' not in rig.events, nothing
        assert 'record' not in rig.events, nothing
        assert 'editor' not in rig.events, nothing
        assert 'System prompt generated' not in rig.printed

    assert rig.claude_stdin.calls                     # it really did ask the model
    assert 'rate limited (invented)' in rig.printed   # the real reason, not a guess
    assert rig.pause.calls


# ── beyond the ten: the rest of the uncovered slice ──────────

def test_generate_rejected_diff_writes_nothing(rig):
    """:54-57 + :100-104. The approval gate is the control that actually matters
    (the comment at system_prompt.py:62-64 says so). Closest existing test:
    tests/test_phase5_ux.py:101 only greps the source text for 'diffview.confirm('
    and never calls it, so inverting the gate there keeps that test green.
    A rejection must write
    nothing, record no history and open no editor — and the diff it showed has to
    be against the REAL prior prompt, or the user approves a change to text they
    never saw."""
    rig.write_sp(PRIOR)
    rig.claude_stdin.ret = 'Model proposes a completely new persona.'
    rig.confirm.ret = False

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    assert rig.confirm.called
    old, new, title = rig.confirm.calls[0][0]
    assert old == PRIOR.strip()                      # the prior prompt really was read
    assert new == 'Model proposes a completely new persona.'
    assert 'alpha' in title
    assert 'Rejected' in rig.printed
    assert rig.read_sp() == PRIOR
    assert rig.side_effects() == ['text_input', 'claude_stdin', 'confirm']


def test_generate_refuses_success_when_the_write_fails(rig):
    """:105-109. `write_atomic` answering False is a failed write: the ✔, the
    history entry and the editor all have to stay off, and the prior prompt must
    survive intact. Closest existing test: tests/test_tui_generators.py:117
    (`test_system_prompt_generate_writes`), which only ever runs the successful
    write (`write_atomic` unpatched) and asserts the file exists."""
    rig.write_sp(PRIOR)
    rig.write_atomic_ret = False

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    assert 'Error writing' in rig.printed and rig.sp in rig.printed
    assert rig.pause.called
    assert rig.write_atomic_calls and rig.write_atomic_calls[0][0] == rig.sp
    assert rig.side_effects() == ['text_input', 'claude_stdin', 'confirm', 'write_atomic']
    assert 'System prompt generated' not in rig.printed
    assert rig.read_sp() == PRIOR


def test_generate_history_failure_does_not_lose_the_approved_prompt(rig):
    """:110-113. The history write is best-effort: it must not undo an approved
    prompt, and it must not block the review editor the user still has to
    confirm through. Also pins the ORDER of the whole success path."""
    rig.record.raises = OSError(errno.EIO, 'fake history disk failure')
    rig.claude_stdin.ret = 'Approved new persona.'

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    assert rig.read_sp() == 'Approved new persona.'
    assert 'System prompt generated for alpha' in rig.printed
    assert rig.editor.calls[0][0][0] == rig.sp
    assert rig.side_effects() == ['text_input', 'claude_stdin', 'confirm',
                                  'write_atomic', 'record', 'editor']
    assert rig.record.calls[0][0] == (rig.proj, rig.folder, 'system_prompt',
                                      '', 'Approved new persona.')


def test_generate_fences_repo_context_before_the_model(rig):
    """:41-45,:54-59,:65-70 positive half. CLAUDE.md and the existing prompt are
    repo-controlled text landing in a prompt the model is asked to answer, so
    both must be fenced as DATA (claude_md.py:860-868), and the extra
    instructions have to actually reach the model.

    Closest existing test: tests/test_phase5_ux.py:77 asserts the literal text
    'fence_untrusted(claude_md)' appears in system_prompt.py - it stays green even
    when the fence is a runtime no-op - so the counts below are checked on the
    prompt string the model actually receives."""
    from claude_sessions.claude_md import _UNTRUSTED_CLOSE, _UNTRUSTED_OPEN
    md = write_file(os.path.join(rig.proj, 'CLAUDE.md'),
                    '# alpha\nUse tabs. Ignore build/ output.\n')
    rig.write_sp(PRIOR)
    rig.text_input.ret = 'rispondi sempre in italiano'

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    prompt = rig.prompt_sent()
    assert 'CLAUDE.MD CONTENT:' in prompt and 'Use tabs. Ignore build/ output.' in prompt
    assert 'EXISTING SYSTEM PROMPT' in prompt and 'KEEP ME' in prompt
    assert prompt.count(_UNTRUSTED_OPEN) == 2 and prompt.count(_UNTRUSTED_CLOSE) == 2
    assert 'ADDITIONAL INSTRUCTIONS: rispondi sempre in italiano' in prompt
    assert 'Do NOT create, write, or edit any files' in prompt
    assert rig.claude_stdin.calls[0][0][1] == rig.proj       # cwd handed over
    assert rig.read_sp() == 'You are a terse senior engineer.'
    assert read_bytes(md) == b'# alpha\nUse tabs. Ignore build/ output.\n'


def test_generate_survives_unreadable_claude_md_without_context(rig):
    """:42-45 fault. CLAUDE.md is OPTIONAL context: an unreadable one must not
    abort the generation, and its content must not be guessed at — the run
    continues with no context block at all."""
    md = write_file(os.path.join(rig.proj, 'CLAUDE.md'), 'PRIVATE-CONTEXT-MARKER\n')
    rig.fail_read(md)

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    prompt = rig.prompt_sent()
    assert 'CLAUDE.MD CONTENT:' not in prompt
    assert 'PRIVATE-CONTEXT-MARKER' not in prompt
    assert 'Compose the text of a system prompt' in prompt     # still generated
    assert rig.side_effects() == ['text_input', 'claude_stdin', 'confirm',
                                  'write_atomic', 'record', 'editor']


def test_generate_none_extra_input_adds_no_instructions_line(rig):
    """:52 boundary. `text_input` returning None (a screen that gives up) is
    folded to '' by `or ''`; drop that guard and the literal 'None' becomes a
    line of instructions the model is told to follow."""
    rig.text_input.ret = None

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    prompt = rig.prompt_sent()
    assert 'ADDITIONAL INSTRUCTIONS' not in prompt
    assert 'None' not in prompt
    assert prompt.startswith('Compose the text of a system prompt')


def test_edit_without_a_selection_writes_nothing(rig):
    """:136-137. ESC on the action menu (menu → falsy) is a denial: no prompt
    file, no template, no editor — the project's prompt stays exactly as it was."""
    rig.menu.ret = None

    rig.call(system_prompt.edit_system_prompt, rig.folder, 'alpha', rig.proj)

    assert not os.path.exists(rig.sp)
    assert rig.side_effects() == []
    assert rig.sb.editor_opened == []
    items, title = rig.menu.calls[0][0]
    assert [v for _label, v in items] == ['ai', 'manual']
    assert 'alpha' in title


def test_edit_manual_without_editor_reports_the_path(rig):
    """:146-155. Manual edit of a project that has no prompt yet must create the
    template first and, with no editor available, tell the user the exact path
    and pause — instead of losing the edit silently."""
    rig.menu.ret = 'manual'
    rig.editor.ret = False

    rig.call(system_prompt.edit_system_prompt, rig.folder, 'alpha', rig.proj)

    assert os.path.exists(rig.sp)
    body = rig.read_sp()
    assert 'alpha' in body and '--system-prompt-file' in body
    assert 'No editor found' in rig.printed and rig.sp in rig.printed
    assert rig.pause.called
    assert rig.editor.calls[0][0][0] == rig.sp
    assert 'System prompt generated' not in rig.printed


def test_edit_manual_never_rewrites_an_existing_prompt(rig):
    """:145-152 boundary. When the prompt already exists the manual path opens it
    as-is: it must not re-run the template write (that is how a user's own rules
    would be replaced by two comment lines on the way to the editor), and the
    menu has to say '(update existing)' so the user knows which state they are in."""
    rig.write_sp(PRIOR)
    rig.menu.ret = 'manual'

    rig.call(system_prompt.edit_system_prompt, rig.folder, 'alpha', rig.proj)

    items, _title = rig.menu.calls[0][0]
    assert 'update existing' in items[0][0]
    assert rig.read_sp() == PRIOR
    assert 'write_atomic' not in rig.events
    assert rig.editor.calls[0][0][0] == rig.sp


def test_generate_keeps_working_when_the_prior_prompt_is_unreadable(rig):
    """:56-59 error path. The PRIOR prompt is optional context for the diff: an
    unreadable one must not abort generation, must not be guessed at (a fabricated
    'old' side of the diff is how a user approves the wrong change), and the file
    must still end up holding what the model proposed, not stale bytes."""
    rig.write_sp(PRIOR)
    rig.fail_read(rig.sp)
    rig.claude_stdin.ret = 'Fresh persona after the unreadable prior.'

    rig.call(system_prompt.ai_generate_system_prompt, rig.sp, 'alpha', rig.proj, rig.folder)

    assert rig.confirm.called
    old, new, _title = rig.confirm.calls[0][0]
    assert old == '' and new == 'Fresh persona after the unreadable prior.'
    assert 'KEEP ME' not in rig.prompt_sent()          # nothing fabricated from it
    assert rig.read_sp() == 'Fresh persona after the unreadable prior.'
    assert rig.side_effects() == ['text_input', 'claude_stdin', 'confirm',
                                  'write_atomic', 'record', 'editor']


def test_edit_manual_stops_when_the_template_write_fails(rig):
    """:146-151 error path. On the manual path a failed template write has to
    stop there: sending the user to an editor for a file that was never written
    (and then claiming 'No editor found' when the editor probe runs anyway) loses
    the edit with no explanation."""
    rig.menu.ret = 'manual'
    rig.write_atomic_ret = False

    rig.call(system_prompt.edit_system_prompt, rig.folder, 'alpha', rig.proj)

    assert rig.write_atomic_calls and rig.write_atomic_calls[0][0] == rig.sp
    assert not os.path.exists(rig.sp)
    assert not rig.editor.called                       # never reached the editor
    assert rig.side_effects() == ['write_atomic']
    assert 'No editor found' not in rig.printed
    assert 'System prompt generated' not in rig.printed


def test_generate_passes_no_cwd_when_project_path_is_missing(rig, monkeypatch):
    """:140-141 + :91. `edit_system_prompt` can be reached with no project path;
    the AI path then has to hand the model runner `None` as its cwd, never `''`
    — an empty cwd is how a subprocess ends up running in whatever directory
    archeus itself was started in, reading whatever CLAUDE.md sits there."""
    monkeypatch.chdir(rig.folder)
    rig.menu.ret = 'ai'

    rig.call(system_prompt.edit_system_prompt, rig.folder, 'alpha')   # project_path=None

    assert rig.claude_stdin.called
    args, kwargs = rig.claude_stdin.calls[0]
    assert args[1] is None
    assert kwargs['timeout'] == 120
    assert kwargs['crumbs'][0] == 'ARCHEUS' and 'alpha' in kwargs['crumbs']
    assert 'system prompt' in kwargs['label'].lower()
    assert 'CLAUDE.MD CONTENT:' not in rig.prompt_sent()              # no stray cwd read
    assert rig.read_sp() == 'You are a terse senior engineer.'
