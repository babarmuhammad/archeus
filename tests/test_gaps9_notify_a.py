"""T-1354 · highest-risk test gaps in claude_sessions/notify.py 39-106.

Slice: `enabled`, `_ps_toast`, `command` and `send` (39-106) at tip 10d688c0.
Selected branches, ranked (denial first, then boundaries, then error paths):

 1. 60-68 (line 64) — PREMISE, strict xfail: a message line starting with `'@`
    ends the PowerShell single-quoted here-string early; xml escape does not cover newlines.
 2. 40-41 — ARCHEUS_NO_NOTIFY set: enabled() is False, send() returns False before argv.
 3. 42-46 — a settings load failure disables notifications (fail closed).
 4. 57-59 — title and message are XML-escaped, so markup stays text.
 5. 79-80 — Windows argv runs hidden and non-interactive.
 6. 53-59 — None and int title/message are str()-coerced and never raise.
 7. 81-85 — darwin escaping doubles a backslash before it escapes a quote.
 8. 86-88 — notify-send gets title and message as separate argv items. Replaces the
    missing-notifier case, which test_notify.py already pins
    (test_a_machine_with_no_notifier_is_silent_not_broken).
 9. 99-104 — Popen output goes to DEVNULL; a Popen failure is False, not raised.
10. 107-115 — job_finished (outside the stated slice, reached through send): the
    threshold is inclusive at MIN_SECONDS, only done/error notify, and a blank
    detail gets the default line.

Seams: config.load_settings, os.environ, proc.WINDOWS, sys.platform, shutil.which,
subprocess.Popen (recorder). No toast, osascript or notify-send is spawned.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import config, notify, proc


@pytest.fixture
def toast(monkeypatch):
    monkeypatch.delenv('ARCHEUS_NO_NOTIFY', raising=False)
    monkeypatch.setattr(config, 'load_settings', lambda: {})
    monkeypatch.setattr(proc, 'WINDOWS', True)
    spawned = []
    monkeypatch.setattr(notify.subprocess, 'Popen',
                        lambda argv, **kw: spawned.append((argv, kw)))
    return spawned


def _no_argv(*a, **kw):
    raise AssertionError('built an argv while notifications were off')


def test_a_line_starting_with_the_here_string_closer_cannot_end_the_script_early(toast):
    script = notify.command('t', "ok\n'@; Start-Process calc; @'\nmore")[-1]
    closers = [line for line in script.split('\n') if line.startswith("'@")]
    assert len(closers) == 1


def test_the_suite_switch_stops_before_any_argv_is_built(toast, monkeypatch):
    monkeypatch.setenv('ARCHEUS_NO_NOTIFY', '1')
    monkeypatch.setattr(notify, 'command', _no_argv)
    assert notify.enabled() is False
    assert notify.send('t', 'm') is False
    assert toast == []


def test_an_unreadable_settings_file_turns_notifications_off(toast, monkeypatch):
    def broken():
        raise ValueError('unreadable')
    monkeypatch.setattr(config, 'load_settings', broken)
    monkeypatch.setattr(notify, 'command', _no_argv)
    assert notify.enabled() is False
    assert notify.job_finished('Build', 'done', 90) is False
    assert toast == []


def test_markup_in_title_and_message_stays_text_in_the_toast_xml(toast):
    script = notify.command('<b>Tom & Jerry</b>', 'a<script>')[-1]
    assert '<text id="1">&lt;b&gt;Tom &amp; Jerry&lt;/b&gt;</text>' in script
    assert '<text id="2">a&lt;script&gt;</text>' in script


def test_the_toast_process_starts_hidden_and_non_interactive(toast):
    argv = notify.command('t', 'm')
    assert argv[argv.index('-WindowStyle') + 1] == 'Hidden'
    assert '-NonInteractive' in argv


def test_none_and_numbers_are_stringified_not_raised(toast):
    script = notify.command(None, 5)[-1]
    assert '<text id="1">None</text>' in script
    assert '<text id="2">5</text>' in script
    assert notify.send(None, 0) is True
    assert len(toast) == 1


def test_a_backslash_before_a_quote_cannot_escape_the_applescript_string(monkeypatch):
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    argv = notify.command('t', 'end\\"')
    assert argv[-1] == 'display notification "end\\\\\\"" with title "t"'


def test_notify_send_gets_title_and_message_as_their_own_arguments(monkeypatch):
    import shutil
    monkeypatch.setattr(proc, 'WINDOWS', False)
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setattr(shutil, 'which', lambda n: '/usr/bin/notify-send')
    assert notify.command('a; rm -rf x', '$(id)') == [
        'notify-send', '-a', notify.APP_NAME, 'a; rm -rf x', '$(id)']


def test_a_spawn_is_detached_with_its_output_sent_to_devnull(toast):
    assert notify.send('t', 'm') is True
    _argv, kw = toast[0]
    assert kw['stdout'] is subprocess.DEVNULL
    assert kw['stderr'] is subprocess.DEVNULL


def test_a_spawn_that_fails_is_false_not_raised(toast, monkeypatch):
    def boom(*a, **kw):
        raise OSError('no such program')
    monkeypatch.setattr(notify.subprocess, 'Popen', boom)
    assert notify.send('t', 'm') is False


def test_the_threshold_is_inclusive_and_only_finished_jobs_notify(toast):
    assert notify.job_finished('Build', 'done', notify.MIN_SECONDS - 0.5) is False
    assert notify.job_finished('Build', 'running', 300) is False
    assert toast == []
    assert notify.job_finished('Build', 'done', notify.MIN_SECONDS) is True
    assert len(toast) == 1


def test_a_blank_detail_gets_the_default_line(toast):
    notify.job_finished(None, 'error', 30, '')
    notify.job_finished('Build', 'done', 30, '')
    scripts = [argv[-1] for argv, _kw in toast]
    assert '<text id="1">Job — failed</text>' in scripts[0]
    assert '<text id="2">See the job banner for the error.</text>' in scripts[0]
    assert '<text id="1">Build — done</text>' in scripts[1]
    assert '<text id="2">Finished in 30s.</text>' in scripts[1]
