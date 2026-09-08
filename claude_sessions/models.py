"""The Claude model catalogue, read from Anthropic instead of hand-edited.

Four things worth knowing before changing this:

- **The credential already exists.** archeus holds no Anthropic API key and
  deliberately strips one from every launch env (accounts._env_for), but Claude
  Code's own OAuth token — the one `usage.py` reads for the plan meters — is
  accepted by `GET /v1/models` (scope `user:inference`). So a live catalogue
  costs no new secret, no new setting and no new prompt.

- **The API owns facts; this repo owns editorial.** `/v1/models` returns ids,
  display names, release dates, context windows, output caps and which effort
  levels each model accepts. It does NOT return pricing, capability rank, SWE
  scores or "best for" prose, and it has never heard of `ultracode` (a Claude
  Code setting, not an API one). Those stay in `config.py`, matched by family,
  so a model nobody has profiled yet still appears in the picker with blanks
  where the editorial has not caught up. Visible and unprofiled beats absent.

- **The roster stays short.** Ten models are listed today and six of them are
  previous generations. `roster()` returns the newest per family and nothing
  else; the rest are reachable through `all_models()` behind a "show all" row.
  A picker that grows by two rows per release is the "too complicated to use"
  complaint restated.

- **The bundled table is the floor, never the ceiling.** An empty cache, a dead
  network, an expired login and `auto_update: off` all land on `config.MODELS`
  unchanged. Nothing here can empty the launch picker.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

from . import config as _c
from . import jsonstore

__all__ = ['fetch', 'roster', 'all_models', 'notices', 'retired_pins',
           'catalogue', 'alias', 'family', 'refresh_in_background', 'status',
           'FAMILY_ORDER', 'CATALOG_TTL']

CATALOG_URL = 'https://api.anthropic.com/v1/models?limit=100'
#: a day. Anthropic ships a model every few weeks, and this runs unattended on
#: a startup daemon thread rather than when a screen opens, so there is nothing
#: to be gained by asking more often.
CATALOG_TTL = 86400
_TIMEOUT = 20

#: Cheapest to most capable — the order the launch picker has always used.
#: FAMILIES change far less often than the models inside them, and a family this
#: list has never heard of is appended rather than dropped, so a genuinely new
#: line shows up at the end instead of silently going missing.
FAMILY_ORDER = ['haiku', 'sonnet', 'opus', 'fable']

_DATED = re.compile(r'-\d{8}$')


def _cache_path():
    return os.path.join(_c.config_dir, 'archeus-models.json')


def alias(model_id):
    """'claude-haiku-4-5-20251001' -> 'claude-haiku-4-5'.

    The API answers with the pinned snapshot id; Claude Code's --model takes the
    alias, and that is what archeus has always stored in settings. Stripping a
    trailing -YYYYMMDD is the whole rule — dateless ids from the 4.6 generation
    on are already their own alias.
    """
    return _DATED.sub('', str(model_id or ''))


def family(model_id):
    """'claude-opus-4-5-20251101' -> 'opus'. The name up to the first numeric
    part, which is what distinguishes a generation from a line."""
    parts = [p for p in alias(model_id).split('-') if p and p != 'claude']
    out = []
    for p in parts:
        if p.isdigit():
            break
        out.append(p)
    return '-'.join(out)


def _token():
    """Claude Code's OAuth access token for the active account, or ''."""
    from . import usage
    if usage._token_expired():
        return ''                       # a doomed call; skip it entirely
    return usage._read_token() or ''


def _row(m):
    """One API model object reduced to what archeus renders."""
    mid = alias(m.get('id'))
    eff = ((m.get('capabilities') or {}).get('effort') or {})
    return {
        'id': mid,
        'snapshot': str(m.get('id') or ''),
        'label': mid[7:] if mid.startswith('claude-') else mid,
        'display': str(m.get('display_name') or ''),
        'created': str(m.get('created_at') or ''),
        'family': family(mid),
        'context': int(m.get('max_input_tokens') or 0),
        'max_out': int(m.get('max_tokens') or 0),
        'efforts': [k for k in ('low', 'medium', 'high', 'xhigh', 'max')
                    if (eff.get(k) or {}).get('supported')],
    }


def fetch(refresh=False):
    """{'models','fetched','error'} — the catalogue, from a daily disk cache.

    Never called from a render path: `ui.menu()` re-polls its banner twice a
    second and every reader below takes the cache. A failed fetch keeps what was
    cached and reports the error beside it, the same contract `versions.released`
    uses, and for the same reason: a stale answer with a note beats an empty one.
    """
    cached = jsonstore.load(_cache_path(), {})
    fresh = (isinstance(cached, dict) and cached.get('models')
             and time.time() - float(cached.get('fetched') or 0) < CATALOG_TTL)
    if fresh and not refresh:
        return dict(cached, error='')
    keep = dict(cached) if isinstance(cached, dict) else {}
    keep.setdefault('models', [])
    if (_c.load_settings().get('auto_update') or 'notify') == 'off':
        return dict(keep, error='')
    token = _token()
    if not token:
        return dict(keep, error='not logged in — run `claude login`')
    try:
        req = urllib.request.Request(CATALOG_URL, headers={
            'Authorization': 'Bearer %s' % token,
            'anthropic-beta': 'oauth-2025-04-20',
            'anthropic-version': '2023-06-01',
            'User-Agent': 'archeus',
        })
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            doc = json.loads(resp.read().decode('utf-8', 'ignore'))
    except (urllib.error.URLError, OSError, ValueError) as e:
        return dict(keep, error=str(e)[:200])
    rows = [_row(m) for m in (doc.get('data') or []) if isinstance(m, dict)]
    rows = [r for r in rows if r['id']]
    if not rows:
        return dict(keep, error='the catalogue came back empty')
    rows.sort(key=lambda r: r['created'], reverse=True)      # newest first
    out = {'models': rows, 'fetched': time.time()}
    jsonstore.save(_cache_path(), out)
    return dict(out, error='')


def catalogue():
    """The cached catalogue, or {} — a pure disk read, safe on any path."""
    c = jsonstore.load(_cache_path(), {})
    return c if isinstance(c, dict) and c.get('models') else {}


def all_models():
    """Every model the account can reach, newest first."""
    return list(catalogue().get('models') or [])


def roster():
    """The launch picker's models: the newest of each family, cheapest family
    first. [] when there is no catalogue, which is what makes config fall back
    to its bundled table rather than show an empty picker."""
    best = {}
    for r in all_models():                       # already newest-first
        best.setdefault(r['family'], r)
    order = {f: i for i, f in enumerate(FAMILY_ORDER)}
    return sorted(best.values(),
                  key=lambda r: (order.get(r['family'], len(order)), r['family']))


def _pins():
    """[(where, model_id)] — every model id pinned in settings, and by what."""
    s = _c.load_settings()
    pins = []
    for key in ('default_model', 'plan_model', 'exec_model', 'extract_model',
                'default_subagent_model', 'review_model'):
        mid = (s.get(key) or '').strip()
        if mid:
            pins.append((key, mid))
    for enc, d in (s.get('project_defaults') or {}).items():
        mid = ((d or {}).get('model') or '').strip() if isinstance(d, dict) else ''
        if mid:
            pins.append(('project %s' % enc, mid))
    return pins


def retired_pins():
    """Pinned model ids the catalogue no longer offers — the DATA, not prose.

    Each surface says it its own way: the Updates screen names what pinned it,
    the launch picker only cares whether the one model in front of you is gone.
    Shipping the sentence instead of the ids meant the launch payload carried a
    string nothing could use, which is how a field starts rotting.

    Empty when there is no catalogue: without one, a pin is UNKNOWN rather than
    retired, and reporting those would turn a failed fetch into a screen of
    false warnings.
    """
    have = {r['id'] for r in all_models()}
    if not have:
        return []
    seen, out = set(), []
    for _where, mid in _pins():
        if mid in have or mid in seen:
            continue
        seen.add(mid)
        out.append(mid)
    return out


def notices():
    """One sentence per retired pin, naming what pinned it.

    Only this case is reported. A newly released model needs no announcement —
    it is simply in the picker, which is the entire point of the feature — but a
    retired one is pinned in settings and will fail at launch with an API error
    that says nothing about where the id came from.
    """
    retired = set(retired_pins())
    if not retired:
        return []
    seen, out = set(), []
    for where, mid in _pins():
        if mid not in retired or mid in seen:
            continue
        seen.add(mid)
        out.append('%s is set to %s, which Anthropic no longer offers' % (where, mid))
    return out


_bg_started = False


def refresh_in_background():
    """Refresh the catalogue once per launch, on a daemon thread, if stale.

    Same shape and same reasoning as `versions.start_background_check`: one
    TTL-gated call at startup, never a re-poll loop, and every reader below
    takes the cache. It is a separate thread rather than a call inside that
    one because neither module should have to import the other to start.
    """
    global _bg_started
    import threading
    if _bg_started:
        return
    _bg_started = True

    def _work():
        try:
            fetch()
        except Exception:
            pass       # a catalogue refresh must never be why archeus misbehaves

    threading.Thread(target=_work, daemon=True).start()


def status():
    """{'count','families','fetched','age','error','live'} for the Updates screen.

    CACHE ONLY — no fetch, so this is safe from a render path. `live` is False
    when the picker is running on the bundled floor, which is the one fact a
    user needs to interpret everything else on the row.
    """
    c = catalogue()
    rows = list(c.get('models') or [])
    fetched = float(c.get('fetched') or 0)
    return {
        'count': len(rows),
        'families': len({r.get('family') for r in rows if r.get('family')}),
        'fetched': fetched,
        'age': (time.time() - fetched) if fetched else 0.0,
        'live': bool(rows),
        'error': '',
    }
