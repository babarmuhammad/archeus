"""T-1293: claude_sessions/events.py:156-198 at 6bbd3b44; same current slice.

Selected probes, not measured coverage; closest test_events.py assertions:
171 interleaved cap/newest order; :178 groups noisy and rare records separately.
167 separate sources/integer ids; :206 tests separate shapes in one source.
169 raw fallback prefix cap; :178 contains valid object JSON only.
183 exact size/no open; :52 checks final bounded size, not threshold.
186 bounded seek/read; :219 never inspects seek or read sizes.
193 CRLF/Unicode byte normalization; :219 uses writer-generated records only.
196 interrupted write preservation; :83 tests record path failure, not rotation.
188 no-newline torn fragment refusal; :219 always writes complete lines.
197 getsize/read/write fault suppression; :83 faults path resolution only.
175 idempotence/rare boundaries/cap=1; :178 uses default cap once.
"""

import builtins
import io
import json
import os
from types import SimpleNamespace

import pytest

from claude_sessions import events as e


def row(src, msg, ts=0):
    return json.dumps({'src': src, 'msg': msg, 'ts': ts})


def test_thinning_interleaved_shapes_keeps_newest_in_original_order(monkeypatch):
    monkeypatch.setattr(e, '_SHAPE_KEEP', 2)
    rows = [row('a', 'slow 1.1', 1), row('rare', 'first', 2),
            row('a', 'slow 2.2', 3), row('a', 'slow 3.3', 4),
            row('rare', 'last', 5)]
    assert e._thin(rows) == rows[1:]


def test_sources_separate_allowances_and_integer_errors_survive(monkeypatch):
    monkeypatch.setattr(e, '_SHAPE_KEEP', 1)
    rows = [row('a', 'slow 1.1'), row('b', 'slow 1.2'), row('a', 'slow 1.3'),
            row('a', 'HTTP 429'), row('a', 'HTTP 500')]
    assert e._thin(rows) == rows[1:]


def test_malformed_and_nonobject_raw_fallback_is_bounded(monkeypatch):
    monkeypatch.setattr(e, '_SHAPE_KEEP', 1)
    prefix = 'x' * 40
    rows = [prefix + 'old', '[]', row('rare', 'error'), prefix + 'new', 'null']
    assert e._thin(rows) == rows[1:]


def test_exact_size_skips_open_one_over_rotates(monkeypatch, tmp_path):
    p = tmp_path / 'events.jsonl'
    raw = b'old\n{"msg":"new"}\n'
    p.write_bytes(raw)
    monkeypatch.setattr(e, 'MAX_BYTES', len(raw))
    monkeypatch.setattr(e, '_KEEP_BYTES', len(raw) - 1)
    with monkeypatch.context() as patch:
        patch.setattr(e, 'open', lambda *a, **k: pytest.fail('threshold opened'), raising=False)
        e._rotate(str(p))
    monkeypatch.setattr(e, 'MAX_BYTES', len(raw) - 1)
    e._rotate(str(p))
    assert p.read_bytes() == b'{"msg":"new"}\n'


def test_rotation_seeks_bounded_tail_before_read(monkeypatch, tmp_path):
    p = str(tmp_path / 'events.jsonl')
    calls = []

    class Tail(io.BytesIO):
        def seek(self, offset, whence=0):
            calls.append(('seek', offset, whence))
            return super().seek(offset, whence)

        def read(self, *args):
            calls.append(('read', self.tell(), args))
            return super().read(*args)

    class Output(io.BytesIO):
        def close(self):
            calls.append(('write', self.getvalue()))
            super().close()

    monkeypatch.setattr(e, 'MAX_BYTES', 10)
    monkeypatch.setattr(e, '_KEEP_BYTES', 12)
    monkeypatch.setattr(e, 'os', SimpleNamespace(SEEK_END=os.SEEK_END,
                        path=SimpleNamespace(getsize=lambda p: 100)))
    monkeypatch.setattr(e, 'open', lambda path, mode: Tail(b'x' * 90 + b'\n{"msg":1}\n')
                        if mode == 'rb' else Output(), raising=False)
    e._rotate(p)
    assert calls[0] == ('seek', -12, os.SEEK_END)
    assert calls[1][0] == 'read' and calls[1][1] > 0
    assert calls[-1] == ('write', b'{"msg":1}\n')


def test_rotation_normalizes_mixed_newlines_and_unicode(monkeypatch, tmp_path):
    p = tmp_path / 'events.jsonl'
    tail = 'partial\r\n{"msg":"é"}\r\n\r\n{"msg":"中"}\n'.encode()
    p.write_bytes(b'old' * 30 + tail)
    monkeypatch.setattr(e, 'MAX_BYTES', 50)
    monkeypatch.setattr(e, '_KEEP_BYTES', len(tail))
    e._rotate(str(p))
    assert p.read_bytes() == '{"msg":"é"}\n{"msg":"中"}\n'.encode()


@pytest.mark.xfail(strict=True, reason='wb truncates audit evidence before write succeeds: claude_sessions/events.py:195-196')
def test_interrupted_rotation_preserves_old_complete_audit(monkeypatch, tmp_path):
    p = tmp_path / 'events.jsonl'
    old = b'old\n{"msg":"new"}\n'
    p.write_bytes(old)
    monkeypatch.setattr(e, 'MAX_BYTES', 5)
    monkeypatch.setattr(e, '_KEEP_BYTES', len(old) - 1)

    class Interrupted:
        def __enter__(self):
            self.fh = builtins.open(p, 'wb')
            return self

        def write(self, data):
            raise OSError('write fault')

        def __exit__(self, *args):
            self.fh.close()

    monkeypatch.setattr(e, 'open', lambda path, mode: Interrupted() if mode == 'wb'
                        else builtins.open(path, mode), raising=False)
    e._rotate(str(p))
    assert p.read_bytes() == old


def test_tail_without_newline_does_not_publish_torn_fragment(monkeypatch, tmp_path):
    p = tmp_path / 'events.jsonl'
    old = b'x' * 40
    p.write_bytes(old)
    monkeypatch.setattr(e, 'MAX_BYTES', 20)
    monkeypatch.setattr(e, '_KEEP_BYTES', 10)
    e._rotate(str(p))
    assert p.read_bytes() in (old, b'')


@pytest.mark.parametrize('stage', ['size', 'read', 'write'])
def test_rotation_faults_do_not_escape_or_touch_unrelated_file(monkeypatch, tmp_path, stage):
    p = tmp_path / 'events.jsonl'
    sibling = tmp_path / 'other'
    old = b'old\n{"msg":"new"}\n'
    p.write_bytes(old)
    sibling.write_bytes(b'unrelated')
    modes = []
    monkeypatch.setattr(e, 'MAX_BYTES', 5)
    monkeypatch.setattr(e, '_KEEP_BYTES', len(old) - 1)

    def size(path):
        if stage == 'size':
            raise OSError('size fault')
        return len(old)

    def open_log(path, mode):
        modes.append(mode)
        if (stage == 'read' and mode == 'rb') or (stage == 'write' and mode == 'wb'):
            raise OSError('open fault')
        return builtins.open(path, mode)

    monkeypatch.setattr(e, 'os', SimpleNamespace(SEEK_END=os.SEEK_END,
                        path=SimpleNamespace(getsize=size)))
    monkeypatch.setattr(e, 'open', open_log, raising=False)
    assert e._rotate(str(p)) is None
    assert modes == {'size': [], 'read': ['rb'], 'write': ['rb', 'wb']}[stage]
    assert p.read_bytes() == old and sibling.read_bytes() == b'unrelated'


def test_thinning_idempotent_rare_boundaries_cap_one_and_empty(monkeypatch):
    monkeypatch.setattr(e, '_SHAPE_KEEP', 1)
    rows = [row('rare', 'first')] + [row('noise', f'slow {i}.1') for i in range(4)]
    rows += [row('rare', 'last')]
    expected = [rows[0], rows[-2], rows[-1]]
    assert e._thin(rows) == expected
    assert e._thin(e._thin(rows)) == expected
    assert e._thin([]) == []
