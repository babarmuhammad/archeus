"""Gap tests for archeus/core/execution/canonical.py lines 470-930 (T-703).

Every test here names, in its docstring, the branch of the command classifier it
exists to protect, and each one fails when that branch is removed or inverted.
The existing suite (``tests/v1/unit/test_execution_units.py``) walks a table of
happy-path commands and a list of obviously-dangerous ones; it never reads the
git launcher rules, ``find``'s ``-exec`` rule, the carrier and ``-o`` rules, the
payload families beyond ``bash -c``-style calls, the send-flag spellings, or the
chip-host refusal and redaction. A classifier that skipped every one of those
rules and classified the calls by the plain table would have passed the old
suite unchanged. Those are the branches covered here.

Style and fixtures follow ``tests/v1/unit/test_execution_units.py`` (the module's
own unit file) and ``tests/v1/unit/test_gaps_core_execution_command_allowlist.py``
(the sibling gaps file). Everything is platform-neutral: no OS call, no process,
no filesystem, no network, no reliance on case-insensitive names, no ``?`` or
``:`` in any name the test asserts as a path, and no assertion that a POSIX
absolute path is absolute (the POSIX-looking words below are classifier inputs,
never touched by the OS). The private helpers ``_pwsh_word`` and ``clear_host``
are used at their own seams for the exception lists and the length boundaries a
real command string cannot isolate on its own
(``pwsh -ExecutionPolicy`` is held anyway by the
later option-name rule, so the ``PWSH_NOT_CODE`` exception is invisible through
``command``).
"""
import os

import pytest

from archeus.core.execution import canonical as C

WD = os.path.abspath('workspace-root')
CTX = {'workdir': WD, 'branch': 'archeus/m/t', 'remotes': {'origin': 'github.com'}}


def classified(cmd):
    """The actions of *cmd*, asserting the classifier classified it."""
    actions, unclassified = C.command(cmd, dict(CTX))
    assert unclassified is False, (cmd, 'must classify', [(a.action_class, a.target)
                                                          for a in actions])
    return actions


def refuses(cmd, target):
    """The unclassified exec *cmd* must produce, asserting it refused *target*."""
    actions, unclassified = C.command(cmd, dict(CTX))
    assert unclassified is True, (cmd, 'must refuse', [(a.action_class, a.target)
                                                       for a in actions])
    assert [a.action_class for a in actions] == ['exec'], (cmd, actions)
    assert actions[0].target == target, (cmd, actions[0].target)
    return actions


# ── git: the subcommands that run a program are refused ──────────────────────

def test_git_rebase_that_runs_a_command_is_refused():
    """canonical.py:838 (`_git_actions`): `rebase` with `-x`, a clustered `-ix`
    or `--exec` (by any abbreviation) returns None, and :828-830 turns that into
    one unclassified exec. Removing the line leaves `git rebase -ix vim main`
    classified as a plain `write_repo` (the `GIT_WRITE` row it also is), exactly
    the wrong-permissive direction; the control pins that the plain rebase stays
    classified."""
    refuses('git rebase -ix vim main', 'git')
    refuses('git rebase --exec vim main', 'git')
    refuses('git rebase --ex vim main', 'git')
    (action,) = classified('git rebase main')
    assert (action.action_class, action.target) == ('write_repo', 'git rebase')


def test_git_config_key_that_names_a_command_is_refused():
    """canonical.py:840: `config` with a key containing a word of
    ``_GIT_CONFIG_RUNS`` returns None -> unclassified; the *value* is never
    judged. Removing the line classifies `git config alias.lol ...` as
    `write_repo` (the `GIT_WRITE` row for `config`), so an alias that runs a
    command would sail through as a plain write; the control pins a key that
    names no command stays classified."""
    refuses('git config alias.lol log', 'git')
    refuses('git config core.pager cat', 'git')
    (action,) = classified('git config user.name qwen')
    assert (action.action_class, action.target) == ('write_repo', 'git config')


@pytest.mark.parametrize('cmd', [
    pytest.param('git clone --upload-pack /tmp/tool https://host.example/repo', id='upload-pack'),
    pytest.param('git clone --upload-p /tmp/tool https://host.example/repo', id='abbrev'),
    pytest.param('git push --receive-pack evil origin main', id='receive-pack'),
    pytest.param('git pull origin ext::foo', id='ext-colon'),
    pytest.param('git clone -u /bin/tool repo', id='clone-u'),
    pytest.param('git clone -c protocol.foo=1 https://host.example/repo', id='c-key'),
])
def test_git_fetch_subcommands_that_run_a_command_are_refused(cmd):
    """canonical.py:842 dispatches to :782-800 (`_fetch_runs`): a config key of
    the list given with `-c` (:789-795), `--upload-pack`/`--receive-pack`/
    `--exec` by any abbreviation, an `ext::` word or clone's `-u` (:796-798)
    return None -> unclassified. Removing them classifies these as `web` or
    `write_repo` (clone/fetch/ls-remote are web, pull is write_repo): a command
    run by git judged as a page fetch. The control pins an ordinary clone stays
    classified."""
    refuses(cmd, 'git')


def test_git_clone_without_a_launcher_is_classified_as_web():
    """canonical.py:870-876 (`_git_actions`): a clone with no launcher names its
    remote, its host and the chip host. This is the control that keeps
    :842 (`_fetch_runs`) from being a blanket hold: inverting it to always
    True makes it fail, as does any rule that refuses every clone."""
    (action,) = classified('git clone https://host.example/repo')
    assert (action.action_class, action.target) == ('web', 'https://host.example/repo')
    assert (action.host, action.chip_host) == ('host.example', 'host.example')


def test_git_global_options_are_skipped_with_their_value_and_unknown_ones_refuse():
    """canonical.py:802-824 (`_git_split`): the value options are skipped with
    their value (:813-814), the `=` spelling names its option (:815-816), an
    unknown single word is refused (:819-820) and a bare `--exec-path` is
    refused because its possible value must never be read as the subcommand
    (:817-820 with the `=`-spelling guard at :815-816). Skip `i += 2` and
    `git -C dir log` wrongly turns unclassified; accept the unknown word and
    `git --weird log` (or the value-taking `--exec-path` bare form) is classified
    off a subcommand the classifier never saw."""
    (action,) = classified('git -C dir log')
    assert (action.action_class, action.target) == ('read', 'git log')
    (action,) = classified('git --git-dir=/x log')
    assert (action.action_class, action.target) == ('read', 'git log')
    (action,) = classified('git --exec-path=/x log')
    assert (action.action_class, action.target) == ('read', 'git log')
    refuses('git --weird log', 'git')
    refuses('git --exec-path /x log', 'git')


@pytest.mark.parametrize('cmd', [
    pytest.param('git -c core.pager=evil log', id='dash-c'),
    pytest.param('git --config-env foo log', id='config-env'),
])
def test_git_config_options_are_never_skipped_with_a_value(cmd):
    """canonical.py:811-812 (`_git_split`): `-c` and `--config-env` are never
    skipped with their value, so the config word can never become the
    subcommand. Today the generic unknown-option rule (:819) refuses them too,
    but any code that moves `-c` into ``_GIT_VALUE`` (the natural "GNU-style
    long options" refactor) would skip the config, read `log` as the subcommand
    and classify a command-running call as `read`; these tests fail there."""
    refuses(cmd, 'git')


# ── find: the programs it runs ───────────────────────────────────────────────

def test_find_executing_rm_is_destructive_and_anything_else_is_refused():
    """canonical.py:899-906 (`_find`): the word after `-exec`, `-execdir`,
    `-ok` or `-okdir` decides everything (:899). A program that is not `rm` is
    an unseen payload: unclassified (:900-901) — invert or remove that line and
    `find . -exec chmod 644 f \\;` comes back `destructive` (a guess the rule
    forbids). `rm` after them, or `-delete`, is destructive (:902-904) — remove
    it and they come back `read`, the wrong-permissive direction. A dangling
    `-exec` with no word after it takes the :899 `else ''` and is refused. The
    plain find stays `read`."""
    refuses('find . -exec chmod 644 f \\;', 'find')
    refuses('find . -ok chown root f \\;', 'find')
    refuses('find . -exec', 'find')
    for cmd in ('find . -exec rm {} \\;', 'find . -execdir rm {} \\;'):
        (action,) = classified(cmd)
        assert (action.action_class, action.target) == ('destructive', 'find'), cmd
        assert action.paths[0] == '.' and 'rm' in action.paths, cmd
    (action,) = classified('find . -name x')
    assert (action.action_class, action.target) == ('read', 'find')


# ── options and carriers that name a program to run ──────────────────────────

@pytest.mark.parametrize('cmd,target', [
    pytest.param('rg --pre tool file.txt', 'rg', id='rg-pre'),
    pytest.param('rg --pr""e tool file.txt', 'rg', id='glued-quote'),
    pytest.param('sort --compress-program=zip f', 'sort', id='compress-program'),
    pytest.param('tar -I mytool -cf a.tar d', 'tar', id='tar-I'),
    pytest.param('tar cIf mytool a.tar d', 'tar', id='tar-bundle'),
    pytest.param('tar --checkpoint-action=x -cf a.tar d', 'tar', id='checkpoint-action'),
    pytest.param('wget --use-askpass myask http://host.example/x', 'wget', id='askpass'),
    pytest.param('rsync -av --rsh=myssh sub/ host.example:d', 'rsync', id='rsh'),
    pytest.param('scp -S myprog a.txt user@host.example:x', 'scp', id='scp-S'),
])
def test_options_that_name_a_program_to_run_are_refused(cmd, target):
    """canonical.py:720-721: `any(_gives_a_command(p) for p in _pieces(cmd)[1:]
    + args) or _carries(prog, args)` -> unclassified. The `rg --pr""e` case is
    the `+ args` half of the call site (shlex glues the quoted word: dropping
    the args list lets it classify as `read`, since `rg` is a READ_COMMAND);
    the tar/-I, bundle, checkpoint-action, wget --use-askpass, --rsh and scp -S
    cases are `_carries` (:258-272, its long names held by any abbreviation via
    `_abbrev` :236-241). Removing the call site turns every one of these into the class
    the plain table gives the program (`read` for rg and sort, `exec` for tar).
    `--checkpoint` itself is the held boundary: it stays classified."""
    refuses(cmd, target)
    (action,) = classified('rg -n x file.txt')
    assert (action.action_class, action.target) == ('read', 'rg')
    (action,) = classified('tar -cf a.tar d')
    assert (action.action_class, action.target) == ('exec', 'tar')
    (action,) = classified('tar --checkpoint 10 -cf a.tar d')
    assert (action.action_class, action.target) == ('exec', 'tar')


# ── ssh -o and the REMOTE family-name rule ───────────────────────────────────

def test_ssh_option_that_names_a_command_is_refused():
    """canonical.py:722-723 with `_o_runs` (:245-255): a `-o` alone, in a
    cluster or glued, whose value's first word is `Match` or names a command
    (:252-254) -> unclassified. The clustered `-vo Match host.example` is the
    probe only this branch covers: no other word of it is a command word, so
    removing the `_o_runs` call classifies the call as `external_comm` (the
    REMOTE row) — a remote shell that runs a chosen program judged as a plain
    remote call. The control pins an ordinary `-o` stays classified with its
    host."""
    refuses('ssh -vo Match host.example', 'ssh')
    refuses('ssh -o Match host.example', 'ssh')
    refuses('ssh -oLocalCommand=tool host.example', 'ssh')
    (action,) = classified('ssh -o StrictHostKeyChecking=no user@host.example')
    assert (action.action_class, action.target, action.host) == ('external_comm', 'ssh',
                                                                  'host.example')


def test_remote_given_a_family_name_as_an_argument_is_refused():
    """canonical.py:743-747 (`_family(_norm(n)) for p in _pieces(cmd)[1:] ...`):
    a program of the REMOTE table given a shell or interpreter name quotes it,
    so the call is unclassified. Remove the check and `ssh host.example python`
    is classified `external_comm` while the remote shell runs whatever python
    names. The controls pin ordinary remote calls stay classified and keep the
    host of their destination."""
    refuses('ssh host.example python', 'ssh')
    (action,) = classified('scp a.txt user@host.example:x')
    assert (action.action_class, action.target, action.host) == ('external_comm', 'scp',
                                                                  'host.example')
    (action,) = classified('rsync -av sub/ host.example:d')
    assert (action.action_class, action.target, action.host) == ('external_comm', 'rsync',
                                                                  'host.example')


# ── pagers and man ───────────────────────────────────────────────────────────

def test_pager_launches_that_run_a_command_are_refused():
    """canonical.py:724-728: an argument starting with `+` or holding `!` for a
    pager, or `-P` for man -> unclassified. `less` is a READ_COMMANDS member, so
    removing the line classifies `less +F notes.txt` as `read` while the pager
    runs its `+`/`!` command at startup — wrong-permissive. `less "x!y"` keeps
    the `!` inside quotes so the earlier operator rule cannot be what refuses
    it; only this line can. The control pins the plain pager stays `read`."""
    refuses('less +F notes.txt', 'less')
    refuses('less "x!y"', 'less')
    refuses('man -P less notes', 'man')
    (action,) = classified('less notes.txt')
    assert (action.action_class, action.target) == ('read', 'less')


# ── a program outside the tables given a command word ────────────────────────

def test_unknown_program_given_a_command_word_is_refused():
    """canonical.py:759-761: `_names_command(_pieces(cmd)[1:] + args words)` or
    `_glob_names_command` on any argument -> unclassified; otherwise the call
    is a plain `exec` over the workspace (:761). Removing the check classifies
    `gtimeout 5 rm -R build` and `docker run alpine echo x` as `exec` with
    paths `('.',)` — a recursive delete the classifier waved through because
    the launcher's name is not in the tables. The glob form `mytool b?sh x` is
    the `_glob_names_command` half (:203-210): the shell may expand it to a
    shell. The controls pin launchers of ordinary arguments stay classified."""
    refuses('gtimeout 5 rm -R build', 'gtimeout')
    refuses('docker run alpine echo x', 'docker')
    refuses('mytool b?sh x', 'mytool')
    for cmd in ('gtimeout 5 pytest -q', 'mytool data.csv'):
        (action,) = classified(cmd)
        assert action.action_class == 'exec' and action.paths == ('.',), cmd


# ── payload families (the section's own rules) ───────────────────────────────

@pytest.mark.parametrize('cmd,target', [
    pytest.param('sed 1e date f', 'sed', id='sed-e-command'),
    pytest.param("sed -e'e x' f", 'sed', id='sed-glued-option'),
    pytest.param('sed s/a/b/e x', 'sed', id='sed-s-flag'),
    pytest.param('pwsh -cGet-Process', 'pwsh', id='pwsh-glued'),
    pytest.param('pwsh \u2013cRemove-Item', 'pwsh', id='en-dash'),
    pytest.param('cmd /cCopy a b', 'cmd', id='cmd-glued'),
    pytest.param('node --import data:text/plain,x app.js', 'node', id='node-data-url'),
    pytest.param('gawk {print} f', 'gawk', id='code-family'),
])
def test_payload_families_refuse_a_call_that_carries_code(cmd, target):
    """canonical.py:703 (`any(_payload(f, args) ...)`) into :567-597: the code
    family is held whole (:572-573, the gawk case — every name ending `awk`);
    sed holds its `e` command and `s///e` flag, also glued to `-e` (:574-575,
    `_SED_CODE`/`_SED_OPTION`); cmd holds `/c` `/k` `/r` anywhere in any case,
    glued after another switch included (:582-584); pwsh holds a word whose
    first letter is c or e, with the en-dash switch prefix (:585-586 and
    :556-564); node holds a module hook given as a data: URL (:579-581). Removing
    Removing each branch classifies these as `exec` (or, for cmd/pwsh/gawk,
    whatever the table gives an unknown name) instead of refusing them. The
    controls pin the same programs without code staying classified."""
    refuses(cmd, target)
    for control, control_target in (('sed -n 3p out.txt', 'sed'), ('sed -n s/1/2/gr f', 'sed'),
                                    ('pwsh -NoLogo', 'pwsh'), ('cmd /Q /ON', 'cmd'),
                                    ('node --import hooks.cjs app.js', 'node'),
                                    ('node data:text/plain,x app.js', 'node')):
        (action,) = classified(control)
        assert action.action_class == 'exec' and action.target == control_target, control


def test_pwsh_two_parameters_that_carry_no_code_are_the_exception():
    """canonical.py:556-564 (`_pwsh_word`): the first letter of the switch word
    decides, since every pwsh parameter starting with c or e takes code — except
    the two in ``PWSH_NOT_CODE`` (:480). Through `command` this exception is
    invisible (`-ExecutionPolicy` is held later by the option-name rule at
    :720), so the rule is read at its own seam: a word starting with c or e that
    is not one of the two holds (:562-564), an ordinary parameter does not, and
    the switch prefix may be an en dash (:561 with `_SWITCH_DASHES` :553).
    Removing the `PWSH_NOT_CODE` guard or the dash set makes this fail."""
    assert C._pwsh_word('-cRemove-Item') is True
    assert C._pwsh_word('-eFile') is True
    assert C._pwsh_word('\u2013cfoo') is True
    assert C._pwsh_word('/cfoo') is True
    assert C._pwsh_word('-ExecutionPolicy') is False
    assert C._pwsh_word('-ConfigurationName') is False
    assert C._pwsh_word('-NoLogo') is False
    assert C._pwsh_word('-ENCx') is True


# ── the send flags: every spelling ───────────────────────────────────────────

@pytest.mark.parametrize('cmd', [
    pytest.param('curl -dfoo=1 https://host.example/x', id='attached-d'),
    pytest.param('curl -XPOST https://host.example/x', id='attached-X'),
    pytest.param('curl -X PUT https://host.example/x', id='next-word-X'),
    pytest.param('curl --data-urlencode a https://host.example/x', id='data-long'),
    pytest.param('curl -T upload.bin https://host.example/x', id='attached-T'),
    pytest.param('curl --upload-file up.bin https://host.example/x', id='upload-file'),
    pytest.param('curl --json {} https://host.example/x', id='json'),
])
def test_a_call_that_sends_a_body_is_external_comm(cmd):
    """canonical.py:741 (`'external_comm' if _sends(args) else 'web'`) into
    :600-614: the long names and prefixes (:605-606), `-X` with the method as
    the next word (:607-610), an attached `-XMETHOD` (:611-612) and an attached
    `-d`/`-F`/`-T` (:613-614) all send. Losing a branch turns that spelling
    into `web` — the wrong-permissive direction a send would slip through on.
    `{}` alone is not a brace word (:508 `_BRACE`), so the json case must hold
    too."""
    (action,) = classified(cmd)
    assert action.action_class == 'external_comm', (cmd, action.action_class)


@pytest.mark.parametrize('cmd', [
    pytest.param('curl -X GET https://host.example/x', id='GET'),
    pytest.param('curl -XGET https://host.example/x', id='attached-GET'),
    pytest.param('curl -X', id='dangling-X'),
])
def test_a_get_is_never_a_send(cmd):
    """canonical.py:607-612: `-X`/`--request` send only with a method other
    than GET — attached (`-XGET`, :611) or as the next word (:608), and `-X`
    as the very last word defaults to GET (:608, `else 'GET'`). Inverting the
    GET comparison or dropping the default turns these reads into
    `external_comm` and this test fails."""
    (action,) = classified(cmd)
    assert action.action_class == 'web', (cmd, action.action_class)


# ── the chip host: what it may name and what it must redact ──────────────────

def test_the_chip_names_only_the_one_url_that_says_its_scheme():
    """canonical.py:742 (`chip_host=clear_host(_url_arg(prog, args))`) into
    :626-655. A single plain URL names the chip host (:655, :649-651); two
    URLs name none (:655, `len(urls) == 1`); the value of a listed flag is not
    a positional at all (:645-647, `--proxy https://...` leaves no url); a URL
    right after a flag that may take a value is none either (:649-651
    `maybe_value`, then :655 `not urls[0][1]`); a header flag's quoted value
    does not contaminate the pick (the `-H` case). The last pair is P21 D6:
    the *policy* host stays the first build's pick (a dotted word, `upload.bin`
    below) while the chip names only the scheme-spelling URL — removing the
    chip rule or letting a decoy through fails here."""
    (action,) = classified('curl https://host.example/x')
    assert action.chip_host == 'host.example'
    (action,) = classified('curl https://a.example/1 https://b.example/2')
    assert action.chip_host is None
    (action,) = classified('curl --proxy https://p.example/x')
    assert (action.host, action.chip_host) == ('p.example', None)
    (action,) = classified('curl --socks5 https://p.example/x')
    assert action.chip_host is None
    (action,) = classified('curl -H "Accept: text/plain" https://host.example/x')
    assert (action.action_class, action.chip_host) == ('web', 'host.example')
    (action,) = classified('curl -T upload.bin https://host.example/x')
    assert (action.action_class, action.target, action.host) == ('external_comm',
                                                                  'upload.bin', 'upload.bin')
    assert action.chip_host == 'host.example'


@pytest.mark.parametrize('url,want', [
    pytest.param('https://host.example/x', 'host.example', id='plain'),
    pytest.param('https://User:pw@Host.Example:8080/a?b=c#d', 'host.example', id='userinfo-port'),
    pytest.param('https://' + 'a' * 20 + '.example/x', 'a' * 20 + '.example', id='len-20'),
    pytest.param('https://' + 'a' * 21 + '.example/x', '\u2026.example', id='len-21'),
    pytest.param('https://a1234.example/x', '\u2026.example', id='letter-digit-5'),
    pytest.param('https://a123.example/x', 'a123.example', id='letter-digit-4'),
    pytest.param('https://1234567.example/x', '\u2026.example', id='digits-7'),
    pytest.param('https://123456.example/x', '123456.example', id='digits-6'),
    pytest.param('https://host_name.example/x', None, id='bad-char'),
    pytest.param('example.com', None, id='no-scheme'),
    pytest.param('', None, id='empty'),
    pytest.param('//plain.example/x', 'plain.example', id='scheme-relative'),
])
def test_clear_host_refuses_what_it_cannot_name_and_redacts_what_it_may(url, want):
    """canonical.py:658-677: no scheme, or none at all, is not nameable
    (:662-663); a host that is not letters, digits, dots and dashes is refused
    (:664-666, `_HOST`); and a label that can carry a secret — over 20
    characters, a letter and a digit over 4, or all digits over 6 (:670-677) —
    becomes an ellipsis while the plain words stay (:667). The userinfo and
    port of the userinfo-port case must not reach the string at all (host_of
    strips them, :664). Flipping any comparison or dropping the ellipsis join
    fails this test."""
    assert C.clear_host(url) == want
