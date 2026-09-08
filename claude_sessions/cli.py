"""Console-script entry point (`claudectl`) — and the two answers that must
not cost anything: `--help` and `--version`.

Deliberately thin, and the statusline dispatch is deliberately duplicated from
__main__.py rather than shared: importing anything that would let it be shared is
the exact cost this exists to avoid. `main` pulls the whole TUI stack plus
`usage`, which drags in urllib/ssl/http.client for an OAuth poll the statusline
must never make — measured at 66ms of import on a path that runs on every
conversation turn, and the console script was paying it because it pointed
straight at main:run.

`--help` lives HERE for the same reason plus one of its own: it is the first
thing a new install types, and it must neither pay for the TUI stack nor be
breakable by anything in it. This module imports the standard library only.
"""
import sys

HELP = """claudectl {ver}— the workspace layer for Claude Code.

  NOTE  claudectl is now archeus. This is the last release under the old name.
        Install the new one with:  pip install archeus
        Your settings, memory graphs and project state migrate automatically
        the first time archeus runs. Nothing is deleted.

USAGE
  claudectl                  open the workspace UI (TUI unless ui_mode says GUI)
  claudectl --gui | --tui    force the web/desktop GUI, or the terminal UI
  claudectl <command> [...]

COMMANDS
  workspace status           print the current folder's project status — memory
                             freshness, CLAUDE.md, MCP servers, git. No UI, so
                             it is safe to call from a script or a hook.
  recall "<query>"           print the task-relevant slice of this project's
                             memory graph. This is what the recall hook injects
                             into a session, and what CLAUDE.md points Claude at.
  review [--staged | --branch BASE] [--min-confidence N] [PATH]
                             confidence-scored review of the working tree,
                             printed to stdout.
  sync-accounts [--yes | --dry-run]
                             level every configured account up to what you have
                             provisioned (hooks, statusline, settings). Shows
                             the diff before writing anything.
  statusline                 Claude Code's statusLine command: reads one JSON
                             payload on stdin and prints one line. Install it
                             from the Hooks screen rather than wiring it by hand.
  --failover-stop            stop the background model-failover proxy.

OPTIONS
  -h, --help                 this text
  -V, --version              print the installed claudectl version

WHAT YOU GET
  Projects   every folder Claude Code has a session for, across all accounts, in
             one list — launch with a chosen model, effort, permission mode,
             agent set and worktree. Projects you never want to see can be
             hidden from the list (they are not deleted, and come back).
  Memory     a per-project graph of entities, relations and learned lessons in
             <project>/.claudectl/memory, injected through CLAUDE.md and the
             recall hook, so a fresh session starts knowing the project.
  Sessions   browse, resume, fork, rename, tag, export or archive any past
             session; read its transcript, tokens and cost.
  Config     MCP servers, agents, skills, plugins, hooks and output styles —
             per project and globally, per account.
  GUI        the same workspace as a local web app (--gui), bound to 127.0.0.1
             behind a per-run token. Nothing is uploaded anywhere.

FILES
  ~/.claude/claudectl.json      claudectl's own settings (accounts, defaults)
  ~/.claude/                    Claude Code's config dir. CLAUDE_CONFIG_DIR
                                overrides it, and claudectl follows it.
  <project>/.claudectl/memory   that project's memory graph

DOCS   https://docs.claudectl.space/
"""




def _version():
    try:
        from .versions import self_installed
        return self_installed() or ''
    except Exception:
        return ''


def _utf8_stdout():
    """Claude Code (and `| more`) capture stdout as a PIPE, where CPython picks
    the locale codepage — cp1252 on Windows — and an em dash raises. Every
    stdout writer in this codebase does this; see the encoding note in
    CLAUDE.md."""
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def print_help():
    ver = _version()
    _utf8_stdout()
    print(HELP.format(ver=(ver + ' ') if ver else ''))


def print_version():
    _utf8_stdout()
    print(_version() or 'unknown')


def run():
    if len(sys.argv) >= 2 and sys.argv[1] == 'statusline':
        from .statusline import main
        raise SystemExit(main(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] in ('--help', '-h', 'help'):
        print_help()
        return
    if len(sys.argv) >= 2 and sys.argv[1] in ('--version', '-V'):
        print_version()
        return
    from .main import run as _run
    _run()
