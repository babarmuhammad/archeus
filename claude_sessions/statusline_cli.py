"""Claude Code `statusLine` command entry point — the rendering lives in
`statusline.py`.

This file exists because of how the statusline used to be installed:

    "<python.exe>" -m claude_sessions statusline

`-m` resolves the package off `sys.path`, and `sys.path[0]` for `-m` is the
CURRENT DIRECTORY. archeus is normally run from a source checkout rather than
installed, so that command found `claude_sessions` only when the session's cwd
happened to BE the checkout. In every other project it exited 1 with
"No module named claude_sessions", printed nothing, and Claude Code drew an
empty statusline — silently, because it swallows the command's failure.

It looked like an account problem for exactly as long as the accounts were
tested in different directories.

The fix is the pattern the seven hook scripts already use: an absolute path to
a real file that bootstraps `sys.path` from its own location, so it works from
any cwd and under any install mode.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions.statusline import main  # noqa: E402


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
