"""R2: the guarded Git runner freezes the repository configuration (Windows).

The configuration is held open without write or delete sharing while the guarded
Git call runs, so a key written after the driver enumeration cannot be read by Git.
"""
import os
import subprocess
import sys

import pytest

from archeus.node import local

WINDOWS = pytest.mark.skipif(os.name != 'nt', reason='Windows sharing modes')
ENV = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
ENV.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_AUTHOR_NAME='t',
           GIT_AUTHOR_EMAIL='t@t', GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
REAL_RUN = subprocess.run


def git(root, *args):
    return REAL_RUN(['git', '-C', root, *args], capture_output=True, env=ENV, check=True)


def make_repo(tmp_path):
    root = str(tmp_path / 'repo')
    os.makedirs(root)
    git(root, 'init', '-q')
    return root


def config_path(root):
    return os.path.join(root, '.git', 'config')


def recording(monkeypatch, ran):
    def run(argv, **kw):
        ran.append(list(argv))
        return REAL_RUN(argv, **kw)
    monkeypatch.setattr(local.subprocess, 'run', run)


@WINDOWS
@pytest.mark.parametrize('writer', ['in_place', 'replace', 'delete'])
def test_a_key_written_after_enumeration_is_denied_and_never_runs(tmp_path, monkeypatch, writer):
    root = make_repo(tmp_path)
    marker = (tmp_path / 'marker').as_posix()
    git(root, 'config', 'filter.foo.clean', 'exit 0')
    cfg = config_path(root)
    events = []
    line = '[filter "foo"]\n\tprocess = printf x > %s\n' % marker

    def run(argv, **kw):
        result = REAL_RUN(argv, **kw)
        if 'config' in argv and '--get-regexp' in argv and '--file' not in argv:
            events.append('ENUMERATED')
            # attributes select foo; the writer then adds the process driver
            with open(os.path.join(root, '.git', 'info', 'attributes'), 'w') as f:
                f.write('f.txt filter=foo\n')
            try:
                if writer == 'in_place':
                    with open(cfg, 'a') as f:
                        f.write(line)
                elif writer == 'replace':
                    with open(cfg + '.new', 'w') as f:
                        f.write(open(cfg).read() + line)
                    os.replace(cfg + '.new', cfg)
                else:
                    os.remove(cfg)
                events.append('WRITE_SUCCEEDED')
            except OSError:
                events.append('WRITE_DENIED')
        return result

    monkeypatch.setattr(local.subprocess, 'run', run)
    with open(os.path.join(root, 'f.txt'), 'w') as f:
        f.write('content\n')
    r = local._project_git(root, ['add', '--', 'f.txt'])
    assert events[:2] == ['ENUMERATED', 'WRITE_DENIED']
    assert r is not None and r.returncode == 0
    assert not os.path.exists(marker)


@WINDOWS
def test_the_guarded_command_reads_the_frozen_configuration(tmp_path):
    root = make_repo(tmp_path)
    git(root, 'config', 'user.name', 'kept')
    r = local._project_git(root, ['config', '--get', 'user.name'])
    assert r is not None and r.returncode == 0 and r.stdout.strip() == 'kept'


@WINDOWS
def test_an_include_is_refused_and_no_guarded_command_runs(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    with open(config_path(root), 'a') as f:
        f.write('[include]\n\tpath = other.cfg\n')
    ran = []
    recording(monkeypatch, ran)
    assert local._project_git(root, ['status', '--porcelain']) is None
    assert not any('status' in argv for argv in ran)


@WINDOWS
def test_a_conditional_include_is_refused(tmp_path):
    root = make_repo(tmp_path)
    with open(config_path(root), 'a') as f:
        f.write('[includeIf "gitdir:x/"]\n\tpath = other.cfg\n')
    assert local._project_git(root, ['status', '--porcelain']) is None


@WINDOWS
def test_worktree_config_enabled_but_absent_is_refused(tmp_path):
    root = make_repo(tmp_path)
    git(root, 'config', 'core.repositoryformatversion', '1')
    git(root, 'config', 'extensions.worktreeConfig', 'true')
    assert local._project_git(root, ['status', '--porcelain']) is None


@WINDOWS
def test_an_enabled_worktree_config_is_frozen_and_read(tmp_path):
    root = make_repo(tmp_path)
    git(root, 'config', 'core.repositoryformatversion', '1')
    git(root, 'config', 'extensions.worktreeConfig', 'true')
    wt = os.path.join(root, '.git', 'config.worktree')
    with open(wt, 'w') as f:
        f.write('[core]\n\tbare = false\n')
    assert local._project_git(root, ['status', '--porcelain']) is not None
    with open(wt, 'a') as f:
        f.write('# written after the call\n')


@WINDOWS
def test_a_missing_config_is_refused(tmp_path):
    root = make_repo(tmp_path)
    os.remove(config_path(root))
    assert local._project_git(root, ['status', '--porcelain']) is None


@WINDOWS
def test_a_reparse_component_is_refused(tmp_path):
    real = make_repo(tmp_path)
    link = str(tmp_path / 'link')
    subprocess.run(['cmd', '/c', 'mklink', '/J', link, real], check=True, capture_output=True)
    try:
        assert local._project_git(link, ['status', '--porcelain']) is None
    finally:
        os.rmdir(link)


@WINDOWS
def test_a_failed_handle_acquisition_is_refused_and_launches_nothing(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    ran = []
    recording(monkeypatch, ran)
    with open(config_path(root), 'r+b'):      # a writer already holds the file
        assert local._project_git(root, ['status', '--porcelain']) is None
    assert not any('status' in argv for argv in ran)


@WINDOWS
@pytest.mark.parametrize('how', ['success', 'refusal', 'timeout', 'capped'])
def test_the_handles_are_released_after_every_outcome(tmp_path, monkeypatch, how):
    root = make_repo(tmp_path)
    git(root, 'config', 'user.name', 'kept')
    if how == 'refusal':
        with open(config_path(root), 'a') as f:
            f.write('[include]\n\tpath = other.cfg\n')
        assert local._project_git(root, ['status']) is None
    elif how == 'timeout':
        def run(argv, **kw):
            if 'status' in argv:
                raise subprocess.TimeoutExpired(argv, 1)
            return REAL_RUN(argv, **kw)
        monkeypatch.setattr(local.subprocess, 'run', run)
        assert local._project_git(root, ['status']) is None
    elif how == 'capped':
        assert local._project_git(root, ['status'], max_bytes=4) is not None
    else:
        assert local._project_git(root, ['status']) is not None
    with open(config_path(root), 'a') as f:       # a write succeeds again
        f.write('[x]\n\ty = 1\n')


@WINDOWS
def test_worktree_add_on_head_keeps_the_config(tmp_path):
    root = make_repo(tmp_path)
    git(root, 'commit', '-q', '--allow-empty', '-m', 'base')
    before = open(config_path(root), 'rb').read()
    path = str(tmp_path / 'wt')
    local.LocalNode.add_worktree(root, path, 'archeus/m.t1', base='HEAD')
    assert open(config_path(root), 'rb').read() == before
    assert local.LocalNode.remove_worktree(root, path)


@WINDOWS
def test_another_process_holding_the_config_for_writing_refuses_without_hanging(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    holder = subprocess.Popen(
        [sys.executable, '-c',
         'import sys\nf = open(sys.argv[1], "r+b")\nprint("held", flush=True)\nsys.stdin.readline()',
         config_path(root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == 'held'
        ran = []
        recording(monkeypatch, ran)
        assert local._project_git(root, ['status', '--porcelain']) is None
        assert not any('status' in argv for argv in ran)
    finally:
        holder.communicate('\n', timeout=30)
    assert holder.returncode == 0
    with open(config_path(root), 'a') as f:
        f.write('[x]\n\ty = 1\n')


@pytest.mark.real_config_freeze
def test_an_unsupported_platform_refuses_before_any_repository_git_call(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    monkeypatch.setattr(sys, 'platform', 'linux')
    ran = []
    recording(monkeypatch, ran)
    assert local._project_git(root, ['status', '--porcelain']) is None
    assert all(argv[-1] == 'version' for argv in ran)
    assert local._VERSION, 'Git is below the floor, so the freeze was never reached'


@pytest.mark.real_config_freeze
@pytest.mark.skipif(sys.platform == 'win32', reason='Windows takes the freeze')
def test_off_windows_the_real_guard_refuses_the_repository_call(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    ran = []
    recording(monkeypatch, ran)
    assert local._project_git(root, ['status', '--porcelain']) is None
    assert all(argv[-1] == 'version' for argv in ran)
    assert local._VERSION, 'Git is below the floor, so the freeze was never reached'


@WINDOWS
def test_the_freeze_seam_is_inactive_on_windows():
    assert not getattr(local._frozen_config, '_seam', False)
