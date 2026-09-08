"""Desktop notifications for work that finishes while you are elsewhere.

Memory refreshes, plans and reviews take minutes and run in the background on
purpose — the job banner exists so you can navigate away. That is exactly why
the finish has to reach you outside the window: the detached memory worker
(`archeus --bg-scan`) has no UI at all, and a Plan→Execute run that ends while
you are in another app ended silently.

Stdlib only, fire-and-forget, and it never raises: a notification that breaks
the thing it is reporting on is worse than no notification.

  Windows  PowerShell + the WinRT toast API, under PowerShell's own AppID.
           Nothing to install — the BurntToast module is not assumed.
  macOS    osascript `display notification`.
  Linux    notify-send, when it exists.

Two switches, deliberately: the `notifications` setting is the user's, and
`ARCHEUS_NO_NOTIFY` is the test suite's — conftest sets it for the whole run
so no test can pop a real toast, the same choke-point discipline the editor
spawn already uses.
"""

import os
import subprocess
import sys

from . import proc

__all__ = ['send', 'enabled', 'job_finished', 'MIN_SECONDS']

#: a job that took less than this was watched, not waited for. Notifying on a
#: two-second refresh is how a feature like this becomes something people turn
#: off — see the ambient-motion lesson in CLAUDE.md.
MIN_SECONDS = 20

APP_NAME = 'archeus'


def enabled():
    if os.environ.get('ARCHEUS_NO_NOTIFY'):
        return False
    try:
        from .config import load_settings
        return bool(load_settings().get('notifications', True))
    except Exception:
        return False


def _ps_toast(title, message):
    """PowerShell one-liner building a WinRT toast.

    The AppID is PowerShell's own registered AUMID: a toast raised under an
    unregistered id is silently dropped by Windows, and archeus has no
    installer to register one of its own.
    """
    def q(s):
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    xml = ('<toast><visual><binding template="ToastText02">'
           '<text id="1">%s</text><text id="2">%s</text>'
           '</binding></visual></toast>' % (q(title), q(message)))
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
        " ContentType=WindowsRuntime] > $null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        "$x.LoadXml(@'\n%s\n'@);"
        "$t = New-Object Windows.UI.Notifications.ToastNotification $x;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'"
        ").Show($t);" % xml)
    return ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
            '-Command', script]


def command(title, message):
    """The argv for this platform, or None when there is nothing to run.

    Split out from `send` so a test can assert the command instead of the side
    effect — the only way to check this without a real desktop.
    """
    if proc.WINDOWS:
        return _ps_toast(title, message)
    if sys.platform == 'darwin':
        def esc(s):
            return str(s).replace('\\', '\\\\').replace('"', '\\"')
        return ['osascript', '-e', 'display notification "%s" with title "%s"'
                % (esc(message), esc(title))]
    import shutil
    if shutil.which('notify-send'):
        return ['notify-send', '-a', APP_NAME, str(title), str(message)]
    return None


def send(title, message=''):
    """Raise one notification. True if something was spawned."""
    if not enabled():
        return False
    argv = command(title, message)
    if not argv:
        return False
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=proc.no_window_flags)
        return True
    except Exception:
        return False


def job_finished(label, status, seconds, detail=''):
    """The job runner's hook: notify only for work that actually ran long
    enough for the user to have left, and say how it ended."""
    if seconds < MIN_SECONDS or status not in ('done', 'error'):
        return False
    head = label or 'Job'
    if status == 'error':
        return send('%s — failed' % head, detail or 'See the job banner for the error.')
    return send('%s — done' % head, detail or 'Finished in %ds.' % int(seconds))
