"""Session adapters (p12-design-gate §13.3): a user's own sessions — found,
launched, resumed and read — one per harness that declares `interactive`.

A separate protocol from the P1 execution adapter, as `calls.py` is for
`call()`: nothing here spawns an execution, and nothing here is supervised. A
session adapter answers five questions about its harness's sessions:

    discover()                  installed?
    capabilities(account)       `interactive`, `resume`, models, efforts
    locate(ref, home, cwd)      is that provider session still there? (its transcript)
    launch_argv(spec)           the terminal command for a new session or a resume
    turns(transcript, limit)    the user and assistant text turns, for a hand-off artifact
    find(home, cwd, since)      a session the harness named itself (pi mints no ref)

Claude Code and pi build their argv with `claude_sessions.launch.build_launch_command`
— the command line the current product ships, whose vocabulary rule (a model
or effort the harness does not know is dropped) is already R1's. The fake
adapter records instead of launching; two of them with different ids are how
R1 and H1 run over two harnesses with no domain change.
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Optional

from . import base


@dataclass(frozen=True)
class SessionSpec:
    """What to launch: a new session (`resume_ref` None) or a resume, on one home."""
    session_id: str
    cwd: str
    home: Optional[str] = None          # the account's home; None: the harness's own
    model: Optional[str] = None
    effort: Optional[str] = None
    resume_ref: Optional[str] = None
    opening: Optional[str] = None       # the opening message (a pointer to an artifact)


@dataclass(frozen=True)
class Launch:
    argv: list
    env: dict = field(default_factory=dict)
    ref: Optional[str] = None           # the provider session ref, when known before launch


@dataclass(frozen=True)
class Located:
    transcript_path: str
    model: Optional[str] = None
    effort: Optional[str] = None


def _caps(models, efforts):
    return base.Capabilities(frozenset({'interactive', 'resume'}), 'none', tuple(models),
                             efforts=tuple(e for e in efforts if e))


# ── the fake (tests, the judge) ─────────────────────────────────────────────

class FakeSessions:
    """A harness whose provider sessions are files under `<ARCHEUS_HOME>/
    fake_sessions/<id>/<ref>.jsonl`, one `{"role", "text"}` line per turn.
    Launching writes the file (a provider starting a session) and records the
    spec; nothing runs."""

    def __init__(self, id='fake', *, models=('fake-model', 'fake-large'),
                 efforts=('low', 'high'), installed=True):
        self.id, self._models, self._efforts = id, tuple(models), tuple(efforts)
        self.installed = installed
        self.launched = []

    def _dir(self):
        from ..infra.paths import archeus_home
        return os.path.join(archeus_home(), 'fake_sessions', self.id)

    def path(self, ref):
        return os.path.join(self._dir(), '%s.jsonl' % ref)

    def write(self, ref, turns):
        """A provider session with these (role, text) turns, as a user made it."""
        os.makedirs(self._dir(), exist_ok=True)
        with open(self.path(ref), 'w', encoding='utf-8') as f:
            for role, text in turns:
                f.write(json.dumps({'role': role, 'text': text}) + '\n')
        return self.path(ref)

    def discover(self):
        return base.HarnessInfo(self.id, self.installed, None, 'fake' if self.installed else None)

    def capabilities(self, account=None):
        return _caps([base.ModelInfo(m) for m in self._models], self._efforts)

    def locate(self, ref, home, cwd):
        p = self.path(ref) if ref else ''
        return Located(p) if p and os.path.exists(p) else None

    def launch_argv(self, spec):
        ref = spec.resume_ref or str(uuid.uuid4())
        if spec.resume_ref is None:
            self.write(ref, [])
        self.launched.append(spec)
        argv = ['fake-session', '--ref', ref]
        if spec.model:
            argv += ['--model', spec.model]
        if spec.effort:
            argv += ['--effort', spec.effort]
        if spec.opening:
            argv += [spec.opening]
        return Launch(argv, {}, ref)

    def turns(self, transcript_path, limit):
        out = []
        with open(transcript_path, encoding='utf-8') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get('role') in ('user', 'assistant') and obj.get('text'):
                    out.append((obj['role'], str(obj['text'])))
        return out[-limit:]

    def find(self, home, cwd, since):
        return None


# ── Claude Code ─────────────────────────────────────────────────────────────

class ClaudeCodeSessions:
    """`claude [-r <ref>] [--model] [--effort] ["<opening>"]`, on one config dir.
    Transcripts are `<home>/projects/<enc(cwd)>/<ref>.jsonl`."""
    id = 'claude_code'
    _legacy = 'claude'

    def _home(self, home):
        from claude_sessions import harnesses
        return home or harnesses.home_dir(self._legacy)

    def discover(self):
        from claude_sessions import config
        exe = config.get_claude_exe()
        return base.HarnessInfo(self.id, bool(exe), None, exe)

    def capabilities(self, account=None):
        from claude_sessions import harnesses
        from .calls import claude_models
        return _caps(claude_models(), harnesses.descriptor(self._legacy)['efforts'])

    def locate(self, ref, home, cwd):
        from claude_sessions import paths, store, transcripts
        if not ref:
            return None
        try:
            folder = store.project_folder(self._home(home), paths.encode_component(cwd))
        except ValueError:
            return None
        p = os.path.join(folder, '%s.jsonl' % ref)
        if not os.path.isfile(p):
            return None
        model = None
        for obj in transcripts.iter_json(p, prefilter='"model"'):
            m = (obj.get('message') or {}).get('model') if isinstance(obj, dict) else None
            if isinstance(m, str) and m and not m.startswith('<'):
                model = m
        return Located(p, model)

    def launch_argv(self, spec):
        from claude_sessions import paths
        from claude_sessions.launch import build_launch_command
        opts = {'cfgdir': self._home(spec.home), 'model': spec.model or '',
                'effort': spec.effort or '', 'perm': '', 'name': '', 'worktree': '',
                'agent': '', 'prompt': spec.opening or ''}
        choice = 'resume:%s' % spec.resume_ref if spec.resume_ref else 'new'
        args, env, _folder = build_launch_command(spec.cwd, paths.encode_component(spec.cwd),
                                                  choice, opts)
        ref = spec.resume_ref
        if ref is None and '--session-id' in args:
            ref = args[args.index('--session-id') + 1]
        return Launch(list(args), dict(env), ref)

    def turns(self, transcript_path, limit):
        from claude_sessions import transcript
        return [(m['role'], m['text']) for m in transcript.iter_transcript(transcript_path)
                if m.get('role') in ('user', 'assistant') and m.get('text')][-limit:]

    def find(self, home, cwd, since):
        return None             # a new Claude session's ref is chosen before launch


# ── pi ──────────────────────────────────────────────────────────────────────

class PiSessions:
    """`pi [--session <ref>] [--model] [--thinking] [-- "<opening>"]` on one pi
    home. pi names a new session itself, so its ref is found after launch:
    the one session of that cwd started after the launch, never a guess
    between two (p12-design-gate §28)."""
    id = 'pi'
    _legacy = 'pi'

    def _home(self, home):
        from claude_sessions import harnesses
        return home or harnesses.home_dir(self._legacy)

    def _folder(self, home, cwd):
        from claude_sessions import paths
        return os.path.join(self._home(home), 'projects', paths.encode_component(cwd))

    def discover(self):
        from claude_sessions import harnesses
        exe = None if 'pi' in harnesses.disabled() else harnesses.exe('pi')
        return base.HarnessInfo(self.id, bool(exe), None, exe)

    def capabilities(self, account=None):
        from claude_sessions import harnesses
        from .calls import pi_models
        return _caps(pi_models(), harnesses.descriptor(self._legacy)['efforts'])

    def locate(self, ref, home, cwd):
        from claude_sessions import pi
        p = pi.transcript_path(self._folder(home, cwd), ref) if ref else ''
        return Located(p) if p else None

    def launch_argv(self, spec):
        from claude_sessions import paths
        from claude_sessions.launch import build_launch_command
        opts = {'cfgdir': self._home(spec.home), 'model': spec.model or '',
                'effort': spec.effort or '', 'perm': '', 'name': '', 'worktree': '',
                'agent': '', 'prompt': spec.opening or ''}
        choice = 'resume:%s' % spec.resume_ref if spec.resume_ref else 'new'
        args, env, _folder = build_launch_command(spec.cwd, paths.encode_component(spec.cwd),
                                                  choice, opts)
        return Launch(list(args), dict(env), spec.resume_ref)

    def turns(self, transcript_path, limit):
        from claude_sessions import pi, transcripts
        out = []
        for obj in transcripts.iter_json(transcript_path, prefilter='"message"'):
            m = (obj.get('message') or {}) if obj.get('type') == 'message' else {}
            if m.get('role') in ('user', 'assistant'):
                text = pi._text(m.get('content'))
                if text:
                    out.append((m['role'], text))
        return out[-limit:]

    def find(self, home, cwd, since):
        from claude_sessions import pi
        new = [p for mtime, p in pi._files(pi._dir_for(self._folder(home, cwd)))
               if mtime >= since]
        return pi._sid(new[0]) if len(new) == 1 else None


def real_session_adapters():
    return [ClaudeCodeSessions(), PiSessions()]
