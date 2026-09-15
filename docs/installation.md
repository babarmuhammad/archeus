---
description: >-
  Install archeus with pipx or pip, run it from a checkout, add it to a Claude Code
  session as a plugin, and set up the desktop app window and shortcuts.
---

# Installation

## Requirements

- Python 3.10+
- Windows, macOS or Linux
- [Claude Code CLI](https://docs.anthropic.com/claude-code) installed (auto-detected at `~/.local/bin/` or on PATH; overridable in Settings)
- Any text editor — Notepad++ / VS Code / `$EDITOR` are auto-detected (overridable in Settings)

No API key: archeus uses the Claude Code authentication you already have. No third-party
packages — it is pure Python standard library.

## Coming from claudectl

archeus is the same project under a new name. Everything you have is kept.

**The one-line upgrade**, if `claudectl` is all you have installed:

```
pip install -U claudectl        # or: pipx upgrade claudectl
archeus
```

`claudectl 1.9.2` ships no code — it exists only to depend on archeus, so
upgrading it installs archeus and keeps the `claudectl` command working.

**If you already have both installed, uninstall the old one first, then install
the new one — in that order.**

```
pipx uninstall claudectl && pipx install archeus     # or the pip equivalents
archeus
```

The order matters and the reason is not obvious: both packages ship the same
internal module, so installing archeus on top of claudectl overwrites those
files and leaves *both* claiming to own them. `pip uninstall claudectl` then
deletes them, and archeus stops working while still showing up as installed.
If you have already done it in that order, the repair is one line:

```
pip uninstall claudectl && pip install --force-reinstall archeus
```

archeus warns you about this on startup whenever it finds both installed.

**What moves, the first time you run `archeus`:** your settings and accounts,
per-project launch defaults, the stats/model/version caches, your agent and
skill libraries, and every project's `.claudectl/` — its memory graph,
snapshots, plans and logs — become their `archeus` equivalents. Nothing is
deleted, nothing is overwritten, and a step that fails is retried on the next
start rather than skipped. It runs once and reports what it did.

**Hooks and the statusline need nothing from you.** They record a path to a
script rather than the command name, so an in-place upgrade leaves them
working. If the environment they point at goes away — pipx builds a new one,
you move or re-clone a checkout, you rebuild a venv — archeus re-points them at
the current install on its next start, every start, not only during the
migration. Only a path that no longer exists *and* names one of its own scripts
is ever rewritten; anything you wrote by hand is left alone.

**Two things it reports rather than fixes**, because neither is archeus's to
edit: environment variables you set under the old name (`CLAUDECTL_*` are
`ARCHEUS_*` now and the old spellings are read nowhere), and the Claude Code
plugin, whose id moved with everything else:

```
/plugin uninstall claudectl@claudectl
/plugin marketplace add babarmuhammad/archeus
/plugin install archeus@archeus
```

**Your `CLAUDE.md` files are tidied once.** The memory, agent-routing and loop
blocks are marked with sentinel comments carrying the old name; a block that has
since been rewritten under the new one is removed, and a block that has not is
renamed in place so the next build updates it instead of appending a second copy
beside it. Your own prose is never touched.

The last release under the old name is `claudectl 1.9.2`.

## Setup

### Installing it as a command

```
pipx install archeus     # or: pip install archeus
archeus
```

That gives you `archeus`, `archeus --gui`, `archeus review`,
`archeus recall "<topic>"` and `archeus statusline` from anywhere.

### Without installing it first

```
npx archeus
```

You already have npm if you installed Claude Code with it. The npm package is a
launcher, not a copy of the tool: it runs archeus if it can find it, and if it
cannot, it prints the exact install command and hands it to pipx (or pip, inside
a virtualenv or when pipx is missing) before running it. On Windows it also
covers the common case where pip has installed archeus but its `Scripts`
directory is not on your PATH — it runs it as a module and tells you which
directory to add.

### The name on other registries

archeus is a Python package. PyPI carries it, npm carries the launcher above,
and the entries on [RubyGems](https://rubygems.org/gems/archeus), crates.io and
NuGet are there to keep the name pointing at this project — each one prints the
`pipx install archeus` line and exits non-zero rather than pretending to have
installed anything.

### Clone and run

```
git clone https://github.com/babarmuhammad/archeus.git
cd archeus
python claude-sessions.py
```

There is nothing to build and no dependencies to install. On Windows you can double-click
`Open Repo cmd.bat` instead of using a terminal.

To put the command on your PATH from a checkout — for development, or to run an unreleased
change:

```
pip install -e .        # or: pipx install .
```

### Inside a Claude Code session

archeus also ships as a Claude Code plugin, which puts its three slash commands and its
eight skills inside the session itself:

```
/plugin marketplace add babarmuhammad/archeus
/plugin install archeus@archeus
```

It is independent of the CLI install, and it deliberately ships no hooks. See
[Claude Code plugin](plugin.md).

### GUI setup

The [desktop app](desktop.md) needs no extra dependencies for the Edge/browser shells. For the
native window install PyQt6 (optional):

```
pip install PyQt6 PyQt6-WebEngine
```

Start it with:

```
python claude-sessions.py --gui   # from the checkout
archeus --gui                   # after `pip install -e .`
```

`gui_shell` in Settings picks the window: `auto` (Qt → Edge app window → browser), `qt`,
`edge`, or `browser`. The bottom-left **TUI/GUI** toggle (or the `ui_mode` setting) selects
which interface starts by default; `--tui` / `--gui` always override.

**Desktop shortcut for the GUI** — `pythonw.exe` runs it without a console window.
`archeus.ico` is the icon for every surface (rebuild it with `py tools/make_icon.py`,
which writes it and both site favicons from `docs/assets/logo.png`):

```powershell
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut("$env:USERPROFILE\Desktop\archeus GUI.lnk")
$lnk.TargetPath       = "$env:LOCALAPPDATA\Programs\Python\Python310\pythonw.exe"
$lnk.Arguments        = "`"$PWD\claude-sessions.py`" --gui"
$lnk.WorkingDirectory = "$PWD"
$lnk.IconLocation     = "$PWD\claude_sessions\archeus.ico, 0"
$lnk.Save()
```

## Windows shortcuts & taskbar pin

??? note "Desktop shortcut, taskbar pin and elevated launch"

    **Desktop shortcut** — right-click `Open Repo cmd.bat` → **Send to** →
    **Desktop (create shortcut)**.

    **Pin to taskbar (Windows 11)** — Windows 11 can't pin `.bat` shortcuts directly; the
    shortcut must point to `cmd.exe`. Run this once in PowerShell from the repo folder:

    ```powershell
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut("$env:USERPROFILE\Desktop\Open Repo Claude.lnk")
    $lnk.TargetPath       = "C:\Windows\System32\cmd.exe"
    $lnk.Arguments        = "/c `"$PWD\Open Repo cmd.bat`""
    $lnk.WorkingDirectory = "$PWD"
    $lnk.IconLocation     = "$PWD\claude_sessions\archeus.ico, 0"
    $lnk.Save()
    ```

    Then right-click the Desktop shortcut → **Pin to taskbar**.

    **Elevated shortcut, no repeated UAC prompt** — if `claude.exe` or your project paths
    need admin rights, a plain "Run as administrator" shortcut checkbox triggers a UAC
    prompt on every launch. To elevate once and skip the prompt afterward, register a
    Scheduled Task that already runs at highest privilege, then point the shortcut at
    `schtasks /run`:

    ```powershell
    # 1) register the task (one-time)
    $action    = New-ScheduledTaskAction -Execute "C:\Users\<you>\AppData\Local\Microsoft\WindowsApps\wt.exe" -Argument '-d "<repo>" powershell -Command "& ''<repo>\Open Repo cmd.bat''"' -WorkingDirectory "<repo>"
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -RunLevel Highest -LogonType Interactive
    $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName "Archeus" -Action $action -Principal $principal -Settings $settings -Force

    # 2) point the shortcut at the task instead of launching directly
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut("$env:USERPROFILE\Desktop\archeus.lnk")
    $lnk.TargetPath       = "C:\Windows\System32\schtasks.exe"
    $lnk.Arguments        = '/run /tn "Archeus"'
    $lnk.WorkingDirectory = "<repo>"
    $lnk.IconLocation     = "<repo>\claude_sessions\archeus.ico, 0"
    $lnk.Save()
    ```

    Leave the shortcut's own **"Run as administrator"** checkbox unticked — `schtasks.exe`
    itself doesn't need to be elevated, only the task it triggers. Launching via `wt.exe`
    (instead of `cmd.exe`/`powershell.exe` directly) also avoids the legacy-conhost fallback
    that elevated console apps can trigger, which otherwise makes the TUI render with broken
    colors/box-drawing under UAC.

## Next steps

- [Quickstart](quickstart.md) — install to first session in five minutes
- [Terminal UI](tui.md) — every screen and every key binding
- [Command line](cli.md) — every command, for scripts and hooks
- [Installing the agent library](agent-library.md) — bulk-install 150+ community subagents
