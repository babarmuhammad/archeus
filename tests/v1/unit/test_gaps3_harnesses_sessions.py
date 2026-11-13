"""T-1163: the highest-risk test gaps in archeus/harnesses/sessions.py lines 1-255
inclusive, at tip 56d53504 — the empty/absent transcript, the home an argv and a
transcript bind to, and the reads that must answer nothing.

Fail-closed and denial first, then boundaries, then error paths. Every branch below
is a source branch that no existing test of this module reaches, so it still fails
when that branch is removed or inverted. Style and seams follow the nearest existing
coverage of this module (tests/v1/unit/test_gaps_harnesses_sessions.py and
test_session_units.py): every OS call goes through an existing seam
(`launch.build_launch_command`, `harnesses.home_dir`, `store.project_folder`), every
byte on disk is written under tmp_path with explicit newlines, no process is spawned,
nothing reads the user's home or the host environment.

The ten final selected branches (source file:line, and what removal/inversion catches):

  1. sessions.py:156  ClaudeCodeSessions.locate `if not ref` — an empty ref is denied
     before the project folder is ever named.
  2. sessions.py:186  ClaudeCodeSessions.find `return None` — a new Claude session's
     ref is chosen before launch, so find never names a session (p12 §28).
  3. sessions.py:129  FakeSessions.find `return None` — the fake never names a ref.
  4. sessions.py:183  ClaudeCodeSessions.turns `out[-limit:] if limit > 0 else []` —
     a request for zero turns is NO turns, never the whole transcript.
  5. sessions.py:245  PiSessions.turns `out[-limit:] if limit > 0 else []` — same cap.
  6. sessions.py:228  PiSessions.launch_argv `'cfgdir': self._home(spec.home)` — the
     launch argv binds the CHOSEN home, never the harness default.
  7. sessions.py:142  ClaudeCodeSessions._home `home or harnesses.home_dir('claude')`
     — with no home chosen, the argv binds the harness's own home.
  8. sessions.py:201  PiSessions._home `home or harnesses.home_dir('pi')` — same for pi.
  9. sessions.py:230  PiSessions.launch_argv `'prompt': spec.opening or ''` — an
     opening is carried verbatim as the prompt.
 10. sessions.py:112  FakeSessions.launch_argv `argv += [spec.opening]` — an
     option-like opening stays ONE argv element, never split into flags.

Replaced probes (already covered or inapplicable inside this slice, with evidence):
missing transcript (covered by test_gaps test_claude_code_locate_refuses_a_transcript_
that_is_not_a_file and the pi locate test), fork versus continue (both `resume:`/`new`
choice branches are covered by the builder and fake resume tests), opaque resume
identifier (covered by the path-ref refusal tests), truncated/garbage transcript
(covered by the fake garbage and invalid-utf8 tests), since-boundary excludes old
sessions (covered by test_pi_find_waits_for_a_session_at_all and the `>=` edge test).
"""

import json
import os

from archeus.harnesses.sessions import (ClaudeCodeSessions, FakeSessions, PiSessions,
                                        SessionSpec)
from claude_sessions import harnesses, launch, store

#: a fixed wall-clock epoch for the find boundary; mtimes are never slept on
BASE = 1700000000.0


def _write_lines(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for line in lines:
            f.write(line + '\n')


class _Recorder:
    """`launch.build_launch_command` answering a canned argv and recording the opts."""

    def __init__(self):
        self.opts = None

    def __call__(self, path, encoded_name, choice, opts):
        self.opts = {'path': path, 'encoded': encoded_name, 'choice': choice,
                     'opts': dict(opts)}
        return ['claude.exe'], {'CFGDIR': self.opts['opts']['cfgdir']}, None


def _install_builder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(launch, 'build_launch_command', rec)
    return rec


# ── 1. denial: Claude locate refuses an empty ref without naming a folder ─────

def test_claude_locate_refuses_an_empty_ref_without_naming_a_project_folder(tmp_path,
                                                                           monkeypatch):
    """sessions.py:156 `if not ref or os.path.basename(ref) != ref: return None`.

    Removing the `not ref` half of the guard lets an empty ref fall through to
    `store.project_folder` (an empty basename equals an empty ref), naming a real
    project folder it was never asked about. The boom seam proves the folder is never
    even named. Closest existing test — test_claude_code_locate_refuses_a_ref_that_is_
    a_path — only feeds non-empty path refs, so it still passes when the empty-ref
    denial is dropped.
    """
    def boom(cfgdir, enc):
        raise AssertionError('a project folder was named for an empty ref')

    monkeypatch.setattr(store, 'project_folder', boom)
    a = ClaudeCodeSessions()
    assert a.locate('', str(tmp_path / 'home'), str(tmp_path / 'work')) is None
    assert a.locate(None, str(tmp_path / 'home'), str(tmp_path / 'work')) is None


# ── 2 & 3. denial: find never names a session the adapter did not choose ──────

def test_claude_find_never_names_a_session_its_adapter_did_not_choose(tmp_path):
    """sessions.py:186 `def find(...): return None`.

    A new Claude session's ref is chosen before launch, so post-launch `find` must
    answer None. Flipping it to name a transcript would let a session bind to a ref
    its adapter never chose — the §28 "never a guess" rule. No existing test of this
    module calls ClaudeCodeSessions.find at all. A decoy transcript is planted under
    the folder so a guessing implementation would find something and fail.
    """
    from claude_sessions import paths
    home = tmp_path / 'cfg'
    cwd = tmp_path / 'work'
    cwd.mkdir()
    folder = os.path.join(str(home), 'projects', paths.encode_component(str(cwd)))
    _write_lines(os.path.join(folder, 'decoy.jsonl'), ['{"role": "user", "text": "hi"}'])
    assert ClaudeCodeSessions().find(str(home), str(cwd), BASE) is None


def test_the_fake_find_never_names_a_session():
    """sessions.py:129 `def find(...): return None` for the fake.

    The fake records and locates but must never name a ref either: a fake that
    started guessing refs would make a session binding pass for the wrong reason. A
    real session file is planted under the fake's own directory so a non-None return
    would be reachable and the assertion would bite.
    """
    a = FakeSessions('f_find')
    a.write('a-real-one', [('user', 'hi')])
    assert a.locate('a-real-one', None, '/w') is not None      # it does locate the real one
    assert a.find(None, '/w', BASE) is None                   # ... but never names it


# ── 4 & 5. boundary: a request for zero turns is no turns, not the transcript ─

def test_claude_turns_asks_for_nothing_and_gets_nothing(tmp_path):
    """sessions.py:183 `return out[-limit:] if limit > 0 else []`.

    Drop the `if limit > 0` guard and `out[-0:]` is the WHOLE transcript, so a
    hand-off artifact that asked for no turns would carry every user and assistant
    line — the leak T-652#F4 closed for the fake, still open for the real Claude
    reader (test_claude_code_turns_keep_only_conversation_text only ever asks for 10
    and 2). The tail and the limit==len / limit>len boundary are asserted too so the
    cap is not merely inverted to always-empty.
    """
    p = str(tmp_path / 'claude.jsonl')
    _write_lines(p, [json.dumps({'message': {'role': 'user', 'content': 'hello'}}),
                     json.dumps({'message': {'role': 'assistant',
                                             'content': [{'type': 'text', 'text': 'done'}]}})])
    a = ClaudeCodeSessions()
    assert a.turns(p, 0) == []
    assert a.turns(p, -1) == []
    assert a.turns(p, 1) == [('assistant', 'done')]                       # the tail
    assert a.turns(p, 2) == [('user', 'hello'), ('assistant', 'done')]    # limit == len
    assert a.turns(p, 99) == [('user', 'hello'), ('assistant', 'done')]   # limit > len


def test_pi_turns_asks_for_nothing_and_gets_nothing(tmp_path):
    """sessions.py:245 `return out[-limit:] if limit > 0 else []`.

    The same whole-transcript leak, on pi's reader: with the guard removed a
    zero-turn request returns both message turns. The nearest test —
    test_pi_turns_reads_only_the_message_records_pi_means — only asks for 10 and 1.
    """
    p = str(tmp_path / 'pi_session.jsonl')
    _write_lines(p, [json.dumps({'type': 'session', 'id': 'sid-1', 'cwd': '/w'}),
                     json.dumps({'type': 'message',
                                 'message': {'role': 'user', 'content': 'hi'}}),
                     json.dumps({'type': 'message',
                                 'message': {'role': 'assistant',
                                             'content': [{'type': 'text', 'text': 'yo'}]}})])
    a = PiSessions()
    assert a.turns(p, 0) == []
    assert a.turns(p, -1) == []
    assert a.turns(p, 1) == [('assistant', 'yo')]
    assert a.turns(p, 2) == [('user', 'hi'), ('assistant', 'yo')]
    assert a.turns(p, 99) == [('user', 'hi'), ('assistant', 'yo')]


# ── 6. boundary: a pi launch argv binds the CHOSEN home, never the default ────

def test_a_pi_launch_binds_the_chosen_home_not_the_harness_default(tmp_path, monkeypatch):
    """sessions.py:228 `'cfgdir': self._home(spec.home)`.

    The chosen home is what the launch must bind — the config dir points the harness
    at one account, and the wrong home reads another account's transcripts and login.
    test_a_new_pi_launch_never_borrows_a_ref asserts the `choice`, the absent ref and
    the model but never the cfgdir, so a launch that quietly fell back to the harness
    default would still pass. The default is made a decoy so a fallback is observable
    and wrong.
    """
    rec = _install_builder(monkeypatch)
    chosen = str(tmp_path / 'chosen-pi-home')
    decoy_default = str(tmp_path / 'DECOY-default-home')
    monkeypatch.setattr(harnesses, 'home_dir', lambda hid=None: decoy_default)
    PiSessions().launch_argv(SessionSpec('ses_1', str(tmp_path), home=chosen,
                                         resume_ref='sid-7'))
    assert rec.opts['opts']['cfgdir'] == chosen             # the chosen home binds
    assert rec.opts['opts']['cfgdir'] != decoy_default      # never the default
    assert rec.opts['choice'] == 'resume:sid-7'


# ── 7 & 8. boundary: with no home chosen, argv binds the harness's own home ───

def test_a_claude_launch_binds_the_harness_home_when_none_is_chosen(tmp_path, monkeypatch):
    """sessions.py:142 `return home or harnesses.home_dir(self._legacy)` (Claude).

    When the caller passes no home, the argv must bind the Claude Code harness's own
    home, not None. Every existing Claude launch test passes an explicit home, so the
    fallback half of this `or` is never taken; making `home_dir` a boom-free sentinel
    proves it is reached. If the fallback were dropped, cfgdir would reach the builder
    as None.
    """
    rec = _install_builder(monkeypatch)
    default = str(tmp_path / 'CLAUDE-default-home')
    monkeypatch.setattr(harnesses, 'home_dir', lambda hid=None: default)
    got = ClaudeCodeSessions().launch_argv(SessionSpec('ses_1', str(tmp_path), home=None,
                                                       resume_ref='abc'))
    assert rec.opts['opts']['cfgdir'] == default
    assert got.ref == 'abc'


def test_a_pi_launch_binds_the_harness_home_when_none_is_chosen(tmp_path, monkeypatch):
    """sessions.py:201 `return home or harnesses.home_dir(self._legacy)` (pi).

    Same fallback for pi: a launch with no chosen home binds pi's own home. The
    existing pi launch test passes home=harnesses.home_dir('pi') (the default) as an
    explicit truthy value, so it never exercises the `or` fallback either.
    """
    rec = _install_builder(monkeypatch)
    default = str(tmp_path / 'PI-default-home')
    monkeypatch.setattr(harnesses, 'home_dir', lambda hid=None: default)
    PiSessions().launch_argv(SessionSpec('ses_1', str(tmp_path), home=None,
                                        resume_ref='sid-1'))
    assert rec.opts['opts']['cfgdir'] == default


# ── 9. boundary: a pi launch carries the opening verbatim as the prompt ───────

def test_a_pi_launch_carries_the_opening_as_the_prompt(tmp_path, monkeypatch):
    """sessions.py:230 `'prompt': spec.opening or ''`.

    The opening — a pointer to a hand-off artifact — must reach the builder as the
    prompt, and the pi adapter never had a test that passed one at all. The chosen
    home is bound too, so a prompt that landed on the wrong home is caught here.
    """
    rec = _install_builder(monkeypatch)
    chosen = str(tmp_path / 'pi-home')
    PiSessions().launch_argv(SessionSpec('ses_1', str(tmp_path), home=chosen,
                                        resume_ref='sid-9', opening='read the artifact'))
    assert rec.opts['opts']['prompt'] == 'read the artifact'
    assert rec.opts['opts']['cfgdir'] == chosen


# ── 10. boundary: an option-like opening stays ONE argv element (the fake) ─────

def test_the_fake_keeps_an_option_like_opening_as_one_argument():
    """sessions.py:111-112 `if spec.opening: argv += [spec.opening]`.

    The opening is appended as a SINGLE element, so text that begins like a flag
    stays a positional prompt and never becomes an option the fake-session command
    would act on. test_the_fake_session_adapter_records_and_never_launches only ever
    uses a plain-word opening ('read it'), so an inversion that shell-split the
    opening (`argv += spec.opening.split()`) would still pass it. Here the option-like
    opening must survive as exactly one trailing element and never appear as a flag.
    """
    a = FakeSessions('f_opt')
    got = a.launch_argv(SessionSpec('ses_1', '/w', resume_ref='ref-1',
                                    opening='--model evil --effort max'))
    assert got.argv == ['fake-session', '--ref', 'ref-1', '--model evil --effort max']
    assert got.argv[-1] == '--model evil --effort max'         # one element, not split
    assert '--model' not in got.argv[:-1]                      # never became a flag
