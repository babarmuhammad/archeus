"""T-1273: claude_sessions/conventions.py:177-256 at 6bbd3b44 (managed CONVENTIONS block preserves manual text).

Selected probes, denial first, then boundaries, then error paths:
223 conventions_to_global=False reads, creates and writes nothing (test_sync_disabled_touches_no_file)
233 reversed markers do not duplicate prose (test_reversed_markers_do_not_duplicate_manual_text, strict xfail)
230 unreadable existing file is not replaced by an empty one (test_unreadable_file_is_not_overwritten, strict xfail)
245 valid block replaced, manual prefix/suffix and other blocks kept (test_valid_block_replaced_around_manual_text)
238 empty body removes only the owned block (test_empty_body_removes_only_owned_block)
246 missing owned block appended, unterminated marker kept (test_missing_owned_block_appends_without_erasing_manual_text)
246 duplicate owned blocks do not swallow prose (test_duplicate_owned_blocks_keep_surrounding_prose)
250 identical block returns True without write (test_identical_block_returns_true_without_write, strict xfail)
245 re-sync of a block is a fixed point (test_resync_of_block_followed_by_text_is_a_fixed_point, strict xfail)
253 failed write returns False and logs (test_failed_write_returns_false_and_leaves_file)
212 MAX_TOKENS exact bound accepted, next item excluded (test_max_tokens_exact_bound_accepted_next_item_excluded)
200-202 pin only eligible lessons, save only touched graphs (test_pin_touches_only_eligible_lessons_and_saves_touched_graphs)
200-202 failed save does not count pins (test_pin_does_not_count_when_save_fails, strict xfail)
"""

import logging
import os

import pytest

from claude_sessions import config, conventions, memory

START = config._CONV_START
END = config._CONV_END
OTHER_S = '<!-- OTHER:START -->'
OTHER_E = '<!-- OTHER:END -->'
OTHER_BLOCK = OTHER_S + '\nOTHER BLOCK\n' + OTHER_E + '\n'
HEADER = '## Conventions (archeus — learned across your projects)'


def _read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def _arrange(monkeypatch, tmp_path, old=None, body='- rule', fail=False):
    target = tmp_path / 'acct' / 'CLAUDE.md'
    target.parent.mkdir(parents=True, exist_ok=True)
    if old is not None:
        with open(target, 'w', encoding='utf-8', newline='') as f:
            f.write(old)
    writes = []

    def fake_write(path, text, mode=None):
        writes.append(text)
        if fail:
            return False
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        return True

    monkeypatch.setattr(config, 'load_settings', lambda: {'conventions_to_global': True})
    monkeypatch.setattr(config, 'global_claude_md_for', lambda cfgdir=None: str(target))
    monkeypatch.setattr(config, 'generated_note', lambda source, how: 'NOTE')
    monkeypatch.setattr(conventions, 'build_block', lambda: body)
    monkeypatch.setattr(config, 'write_atomic', fake_write)
    return str(target), writes


def _section(body):
    return f'{START}\nNOTE\n{body}\n{END}\n'


def test_sync_disabled_touches_no_file(monkeypatch, tmp_path):
    target, writes = _arrange(monkeypatch, tmp_path, old=None)
    monkeypatch.setattr(config, 'load_settings', lambda: {'conventions_to_global': False})
    monkeypatch.setattr(os, 'makedirs', lambda *a, **k: pytest.fail('mkdir'))
    assert conventions.sync_to_global() is False
    assert writes == []
    assert not os.path.exists(target)


def test_reversed_markers_do_not_duplicate_manual_text(monkeypatch, tmp_path):
    old = 'HEAD\n' + END + '\nMIDDLE MUST SURVIVE\n' + START + '\nstale\n'
    target, _writes = _arrange(monkeypatch, tmp_path, old=old, body='- rule')
    conventions.sync_to_global()
    out = _read(target)
    assert out.count('MIDDLE MUST SURVIVE') == 1
    assert out.count('HEAD') == 1


def test_unreadable_file_is_not_overwritten(monkeypatch, tmp_path):
    real_open = open
    target, writes = _arrange(monkeypatch, tmp_path, old='MANUAL TEXT MUST SURVIVE\n')

    def failing_read(path, *args, **kwargs):
        if os.path.abspath(str(path)) == os.path.abspath(target) and 'w' not in (
                args[0] if args else kwargs.get('mode', 'r')):
            raise OSError('cannot read')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', failing_read)
    conventions.sync_to_global()
    monkeypatch.setattr('builtins.open', real_open)
    assert 'MANUAL TEXT MUST SURVIVE' in _read(target)
    assert writes == []


def test_valid_block_replaced_around_manual_text(monkeypatch, tmp_path):
    old = ('PRE PROSE\n' + OTHER_BLOCK + START + '\nold rule\n' + END
           + '\nPOST PROSE\n')
    target, _writes = _arrange(monkeypatch, tmp_path, old=old, body='- new rule')
    assert conventions.sync_to_global() is True
    out = _read(target)
    assert out.startswith('PRE PROSE\n' + OTHER_BLOCK + START + '\nNOTE\n- new rule\n' + END)
    assert out.endswith('\nPOST PROSE\n')
    assert 'old rule' not in out
    assert out.count('PRE PROSE') == 1 and out.count('POST PROSE') == 1
    assert OTHER_BLOCK in out


def test_resync_of_block_followed_by_text_is_a_fixed_point(monkeypatch, tmp_path):
    old = 'PRE PROSE\n' + START + '\nold rule\n' + END + '\nPOST PROSE\n'
    target, _writes = _arrange(monkeypatch, tmp_path, old=old, body='- new rule')
    conventions.sync_to_global()
    first = _read(target)
    conventions.sync_to_global()
    assert _read(target) == first


def test_empty_body_removes_only_owned_block(monkeypatch, tmp_path):
    old = ('PRE PROSE\n' + OTHER_BLOCK + '\n' + START + '\nold rule\n' + END
           + '\nPOST PROSE\n')
    target, _writes = _arrange(monkeypatch, tmp_path, old=old, body='')
    assert conventions.sync_to_global() is True
    out = _read(target)
    assert START not in out and END not in out
    assert OTHER_BLOCK in out
    assert out.count('PRE PROSE') == 1 and out.count('POST PROSE') == 1


def test_missing_owned_block_appends_without_erasing_manual_text(monkeypatch, tmp_path):
    old = 'MANUAL A\n' + START + '\nunterminated tail\n'
    target, _writes = _arrange(monkeypatch, tmp_path, old=old, body='- rule')
    assert conventions.sync_to_global() is True
    out = _read(target)
    assert out.startswith('MANUAL A\n')
    assert 'unterminated tail' in out
    assert out.endswith(_section('- rule'))


def test_duplicate_owned_blocks_keep_surrounding_prose(monkeypatch, tmp_path):
    old = ('A PROSE\n' + START + '\nstale1\n' + END + '\nB PROSE\n'
           + START + '\nstale2\n' + END + '\nC PROSE\n')
    target, _writes = _arrange(monkeypatch, tmp_path, old=old, body='- rule')
    conventions.sync_to_global()
    out = _read(target)
    assert out.count('A PROSE') == 1
    assert out.count('B PROSE') == 1
    assert out.count('C PROSE') == 1
    assert 'stale1' not in out


def test_identical_block_returns_true_without_write(monkeypatch, tmp_path):
    old = 'PRE\n' + _section('- rule')
    target, writes = _arrange(monkeypatch, tmp_path, old=old, body='- rule')
    assert conventions.sync_to_global() is True
    assert writes == []
    assert _read(target) == old


def test_failed_write_returns_false_and_leaves_file(monkeypatch, tmp_path, caplog):
    old = 'MANUAL\n'
    target, writes = _arrange(monkeypatch, tmp_path, old=old, body='- rule', fail=True)
    with caplog.at_level(logging.ERROR):
        assert conventions.sync_to_global() is False
    assert 'conventions: global write failed' in caplog.text
    assert len(writes) == 1
    assert _read(target) == old


def test_max_tokens_exact_bound_accepted_next_item_excluded(monkeypatch):
    monkeypatch.setattr(conventions, 'tokens_estimate', len)
    first_len = conventions.MAX_TOKENS - len(HEADER) - 1
    first = '- ' + 'x' * (first_len - 2)
    assert len(HEADER + '\n' + first) == conventions.MAX_TOKENS
    monkeypatch.setattr(conventions, 'collect_conventions',
                        lambda: [{'text': first[2:]}, {'text': 'y'}])
    assert conventions.build_block() == HEADER + '\n' + first


def _lesson(summary, status='pending', kind='preference', type_='lesson'):
    return {'type': type_, 'kind': kind, 'status': status, 'summary': summary}


TEXT = 'never edit generated files by hand'


def test_pin_touches_only_eligible_lessons_and_saves_touched_graphs(monkeypatch):
    g1 = {'entities': [
        _lesson(TEXT),
        _lesson('unrelated preference about tabs'),
        _lesson(TEXT, kind='error_fix'),
        _lesson(TEXT, status='pinned'),
        _lesson(TEXT, type_='note'),
    ]}
    g2 = {'entities': [_lesson(TEXT)]}
    g3 = {'entities': [_lesson('unrelated preference about tabs')]}
    graphs = [('k1', g1, '/w/a', '/f/a'), ('k2', g2, '/w/b', '/f/b'),
              ('k3', g3, '/w/c', '/f/c')]
    saved = []
    monkeypatch.setattr(conventions, '_iter_project_graphs', lambda: graphs)
    monkeypatch.setattr(memory, 'save_memory',
                        lambda p, f, g: saved.append((p, f, g)) or True)
    assert conventions.pin_convention(TEXT) == 2
    assert [(p, f) for p, f, _g in saved] == [('/w/a', '/f/a'), ('/w/b', '/f/b')]
    statuses = [e['status'] for e in g1['entities']]
    assert statuses == ['pinned', 'pending', 'pending', 'pinned', 'pending']
    assert g2['entities'][0]['status'] == 'pinned'
    assert g3['entities'][0]['status'] == 'pending'


def test_pin_does_not_count_when_save_fails(monkeypatch):
    g = {'entities': [_lesson(TEXT)]}
    monkeypatch.setattr(conventions, '_iter_project_graphs',
                        lambda: [('k1', g, '/w/a', '/f/a')])
    monkeypatch.setattr(memory, 'save_memory', lambda p, f, g: False)
    assert conventions.pin_convention(TEXT) == 0
