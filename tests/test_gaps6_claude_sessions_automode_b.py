"""T-1281: claude_sessions/automode.py:152-240 at 6bbd3b44; same current slice.

Selected probes, not measured coverage; closest test_automode.py assertions:
209 cut-crossing command/reason secrets; :89 does not exercise redaction.
213 append/newline/failure; :89 checks values, not bytes or failed append.
214 rotation fault retains appended record; :123 covers successful rotations.
231 exact threshold/bounded read; :123 checks final size only.
236 mid-multibyte tail drop; :123 uses ASCII complete records only.
237 interrupted rotation durability; :123 never injects write faults.
166 valid dict limit/garbage; :89 contains valid records only.
169 partial reader failure; :118 has no file, not failed observation.
185 blank Bash/fallback groups; :103 has nonempty Bash and named Read only.
190 bad timestamps/ties/sample bounds; :103 checks counts and sample cap only.
"""

import builtins
import io
import json
import os
from types import SimpleNamespace

import pytest

from claude_sessions import automode as a, store, transcripts


@pytest.fixture
def audit(monkeypatch, tmp_path):
    p = tmp_path / 'denied.jsonl'
    monkeypatch.setattr(store, 'workdir', lambda project: str(tmp_path))
    monkeypatch.setattr(store, 'workfile', lambda project, name: str(tmp_path / name))
    monkeypatch.setattr(a.time, 'time', lambda: 1234.0)
    return p


def test_command_reason_secrets_crossing_cuts_are_redacted(audit, monkeypatch):
    monkeypatch.setattr(a, '_rotate', lambda path: None)
    token = 'sk-ant-' + 'A' * 50
    assert a.record('project', 'Bash', 'c' * 490 + ' ' + token, 'r' * 290 + ' ' + token)
    row = json.loads(audit.read_text(encoding='utf-8'))
    assert row == {'ts': 1234, 'tool': 'Bash',
                   'command': ('c' * 490 + ' [redacted]')[:500],
                   'reason': ('r' * 290 + ' [redacted]')[:300]}
    assert 'sk-ant-' not in audit.read_text(encoding='utf-8')


def test_append_keeps_previous_line_and_write_fault_returns_false(audit, monkeypatch):
    monkeypatch.setattr(a, '_rotate', lambda path: None)
    audit.write_bytes(b'{"tool":"previous"}\n')
    assert a.record('project', 'Read', 'file', 'blocked')
    raw = audit.read_bytes()
    assert raw.startswith(b'{"tool":"previous"}\n') and raw.endswith(b'\n')
    assert len(raw.splitlines()) == 2

    def fail(*args, **kwargs):
        raise OSError('append fault')

    monkeypatch.setattr(a, 'open', fail, raising=False)
    assert a.record('project', 'Read', 'other', 'blocked') is False
    assert audit.read_bytes() == raw


def test_rotation_fault_retains_just_appended_record(audit, monkeypatch):
    calls = []

    def rotate(path):
        assert audit.read_bytes().endswith(b'\n')
        assert json.loads(audit.read_text(encoding='utf-8'))['command'] == 'command'
        calls.append(path)
        raise OSError('rotation fault')

    monkeypatch.setattr(a, '_rotate', rotate)
    assert a.record('project', 'Bash', 'command', 'reason') is False
    assert calls == [str(audit)] and len(audit.read_bytes().splitlines()) == 1


def test_rotation_exact_threshold_and_bounded_seek(monkeypatch, tmp_path):
    path = str(tmp_path / 'denied.jsonl')
    size = [20]
    calls = []

    class Tail(io.BytesIO):
        def seek(self, offset, whence=0):
            calls.append(('seek', offset, whence))
            return super().seek(offset, whence)

        def read(self, *args):
            calls.append(('read', self.tell()))
            return super().read(*args)

    class Output(io.BytesIO):
        def close(self):
            calls.append(('written', self.getvalue()))
            super().close()

    def open_log(path, mode):
        calls.append(('open', mode))
        return Tail(b'x' * 30 + b'\n{}\n') if mode == 'rb' else Output()

    monkeypatch.setattr(a, '_MAX_BYTES', 20)
    monkeypatch.setattr(a, '_KEEP_BYTES', 5)
    monkeypatch.setattr(a, 'os', SimpleNamespace(SEEK_END=os.SEEK_END,
                        path=SimpleNamespace(getsize=lambda p: size[0])))
    monkeypatch.setattr(a, 'open', open_log, raising=False)
    a._rotate(path)
    assert calls == []
    size[0] = 21
    a._rotate(path)
    assert calls == [('open', 'rb'), ('seek', -5, os.SEEK_END), ('read', 29),
                     ('open', 'wb'), ('written', b'{}\n')]


def test_rotation_drops_mid_multibyte_record_preserves_complete_bytes(audit, monkeypatch):
    complete = '{"tool":"Read","command":"中"}\r\n'.encode()
    raw = b'old' * 30 + 'é'.encode() + b'partial\n' + complete
    audit.write_bytes(raw)
    monkeypatch.setattr(a, '_MAX_BYTES', 40)
    monkeypatch.setattr(a, '_KEEP_BYTES', 1 + len(b'partial\n') + len(complete))
    a._rotate(str(audit))
    assert audit.read_bytes() == complete


@pytest.mark.xfail(strict=True, reason='wb truncates prior denials before write succeeds: claude_sessions/automode.py:237-238')
def test_interrupted_rotation_preserves_previous_denials(audit, monkeypatch):
    old = b'old\n{"tool":"Read"}\n'
    audit.write_bytes(old)
    monkeypatch.setattr(a, '_MAX_BYTES', 5)
    monkeypatch.setattr(a, '_KEEP_BYTES', len(old) - 1)

    class Interrupted:
        def __enter__(self):
            self.fh = builtins.open(audit, 'wb')
            return self

        def write(self, data):
            raise OSError('rotation write fault')

        def __exit__(self, *args):
            self.fh.close()

    monkeypatch.setattr(a, 'open', lambda path, mode: Interrupted() if mode == 'wb'
                        else builtins.open(path, mode), raising=False)
    a._rotate(str(audit))
    assert audit.read_bytes() == old


def test_denials_skip_nondicts_limit_valid_records_once(audit, monkeypatch):
    audit.write_bytes(b'synthetic')
    calls = []

    def records(path):
        calls.append(path)
        return iter([{'tool': 'old'}, [], None, 'bad', {'tool': 'new'}])

    monkeypatch.setattr(transcripts, 'iter_json', records)
    assert a.denials('project', limit=1) == [{'tool': 'new'}]
    assert calls == [str(audit)]
    assert audit.read_bytes() == b'synthetic'


def test_reader_exception_discards_partial_result_without_deleting(audit, monkeypatch):
    audit.write_bytes(b'prior evidence')

    def records(path):
        yield {'tool': 'partial'}
        raise OSError('read fault')

    monkeypatch.setattr(transcripts, 'iter_json', records)
    monkeypatch.setattr(a, 'record', lambda *args: pytest.fail('reader appended'))
    monkeypatch.setattr(a, '_rotate', lambda path: pytest.fail('reader rotated'))
    assert a.denials('project') == []
    assert audit.read_bytes() == b'prior evidence'


def test_summary_empty_bash_and_nonshell_fallbacks(monkeypatch):
    records = [{'tool': 'Bash', 'command': '  git status && echo hi'},
               {'tool': 'Bash', 'command': 'git diff'},
               {'tool': 'Bash', 'command': '   '},
               {'tool': 'Read', 'command': 'git status'}, {'command': 'unknown'}]
    monkeypatch.setattr(a, 'denials', lambda *args, **kw: records)
    groups = {g['key']: g for g in a.summarise('project')}
    assert {k: v['count'] for k, v in groups.items()} == {
        'Bash:git': 2, 'Bash': 1, 'Read': 1, '?': 1}
    assert groups['Bash:git']['samples'] == ['  git status && echo hi', 'git diff']


def test_summary_bad_timestamps_stable_order_and_bounded_samples(monkeypatch):
    records = [{'tool': 'Read', 'command': cmd, 'ts': ts, 'reason': 'r' * 250}
               for cmd, ts in [('a', 'bad'), ('a', {}), ('b', '7'), ('c' * 250, 9), ('d', 1)]]
    records += [{'tool': 'Write', 'command': 'w', 'ts': 8},
                {'tool': 'Edit', 'command': 'e', 'ts': 8}]
    monkeypatch.setattr(a, 'denials', lambda *args, **kw: records)
    got = a.summarise('project')
    assert [g['key'] for g in got] == ['Read', 'Write', 'Edit']
    assert got[0]['count'] == 5 and got[0]['last'] == 9
    assert got[0]['reason'] == 'r' * 200
    assert got[0]['samples'] == ['a', 'b', 'c' * 200]
