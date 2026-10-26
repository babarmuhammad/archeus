"""Builds the V2 Live review package: clients/v2-live (without tests, probes' output and caches), a root start.cmd and README-FIRST.txt.
  py tools\\v2_live_package.py [--out D:\\Archeus\\dist\\Archeus-V2-Live.zip]
Prints the zip path, size and file count. Nothing is read from outside clients/v2-live."""
import argparse
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'clients', 'v2-live')
SKIP_DIRS = {'test', '.pv20-out', '__pycache__', 'node_modules', '.git'}
SKIP_SUFFIX = ('.test.mjs', '.pyc')

START = '@echo off\r\nrem V2 Live: starts a local server for the app and opens the browser. Close the server window to stop it.\r\ncall "%~dp0clients\\v2-live\\start.cmd"\r\n'
FIRST = """Archeus V2 Live
===============

1. Double-click start.cmd. A small server window opens (minimised) and your browser opens
   http://127.0.0.1:8000
   If the browser does not open, type that address in yourself. Python 3 must be installed.
2. Close the server window when you are done.

What this is: a fixture simulation. Every project, mission, approval, usage number and reply is
made up by a scripted clock, and nothing is connected to a Core. Every screen says SIMULATED.
It shows the V2 interface as decided and built so far, on a phone, a tablet, a desktop and a
terminal view (the Device button in the top bar; "All devices" shows them side by side).

Audience: internal review only. Please do not share it outside the team.

Press ? in the app for the keyboard shortcuts. README.md inside clients\\v2-live lists the URL
options, routes and known limits. IT-REVIEW.md lists every Italian string that still needs a
native check.
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=r'D:\Archeus\dist\Archeus-V2-Live.zip')
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    n = 0
    with zipfile.ZipFile(a.out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('start.cmd', START)
        z.writestr('README-FIRST.txt', FIRST.replace('\n', '\r\n'))
        for d, dirs, files in os.walk(APP):
            dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
            for f in sorted(files):
                if f.endswith(SKIP_SUFFIX):
                    continue
                p = os.path.join(d, f)
                z.write(p, os.path.join('clients', 'v2-live', os.path.relpath(p, APP)).replace('\\', '/'))
                n += 1
    print('%s  %d bytes  %d app files + start.cmd + README-FIRST.txt' % (a.out, os.path.getsize(a.out), n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
