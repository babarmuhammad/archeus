"""Desktop notifications: the right work, on every platform, and never in tests.

Two things can go wrong here and neither is visible by reading. A notification
for every job turns into noise and gets switched off, so the threshold has to be
real; and a test that pops a toast on the machine running it is the same class
of failure as the test run that once opened Notepad++ — which is why the block
lives in conftest, on the spawn, and is asserted here.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox

from claude_sessions import config, notify, proc


@pytest.fixture
def sent(monkeypatch, tmp_path):
    """Capture what would have been spawned.

    `notify-send` is pinned as present because otherwise these tests assert a
    property of the HOST rather than of archeus: on Linux with no notifier
    installed — a headless CI runner, for instance — `command()` correctly
    returns None, `send()` returns False before it ever reaches Popen, and the
    'a long job notifies' tests below fail for a reason that has nothing to do
    with the behaviour they describe. The real per-platform argv builder still
    runs (Windows and macOS never consult `which`), and the three tests at the
    bottom of this file cover each branch of it directly."""
    import shutil
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.delenv('ARCHEUS_NO_NOTIFY', raising=False)
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/notify-send')
    calls = []
    monkeypatch.setattr(notify.subprocess, 'Popen',
                        lambda argv, **kw: calls.append(argv))
    return calls


# ── when ─────────────────────────────────────────────────────

def test_a_quick_job_does_not_notify(sent):
    assert notify.job_finished('Building memory', 'done', 3) is False
    assert not sent


def test_a_long_job_does(sent):
    assert notify.job_finished('Building memory', 'done', 90) is True
    assert len(sent) == 1
    assert any('Building memory' in str(a) for a in sent[0])


def test_a_failure_says_so(sent):
    notify.job_finished('Writing plan', 'error', 120, 'model refused')
    assert any('failed' in str(a) for a in sent[0])
    assert any('model refused' in str(a) for a in sent[0])


def test_a_cancelled_job_is_not_news(sent):
    assert notify.job_finished('Reviewing changes', 'cancelled', 300) is False
    assert not sent


# ── the switches ─────────────────────────────────────────────

def test_the_setting_turns_it_off(sent):
    s = config.load_settings()
    s['notifications'] = False
    config.save_settings(s)
    assert notify.enabled() is False
    assert notify.send('x', 'y') is False
    assert not sent


def test_it_is_on_by_default(sent):
    assert notify.enabled() is True


def test_the_suite_cannot_raise_a_real_notification(monkeypatch, tmp_path):
    """conftest sets ARCHEUS_NO_NOTIFY for every test. Without this assertion
    the block is a convention; with it, deleting the fixture goes red."""
    Sandbox(monkeypatch, tmp_path)
    assert os.environ.get('ARCHEUS_NO_NOTIFY')
    assert notify.enabled() is False


# ── how, per platform ────────────────────────────────────────

def test_windows_uses_a_powershell_toast(monkeypatch):
    monkeypatch.setattr(proc, 'WINDOWS', True)
    argv = notify.command('Memory updated', 'archeus')
    assert argv[0] == 'powershell' and '-NoProfile' in argv
    script = argv[-1]
    assert 'ToastNotificationManager' in script
    # an unregistered AppID is silently dropped by Windows, so the toast has to
    # ride on one that exists
    assert 'powershell.exe' in script


def test_macos_uses_osascript(monkeypatch):
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    argv = notify.command('Memory updated', 'done')
    assert argv[0] == 'osascript'
    assert 'display notification' in argv[-1]


def test_linux_uses_notify_send_when_present(monkeypatch):
    import shutil
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/notify-send')
    assert notify.command('a', 'b')[0] == 'notify-send'
    monkeypatch.setattr(shutil, 'which', lambda n: None)
    assert notify.command('a', 'b') is None       # no notifier: silence, not a crash


def test_a_machine_with_no_notifier_is_silent_not_broken(monkeypatch, tmp_path):
    """The headless case — a Linux CI runner, a server, a stripped container.
    `job_finished` reports that nothing was raised, and nothing raises.

    Asserted deliberately because it used to be asserted by ACCIDENT, in the
    other direction: the 'a long job notifies' tests stubbed Popen but not the
    command builder, so on a host without notify-send they failed on a property
    of the machine rather than of archeus."""
    import shutil
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.delenv('ARCHEUS_NO_NOTIFY', raising=False)
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(shutil, 'which', lambda n: None)

    def _boom(*a, **kw):
        raise AssertionError('spawned a notifier that does not exist')

    monkeypatch.setattr(notify.subprocess, 'Popen', _boom)
    assert notify.enabled() is True
    assert notify.send('Memory updated', 'x') is False
    assert notify.job_finished('Building memory', 'done', 90) is False


def test_a_quoted_title_cannot_close_the_applescript_string(monkeypatch):
    """The title reaches an AppleScript string literal, so its quotes must be
    escaped there — otherwise a job label could end the string and append its
    own statement."""
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    script = notify.command('a" & do shell script "rm -rf /', 'x')[-1]
    assert '\\"' in script, 'the quote was not escaped'
    # the literal stays one string: exactly four UNESCAPED quotes (two pairs)
    assert len(re.findall(r'(?<!\\)"', script)) == 4, script


def test_the_job_runner_notifies_from_its_one_terminal_point():
    """Thirty start_job call sites, one place a job ends. The hook belongs in
    the `finally` that already forces a terminal status — anywhere else is a
    per-kind list that goes stale (the same argument as the approval gate)."""
    import inspect
    from claude_sessions import gui_api
    src = inspect.getsource(gui_api.start_job)
    assert 'notify.job_finished' in src
    assert src.index('finally:') < src.index('notify.job_finished')


def test_the_detached_memory_worker_notifies():
    """It has no interface of any kind: no banner, no window, nothing. If it
    does not notify, its result reaches nobody."""
    import inspect
    from claude_sessions import main
    src = inspect.getsource(main._bg_scan_cli)
    assert 'notify.job_finished' in src
