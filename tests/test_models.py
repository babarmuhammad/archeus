"""The live model catalogue: reading it, falling back from it, and the two
ways it can quietly do damage.

The feature exists because the launch picker was a hand-edited list in
`config.py`, so a model released after an archeus release was unreachable
until someone shipped a new one. `/v1/models` answers that with the OAuth token
Claude Code already holds — no API key, no new setting.

Three hazards are what most of this file is about, and each one is a real thing
this design can do wrong rather than a restatement of the code:

- **Emptying the picker.** Every failure path — no cache, dead network, expired
  login, `auto_update: off`, a catalogue that comes back empty — must land on
  `config.MODELS` unchanged. There is no state in which a user cannot pick a
  model.
- **Erasing a pin.** The pickers resolve the saved model to a cursor INDEX and
  write `ids[idx]` back on save. A model Anthropic retires therefore resolves to
  index 0 (= account default) and is erased the next time the screen is saved,
  without the user touching that field. `config.models(*extra)` is the fix and
  `notices()` is how the user finds out.
- **Fetching from a render path.** `ui.menu()` re-polls its banner twice a
  second. Anything a screen calls must be a pure disk read.
"""

import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox

from claude_sessions import config as config_mod
from claude_sessions import jsonstore
from claude_sessions import models as m


# ── fixtures ─────────────────────────────────────────────────

def _model(mid, created, ctx=200000, out=64000, efforts=('low', 'medium', 'high'),
           display=''):
    return {'id': mid, 'display_name': display or mid, 'created_at': created,
            'max_input_tokens': ctx, 'max_tokens': out,
            'capabilities': {'effort': {e: {'supported': True} for e in efforts}}}


#: deliberately shaped like the real answer: newest first is NOT guaranteed by
#: the API, several generations of the same family are listed together, and the
#: ids carry the -YYYYMMDD snapshot suffix the older generations still use.
_DATA = [
    _model('claude-sonnet-5', '2026-02-01T00:00:00Z'),
    _model('claude-haiku-4-5-20251001', '2025-10-01T00:00:00Z'),
    _model('claude-opus-5', '2026-01-15T00:00:00Z'),
    _model('claude-sonnet-4-6-20260101', '2026-01-01T00:00:00Z'),
    _model('claude-fable-5', '2026-03-01T00:00:00Z'),
]


def _api(monkeypatch, data=None, calls=None, boom=None):
    """Stub /v1/models. `calls` records every request that was actually made,
    which is what the no-fetch-from-a-render-path tests assert on."""
    doc = json.dumps({'data': _DATA if data is None else data}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=0):
        if calls is not None:
            calls.append(getattr(req, 'full_url', req))
        if boom:
            raise boom
        return _Resp(doc)

    monkeypatch.setattr(m.urllib.request, 'urlopen', fake)


def _logged_in(monkeypatch, token='sk-ant-oat-fake'):
    monkeypatch.setattr(m, '_token', lambda: token)


def _cache(monkeypatch, tmp_path):
    p = str(tmp_path / 'archeus-models.json')
    monkeypatch.setattr(m, '_cache_path', lambda: p)
    return p


# ── the id rules ─────────────────────────────────────────────

def test_the_snapshot_suffix_is_stripped_because_the_cli_takes_the_alias():
    # The API answers with the pinned snapshot; --model and every settings key
    # archeus has ever written take the alias.
    assert m.alias('claude-haiku-4-5-20251001') == 'claude-haiku-4-5'
    assert m.alias('claude-sonnet-4-6-20260101') == 'claude-sonnet-4-6'
    # dateless ids from the 5 generation on are already their own alias
    assert m.alias('claude-sonnet-5') == 'claude-sonnet-5'
    assert m.alias('') == ''


def test_a_version_inside_the_id_is_not_mistaken_for_a_date():
    # -4-5 is a generation, not a YYYYMMDD, and stripping it would collapse two
    # different models onto one id.
    assert m.alias('claude-haiku-4-5') == 'claude-haiku-4-5'


def test_the_family_is_the_name_up_to_the_first_number():
    assert m.family('claude-opus-4-5-20251101') == 'opus'
    assert m.family('claude-sonnet-5') == 'sonnet'
    assert m.family('claude-fable-5') == 'fable'
    # a hyphenated line name survives intact
    assert m.family('claude-deep-research-2') == 'deep-research'


# ── the roster ───────────────────────────────────────────────

def test_the_roster_is_the_newest_of_each_family_cheapest_first(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)

    ids = [r['id'] for r in m.roster()]
    # sonnet-4-6 is older than sonnet-5, so the family shows once
    assert ids == ['claude-haiku-4-5', 'claude-sonnet-5',
                   'claude-opus-5', 'claude-fable-5']
    # ...but the older one is still reachable
    assert 'claude-sonnet-4-6' in [r['id'] for r in m.all_models()]


def test_a_family_nobody_has_heard_of_lands_at_the_end_not_in_the_bin(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch, data=_DATA + [_model('claude-quartz-1', '2026-06-01T00:00:00Z')])
    m.fetch(refresh=True)

    ids = [r['id'] for r in m.roster()]
    assert ids[-1] == 'claude-quartz-1', ids
    assert len(ids) == 5


def test_the_row_carries_the_facts_the_api_owns(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch, data=[_model('claude-opus-5', '2026-01-15T00:00:00Z',
                                   ctx=1000000, out=128000,
                                   efforts=('high', 'xhigh', 'max'),
                                   display='Claude Opus 5')])
    m.fetch(refresh=True)

    r = m.all_models()[0]
    assert r['id'] == 'claude-opus-5'
    assert r['label'] == 'opus-5'          # what a picker shows
    assert r['display'] == 'Claude Opus 5'
    assert r['context'] == 1000000
    assert r['max_out'] == 128000
    assert r['efforts'] == ['high', 'xhigh', 'max']


# ── nothing may empty the picker ─────────────────────────────

def test_with_no_catalogue_the_picker_is_the_bundled_table(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    ids, labels = config_mod.models()
    assert ids == config_mod.MODELS
    assert labels == config_mod.MODEL_LABELS


def test_a_dead_network_keeps_what_was_cached_and_says_why(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)
    before = m.all_models()

    _api(monkeypatch, boom=OSError('getaddrinfo failed'))
    out = m.fetch(refresh=True)
    assert 'getaddrinfo' in out['error']
    assert out['models'] == before           # a stale answer beats an empty one
    assert m.roster()                        # and the picker is untouched


def test_a_catalogue_that_comes_back_empty_is_refused(monkeypatch, tmp_path):
    # An empty `data` is far more likely to be an API change than a real answer,
    # and writing it to the cache would empty the picker for a whole day.
    Sandbox(monkeypatch, tmp_path)
    path = _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)

    _api(monkeypatch, data=[])
    out = m.fetch(refresh=True)
    assert out['error']
    assert len(out['models']) == 5
    assert len(jsonstore.load(path, {}).get('models') or []) == 5


def test_a_logged_out_account_says_so_and_changes_nothing(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    calls = []
    _api(monkeypatch, calls=calls)
    monkeypatch.setattr(m, '_token', lambda: '')

    out = m.fetch(refresh=True)
    assert 'login' in out['error']
    assert calls == []                       # a doomed call is not made at all
    assert config_mod.models()[0] == config_mod.MODELS


def test_an_expired_token_is_not_spent_on_a_doomed_call(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    calls = []
    _api(monkeypatch, calls=calls)
    from claude_sessions import usage
    monkeypatch.setattr(usage, '_token_expired', lambda: True)
    monkeypatch.setattr(usage, '_read_token', lambda: 'stale')

    assert 'login' in m.fetch(refresh=True)['error']
    assert calls == []


def test_auto_update_off_stops_the_catalogue_too(monkeypatch, tmp_path):
    # One switch for everything archeus fetches on the user's behalf — the
    # setting the GUI describes as stopping "both checks".
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    calls = []
    _api(monkeypatch, calls=calls)
    s = config_mod.load_settings()
    s['auto_update'] = 'off'
    config_mod.save_settings(s)

    out = m.fetch(refresh=True)
    assert calls == []
    assert out['models'] == []
    assert config_mod.models()[0] == config_mod.MODELS


def test_a_broken_catalogue_module_does_not_take_the_launch_picker_down(monkeypatch, tmp_path):
    # config.models() wraps the read: a model list is a nicety, launching is not.
    Sandbox(monkeypatch, tmp_path)

    def boom():
        raise RuntimeError('cache is a directory')

    monkeypatch.setattr(m, 'roster', boom)
    assert config_mod.models()[0] == config_mod.MODELS


# ── the cache ────────────────────────────────────────────────

def test_a_fresh_cache_is_not_refetched(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    calls = []
    _api(monkeypatch, calls=calls)

    m.fetch()
    assert len(calls) == 1
    m.fetch()
    m.fetch()
    assert len(calls) == 1


def test_a_stale_cache_is_refetched(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    path = _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    calls = []
    _api(monkeypatch, calls=calls)
    m.fetch()
    assert len(calls) == 1

    doc = jsonstore.load(path, {})
    doc['fetched'] = time.time() - m.CATALOG_TTL - 60
    jsonstore.save(path, doc)
    m.fetch()
    assert len(calls) == 2


def test_nothing_a_screen_calls_can_fetch(monkeypatch, tmp_path):
    """`ui.menu()` re-polls its banner twice a second and every renderer below
    reads the catalogue, so a fetch on any of these paths is a stall on every
    keystroke. Only `fetch()` is allowed to open a socket."""
    Sandbox(monkeypatch, tmp_path)
    path = _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)
    # expire it — a reader that fetches would do so NOW
    doc = jsonstore.load(path, {})
    doc['fetched'] = 0
    jsonstore.save(path, doc)

    calls = []
    _api(monkeypatch, calls=calls)
    m.catalogue()
    m.all_models()
    m.roster()
    m.notices()
    m.status()
    config_mod.models()
    config_mod.model_card_rows()
    config_mod.frontier_rows()
    assert calls == [], 'a render path opened a socket'


# ── a pin must not be erased ─────────────────────────────────

def test_a_retired_pin_keeps_its_place_in_the_picker(monkeypatch, tmp_path):
    """The launch picker resolves the saved model to an index and writes
    ids[idx] back on save. A pin missing from the list resolves to 0 —
    account default — and is erased on the next save of an unrelated field."""
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)

    ids, labels = config_mod.models('claude-opus-4-1')
    assert 'claude-opus-4-1' in ids
    assert labels[ids.index('claude-opus-4-1')] == 'opus-4-1'
    # and it is not duplicated when it IS offered
    ids2, _ = config_mod.models('claude-opus-5')
    assert ids2.count('claude-opus-5') == 1


def test_the_retired_pin_is_reported_once_per_model(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)

    s = config_mod.load_settings()
    s['default_model'] = 'claude-opus-4-1'
    s['default_subagent_model'] = 'claude-opus-4-1'    # the same retired model
    s['extract_model'] = 'claude-haiku-4-5'           # still offered
    config_mod.save_settings(s)

    notes = m.notices()
    assert len(notes) == 1, notes
    assert 'claude-opus-4-1' in notes[0]
    assert 'haiku' not in notes[0]


def test_the_ids_and_the_prose_are_separate_surfaces(monkeypatch, tmp_path):
    """`notices()` names what pinned a retired model — right for the Updates
    screen. The launch picker asks a different question about ONE model, so it
    gets ids. Shipping the sentence to both left a string in the launch payload
    that nothing could use."""
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)

    s = config_mod.load_settings()
    s['default_model'] = 'claude-opus-4-1'
    config_mod.save_settings(s)

    assert m.retired_pins() == ['claude-opus-4-1']
    assert 'default_model' in m.notices()[0]      # the prose names the source
    # a still-offered pin is in neither
    s['default_model'] = 'claude-sonnet-5'
    config_mod.save_settings(s)
    assert m.retired_pins() == [] and m.notices() == []


def test_the_launch_picker_says_a_retired_model_will_fail(monkeypatch, tmp_path):
    """The pin stays in the list on purpose, so the picker is the only thing
    that can tell the user it is gone. Without this the launch fails with an
    API error that never mentions where the id came from."""
    from claude_sessions import ui
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)

    src = io.open(ui.__file__, encoding='utf-8').read()
    assert 'retired_pins' in src, 'the TUI launch picker does not consult it'
    assert "no longer offers" in src

    js = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(ui.__file__))), 'claude_sessions', 'web', 'app.js'),
        encoding='utf-8').read()
    assert 'model_retired' in js, 'the GUI launch picker does not consult it'
    from claude_sessions import gui
    s = config_mod.load_settings()
    s['default_model'] = 'claude-opus-4-1'
    config_mod.save_settings(s)
    assert gui.state_payload()['options']['model_retired'] == ['claude-opus-4-1']


def test_a_project_default_is_checked_too(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)

    s = config_mod.load_settings()
    s['project_defaults'] = {'D--Thing': {'model': 'claude-opus-3'}}
    config_mod.save_settings(s)
    assert any('claude-opus-3' in n for n in m.notices())


def test_nothing_is_reported_when_there_is_no_catalogue(monkeypatch, tmp_path):
    """Without a catalogue every pin is 'unknown', not 'retired'. Reporting
    them would turn a failed fetch into a screen of false warnings."""
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    s = config_mod.load_settings()
    s['default_model'] = 'claude-opus-4-1'
    config_mod.save_settings(s)
    assert m.notices() == []


# ── editorial: facts from the API, prose from the repo ───────

def test_a_new_generation_inherits_its_family_editorial(monkeypatch, tmp_path):
    """/v1/models returns no cost, no capability rank and no prose, so an
    unprofiled model would otherwise land in the picker with every column
    blank. A family match carries the parts that generalise."""
    Sandbox(monkeypatch, tmp_path)
    prof = config_mod.profile('claude-sonnet-6')
    assert prof and prof['best_for'] == config_mod.MODEL_PROFILES['claude-sonnet-5']['best_for']
    assert config_mod.cap_bar('claude-sonnet-6') == config_mod.cap_bar('claude-sonnet-5')


def test_a_benchmark_score_is_never_inherited(monkeypatch, tmp_path):
    """Rank and prose generalise across a family; a measured SWE-bench score is
    a measurement of one model, and attributing it to another is invented data."""
    Sandbox(monkeypatch, tmp_path)
    assert config_mod.swe_str('claude-sonnet-5') == '85%'
    assert config_mod.swe_str('claude-sonnet-6') == '—'


def test_an_unprofiled_model_is_visible_with_blanks_not_absent(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch, data=_DATA + [_model('claude-quartz-1', '2026-06-01T00:00:00Z')])
    m.fetch(refresh=True)

    rows = {r[0]: r for r in config_mod.model_card_rows()}
    assert 'claude-quartz-1' in rows, 'an unknown model vanished from the guide'
    _mid, label, cost, cap, best, swe = rows['claude-quartz-1']
    assert label == 'quartz-1'
    assert (cost, cap, best, swe) == ('', '', '', '—')
    # and the profiled ones still read as before
    assert rows['claude-sonnet-5'][4] == 'default coding (~90% of tasks)'


# ── the pickers read the live list, not the floor ────────────

def test_the_launch_picker_offers_a_model_released_after_this_release(monkeypatch, tmp_path):
    """The whole point of the feature, asserted end to end: a model that is not
    in `config.MODELS` reaches the launch options screen."""
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    _api(monkeypatch, data=_DATA + [_model('claude-sonnet-6', '2026-07-01T00:00:00Z')])
    m.fetch(refresh=True)

    assert 'claude-sonnet-6' not in config_mod.MODELS
    ids, labels = config_mod.models()
    assert 'claude-sonnet-6' in ids
    assert labels[ids.index('claude-sonnet-6')] == 'sonnet-6'
    # and it replaced sonnet-5 rather than being added beside it
    assert 'claude-sonnet-5' not in ids


def test_no_picker_reads_the_bundled_table_directly():
    """MODELS/MODEL_LABELS are the FLOOR. A screen reading them instead of
    `config.models()` cannot show a new release and will erase a retired pin —
    both silently. Only config.py itself (which defines the fallback) and the
    module docstrings may name them.

    This is the gate for a whole class of mistake, so it is an AST walk rather
    than a list of the four files that happened to be wrong once.
    """
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pkg = os.path.join(root, 'claude_sessions')
    allowed = {'config.py'}
    bad = []
    for name in sorted(os.listdir(pkg)):
        if not name.endswith('.py') or name in allowed:
            continue
        src = io.open(os.path.join(pkg, name), encoding='utf-8').read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ('MODELS', 'MODEL_LABELS'):
                bad.append(f'{name}: reads config.{node.attr}')
            if isinstance(node, ast.ImportFrom) and (node.module or '').endswith('config'):
                for a in node.names:
                    if a.name in ('MODELS', 'MODEL_LABELS'):
                        bad.append(f'{name}: imports {a.name} by value')
    assert not bad, ('these must read config.models() instead:\n  '
                     + '\n  '.join(bad))


# ── the background refresh ───────────────────────────────────

def test_the_refresh_runs_once_per_launch_and_never_on_a_screen(monkeypatch, tmp_path):
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    _logged_in(monkeypatch)
    calls = []
    _api(monkeypatch, calls=calls)
    monkeypatch.setattr(m, '_bg_started', False)

    started = []

    class _T:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            started.append(1)
            self.target()

    import threading
    monkeypatch.setattr(threading, 'Thread', _T)
    m.refresh_in_background()
    m.refresh_in_background()
    assert started == [1]
    assert len(calls) == 1


def test_a_refresh_that_explodes_is_swallowed(monkeypatch, tmp_path):
    # A catalogue refresh must never be why archeus misbehaves.
    Sandbox(monkeypatch, tmp_path)
    monkeypatch.setattr(m, '_bg_started', False)
    monkeypatch.setattr(m, 'fetch', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('x')))

    class _T:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

    import threading
    monkeypatch.setattr(threading, 'Thread', _T)
    m.refresh_in_background()          # must not raise


# ── the Updates surface ──────────────────────────────────────

def test_the_updates_row_says_when_the_picker_is_on_the_bundled_list(monkeypatch, tmp_path):
    """The one state a user cannot see from the picker itself."""
    from claude_sessions import versions
    Sandbox(monkeypatch, tmp_path)
    _cache(monkeypatch, tmp_path)
    assert 'bundled' in versions._models_row(m.status())

    _logged_in(monkeypatch)
    _api(monkeypatch)
    m.fetch(refresh=True)
    row = versions._models_row(m.status())
    assert '5 from Anthropic' in row and '4 families' in row
    assert 'bundled' not in row
