"""Unit tests for tools/pv20_mxc/native/n4_check.py (the N4 native script).

Nothing here launches a process, creates a Job, loads a native library, runs Git or touches a
real profile: every Windows-facing seam (the harness, the api, the node, look_at, junctions) is a
fake. The fake provider and the forbidden listener are exercised over 127.0.0.1 inside this
process only, and the production modules are imported only where they are pure.
"""

import ast
import http.client
import importlib
import json
import os
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from tools.pv20_mxc.native import common, n2_check as n2, n4_check as n4
from tools.pv20_mxc.native.common import StopRun
from tools.pv20_mxc.protocol import STAGES

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), 'tools', 'pv20_mxc', 'native', 'n4_check.py')
SECRET = 'S3CR3T'
SEED_CONFIG = b'[core]\n\tbare = false\n'


class Rec:
    """Records what a step reports; FAIL stops the step the way the real Recorder does."""

    def __init__(self):
        self.rows = []

    def record(self, case, status, detail=''):
        self.rows.append((case, status, detail))
        if status == 'FAIL':
            raise StopRun(case)

    def statuses(self):
        return [s for _, s, _ in self.rows]


def _lay(tmp_path):
    lay = n4.layout(str(tmp_path / 'root'))
    n4.make_dirs(lay)
    return lay


def _under(path, folder):
    return os.path.normcase(path).startswith(os.path.normcase(folder) + os.sep)


# ---------------------------------------------------------------- layout and environment

def test_every_directory_lies_under_the_root(tmp_path):
    lay = _lay(tmp_path)
    for key, path in lay.items():
        assert path == lay['root'] or _under(path, lay['root']), key
    for key in ('private', 'toolchain', 'envhome', 'home', 'localappdata', 'outside', 'src', 'seedws', 'ctl', 'faults'):
        assert os.path.isdir(lay[key])
    assert not os.path.exists(lay['sdk']) and not os.path.exists(lay['cli'])      # staged, never made empty
    assert not os.path.exists(lay['ledger'])                                       # the production Ledger makes it


def test_pin_environment_points_every_profile_variable_inside_the_root(tmp_path):
    lay, env = _lay(tmp_path), {}
    n4.pin_environment(env, lay)
    assert set(env) == set(n2.HOME_VARS) | {'ARCHEUS_HOME'}
    assert all(env[k] == lay['envhome'] for k in n2.HOME_VARS if k != 'ARCHEUS_HOME')
    assert env['ARCHEUS_HOME'] == lay['home']


# ---------------------------------------------------------------- seed tree and fast-import stream

def _walk_import(blob):
    pos, lines, payloads = 0, [], []
    while pos < len(blob):
        end = blob.index(b'\n', pos)
        line = blob[pos:end]
        pos = end + 1
        lines.append(line)
        if line.startswith(b'data '):
            size = int(line[5:])
            payloads.append(blob[pos:pos + size])
            pos += size
            assert blob[pos:pos + 1] == b'\n'
            pos += 1
    return lines, payloads


def test_seed_files_carry_the_secret_and_name_every_mode_the_import_must_survive():
    files = n4.seed_files(SECRET)
    assert {m for _, m, _ in files} == {'100644', '100755', '120000', '160000'}
    notes = dict((r, d) for r, _, d in files)['notes.txt']
    assert SECRET.encode() in notes and notes.startswith(b'edit me ')
    assert len({r for r, _, _ in files}) == len(files)


def test_fast_import_stream_is_one_commit_with_exact_data_lengths_and_a_done_marker():
    files = n4.seed_files(SECRET)
    blob = n4.fast_import_stream(n4.SEED_REF, files)
    lines, payloads = _walk_import(blob)
    assert lines[0] == b'commit ' + n4.SEED_REF.encode() and lines[-1] == b'done'
    assert sum(1 for x in lines if x.startswith(b'commit ')) == 1
    assert payloads[0] == b'n4 fixture seed\n'
    assert payloads[1:] == [d for _, m, d in files if m != '160000']
    assert [x for x in lines if x.startswith(b'M 160000 ')] == [b'M 160000 ' + b'1' * 40 + b' sub']
    assert n4.SEED_REF.startswith('refs/archeus/')                                 # never a branch of a real project


def _seeded_tree(tmp_path):
    root = tmp_path / 'ws'
    for rel, mode, data in n4.seed_files(SECRET):
        if mode == '160000':
            (root / rel).mkdir(parents=True)
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (root / '.git').mkdir(exist_ok=True)
    (root / '.git' / 'HEAD').write_text('ref: refs/heads/x\n')
    (root / '.git' / 'config').write_bytes(SEED_CONFIG)
    (root / '.git' / 'objects').mkdir()
    (root / '.git' / 'refs').mkdir()
    return str(root)


def _problems(root):
    return n4.tree_problems(n4.walk_plain(root), root, n4.seed_files(SECRET), SEED_CONFIG)


def test_a_faithful_seed_has_no_problem(tmp_path):
    assert _problems(_seeded_tree(tmp_path)) == []


def test_tree_problems_names_each_way_a_seed_can_be_wrong(tmp_path):
    root = _seeded_tree(tmp_path)
    open(os.path.join(root, 'extra.txt'), 'w').close()
    open(os.path.join(root, 'notes.txt'), 'w').write('changed')
    os.remove(os.path.join(root, 'run.cmd'))
    open(os.path.join(root, '.git', 'hooks'), 'w').close()
    open(os.path.join(root, '.git', 'config'), 'w').write('[core]\n')
    bad = ' | '.join(_problems(root))
    for word in ('unexpected entry: extra.txt', 'differs from the tree: notes.txt', 'missing: run.cmd',
                 'unexpected .git entry: .git/hooks', '.git/config is not the config Core wrote'):
        assert word in bad, word


def test_tree_problems_refuses_alternates_and_a_missing_config(tmp_path):
    root = _seeded_tree(tmp_path)
    os.makedirs(os.path.join(root, '.git', 'objects', 'info'))
    open(os.path.join(root, '.git', 'objects', 'info', 'alternates'), 'w').close()
    assert any('borrows objects' in p for p in _problems(root))
    os.remove(os.path.join(root, '.git', 'config'))
    assert '.git/config missing' in _problems(root)


def test_a_second_name_for_a_file_is_a_problem(tmp_path):
    root = _seeded_tree(tmp_path)
    try:
        os.link(os.path.join(root, 'notes.txt'), os.path.join(root, 'alias.txt'))
    except OSError:
        pytest.skip('hard links unavailable here')
    bad = ' | '.join(_problems(root))
    assert 'a second name for notes.txt' in bad and 'a second name for alias.txt' in bad


def test_tree_problems_flags_every_link_entry():
    info = SimpleNamespace(st_mode=0o100644, st_nlink=1)
    bad = n4.tree_problems([('notes.txt', info, True)], '\\nowhere', [], SEED_CONFIG)
    assert 'alias: notes.txt' in bad


def test_walk_plain_does_not_follow_a_link(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('x')
    root = tmp_path / 'ws'
    root.mkdir()
    try:
        os.symlink(str(outside), str(root / 'evil'), target_is_directory=True)
    except OSError:
        pytest.skip('symlinks need a privilege here')
    entries = n4.walk_plain(str(root))
    assert [(rel, link) for rel, _, link in entries] == [('evil', True)]


# ---------------------------------------------------------------- the fake provider's wire format

def _events(chunks):
    out = []
    for chunk in chunks:
        head, _, tail = chunk.decode().partition('\n')
        assert head.startswith('event: ') and tail.startswith('data: ') and chunk.endswith(b'\n\n')
        data = json.loads(tail[len('data: '):])
        assert data['type'] == head[len('event: '):]
        out.append(data)
    return out


def test_text_turn_is_a_complete_message_stream():
    events = _events(n4.text_turn('hello'))
    assert [e['type'] for e in events] == ['message_start', 'content_block_start', 'content_block_delta',
                                           'content_block_stop', 'message_delta', 'message_stop']
    assert events[2]['delta'] == {'type': 'text_delta', 'text': 'hello'}
    assert events[4]['delta']['stop_reason'] == 'end_turn'
    assert events[0]['message']['model'] == n4.MODEL


def test_tool_turn_streams_the_input_in_two_json_pieces_and_stops_for_the_tool():
    want = {'file_path': 'C:\\w\\notes.txt', 'old_string': 'a', 'new_string': 'b'}
    events = _events(n4.tool_turn('toolu_x', 'Edit', want))
    start = events[1]['content_block']
    assert (start['type'], start['id'], start['name']) == ('tool_use', 'toolu_x', 'Edit')
    pieces = [e['delta']['partial_json'] for e in events if e.get('delta', {}).get('type') == 'input_json_delta']
    assert len(pieces) == 2 and json.loads(''.join(pieces)) == want
    assert events[-2]['delta']['stop_reason'] == 'tool_use'


def test_request_json_and_tool_result_ids_never_raise_on_garbage():
    assert n4.request_json(b'\xff\xfe') == {} and n4.request_json(b'[1]') == {} and n4.request_json(b'{') == {}
    assert n4.tool_result_ids({}) == [] and n4.tool_result_ids({'messages': ['x', {'content': 'str'}]}) == []
    doc = {'messages': [{'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': 't1'},
        {'type': 'tool_result', 'tool_use_id': 't2', 'is_error': True}, {'type': 'text', 'text': 'x'}]}]}
    assert n4.tool_result_ids(doc) == [('t1', False), ('t2', True)]


def test_parse_stream_counts_what_it_cannot_read():
    events, bad = n4.parse_stream('{"type":"a"}\n\nnot json\n[1]\n{"type":"b"}\n')
    assert [e['type'] for e in events] == ['a', 'b'] and bad == 2
    assert n4.parse_stream(None) == ([], 0)


def test_stream_accessors():
    events = [{'type': 'system', 'session_id': 'sess-1'},
              {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Edit'},
                                                            {'type': 'text', 'text': 'x'}]}},
              {'type': 'user', 'message': {'content': 'plain'}},
              {'type': 'result', 'is_error': False, 'result': 'r1'}, {'type': 'result', 'is_error': True}]
    assert n4.session_of(events) == 'sess-1' and n4.session_of([{'session_id': 3}]) is None
    assert n4.result_of(events)['is_error'] is True and n4.result_of([]) is None
    assert [b['name'] for b in n4.blocks(events, 'tool_use', 'assistant')] == ['Edit']
    assert n4.blocks(events, 'tool_use', 'user') == []


def test_streamed_needs_output_well_before_the_end():
    assert n4.streamed([10.0, 11.0], 10.6) and not n4.streamed([10.0], 10.4) and not n4.streamed([], 99.0)


# ---------------------------------------------------------------- the container's environment and argv

def _ex(tmp_path):
    base = str(tmp_path / 'exec')
    paths = SimpleNamespace(home=os.path.join(base, 'home'), tmp=os.path.join(base, 'tmp'),
                            config=os.path.join(base, 'config'))
    return SimpleNamespace(paths=paths)


def test_cli_env_is_explicit_and_only_names_the_execution_the_cli_and_the_broker(tmp_path):
    ex = _ex(tmp_path)
    broker = {'ANTHROPIC_BASE_URL': 'http://127.0.0.1:9', 'ANTHROPIC_AUTH_TOKEN': 'brk_x'}
    env = n4.cli_env('C:\\Windows', ex, 'D:\\cli', broker)
    assert env['PATH'] == 'D:\\cli' and env['ComSpec'] == 'C:\\Windows\\System32\\cmd.exe'
    assert env['SystemDrive'] == 'C:' and env['USERPROFILE'] == env['HOME'] == ex.paths.home
    assert env['TEMP'] == env['TMP'] == ex.paths.tmp and env['CLAUDE_CONFIG_DIR'] == ex.paths.config
    assert broker.items() <= env.items()
    assert env['DISABLE_AUTOUPDATER'] == '1' and env['DISABLE_TELEMETRY'] == '1'
    for name in ('USERNAME', 'COMPUTERNAME', 'APPDATA_HOST', 'ANTHROPIC_API_KEY'):
        assert name not in env
    for name in ('APPDATA', 'LOCALAPPDATA'):
        assert _under(env[name], ex.paths.home)


def test_cli_argv_allows_only_edit_and_read_and_resumes_by_session():
    argv = n4.cli_argv('D:\\cli\\claude.exe', 'do it')
    assert argv[:3] == ['D:\\cli\\claude.exe', '-p', 'do it'] and '--resume' not in argv
    assert argv[argv.index('--allowedTools') + 1] == 'Edit,Read'
    assert argv[argv.index('--permission-mode') + 1] == 'acceptEdits' and '--dangerously-skip-permissions' not in argv
    assert argv[argv.index('--model') + 1] == n4.MODEL
    resumed = n4.cli_argv('D:\\cli\\claude.exe', 'go', resume='sess-1')
    assert resumed[-2:] == ['--resume', 'sess-1']


def test_proxy_problems_accepts_the_production_proxy_policy_and_names_each_deviation(tmp_path):
    from archeus.node import mxc
    lay = _lay(tmp_path)
    work = str(tmp_path / 'w')
    os.makedirs(work)
    url = 'http://127.0.0.1:4321'
    env = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': lay['localappdata']}
    policy = mxc.compile_policy(workspace=(work,), readonly=(lay['toolchain'],), cwd=work, command_line='x',
                                env=env, timeout_ms=1000, proxy_url=url)
    assert n4.proxy_problems(policy.raw, url) == []
    assert n4.proxy_problems(policy.raw, 'http://127.0.0.1:1') == ['proxy endpoint is not the listener']
    deny = mxc.compile_policy(workspace=(work,), readonly=(lay['toolchain'],), cwd=work, command_line='x',
                              env=env, timeout_ms=1000)
    assert 'proxy endpoint is not the listener' in n4.proxy_problems(deny.raw, url)
    raw = json.loads(json.dumps(policy.raw))
    raw['processContainer'] = {'capabilities': ['internetClient', 'privateNetworkClientServer']}
    raw['network']['egress']['default'] = 'allow'
    raw['ui'] = {'disable': False}
    raw['process']['inheritDefaultEnv'] = True
    assert len(n4.proxy_problems(raw, url)) == 4


# ---------------------------------------------------------------- verdict functions

def _run(code=0, out='', ops=None):
    return SimpleNamespace(code=code, out=out, ops=ops or n4.CLEAN)


def _final(text):
    return json.dumps({'type': 'result', 'is_error': False, 'result': text})


def _hit(method='POST', path='/v1/messages', auth=True, body=b''):
    return n4.Hit(method, path, auth, body, 0.0)


def test_text_run_problems():
    ok = _run(out=_final('N4-x'))
    assert n4.text_run_problems(ok, [_hit(path='/v1/messages?beta=true')], 0, 'N4-x') == []
    wrong = _run(code=1, out=_final('other'), ops=n4.QUARANTINED)
    bad = ' | '.join(n4.text_run_problems(wrong, [_hit(auth=False), _hit('CONNECT', 'x:443')], 1, 'N4-x'))
    for word in ('launcher exit 1', 'ledger', 'no successful result', 'broker token', 'CONNECT', 'forbidden listener'):
        assert word in bad, word
    assert any('no successful result' in p for p in n4.text_run_problems(_run(out=''), [_hit()], 0, 'N4-x'))
    errored = json.dumps({'type': 'result', 'is_error': True, 'result': 'N4-x'})
    assert any('no successful result' in p for p in n4.text_run_problems(_run(out=errored), [_hit()], 0, 'N4-x'))


def _edit_stream():
    return '\n'.join([json.dumps({'type': 'system', 'session_id': 's1'}),
                      json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Edit'}]}}),
                      _final('EDITED-x')])


def _second(tool, error=False):
    body = {'messages': [{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': tool, 'is_error': error}]}]}
    return _hit(body=json.dumps(body).encode())


def test_edit_run_problems():
    hits = [_hit(), _second('t1')]
    assert n4.edit_run_problems(_run(out=_edit_stream()), hits, 'edited ' + SECRET, SECRET, 't1', True) == []
    for kw, word in (({'notes_text': 'edit me ' + SECRET}, 'not edited'), ({'notes_text': None}, 'not edited'),
                     ({'streamed_ok': False}, 'while the run was live'),
                     ({'hits': [_hit(), _second('t1', error=True)]}, 'clean result'),
                     ({'hits': [_hit()]}, 'clean result'), ({'hits': []}, 'clean result')):
        args = dict(hits=hits, notes_text='edited ' + SECRET, streamed_ok=True)
        args.update(kw)
        bad = ' | '.join(n4.edit_run_problems(_run(out=_edit_stream()), args['hits'], args['notes_text'], SECRET, 't1',
                                             args['streamed_ok']))
        assert word in bad, (kw, bad)
    no_tool = _run(out='\n'.join([json.dumps({'type': 'system', 'session_id': 's1'}), _final('EDITED-x')]))
    assert any('no Edit tool call' in p for p in n4.edit_run_problems(no_tool, hits, 'edited ' + SECRET, SECRET, 't1', True))
    no_session = _run(out='\n'.join([json.dumps({'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Edit'}]}}), _final('EDITED-x')]))
    assert any('no session id' in p for p in n4.edit_run_problems(no_session, hits, 'edited ' + SECRET, SECRET, 't1', True))


def test_import_problems_subset_by_default_and_exact_when_asked():
    rev = 'a' * 40
    assert n4.import_problems({'revision': rev, 'files_changed': ['M notes.txt']}, ['M notes.txt']) == []
    extra = {'revision': rev, 'files_changed': ['M notes.txt', 'A x']}
    assert n4.import_problems(extra, ['M notes.txt']) == []
    assert n4.import_problems(extra, ['M notes.txt'], exact=True)
    assert n4.import_problems({'revision': rev, 'files_changed': []}, ['M notes.txt'])
    for bad in (None, {}, {'revision': 'short'}, {'revision': 'G' * 40}, {'revision': None}, 'x'):
        assert n4.import_problems(bad, ['M notes.txt']) == ['no import revision']


def test_stop_problems():
    assert n4.stop_problems(TimeoutError(), n4.QUARANTINED, 0, False, True) == []
    assert len(n4.stop_problems(None, n4.CLEAN, 2, True, False)) == 4
    assert any('tried against a live request' in p for p in n4.stop_problems(TimeoutError(), n4.QUARANTINED, 0, False, False))


def test_hostile_files_only_ever_write_marker_files_named_for_the_mechanism(tmp_path):
    marker_dir = str(tmp_path / 'm')
    files = n4.hostile_files(marker_dir)
    assert set(files) == {'.git/config', '.git/hooks/pre-commit', '.git/hooks/post-checkout',
                          '.gitattributes', '.gitmodules'}
    fwd = marker_dir.replace('\\', '/')
    cfg = files['.git/config']
    for mech in ('fsmonitor', 'ssh', 'clean', 'smudge', 'textconv', 'credential'):
        assert '%s/fired_%s.txt' % (fwd, mech) in cfg
    assert '\\' not in cfg
    for text in files.values():
        for line in text.splitlines():
            if 'echo' in line:
                assert fwd in line and line.count('>') == 1


def test_markers_lists_only_fired_files_and_survives_a_missing_folder(tmp_path):
    assert n4.markers(str(tmp_path / 'none')) == []
    (tmp_path / 'fired_b.txt').write_text('x')
    (tmp_path / 'fired_a.txt').write_text('x')
    (tmp_path / 'other.txt').write_text('x')
    assert n4.markers(str(tmp_path)) == ['fired_a.txt', 'fired_b.txt']


def test_inert_problems():
    assert n4.inert_problems(['fired_x.txt'], [], 'c', 'c') == ([], True)
    assert n4.inert_problems([], [], 'c', 'c') == ([], False)
    bad, armed = n4.inert_problems(['f'], ['fired_ssh.txt'], 'c', 'd')
    assert armed and len(bad) == 2 and 'fired_ssh.txt' in bad[0]


def test_verifier_problems():
    ok = {'error': None, 'exit_code': 0, 'confinement': {'ac_profile': 'new'}}
    assert n4.verifier_problems(ok, 1, n4.CLEAN, None, {'old'}) == []
    bad = ' | '.join(n4.verifier_problems(dict(ok, error='x'), 2, n4.QUARANTINED, ('breach', 'home-read'), {'new'}))
    for word in ('verifier result error', 'recorded 2 times', 'ledger', 'containment breach: home-read', 'not fresh'):
        assert word in bad, word
    assert 'control failed: c' in ' '.join(n4.verifier_problems(ok, 1, n4.CLEAN, ('control', 'c'), set()))
    for broken in (None, {}, {'error': None, 'exit_code': 1, 'confinement': {'ac_profile': 'p'}}):
        assert n4.verifier_problems(broken, 1, n4.CLEAN, None, set())


def test_limit_problems_needs_the_named_error_a_quarantine_and_an_empty_job():
    assert n4.limit_problems('bound', RuntimeError('launcher output bound exceeded'), n4.QUARANTINED, 0, False) == []
    assert n4.limit_problems('deadline', TimeoutError('launcher I/O deadline'), n4.QUARANTINED, 0, False) == []
    assert len(n4.limit_problems('bound', None, n4.CLEAN, 1, True)) == 3
    assert n4.limit_problems('bound', RuntimeError('something else'), n4.QUARANTINED, 0, False)


def test_forged_problems_trusts_only_the_launcher_exit():
    assert n4.forged_problems(3, 'FORGED-PASS-x', n4.CLEAN, 3) == []
    bad = ' | '.join(n4.forged_problems(0, 'nothing', n4.QUARANTINED, 3))
    for word in ('failing workload', 'never printed', 'ledger', 'journal outcome'):
        assert word in bad, word
    assert n4.forged_problems(True, 'FORGED-PASS', n4.CLEAN, True)                    # a bool is not an exit code


# ---------------------------------------------------------------- recorder and capture

def test_the_recorder_journals_a_redacted_verdict_for_protocol_cases_only(tmp_path):
    rec = n4._Rec('N4')
    rec.journal = str(tmp_path / 'j.jsonl')
    user = common._username()
    rec.record('copy-only-seed', 'PASS', 'ran as %s' % user)
    rec.record('two-fresh-verifiers', 'INCONCLUSIVE', 'stand-in')
    with pytest.raises(StopRun):
        rec.record('limits-forged-results', 'FAIL', 'bad')
    rows = [json.loads(x) for x in open(rec.journal, encoding='utf-8').read().splitlines()]
    assert [(r['case'], r['status']) for r in rows] == [('copy-only-seed', 'PASS'), ('two-fresh-verifiers', 'INCONCLUSIVE'),
                                                         ('limits-forged-results', 'FAIL')]
    if user and len(user.strip()) >= 2:
        assert '[REDACTED-USER]' in rows[0]['detail']
    assert rec.exit_code() == 1


def test_the_recorder_writes_nothing_without_a_journal_and_refuses_an_unknown_case(tmp_path):
    rec = n4._Rec('N4')
    rec.record('copy-only-seed', 'PASS', 'x')
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        rec.record('not-a-case', 'PASS', 'x')


def test_capture_is_bounded_and_timestamps_each_chunk():
    ticks = iter([1.0, 2.0, 3.0])
    cap = n4.Capture(clock=lambda: next(ticks), limit=10)
    cap('stdout', b'abc')
    cap('stderr', b'de')
    cap('stdout', b'\xc3\xa9x')
    assert cap.times == [1.0, 2.0, 3.0] and cap.text() == 'abcéx'
    assert cap.text('stderr') == 'de'
    with pytest.raises(OverflowError):
        cap('stdout', b'x' * 10)


# ---------------------------------------------------------------- the script's own listeners

@pytest.fixture
def up():
    server = n4.Upstream('brk_tok', pause=0)
    server.start()
    yield server
    server.close()


def _call(server, method, path, body=b'', token='brk_tok', header='Authorization', timeout=10):
    conn = http.client.HTTPConnection(n4.LOOPBACK, server.port, timeout=timeout)
    headers = {'Content-Length': str(len(body))} if method == 'POST' else {}
    if token:
        headers[header] = ('Bearer ' + token) if header == 'Authorization' else token
    conn.request(method, path, body=body or None, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_the_listeners_bind_loopback_only(up):
    assert up.server.server_address[0] == n4.LOOPBACK == '127.0.0.1' and up.url == 'http://127.0.0.1:%d' % up.port
    fb = n4.Forbidden()
    try:
        assert fb.sock.getsockname()[0] == '127.0.0.1'
    finally:
        fb.close()


def test_the_fake_provider_refuses_a_call_without_the_broker_token(up):
    assert _call(up, 'POST', '/v1/messages', b'{}', token=None)[0] == 401
    assert _call(up, 'POST', '/v1/messages', b'{}', token='brk_other')[0] == 401
    assert _call(up, 'GET', '/anything', token=None)[0] == 401
    assert [h.auth for h in up.seen()] == [False, False, False]


def test_the_fake_provider_streams_a_text_reply_for_either_auth_header(up):
    up.mode = {'kind': 'text', 'reply': 'FAKE-REPLY'}
    for header in ('Authorization', 'x-api-key'):
        status, data = _call(up, 'POST', '/v1/messages?beta=true', b'{}', header=header)
        assert status == 200 and b'FAKE-REPLY' in data and data.rstrip().endswith(b'"type": "message_stop"}')
    assert [h.auth for h in up.seen()] == [True, True] and up.count() == 2
    assert up.seen(1)[0].path == '/v1/messages?beta=true'


def test_the_fake_provider_never_tunnels(up):
    conn = http.client.HTTPConnection(n4.LOOPBACK, up.port, timeout=10)
    conn.request('CONNECT', 'example.invalid:443')
    assert conn.getresponse().status == 403
    conn.close()
    assert [h.method for h in up.seen()] == ['CONNECT']


def test_the_fake_provider_other_routes(up):
    assert _call(up, 'POST', '/v1/messages/count_tokens', b'{}') == (200, b'{"input_tokens":10}')
    assert _call(up, 'GET', '/v1/models')[0] == 404


def test_the_edit_mode_asks_for_the_tool_once_then_answers_in_text(up):
    up.mode = {'kind': 'edit', 'tool': 'toolu_1', 'path': 'C:\\w\\notes.txt', 'old': 'a', 'new': 'b', 'reply': 'EDITED-x'}
    first = _call(up, 'POST', '/v1/messages', json.dumps({'messages': []}).encode())[1]
    assert b'tool_use' in first and b'toolu_1' in first and b'EDITED-x' not in first
    body = {'messages': [{'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'toolu_1'}]}]}
    second = _call(up, 'POST', '/v1/messages', json.dumps(body).encode())[1]
    assert b'EDITED-x' in second and b'tool_use' not in second


def test_the_stall_mode_holds_the_request_open_until_released(up):
    up.mode = {'kind': 'stall'}
    done = []

    def client():
        done.append(_call(up, 'POST', '/v1/messages', b'{}', timeout=20))

    thread = threading.Thread(target=client, daemon=True)
    thread.start()
    assert up.stalled.wait(10) and thread.is_alive() and not done
    up.release.set()
    thread.join(10)
    assert done and done[0][0] == 200 and b'message_start' in done[0][1] and b'message_stop' not in done[0][1]


def test_an_oversize_declared_body_is_not_read(up):
    conn = http.client.HTTPConnection(n4.LOOPBACK, up.port, timeout=10)
    conn.putrequest('POST', '/v1/messages')
    conn.putheader('Authorization', 'Bearer brk_tok')
    conn.putheader('Content-Length', str(n4.BODY_MAX + 1))
    conn.endheaders()
    assert conn.getresponse().status == 200
    conn.close()
    assert up.seen()[0].body == b''


def test_upstream_close_before_start_does_not_hang():
    server = n4.Upstream('brk_tok')
    server.close()


def test_the_forbidden_listener_counts_each_connection_and_closes_it():
    fb = n4.Forbidden()
    fb.start()
    try:
        for _ in range(2):
            socket.create_connection((n4.LOOPBACK, fb.port), 5).close()
        end = time.monotonic() + 5
        while fb.hits < 2 and time.monotonic() < end:
            time.sleep(0.05)
        assert fb.hits == 2
    finally:
        fb.close()


def test_host_touch_makes_a_logged_request_and_fails_closed_on_a_dead_port(up):
    n4.host_touch(up.port, b'GET /hostctl HTTP/1.0\r\n\r\n')
    assert [(h.method, h.path, h.auth) for h in up.seen()] == [('GET', '/hostctl', False)]
    fb = n4.Forbidden()
    port = fb.port
    fb.close()
    with pytest.raises(OSError):
        n4.host_touch(port)


# ---------------------------------------------------------------- the production no-output sink

def test_the_fast_import_sink_refuses_any_stdout():
    sink = n4._NoOutput()
    sink.end()
    sink.abort()
    with pytest.raises(OSError):
        sink.feed(b'x')


# ---------------------------------------------------------------- steps over a fake harness

class FakeHarness:
    def __init__(self, tmp_path, **local):
        self.lay = _lay(tmp_path)
        self.secret, self.seeds = SECRET, {}
        self.project, self.seed_commit = 'prj', 'c' * 40
        self.cmd = 'C:\\Windows\\System32\\cmd.exe'
        self.sr = 'C:\\Windows'
        self.up = self.fb = None
        self.local = SimpleNamespace(**local)
        self.m = SimpleNamespace(local=SimpleNamespace(LocalNode=self.local, SEED_CONFIG=SEED_CONFIG))
        self.count = 0
        self.tmp = tmp_path

    def seeded(self):
        self.count += 1
        work = self.tmp / ('work%d' % self.count)
        work.mkdir()
        paths = SimpleNamespace(state=str(work / 'state'), dir=str(work / 'dir'), config=str(work / 'config'),
                                tmp=str(work / 'tmp'), home=str(work / 'home'))
        return SimpleNamespace(eid='exec_%d' % self.count, work=str(work), paths=paths)


def test_fail_records_and_stops():
    rec = Rec()
    with pytest.raises(StopRun):
        n4.fail(rec, 'copy-only-seed', 'x')
    assert rec.rows == [('copy-only-seed', 'FAIL', 'x')]


def _chain_harness(tmp_path, monkeypatch, files, ops=None):
    h = FakeHarness(tmp_path)
    h.seen = []

    def go(tag, argv, rw, ro, **kw):
        h.seen.append((tag, argv, rw, ro, kw))
        return SimpleNamespace(code=0, out='', err='', ops=ops or n4.CLEAN)

    h.go = go
    monkeypatch.setattr(n2, 'look_at', lambda path: files.get(path))
    monkeypatch.setattr(n2, 'done_item', lambda d: n2.Item('write_ok', 'done', 'c', 'donefile', 'D'))
    return h


def test_chain_run_returns_on_a_held_boundary_and_fails_on_a_breach_a_control_or_an_unclean_end(tmp_path, monkeypatch):
    items = [n2.Item('write_ok', 'ctl', 'c', 'in', 'TOK'), n2.Item('write_no', 'out', 'c', 'outside', None)]
    base = {'in': 'TOK', 'donefile': 'D'}
    h = _chain_harness(tmp_path, monkeypatch, base)
    run = n4.chain_run(h, Rec(), 'copy-only-seed', 't', items, ('R',), ('RO',), seed=('a', 'b'))
    tag, argv, rw, ro, kw = h.seen[0]
    assert run.ops == n4.CLEAN and (tag, rw, ro, kw) == ('t', ('R',), ('RO',), {'seed': ('a', 'b')})
    assert argv[0] == h.cmd and argv[1:4] == ['/d', '/s', '/c']
    for files, ops, what in ((dict(base, outside='bad'), None, 'BREACH'), ({'donefile': 'D'}, None, 'control'),
                             ({'in': 'TOK'}, None, 'control'), (base, n4.QUARANTINED, 'not clean')):
        h = _chain_harness(tmp_path, monkeypatch, files, ops)
        rec = Rec()
        with pytest.raises(StopRun):
            n4.chain_run(h, rec, 'copy-only-seed', 't', items, ('R',), ())
        assert what in rec.rows[-1][2]


def test_a_canary_pairs_an_inside_write_with_an_outside_denial_in_one_chain(tmp_path, monkeypatch):
    h = FakeHarness(tmp_path)
    got = {}

    def chain_run(h_, rec, case, tag, items, rw, ro, **kw):
        got.update(tag=tag, items=items, rw=rw, ro=ro)

    monkeypatch.setattr(n4, 'chain_run', chain_run)
    rec = Rec()
    n4.canary(h, rec, 'real-cli-fake-broker', 'pre')
    assert rec.statuses() == ['PASS'] and got['tag'] == 'canary_pre' and got['ro'] == (h.lay['toolchain'],)
    kinds = [i.kind for i in got['items']]
    assert kinds == ['write_ok', 'write_no']
    assert _under(got['rw'][0], h.lay['faults']) and _under(got['items'][1].path, h.lay['outside'])
    assert _under(got['items'][0].path, got['rw'][0])


class ImportNode:
    """store_read and import_workspace as Core's would answer, scripted per call."""

    def __init__(self, results):
        self.results, self.calls, self.names = list(results), 0, ''

    def import_workspace(self, project, eid, commit, workdirs=()):
        self.calls += 1
        out = self.results.pop(0)
        if isinstance(out, Exception):
            raise out
        return out

    def store_read(self, project, args, workdirs=()):
        return self.names


def _import_harness(tmp_path, monkeypatch, results, names=''):
    node = ImportNode(results)
    node.names = names
    h = FakeHarness(tmp_path)
    h.m.local.LocalNode = node
    h.node = node
    monkeypatch.setattr(n4, 'chain_run', lambda *a, **k: None)
    monkeypatch.setattr(n2, '_junction', lambda h_, link, target: None)
    monkeypatch.setattr(n2, '_unjunction', lambda link: None)
    return h


EXACT = {'revision': 'a' * 40, 'files_changed': ['M notes.txt', 'A new_file.txt', 'A done.txt', 'D src/app.txt']}


def test_step_import_passes_an_exact_changed_set_a_refused_replay_and_an_unfollowed_junction(tmp_path, monkeypatch):
    h = _import_harness(tmp_path, monkeypatch, [EXACT, RuntimeError('replay'), {'revision': 'b' * 40}], names='notes.txt\n')
    rec = Rec()
    n4.step_import(h, rec)
    assert rec.statuses() == ['PASS', 'PASS'] and h.node.calls == 3


@pytest.mark.parametrize('results,names,word', [
    ([dict(EXACT, files_changed=EXACT['files_changed'] + ['A .git/agent_marker.txt'])], '', 'import:'),
    ([dict(EXACT, files_changed=['M notes.txt'])], '', 'import:'),
    ([RuntimeError('x')], '', 'raised RuntimeError'),
    ([EXACT, EXACT], '', 'second import'),
    ([EXACT, RuntimeError('replay'), {'revision': 'b' * 40}], 'notes.txt\nknown.txt\n', 'junction')])
def test_step_import_fails_on_each_wrong_outcome(tmp_path, monkeypatch, results, names, word):
    h = _import_harness(tmp_path, monkeypatch, results, names=names)
    rec = Rec()
    with pytest.raises(StopRun):
        n4.step_import(h, rec)
    assert word in rec.rows[-1][2]


def test_step_import_treats_a_refused_junction_import_as_held_and_always_removes_the_link(tmp_path, monkeypatch):
    h = _import_harness(tmp_path, monkeypatch, [EXACT, RuntimeError('replay'), RuntimeError('refused')])
    removed = []
    monkeypatch.setattr(n2, '_unjunction', removed.append)
    rec = Rec()
    n4.step_import(h, rec)
    assert rec.statuses() == ['PASS', 'PASS'] and 'refused' in rec.rows[-1][2] and len(removed) == 1


def _hostile_harness(tmp_path, monkeypatch, control_fires=True, core_fires=False, core_edits_config=False, core_raises=False):
    h = FakeHarness(tmp_path)

    def import_workspace(project, eid, commit, workdirs=()):
        work = os.path.join(str(tmp_path), 'work2')
        if core_fires:
            open(os.path.join(h.lay['ctl'], 'core', 'fired_fsmonitor.txt'), 'w').close()
        if core_edits_config:
            open(os.path.join(work, '.git', 'config'), 'a').write('# changed\n')
        if core_raises:
            raise RuntimeError('refused')
        return {'revision': 'a' * 40}

    h.m.local.LocalNode = SimpleNamespace(import_workspace=import_workspace, store_read=lambda *a, **k: 'x')
    h.git = []

    def naive(h_, work):
        h.git.append(work)
        if control_fires:
            open(os.path.join(h.lay['ctl'], 'naive', 'fired_clean.txt'), 'w').close()
        return 'rc=1'

    monkeypatch.setattr(n4, 'naive_git', naive)
    return h


def test_step_hostile_passes_when_the_control_fires_and_core_stays_quiet(tmp_path, monkeypatch):
    h = _hostile_harness(tmp_path, monkeypatch)
    rec = Rec()
    n4.step_hostile(h, rec)
    assert rec.statuses() == ['PASS'] and len(h.git) == 1
    control = h.git[0]
    assert os.path.isfile(os.path.join(control, '.git', 'hooks', 'pre-commit'))          # the planted state reached disk
    assert open(os.path.join(control, '.git', 'config'), encoding='utf-8').read().count('fired_') == 6
    assert _under(control, str(tmp_path))                                                # only fixture workspaces


def test_step_hostile_is_inconclusive_when_the_control_never_fires(tmp_path, monkeypatch):
    h = _hostile_harness(tmp_path, monkeypatch, control_fires=False)
    rec = Rec()
    n4.step_hostile(h, rec)
    assert rec.statuses() == ['INCONCLUSIVE'] and 'proves nothing' in rec.rows[0][2]


@pytest.mark.parametrize('kw', [{'core_fires': True}, {'core_edits_config': True},
                                {'core_fires': True, 'control_fires': False}])
def test_step_hostile_fails_when_core_fires_a_marker_or_changes_the_config(tmp_path, monkeypatch, kw):
    h = _hostile_harness(tmp_path, monkeypatch, **kw)
    rec = Rec()
    with pytest.raises(StopRun):
        n4.step_hostile(h, rec)
    assert rec.statuses() == ['FAIL']


def test_step_hostile_accepts_a_core_that_refuses_the_import(tmp_path, monkeypatch):
    h = _hostile_harness(tmp_path, monkeypatch, core_raises=True)
    rec = Rec()
    n4.step_hostile(h, rec)
    assert rec.statuses() == ['PASS'] and 'refused (RuntimeError)' in rec.rows[0][2]


def test_naive_git_is_labelled_and_reports_when_there_is_no_absolute_git(tmp_path, monkeypatch):
    h = FakeHarness(tmp_path)
    monkeypatch.setattr(n4.shutil, 'which', lambda name: None)
    assert n4.naive_git(h, str(tmp_path)) == 'no absolute git on PATH'
    monkeypatch.setattr(n4.shutil, 'which', lambda name: 'git')
    assert n4.naive_git(h, str(tmp_path)) == 'no absolute git on PATH'


def test_naive_git_runs_only_the_three_labelled_commands_in_the_given_folder_with_a_bare_environment(tmp_path, monkeypatch):
    h = FakeHarness(tmp_path)
    exe = str(tmp_path / 'bin' / 'git.exe')
    monkeypatch.setattr(n4.shutil, 'which', lambda name: exe)
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(returncode=len(calls))

    monkeypatch.setattr(n4.subprocess, 'run', run)
    assert n4.naive_git(h, str(tmp_path)) == 'rc=3'
    assert [c[0][1] for c in calls] == ['status', 'add', '-c']
    for argv, kw in calls:
        assert argv[0] == exe and kw['cwd'] == str(tmp_path) and 'shell' not in kw and kw['timeout'] == 60
        assert set(kw['env']) == {'SYSTEMROOT', 'PATH', 'HOME', 'GIT_CONFIG_NOSYSTEM', 'GIT_TERMINAL_PROMPT'}
        assert kw['env']['HOME'] == h.lay['envhome']


def test_plant_writes_the_files_with_unix_newlines(tmp_path):
    n4.plant(str(tmp_path), {'.git/hooks/x': 'a\nb\n', 'top.txt': 'c'})
    assert (tmp_path / '.git' / 'hooks' / 'x').read_bytes() == b'a\nb\n' and (tmp_path / 'top.txt').read_bytes() == b'c'


# ---------------------------------------------------------------- verifiers over the real id and path contracts

def _verifier_harness(tmp_path, monkeypatch, result=None, replay='isolation: attempt_consumed', profiles=None,
                      record_twice=False, judged=None):
    from archeus.core.domain import ids
    from archeus.infra import paths
    from archeus.node import isolation, mxc_ledger
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'ah'))
    h = FakeHarness(tmp_path)
    h.m = SimpleNamespace(ids=ids, paths=paths, isolation=isolation, mxc_ledger=mxc_ledger)
    h.api = SimpleNamespace(creates=0)
    h.ledger = None
    h.seeds = {'home': 'h', 'ledger': 'l'}
    h.calls = []
    profile = iter(profiles or ['p1', 'p2', 'p3'])

    def run_confined_check(vid, attempt, argv, toolchain, timeout, record, project_id, revision, workdirs):
        h.calls.append((vid, attempt, toolchain))
        if len([c for c in h.calls if c[:2] == (vid, attempt)]) > 1:
            return {'error': replay}
        h.api.creates += 1
        record({'v': 1})
        if record_twice:
            record({'v': 2})
        return result or {'error': None, 'exit_code': 0, 'confinement': {'ac_profile': next(profile)}}

    h.node = SimpleNamespace(run_confined_check=run_confined_check)
    monkeypatch.setattr(n2, 'judge', lambda items, look: judged)
    monkeypatch.setattr(n2, 'journal_ops', lambda read, ledger, name: (n4.CLEAN, False))
    return h


def test_step_verifiers_runs_three_attempts_as_fresh_identities_and_refuses_a_replay(tmp_path, monkeypatch):
    h = _verifier_harness(tmp_path, monkeypatch)
    rec = Rec()
    n4.step_verifiers(h, rec)
    assert rec.statuses() == ['PASS'] and len(h.calls) == 4
    assert h.calls[0][:2] == h.calls[3][:2] and h.calls[0][1] == 0 and h.calls[2][1] == 1
    assert h.calls[2][0] == h.calls[0][0] != h.calls[1][0]
    assert all(c[2] == [h.lay['toolchain']] for c in h.calls)


def test_the_verifier_journal_key_is_a_legal_journal_name(tmp_path, monkeypatch):
    h = _verifier_harness(tmp_path, monkeypatch)
    vid = h.m.ids.new_id('verification')
    key = h.m.isolation.Principal('verify', vid, 0).key
    assert h.m.mxc_ledger.journal_name(key, 1).endswith('-p1')


@pytest.mark.parametrize('kw,word', [
    ({'result': {'error': 'x', 'exit_code': 0, 'confinement': {'ac_profile': 'p'}}}, 'verifier result'),
    ({'profiles': ['p1', 'p1', 'p3']}, 'not fresh'),
    ({'record_twice': True}, 'recorded 2 times'),
    ({'judged': ('breach', 'home-read')}, 'containment breach'),
    ({'judged': ('control', 'scratch-write')}, 'control failed'),
    ({'replay': None}, 'consumed attempt was read again')])
def test_step_verifiers_fails_on_each_wrong_outcome(tmp_path, monkeypatch, kw, word):
    h = _verifier_harness(tmp_path, monkeypatch, **kw)
    rec = Rec()
    with pytest.raises(StopRun):
        n4.step_verifiers(h, rec)
    assert word in rec.rows[-1][2]


def test_step_verifiers_reports_a_check_that_raises_without_a_stale_hint(tmp_path, monkeypatch):
    h = _verifier_harness(tmp_path, monkeypatch)

    def boom(*a, **k):
        raise TimeoutError('launcher I/O deadline')

    h.node = SimpleNamespace(run_confined_check=boom)
    rec = Rec()
    with pytest.raises(StopRun):
        n4.step_verifiers(h, rec)
    assert 'TimeoutError' in rec.rows[-1][2] and 'child.wait' not in rec.rows[-1][2]


# ---------------------------------------------------------------- run order and the stub rows

def test_run_drives_the_steps_in_the_frozen_order_and_stops_at_the_first_failing_one(monkeypatch):
    order = []
    names = ('seed', 'cli', 'stream', 'import', 'hostile', 'verifiers', 'authority', 'limits')
    for name in names:
        monkeypatch.setattr(n4, 'step_' + name, lambda h, rec, n=name: order.append(n))
    monkeypatch.setattr(n4, 'stubs', lambda rec: order.append('stubs'))
    h = SimpleNamespace(prepare=lambda: order.append('prepare'))
    n4.run(h, Rec())
    assert order == ['prepare'] + list(names) + ['stubs']
    order.clear()

    def stop(h, rec):
        raise StopRun('x')

    monkeypatch.setattr(n4, 'step_import', stop)
    with pytest.raises(StopRun):
        n4.run(h, Rec())
    assert order == ['prepare', 'seed', 'cli', 'stream']


def test_stubs_make_every_case_inconclusive_so_a_clean_run_exits_two(capsys):
    rec = common.Recorder('N4')
    n4.stubs(rec)
    assert [c for c, s in rec.results] == list(STAGES['N4'].cases) and {s for _, s in rec.results} == {'INCONCLUSIVE'}
    assert rec.exit_code() == 2
    assert 'separately-authorized-live-provider' in capsys.readouterr().out


# ---------------------------------------------------------------- main, over fakes

def _main_world(tmp_path, monkeypatch, behave, left=0, claude=True, curl=True):
    parent = tmp_path / 'fx'
    sdk = parent.joinpath(*n2.SDK_TAIL)
    sdk.mkdir(parents=True)
    (sdk / 'package.json').write_text('{}', encoding='utf-8')
    if claude:
        (parent / 'cli').mkdir()
        (parent / 'cli' / 'claude.exe').write_bytes(b'')
    windows = tmp_path / 'Windows'
    (windows / 'System32').mkdir(parents=True)
    if curl:
        (windows / 'System32' / 'curl.exe').write_bytes(b'')
    root = tmp_path / 'root'
    root.mkdir()
    calls = SimpleNamespace(removed=[], winddown=0, safe_root=0, args=None)

    def fake_safe_root(p):
        calls.safe_root += 1
        return str(root)

    class FakeH:
        def __init__(self, *a):
            calls.args = a

        def wind_down(self):
            calls.winddown += 1
            return left

    monkeypatch.setattr(n2, 'parent_ok', lambda p: True)
    monkeypatch.setattr(n2, '_on_windows', lambda: True)
    monkeypatch.setattr(n2, '_system_ok', lambda v: True)
    monkeypatch.setattr(n4, 'safe_root', fake_safe_root)
    monkeypatch.setattr(n4, 'remove_fixture', calls.removed.append)
    monkeypatch.setattr(n4, 'Harness', FakeH)
    monkeypatch.setattr(n4, 'run', behave)
    monkeypatch.setenv('SystemRoot', str(windows))
    return str(parent), str(root), calls


def _all(h, rec, status='PASS', but=None):
    for case in STAGES['N4'].cases:
        rec.record(case, but if case == 'two-fresh-verifiers' and but else status, 'x')


def test_main_hands_the_harness_the_staged_sdk_and_cli_and_removes_on_exit_zero_only_once(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all)
    assert n4.main([parent]) == 0
    assert calls.removed == [root] and calls.winddown == 1
    assert calls.args[0] == root and calls.args[1] == os.path.join(parent, *n2.SDK_TAIL)
    assert calls.args[2] == os.path.join(parent, 'cli') and calls.args[3] == os.environ['SystemRoot']


def test_main_keeps_the_fixture_on_inconclusive(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, lambda h, rec: _all(h, rec, but='INCONCLUSIVE'))
    assert n4.main([parent]) == 2
    assert calls.removed == []


def test_main_stops_at_the_first_fail_and_keeps_the_fixture(tmp_path, monkeypatch):
    seen = []

    def behave(h, rec):
        rec.record('copy-only-seed', 'FAIL', 'bad')
        seen.append('ran past the fail')

    parent, root, calls = _main_world(tmp_path, monkeypatch, behave)
    assert n4.main([parent]) == 1
    assert calls.removed == [] and seen == [] and calls.winddown == 1


@pytest.mark.parametrize('exc', [n2.SetupError('x'), RuntimeError('boom'), KeyError('k'), KeyboardInterrupt()])
def test_main_setup_and_unexpected_errors_exit_three_and_keep_the_fixture(tmp_path, monkeypatch, exc):
    def behave(h, rec):
        raise exc

    parent, root, calls = _main_world(tmp_path, monkeypatch, behave)
    assert n4.main([parent]) == 3
    assert calls.removed == [] and calls.winddown == 1


def test_a_surviving_launcher_turns_a_clean_run_into_exit_three_without_deleting(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all, left=1)
    assert n4.main([parent]) == 3
    assert calls.removed == []


def test_a_run_that_recorded_nothing_never_passes(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, lambda h, rec: None)
    assert n4.main([parent]) == 2
    assert calls.removed == []


def test_the_journal_lands_in_the_root(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, lambda h, rec: _all(h, rec, but='INCONCLUSIVE'))
    n4.main([parent])
    lines = open(os.path.join(root, n4.JOURNAL), encoding='utf-8').read().splitlines()
    assert len(lines) == len(STAGES['N4'].cases) and {json.loads(x)['case'] for x in lines} == set(STAGES['N4'].cases)


def test_main_refuses_before_creating_anything(tmp_path, monkeypatch, capsys):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all)
    monkeypatch.setattr(n2, 'parent_ok', lambda p: False)
    assert n4.main([parent]) == 3                                    # a parent outside the fixture base
    monkeypatch.setattr(n2, 'parent_ok', lambda p: True)
    assert n4.main([]) == 3 and n4.main([parent, 'extra']) == 3
    monkeypatch.setattr(n2, '_on_windows', lambda: False)
    assert n4.main([parent]) == 3
    monkeypatch.setattr(n2, '_on_windows', lambda: True)
    monkeypatch.setattr(n2, '_system_ok', lambda v: False)
    assert n4.main([parent]) == 3
    monkeypatch.setattr(n2, '_system_ok', lambda v: True)
    assert n4.main([str(tmp_path / 'nope')]) == 3
    os.rename(os.path.join(parent, 'cli', 'claude.exe'), os.path.join(parent, 'cli', 'claude.old'))
    assert n4.main([parent]) == 3                                    # staged CLI missing
    os.rename(os.path.join(parent, 'cli', 'claude.old'), os.path.join(parent, 'cli', 'claude.exe'))
    os.rename(os.path.join(parent, 'sdk'), os.path.join(parent, 'sdk2'))
    assert n4.main([parent]) == 3                                    # staged SDK missing
    assert calls.safe_root == 0 and calls.removed == [] and capsys.readouterr().out


def test_main_refuses_a_system_folder_without_curl(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all, curl=False)
    assert n4.main([parent]) == 3 and calls.safe_root == 0


def test_main_does_not_delete_when_the_removal_itself_refuses(tmp_path, monkeypatch):
    parent, root, calls = _main_world(tmp_path, monkeypatch, _all)

    def refuse(r):
        raise ValueError('root is not a fixture tree')

    monkeypatch.setattr(n4, 'remove_fixture', refuse)
    assert n4.main([parent]) == 3


# ---------------------------------------------------------------- the script's own source

def _tree():
    with open(SRC, encoding='utf-8') as fh:
        text = fh.read()
    return text, ast.parse(text)


def _function_of(tree, node):
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.ClassDef)) and any(n is node for n in ast.walk(fn)):
            yield fn.name


def _step_cases(tree):
    """The string a step_* function binds to its `case` variable, then passes to record()."""
    out = {}
    for fn in tree.body:
        if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith('step_')):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assign):
                continue
            target, value = node.targets[0], node.value
            if isinstance(target, ast.Name) and target.id == 'case' and isinstance(value, ast.Constant):
                out[fn.name] = value.value
            elif isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple):
                for t, v in zip(target.elts, value.elts):
                    if isinstance(t, ast.Name) and t.id == 'case' and isinstance(v, ast.Constant):
                        out[fn.name] = v.value
    return out


def test_every_protocol_case_has_a_step_and_a_stub_and_the_live_case_only_a_stub():
    _, tree = _tree()
    cases = _step_cases(tree)
    assert len(cases) == 8 and len(set(cases.values())) == 8
    assert set(cases.values()) == set(STAGES['N4'].cases) - {n4.LIVE_CASE}
    assert n4.LIVE_CASE in STAGES['N4'].cases and n4.LIVE_CASE not in cases.values()
    assert [c for c, _ in n4.STUBS] == list(STAGES['N4'].cases)
    assert all(why.startswith(('missing contract', 'stand-in', 'not run')) for _, why in n4.STUBS)
    assert dict(n4.STUBS)[n4.LIVE_CASE].startswith('not run')
    assert n4.STAGE == 'N4' and n4.BUDGET_S < STAGES['N4'].budget and n4.CASES == STAGES['N4'].cases


def test_steps_record_their_own_case_only():
    _, tree = _tree()
    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef) and fn.name.startswith('step_'):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'record':
                    assert isinstance(node.args[0], ast.Name) and node.args[0].id == 'case', fn.name


def test_the_source_uses_no_acl_profile_or_shell_facility():
    text, _ = _tree()
    code_only = text.split('"""', 2)[2].lower()
    for word in ('icacls', 'takeown', 'set-acl', 'powershell', 'taskkill', 'rmtree', 'os.system', 'shell=true',
                 'win32security', 'urllib', 'http.client', 'requests', 'ctypes', 'createappcontainer'):
        assert word not in code_only, word
    assert '.format(' not in text


def test_only_these_modules_are_imported_and_no_native_or_external_network_library():
    _, tree = _tree()
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module)
    assert mods == {'http.server', 'json', 'ntpath', 'os', 're', 'shutil', 'socket', 'stat', 'subprocess', 'sys',
                    'threading', 'time', 'collections', 'types', 'tools.pv20_mxc.native', 'tools.pv20_mxc.native.common',
                    'tools.pv20_mxc.protocol'}


def test_every_socket_and_server_address_is_the_loopback_constant():
    text, tree = _tree()
    assert n4.LOOPBACK == '127.0.0.1'
    addressed = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = getattr(n.func, 'attr', getattr(n.func, 'id', ''))
            if name in ('bind', 'create_connection', 'ThreadingHTTPServer', 'connect', 'HTTPServer'):
                tuples = [a for a in n.args if isinstance(a, ast.Tuple)]
                assert tuples and isinstance(tuples[0].elts[0], ast.Name) and tuples[0].elts[0].id == 'LOOPBACK', name
                addressed += 1
    assert addressed == 3
    assert '0.0.0.0' not in text


def test_sockets_are_made_only_by_the_listeners_and_the_host_touch():
    _, tree = _tree()
    where = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'socket' \
                and n.attr in ('socket', 'create_connection'):
            where |= set(_function_of(tree, n))
    assert where == {'Forbidden', '__init__', 'host_touch'}


def test_the_only_subprocess_call_is_the_labelled_host_control():
    _, tree = _tree()
    where = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == 'subprocess':
            where |= set(_function_of(tree, n))
    assert where == {'naive_git'}
    shutil_use = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                  and isinstance(n.value, ast.Name) and n.value.id == 'shutil'}
    assert shutil_use == {'copytree', 'which'}


def test_destructive_calls_are_confined_to_the_functions_that_own_them():
    _, tree = _tree()
    where = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in ('rmdir', 'unlink', 'link', '_terminate_process', 'remove',
                                                         'rename', 'replace', 'rmtree', '_unjunction', '_junction'):
            if n.attr == 'replace' and not (isinstance(n.value, ast.Name) and n.value.id == 'os'):
                continue                                                 # str.replace
            where.setdefault(n.attr, set()).update(_function_of(tree, n))
    assert where['_terminate_process'] == {'wind_down', 'Harness'}
    assert where['unlink'] == {'step_seed'} and where['link'] <= {'step_seed', 'plant_then_recheck'}
    assert where['_unjunction'] == {'step_import'} and where['_junction'] == {'step_import'}
    for name in ('rmdir', 'remove', 'rename', 'replace', 'rmtree'):
        assert name not in where, name


def test_the_only_environment_reads_are_systemroot_and_the_import_window():
    _, tree = _tree()
    reads = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in ('environ', 'getenv'):
            reads.append(set(_function_of(tree, n)) - {'Harness'})
    assert reads and all(r <= {'prepare', 'main'} for r in reads)
    sysroot = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == 'get' and n.args and isinstance(n.args[0], ast.Constant)
               and n.args[0].value == 'SystemRoot']
    assert len(sysroot) == 1


def test_only_the_names_the_native_contract_allows_are_imported_from_common():
    _, tree = _tree()
    names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             and n.module == 'tools.pv20_mxc.native.common' for a in n.names}
    assert names == {'Recorder', 'StopRun', 'redact', 'remove_fixture', 'safe_root'}


def test_module_level_code_only_defines_things():
    _, tree = _tree()
    for node in tree.body:
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)    # the docstring
        elif isinstance(node, ast.Assign):
            calls = [c for c in ast.walk(node.value) if isinstance(c, ast.Call)]
            assert all(getattr(c.func, 'id', '') == 'namedtuple' for c in calls), ast.dump(node)[:80]
        elif isinstance(node, ast.If):
            assert ast.unparse(node.test) == "__name__ == '__main__'"
        else:
            assert isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)), type(node)


def test_importing_the_module_runs_nothing(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError('import touched the host')

    with monkeypatch.context() as patch:
        patch.setattr(socket, 'socket', refuse)
        patch.setattr(socket, 'create_connection', refuse)
        patch.setattr(n4.subprocess, 'Popen', refuse)
        patch.setattr(n4.subprocess, 'run', refuse)
        patch.setattr(os, 'makedirs', refuse)
        patch.setattr(os, 'mkdir', refuse)
        patch.setattr(threading.Thread, 'start', refuse)
        patch.setattr('builtins.open', refuse)
        fresh = importlib.reload(n4)
    assert fresh.STAGE == 'N4' and fresh.CASES == STAGES['N4'].cases


def test_the_source_text_passes_the_static_acl_words_gate():
    text, _ = _tree()
    low = text.lower()
    assert 'icacls' not in low and 'takeown' not in low and 'set-acl' not in low
