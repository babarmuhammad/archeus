"""Dashboard endpoint tests — /api/dashboard aggregate shape + the
always-show usage contract on /api/usage_plan (empty accounts never dropped)."""

import json
import os
import threading
import time
import urllib.request

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, make_jsonl
from claude_sessions import gui
from claude_sessions import gui_api


def _serve(monkeypatch):
    srv = gui.make_server(0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'


def _req(url, body=None, headers=None):
    h = {'X-Archeus': gui.TOKEN}
    if headers is not None:
        h = headers
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h,
                               method='POST' if data else 'GET')
    with urllib.request.urlopen(r) as resp:
        return resp.status, json.loads(resp.read() or b'{}')


def _fresh(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    gui_api._dash_cache = None            # dashboard caches 10s module-global
    gui_api._dash_cached_at = 0.0
    with gui_api._JOBS_LOCK:
        gui_api._JOBS.clear()
    return sb


def _seed(sb, monkeypatch):
    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = 'X--enc-alpha'
    folder = sb.projects / enc
    folder.mkdir()
    sid = 'aaaa0000-0000-0000-0000-000000000000'
    make_jsonl(str(folder / f'{sid}.jsonl'), title='Fix the bug')
    monkeypatch.setattr(gui, 'find_actual_path', lambda e, *a, **k: actual if e == enc else None)
    return actual, enc, sid


def _write_today(path, model, tokens=1000):
    """Transcript stamped *now*, so it lands inside the breakdown window."""
    import datetime
    ts = datetime.datetime.now().astimezone().isoformat()
    rows = [{'role': 'user', 'content': 'hello there', 'timestamp': ts},
            {'type': 'assistant',
             'message': {'role': 'assistant', 'model': model,
                         'usage': {'input_tokens': tokens, 'output_tokens': tokens,
                                   'cache_read_input_tokens': 0,
                                   'cache_creation_input_tokens': 0},
                         'content': [{'type': 'text', 'text': 'hi'}]},
             'timestamp': ts}]
    with open(path, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')


def test_dashboard_breakdown_splits_accounts_and_flags_omni(monkeypatch, tmp_path):
    """One scan feeds the whole dashboard: per-day tokens attributed per account,
    per-project OmniRoute flag, and free-tier tokens costed at zero."""
    sb = _fresh(monkeypatch, tmp_path)
    second = tmp_path / 'cfg2' / 'projects'
    second.mkdir(parents=True)
    monkeypatch.setattr('claude_sessions.config.all_config_dirs',
                        lambda: [('default', str(sb.cfg)), ('work', str(tmp_path / 'cfg2'))])
    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = 'X--enc-alpha'
    (sb.projects / enc).mkdir()
    (second / enc).mkdir()
    _write_today(sb.projects / enc / 'a.jsonl', 'claude-sonnet-4-6')
    _write_today(second / enc / 'b.jsonl', 'big-pickle')       # OmniRoute free tier
    for mod in ('claude_sessions.gui.find_actual_path',
                'claude_sessions.paths.find_actual_path'):
        monkeypatch.setattr(mod, lambda e, *a, **k: actual if e == enc else None)
    srv, base = _serve(monkeypatch)
    try:
        _code, d = _req(f'{base}/api/dashboard')
        bd = d['breakdown']
        accts = {a['account']: a for a in bd['accounts']}
        assert set(accts) == {'default', 'work'}
        assert accts['work']['omni_tokens'] > 0
        assert accts['work']['cost'] == 0.0            # free-tier model costs nothing
        assert accts['default']['omni_tokens'] == 0
        assert accts['default']['cost'] > 0
        today = bd['days'][-1]
        assert today['tokens'] > 0
        assert sum(today['accounts'].values()) == today['tokens']
        assert set(today['accounts']) == {'default', 'work'}
        proj = bd['projects'][0]
        assert proj['omni'] is True
        assert sorted(proj['accounts']) == ['default', 'work']
        assert bd['totals']['omni_saved'] > 0          # what OmniRoute avoided
    finally:
        srv.shutdown()


def test_dashboard_recent_spans_accounts_and_skips_headless_oneshots(monkeypatch, tmp_path):
    """Recent sessions come from the transcript scan, not last-session.json —
    that store only knows sessions archeus itself launched, so anything opened
    with `claude` directly (or under another account) never appeared."""
    sb = _fresh(monkeypatch, tmp_path)
    second = tmp_path / 'cfg2' / 'projects'
    second.mkdir(parents=True)
    monkeypatch.setattr('claude_sessions.config.all_config_dirs',
                        lambda: [('default', str(sb.cfg)), ('work', str(tmp_path / 'cfg2'))])
    actual = str(sb.root / 'work' / 'alpha')
    os.makedirs(actual, exist_ok=True)
    enc = 'X--enc-alpha'
    (sb.projects / enc).mkdir()
    (second / enc).mkdir()
    make_jsonl(str(sb.projects / enc / 'real-default.jsonl'), n_msgs=12, title='Real work')
    make_jsonl(str(second / enc / 'real-work.jsonl'), n_msgs=12, title='Other account')
    make_jsonl(str(sb.projects / enc / 'oneshot.jsonl'), n_msgs=2, title='Distil lessons')
    for mod in ('claude_sessions.gui.find_actual_path',
                'claude_sessions.paths.find_actual_path'):
        monkeypatch.setattr(mod, lambda e, *a, **k: actual if e == enc else None)
    srv, base = _serve(monkeypatch)
    try:
        _code, d = _req(f'{base}/api/dashboard')
        sids = [r['sid'] for r in d['recent']]
        assert 'real-default' in sids and 'real-work' in sids
        assert 'oneshot' not in sids
        assert {r['account'] for r in d['recent']} == {'default', 'work'}
        assert all(r['mtime'] > 0 and r['age'] for r in d['recent'])
    finally:
        srv.shutdown()


def test_dashboard_week_is_7_and_increasing(monkeypatch, tmp_path):
    sb = _fresh(monkeypatch, tmp_path)
    _seed(sb, monkeypatch)
    srv, base = _serve(monkeypatch)
    try:
        _code, d = _req(f'{base}/api/dashboard')
        assert _code == 200
        week = d['week']
        assert len(week) == 7
        dates = [w['date'] for w in week]
        assert dates == sorted(dates)
        assert len(set(dates)) == 7            # strictly increasing, no dupes
    finally:
        srv.shutdown()


def test_dashboard_jobs_elapsed_is_int(monkeypatch, tmp_path):
    _fresh(monkeypatch, tmp_path)
    job = gui_api.new_job('test job', jid='fakejob123')
    with gui_api._JOBS_LOCK:
        gui_api._JOBS[job['id']] = job
    srv, base = _serve(monkeypatch)
    try:
        _code, d = _req(f'{base}/api/dashboard')
        jobs = d['jobs']
        assert any(j['id'] == 'fakejob123' for j in jobs)
        assert all(isinstance(j['elapsed'], int) for j in jobs)
    finally:
        srv.shutdown()


def test_usage_plan_returns_every_configured_account(monkeypatch, tmp_path):
    """An account configured but with zero transcripts still appears — the
    regression guard for 'usage must always show'."""
    sb = _fresh(monkeypatch, tmp_path)
    empty_dir = tmp_path / 'empty-cfg'
    empty_dir.mkdir()
    with open(sb.settings, 'w', encoding='utf-8') as f:
        json.dump({'accounts': [{'name': 'second', 'dir': str(empty_dir)}]}, f)
    srv, base = _serve(monkeypatch)
    try:
        _code, d = _req(f'{base}/api/usage/plan')
        accts = {a['account']: a for a in d['accounts']}
        assert 'default' in accts
        assert 'second' in accts
        assert accts['second']['windows'] == []      # zero data → empty windows
    finally:
        srv.shutdown()


# ── the Activity card ─────────────────────────────────────────

def _mk_acct(tmp_path, name, enc, when, n_msgs=12):
    """One account dir holding one project with one transcript, touched at
    `when`. Returns the (mtime, path, enc, cfgdir) entry assemble_breakdown
    consumes — built directly, so this exercises the aggregation rather than
    the path-resolution layer around it."""
    import os
    cfg = tmp_path / name
    proj = cfg / 'projects' / enc
    proj.mkdir(parents=True)
    j = proj / f'{enc}-0000-0000-0000-000000000000.jsonl'
    make_jsonl(j, n_msgs=n_msgs, title=enc)
    os.utime(j, (when, when))
    work = tmp_path / 'work' / enc
    work.mkdir(parents=True, exist_ok=True)
    return (when, str(work), enc, str(cfg))


def test_live_sessions_are_counted_across_every_account(monkeypatch, tmp_path):
    """The Activity card reads LIVE CLAUDE CODE SESSIONS, cross-account.

    It used to read archeus's own background-job count, which is almost
    always zero — so on a workspace burning hundreds of millions of tokens a day
    the card sat at "0 RUNNING" and flat. It reported the tool's idleness, not
    the workspace's.

        "activity section on the dashboard never shows anything, it's always
         like this … activity should be for all accounts working"
    """
    from claude_sessions import config
    from claude_sessions.stats import assemble_breakdown, LIVE_WINDOW

    now = time.time()
    e1 = _mk_acct(tmp_path, 'cfg-a', 'alpha', now)
    e2 = _mk_acct(tmp_path, 'cfg-b', 'beta', now)
    monkeypatch.setattr(config, 'all_config_dirs',
                        lambda: [('default', e1[3]), ('second', e2[3])])

    bd = assemble_breakdown([e1, e2], days=14)
    live = bd['live']
    assert live['window'] == LIVE_WINDOW
    assert live['total'] == 2, live
    # …and it must attribute them, or "for all accounts" means nothing
    assert set(live['by_account']) == {'default', 'second'}, live
    assert sum(live['by_account'].values()) == live['total']


def test_a_stale_session_is_not_live(monkeypatch, tmp_path):
    """Outside the window it stops counting — the card is supposed to reach
    zero. The bug was that it never left it."""
    from claude_sessions import config
    from claude_sessions.stats import assemble_breakdown, LIVE_WINDOW

    old = time.time() - LIVE_WINDOW * 4
    e = _mk_acct(tmp_path, 'cfg-a', 'alpha', old)
    monkeypatch.setattr(config, 'all_config_dirs', lambda: [('default', e[3])])

    bd = assemble_breakdown([e], days=14)
    assert bd['live']['total'] == 0, bd['live']
    # but it still shows in the 24h bars — which is why there are both
    assert len(bd['hours']) == 24
    assert sum(bd['hours']) >= 1, bd['hours']


def test_archeus_own_one_shots_do_not_read_as_activity(monkeypatch, tmp_path):
    """Lesson distilling, graph building and title extraction all land in the
    same transcript store and are a couple of turns each. Counting them would
    mean memory refreshing itself looked like you working."""
    from claude_sessions import config
    from claude_sessions.stats import assemble_breakdown

    now = time.time()
    e = _mk_acct(tmp_path, 'cfg-a', 'alpha', now, n_msgs=2)
    monkeypatch.setattr(config, 'all_config_dirs', lambda: [('default', e[3])])

    bd = assemble_breakdown([e], days=14)
    assert bd['live']['total'] == 0, bd['live']
    assert sum(bd['hours']) == 0, bd['hours']


def test_activity_bars_are_hours_not_days():
    """`days.slice(-24)` was the last 24 DAYS out of a 14-day window — a sparse
    trend chart in a card called Activity."""
    from claude_sessions.gui_html import PAGE
    assert "series:d.hours||[]" in PAGE
    assert "series:days.slice(-24)" not in PAGE
    assert "beats:nlive" in PAGE, 'still driven by archeus job count'


def test_the_stage_surface_comes_down_when_unfocused():
    """Hiding the canvas on blur is zero GPU for the app while you work in
    another one, which is strictly better than a paused-but-present surface.

    It used to be justified by the undefined-backbuffer artefact instead, and
    that reasoning turned out to be right about the fact and wrong about the
    scope — see test_the_drawing_buffer_is_preserved. This check stands on the
    cost argument now, which is the one that does not depend on it."""
    from claude_sessions.gui_html import PAGE
    assert 'blur(on) {' in PAGE
    assert "classList.toggle('stage-blur', !!on)" in PAGE
    assert 'if(window.STAGE)STAGE.blur(!v);' in PAGE, 'setVis does not call it'
    assert 'html.stage-blur #stage{visibility:hidden}' in PAGE


# ── the dashboard's new answers ───────────────────────────────

def test_today_is_split_by_account_in_tokens(monkeypatch, tmp_path):
    """The quota ring stacks one arc per account. Tokens are the only
    cross-account aggregate that is genuinely additive — an account's quota
    `pct` is a share of ITS OWN window, so summing five of those produces a
    number that looks like a total and means nothing."""
    _fresh(monkeypatch, tmp_path)
    srv, base = _serve(monkeypatch)
    try:
        _code, d = _req(f'{base}/api/dashboard')
    finally:
        srv.shutdown()
    today = d['today']
    assert isinstance(today['by_account'], dict)
    assert all(isinstance(v, int) for v in today['by_account'].values())
    # the parts must reconcile with the whole, or the ring lies about the total
    if today['by_account']:
        assert sum(today['by_account'].values()) == today['tokens']


def test_the_dashboard_never_sums_quota_percentages():
    """A guard on the RULE, not on one call site: percentages of five separate
    windows are not addable, and the moment someone writes `+w.pct` in a reduce
    the card starts reporting a confident wrong number."""
    import re
    from claude_sessions.gui_html import PAGE
    js = PAGE[PAGE.index('<script>'):]
    bad = re.findall(r'reduce\([^)]*\bpct\b[^)]*\+', js)
    assert not bad, 'quota percentages are being summed: %s' % bad


def test_finished_jobs_reach_the_dashboard_with_real_durations(monkeypatch, tmp_path):
    """`elapsed` used to be `now - started`, so a job that ran for 12 seconds an
    hour ago reported an hour. The Activity drawer shows finished jobs, which is
    exactly where that would have been visible."""
    _fresh(monkeypatch, tmp_path)
    now = time.time()
    # via the factory, NOT a hand-built literal: this dict went stale twice
    # against job_status and each time surfaced as a 500, not a bad fixture
    job = gui_api.new_job('Memory build', jid='oldjob', status='done',
                          messages=['wrote 18 entities'],
                          started=now - 3600, ended=now - 3558)
    with gui_api._JOBS_LOCK:
        gui_api._JOBS[job['id']] = job
    srv, base = _serve(monkeypatch)
    try:
        _code, d = _req(f'{base}/api/dashboard')
    finally:
        srv.shutdown()
        with gui_api._JOBS_LOCK:
            gui_api._JOBS.pop('oldjob', None)
    j = next(x for x in d['jobs'] if x['id'] == 'oldjob')
    assert j['status'] == 'done'
    assert j['elapsed'] == 42, j          # how long it RAN, not how long ago
    assert j['ended'] and j['last'] == 'wrote 18 entities'


def test_wiring_reports_a_statusline_that_will_never_be_drawn(monkeypatch, tmp_path):
    """Installed-but-invisible looks identical to working from the settings
    file: the classic renderer simply does not draw a statusLine."""
    _fresh(monkeypatch, tmp_path)
    from claude_sessions import hooks
    from claude_sessions import config as _cfg
    # the SAME dir _wiring() will read — hooks._load(None) resolves the module
    # default, which is not necessarily the account the sandbox reports
    _name, cfgdir = list(_cfg.all_config_dirs())[0]
    s = hooks._load(cfgdir)
    s['statusLine'] = {'type': 'command', 'command': 'x'}
    s['tui'] = 'default'
    hooks._save(s, cfgdir)
    w = gui_api._wiring()
    row = next(r for r in w['accounts'] if r['dir'] == cfgdir)
    assert row['statusline'] is True
    assert row['statusline_hidden'] is True
    assert w['ok'] == 0                   # hidden does not count as wired

    s['tui'] = 'fullscreen'
    hooks._save(s, cfgdir)
    assert gui_api._wiring()['accounts'][0]['statusline_hidden'] is False
