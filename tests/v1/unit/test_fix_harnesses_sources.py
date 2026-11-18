"""Regression tests for hostile-audit findings on archeus/harnesses/sources.py."""

import os

from archeus.harnesses import sources


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def test_a_file_that_is_not_a_regular_file_is_not_read():
    assert sources._read(os.devnull) == (None, 'not a regular file')


def test_a_file_over_the_read_limit_is_not_read(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, 'MAX_READ', 10)
    f = str(tmp_path / 'CLAUDE.md')
    _write(f, 'x' * 11)
    assert sources._read(f) == (None, 'too large')
    _write(f, 'x' * 10)
    assert sources._read(f) == (b'x' * 10, None)


def test_the_mcp_config_with_server_secrets_is_written_owner_only(tmp_path, monkeypatch):
    modes = []
    monkeypatch.setattr(sources.config, 'write_atomic',
                        lambda path, text, mode=None: modes.append(mode) or True)
    sources.flag_argv({'setting_sources': [], 'mcp_servers': [{'owner': 'project', 'name': 'a'}],
                       'disable_slash_commands': True, 'plugin_dirs': []},
                      home=None, workdir=str(tmp_path), exec_dir=str(tmp_path))
    assert modes == [0o600]
