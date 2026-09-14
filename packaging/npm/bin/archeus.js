#!/usr/bin/env node
/**
 * `npx archeus` — run archeus, installing it first if it is not there yet.
 *
 * archeus is a Python program, and this package exists because its users are
 * already holding npm: Claude Code itself is installed with it. So the one
 * thing worth shipping here is the step that is otherwise manual — find it, and
 * if it is missing work out which Python is on this machine and hand the
 * install to pipx or pip.
 *
 * Four rules, each because the opposite is worse:
 *
 *   A missing COMMAND is not a missing PACKAGE, and on Windows that is the
 *   common case rather than an edge: pip puts `archeus.exe` in a Scripts
 *   directory that is frequently not on PATH, so the tool is installed and
 *   unreachable. Measured on the machine this was written on. So before
 *   installing anything, ask a Python whether it can already import it, and if
 *   it can, run it as a module — `npx archeus` works, and the PATH note is
 *   advice rather than a dead end.
 *
 *   It never installs silently. The exact command is printed before it runs,
 *   because `npx <thing>` should not put software on a machine without saying
 *   what and how — and because the user needs that line anyway when it fails.
 *
 *   It prefers pipx. archeus is an application, not a library: pipx gives it
 *   its own environment and a command on PATH, which is the shape the Python
 *   packaging docs recommend. pip --user is the fallback, and an already-active
 *   virtualenv takes precedence over both, because a --user install from inside
 *   one lands outside it and shadows confusingly.
 *
 *   It execs rather than wraps. Once archeus is reachable this process passes
 *   argv through with stdio inherited and exits on its code — the TUI reads
 *   keys and draws with ANSI, so anything that buffers or rewrites the streams
 *   breaks it.
 */
'use strict';

const { spawnSync } = require('child_process');
const WINDOWS = process.platform === 'win32';

/** Run a command, capturing stdout. Returns null when it fails or cannot start. */
function capture(cmd, args) {
  const r = spawnSync(cmd, args, { encoding: 'utf8', shell: false });
  return r.error || r.status !== 0 ? null : (r.stdout || '').trim();
}

function onPath(cmd) {
  return capture(WINDOWS ? 'where' : 'which', [cmd]) !== null;
}

/**
 * The Python to use, as {cmd, pre}, or null.
 *
 * `py -3` first on Windows: the launcher is what a python.org install puts on
 * PATH, and it resolves a real interpreter where a bare `python` may be the
 * Microsoft Store stub that only opens the Store. Everywhere else `python3`
 * comes before `python`, which on an old machine can still be 2.7.
 */
function findPython() {
  const candidates = WINDOWS
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];
  for (const [cmd, pre] of candidates) {
    const out = capture(cmd, pre.concat(
      ['-c', 'import sys;print("%d.%d" % sys.version_info[:2])']));
    if (!out) continue;
    const [major, minor] = out.split('.').map(Number);
    if (major === 3 && minor >= 10) return { cmd, pre };
  }
  return null;
}

/** Can this Python already import archeus? */
function importable(py) {
  return capture(py.cmd, py.pre.concat(['-c', 'import claude_sessions'])) !== null;
}

/** Where that Python puts console scripts — the directory to add to PATH. */
function scriptsDir(py) {
  return capture(py.cmd, py.pre.concat(
    ['-c', 'import sysconfig;print(sysconfig.get_path("scripts"))'])) || '';
}

function run(cmd, args) {
  process.stderr.write('archeus: ' + [cmd].concat(args).join(' ') + '\n');
  return spawnSync(cmd, args, { stdio: 'inherit', shell: false }).status === 0;
}

function exec(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', shell: false });
  process.exit(r.status === null ? 1 : r.status);
}

function install(py) {
  if (process.env.VIRTUAL_ENV) {
    return run(py.cmd, py.pre.concat(['-m', 'pip', 'install', '-U', 'archeus']));
  }
  if (onPath('pipx')) {
    if (run('pipx', ['install', 'archeus'])) return true;
    process.stderr.write('archeus: pipx failed, falling back to pip --user\n');
  }
  return run(py.cmd, py.pre.concat(['-m', 'pip', 'install', '--user', '-U', 'archeus']));
}

function main() {
  const args = process.argv.slice(2);
  if (onPath('archeus')) exec('archeus', args);

  const py = findPython();
  if (!py) {
    process.stderr.write(
      'archeus needs Python 3.10 or newer, and none was found on this machine.\n' +
      'Install it from https://www.python.org/downloads/ and run this again.\n');
    process.exit(1);
  }

  if (!importable(py)) {
    process.stderr.write('archeus is not installed yet — installing it now.\n');
    if (!install(py)) process.exit(1);
    if (onPath('archeus')) exec('archeus', args);
    if (!importable(py)) process.exit(1);
  }

  // installed, but its command is not on PATH: run it as a module and say how
  // to fix the PATH once, rather than reinstalling something that is already
  // there or failing with a command-not-found nobody can act on.
  const dir = scriptsDir(py);
  process.stderr.write(
    'archeus: the `archeus` command is not on your PATH — running it as a module.\n' +
    (dir ? 'archeus: add this directory to PATH to use it directly: ' + dir + '\n' : ''));
  exec(py.cmd, py.pre.concat(['-m', 'claude_sessions']).concat(args));
}

main();
