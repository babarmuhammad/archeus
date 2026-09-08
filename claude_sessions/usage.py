"""Subscription usage limits (5-hour window / weekly) for the main screen.

Queries the same OAuth usage endpoint Claude Code's /usage command uses,
authenticated with the local Claude Code OAuth token. Fetched once per run
on a background thread; absent/expired credentials degrade to no line.
"""

import os
import json
import time
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone

from . import config as _c

USAGE_URL = 'https://api.anthropic.com/api/oauth/usage'

_REFRESH_SEC = 300   # re-poll cadence on success (usage changes slowly; avoid rate limits)
_RETRY_BASE  = 30    # first backoff after a failed fetch; doubles each fail
_RETRY_MAX   = 600   # backoff ceiling
_MAX_FAILS   = 3     # give up (blank line) only after this many failures with no data yet

STATUS_TEXT = {
    'pending':      'checking…',
    'expired':      'session expired — run claude login for this account',
    'rate_limited': 'rate-limited by the API',
    'no_creds':     'not logged in',
    'error':        'usage unavailable',
}

_lock       = threading.Lock()
_started    = False
_ready      = False
_data       = None   # active account's usage (back-compat: single-account + stats)
_acct_state = {}     # cfgdir -> {'name','email','data','status',...} per account


def _creds(cfgdir=None):
    """The account's stored OAuth block, read-only. archeus NEVER writes this
    file: refreshing an access token can rotate the refresh token, and a bad
    write-back would log the account out of Claude Code itself."""
    try:
        p = os.path.join(cfgdir or _c.config_dir, '.credentials.json')
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f).get('claudeAiOauth') or {}
    except Exception:
        return {}


def _read_token(cfgdir=None):
    return _creds(cfgdir).get('accessToken')


def _token_expired(cfgdir=None):
    """True when the stored access token is past its expiry — an idle account
    whose token Claude Code hasn't refreshed. Saves a doomed HTTP call."""
    exp = _creds(cfgdir).get('expiresAt')
    try:
        return bool(exp) and float(exp) / 1000.0 <= time.time()
    except (TypeError, ValueError):
        return False


def _account_email(cfgdir=None):
    """Best-effort account email/label from the account's stored credentials."""
    oauth = _creds(cfgdir)
    acc = oauth.get('account') or {}
    for k in ('email_address', 'emailAddress', 'email'):
        if oauth.get(k):
            return oauth[k]
        if acc.get(k):
            return acc[k]
    return ''


def account_meta(cfgdir=None):
    """Plan labels shown next to the meters ('Max 20x')."""
    oauth = _creds(cfgdir)
    return {'plan': oauth.get('subscriptionType') or '',
            'tier': oauth.get('rateLimitTier') or ''}


def _spend_of(data):
    """Pay-as-you-go credit spend, when the account has it enabled."""
    sp = (data or {}).get('spend') or {}
    if not sp.get('enabled'):
        return None
    used = sp.get('used') or {}
    try:
        amount = (used.get('amount_minor') or 0) / (10 ** (used.get('exponent') or 2))
    except (TypeError, ValueError):
        amount = 0.0
    return {'used': round(amount, 2), 'pct': sp.get('percent') or 0,
            'currency': used.get('currency') or 'USD'}


def _targets():
    """[(name, abs cfgdir)] to poll — the default account plus configured ones,
    deduped, default first."""
    s = _c.load_settings()
    out = [('default', os.path.join(_c._USERPROFILE, '.claude'))]
    for a in s.get('accounts', []):
        d = a.get('dir') if isinstance(a, dict) else None
        if d:
            out.append((a.get('name') or d, os.path.expanduser(os.path.expandvars(d))))
    seen, uniq = set(), []
    for n, d in out:
        rd = os.path.normcase(os.path.abspath(d))
        if rd not in seen:
            seen.add(rd)
            uniq.append((n, d))
    return uniq


def fetch_usage(cfgdir=None):
    """GET the OAuth usage endpoint for an account.
    Returns (status, data|None) where status is one of
    'ok' | 'expired' | 'rate_limited' | 'no_creds' | 'error', plus the seconds
    a 429 asked us to wait (0 when it didn't)."""
    token = _read_token(cfgdir)
    if not token:
        return 'no_creds', None, 0
    if _token_expired(cfgdir):
        return 'expired', None, 0       # doomed call — skip it entirely
    req = urllib.request.Request(USAGE_URL, headers={
        'Authorization': f'Bearer {token}',
        'anthropic-beta': 'oauth-2025-04-20',
        'Content-Type': 'application/json',
        'User-Agent': 'archeus',
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 'ok', json.loads(r.read().decode('utf-8', 'replace')), 0
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return 'expired', None, 0
        if e.code == 429:                      # honor Retry-After; don't hammer
            try:
                return 'rate_limited', None, int(e.headers.get('Retry-After') or 0)
            except (TypeError, ValueError):
                return 'rate_limited', None, 0
        return 'error', None, 0
    except Exception:
        return 'error', None, 0


def _poll_account(name, d, active):
    """One account: fetch, record status, keep the last good data. Returns True
    on a live fetch. Per-account backoff, so a dead account can't slow the rest."""
    global _data, _ready
    now = time.time()
    with _lock:
        st = _acct_state.setdefault(d, {'status': 'pending'})
        if st.get('retry_at', 0) > now:
            return False
    try:
        status, data, retry_after = fetch_usage(d)
    except Exception:
        _c.log.exception('usage fetch failed')
        status, data, retry_after = 'error', None, 0
    with _lock:
        st = _acct_state.setdefault(d, {})
        st['name'] = name
        st['status'] = status
        st.update(account_meta(d))
        if not st.get('email'):
            st['email'] = _account_email(d)
        if status == 'ok':
            st['data'] = data                      # never clobbered by a failure
            st['spend'] = _spend_of(data)
            st['fetched_at'] = now
            st.pop('retry_at', None)
            if os.path.normcase(os.path.abspath(d)) == active:
                _data = data
        else:
            back = max(retry_after, _RETRY_BASE if status != 'expired' else _REFRESH_SEC)
            st['retry_at'] = now + min(back, _RETRY_MAX)
        _ready = True
    return status == 'ok'


#: set by stop_background() so server_close() actually ends this loop; every
#: sleep below is a wait on it rather than time.sleep, because a thread parked
#: in sleep(_RETRY_MAX) cannot be told anything
_stop = threading.Event()


def _background():
    """Poll every configured account until told to stop, recording each one's
    health."""
    fails = 0
    while not _stop.is_set():
        active = os.path.normcase(os.path.abspath(_c.config_dir))
        any_ok = False
        for name, d in _targets():
            if _stop.is_set():
                return
            any_ok = _poll_account(name, d, active) or any_ok
            _stop.wait(1)            # small gap between accounts (avoid a burst)
        if any_ok:
            fails = 0
            sleep = _REFRESH_SEC
        else:                        # nothing live at all — exponential backoff
            fails += 1
            sleep = min(_RETRY_BASE * (2 ** max(0, fails - 1)), _RETRY_MAX)
        _stop.wait(sleep)


def _ensure_started():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    _stop.clear()
    threading.Thread(target=_background, daemon=True).start()


def stop_background():
    global _started
    _stop.set()
    with _lock:
        _started = False


def refresh_now():
    """One synchronous fetch pass over every account (GUI refresh button) —
    ignores the per-account backoff, the user asked explicitly."""
    _ensure_started()
    active = os.path.normcase(os.path.abspath(_c.config_dir))
    for name, d in _targets():
        with _lock:
            _acct_state.setdefault(d, {}).pop('retry_at', None)
        _poll_account(name, d, active)


def _fmt_reset(iso):
    """ISO timestamp → short local time ('14:30' today, else 'Tue 09:00')."""
    try:
        dt = datetime.fromisoformat(str(iso).replace('Z', '+00:00')).astimezone()
    except Exception:
        return '?'
    now = datetime.now(dt.tzinfo)
    if dt.date() == now.date():
        return dt.strftime('%H:%M')
    return dt.strftime('%a %H:%M')


def _pct_color(pct):
    if pct >= 80:
        return _c.C_ERR
    if pct >= 50:
        return _c.C_WARN
    return _c.C_OK


def _window_label(key):
    k = key.lower()
    if 'five' in k or '5h' in k:
        return 'session'
    if 'seven' in k or 'week' in k:
        return 'weekly'
    return key[:8]


def _limit_label(item):
    """Label a `limits[]` entry. New usage shape: kind = session | weekly_all |
    weekly_scoped (per-model, with scope.model.display_name, e.g. Fable)."""
    k = str(item.get('kind', '')).lower()
    g = str(item.get('group', '')).lower()
    scope = item.get('scope') or {}
    model = (scope.get('model') or {}) if isinstance(scope, dict) else {}
    if k == 'weekly_scoped' or model.get('display_name'):
        return model.get('display_name') or 'wk-model'
    if k == 'session' or g == 'session' or 'five' in k or '5h' in k:
        return 'session'
    if k == 'weekly_all' or g == 'weekly' or 'week' in k:
        return 'weekly'
    return (k or g)[:8]


def _extract_windows(data):
    """Find limit windows in the response, tolerant of shape variations.
    Returns [(label, pct, resets_at_iso)] ordered daily-first.

    `utilization`/`percent` are already 0-100 percentages from this endpoint —
    they are NOT divided or rescaled here. (An earlier 0..1 heuristic wrongly
    multiplied small values by 100, pinning low usage to 100%.)"""
    if not isinstance(data, dict):
        return []

    def norm(v):
        try:
            return max(0.0, min(float(v), 100.0))
        except (TypeError, ValueError):
            return None

    out = []
    # Prefer the authoritative `limits` array (explicit percent + group).
    limits = data.get('limits')
    if isinstance(limits, list):
        for item in limits:
            if not isinstance(item, dict):
                continue
            pct = norm(item.get('percent'))
            if pct is None:
                continue
            out.append((_limit_label(item), pct, item.get('resets_at')))

    # Fallback: top-level per-window dicts carrying `utilization`.
    if not out:
        for key, val in data.items():
            if not isinstance(val, dict):
                continue
            pct = norm(val.get('utilization'))
            if pct is None:
                continue
            out.append((_window_label(key), pct, val.get('resets_at')))

    order = {'session': 0, 'weekly': 1}   # session, all-models weekly, then per-model
    out.sort(key=lambda w: order.get(w[0], 5))
    return out


_METER_W = 8                        # bar width; visible = _METER_W + 2 borders
_RESET_W = 9                        # 'Sat 08:59'
_CELL_W = (_METER_W + 2) + 1 + 5 + 1 + _RESET_W   # meter ' ' pct% ' ' reset


def _account_grid(accts):
    """Aligned multi-account table. Columns = limit windows (session, weekly,
    then per-model) present with any usage; rows = accounts. Each cell shows
    the bar, %, and reset time, padded to a fixed width so columns line up."""
    from . import render
    rows = []                       # (label, {col: (pct, reset)})
    notes = []                      # accounts with no data — named, never silent
    seen_cols, cols = set(), []
    for name, email, adata, status in accts:
        w = _extract_windows(adata)
        if not w:
            if status and status != 'ok':
                notes.append(f"  {_c.C_DIM}{email or name}: "
                             f"{_c.C_WARN}{STATUS_TEXT.get(status, status)}{_c.C_RESET}")
            continue
        d = {}
        for lbl, pct, reset in w:
            d[lbl] = (pct, reset)
            if lbl not in seen_cols:
                seen_cols.add(lbl)
                cols.append(lbl)
        rows.append((email or name or '?', d))
    if not rows:
        return '\n'.join(notes)
    cols = [c for c in cols if any(r[1].get(c, (0,))[0] for r in rows)]
    if not cols:
        cols = list(seen_cols)[:1]
    order = {'session': 0, 'weekly': 1}
    cols.sort(key=lambda c: (order.get(c, 5), c))

    name_w = min(22, max(len(r[0]) for r in rows))
    hdr = '  ' + ' ' * name_w + '  ' + '  '.join(
        f"{_c.C_DIM}{c[:_CELL_W]:<{_CELL_W}}{_c.C_RESET}" for c in cols)
    out = [hdr]
    for label, d in rows:
        cells = []
        for c in cols:
            if c in d:
                pct, reset = d[c]
                col = _pct_color(pct)
                r = _fmt_reset(reset) if reset else ''
                cells.append(f"{render.meter(pct, width=_METER_W, color=col)} "
                             f"{col}{pct:>4.0f}%{_c.C_RESET} {_c.C_DIM}{r:<{_RESET_W}}{_c.C_RESET}")
            else:
                cells.append(' ' * _CELL_W)
        out.append(f"  {_c.C_TITLE}{render.trunc(label, name_w):<{name_w}}{_c.C_RESET}  "
                   + '  '.join(cells))
    return '\n'.join(out + notes)


def _one_account_line(windows, prefix=''):
    from . import render
    parts = []
    for label, pct, resets in windows[:4]:
        col = _pct_color(pct)
        seg = (f"{_c.C_DIM}{label}{_c.C_RESET} "
               f"{render.meter(pct, width=10, color=col)} "
               f"{col}{pct:.0f}%{_c.C_RESET}")
        if resets:
            seg += f" {_c.C_DIM}→ {_fmt_reset(resets)}{_c.C_RESET}"
        parts.append(seg)
    body = f'  {_c.C_DIM}·{_c.C_RESET}  '.join(parts)
    return (f"  {prefix}{body}" if prefix else f"  {body}")


def usage_status_line():
    """Plan-usage banner. One bar per configured account (labeled by email/name)
    when 2+ accounts exist; a single unlabeled bar otherwise. Empty until data
    is in (or unavailable)."""
    _ensure_started()
    with _lock:
        ready = _ready
        data = _data
        accts = [(v.get('name', ''), v.get('email', ''), v.get('data'),
                  v.get('status', '')) for v in _acct_state.values()
                 if v.get('data') or v.get('status') not in (None, '', 'ok')]
    if not ready:
        return f'  {_c.C_DIM}Plan usage: checking...{_c.C_RESET}'

    # 2+ accounts → an ALIGNED grid: one row per account, one column per limit
    # window, so session/weekly/per-model line up vertically across accounts.
    if len(accts) >= 2:
        grid = _account_grid(accts)
        if grid:
            return grid

    # single account (back-compat)
    windows = _extract_windows(data)
    if not windows:
        return ''
    line = _one_account_line(windows)
    # optional daily-token alert badge (cache-only, cheap)
    try:
        alert = _c.load_settings().get('daily_token_alert', 0) or 0
        if alert:
            from .stats import today_tokens, fmt_tok
            tot = today_tokens()
            if tot >= alert:
                line += f"  {_c.C_DIM}·{_c.C_RESET}  {_c.C_WARN}today {fmt_tok(tot)} tok ⚠{_c.C_RESET}"
    except Exception:
        pass
    return line
