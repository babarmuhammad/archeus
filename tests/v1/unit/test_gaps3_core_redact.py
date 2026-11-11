"""T-1115: the highest-risk uncovered branches of `archeus/core/redact.py` (1-246) at
HEAD 56d53504, focused on the interaction of the two branches merged in 640309f8 (PEM
state, 33375020) with the keyed-secret rules (d5653e0b, ff456f3a). The four shipped
files (test_redact.py, test_redact_keyed.py, test_redact_red_team.py,
test_pins_core_redact.py) cover every statement line of the slice; what none of them
reaches is the single-line decision arms and the cross-feature combinations below.
Nothing here repeats a standalone keyed or standalone PEM case; every probe combines
both merged features in one input.

  1 after 159 (`text is None` on the name path) vs 161 (prose ends a json key): a
    prose field name carrying a `NAME=password` assignment masks the credential and
    keeps the key open; the same string as a value ends it.
  2 after 157-158 + scrub_json 202-215 (key before value): a keyed field name is
    redacted before its value while the key stays open; an END in a field name closes
    the state in time for the value to be read as plain.
  3 scrub_json 236-239 (clash rename) with a PEM END in a field name: two secret names
    collapsing to one redacted key keep every value and the document order across END.
  4 scrub_json 218-225 (state threads through nested containers) + after 155-156 + 161:
    a marker in a nested field name opens the key; a later prose `--password value` is
    credential-masked and closes the key behind it.
  5 after 157-158 + _KEYED long-flag/token rules: a JSON key spelling the END line ends
    the key, a later `--token value` / `token=value` is still masked and a fragment
    after it is plain (the close is real, not just masked).
  6 after 158 (`state in (None, channel)` false side for a cross-channel END) + scrub
    171-172: an END in the stderr channel cannot end a json key, and the tail after it
    keeps its `db_passwd=` name while the credential is masked.
  7 _short 148 (lowercase-word guard) + after 159 `_BODY` / 161 `_PROSE` false sides: a
    structural lowercase word survives an open key while the adjacent keyed secret
    value is masked.
  8 _BODY 133 (trailing quote/comma still a body line) + scrub 173 + pair logic 212-214
    + _PROSE 135 header lookahead: a private-key body line beside a Cookie header
    leaks neither and keeps the key open.
  9 redact 114-116 + _mask 101-102 before SECRET: a scoped `docker login -p` value
    before an inline BEGIN and a glued `mysql -p` value after the END both redact.
 10 scrub 168-175 + _VALUE `(?![\\[redacted)` + scrub_json state round-trip: a second
    scrub over the first output and state is a no-op, collisions keep their suffixes,
    and the input object is not modified.
 11 concurrency tier: two producer threads relay through Events (no sleeps) over one
    scrub chain each; the state machine keeps no hidden state between calls, so each
    chain matches its sequential result whatever the interleaving.

Every secret here is synthetic; nothing touches the OS, the filesystem or a clock.
"""

import copy
import json
import threading

from archeus.core.redact import redact, redact_json, scrub, scrub_json

KEY = 'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7'
BEG = '-----BEGIN PRIVATE KEY-----'
END = '-----END PRIVATE KEY-----'


def dump(x):
    return json.dumps(x, ensure_ascii=False, default=str)


# 1 ---------------------------------------------------------------------------

def test_a_prose_field_name_with_a_password_assignment_masks_and_keeps_the_key():
    """after 159 `text is None` (name path) vs 161 _PROSE: catches inverting the name
    path so a prose-shaped name ends the key, or dropping redact() from the name path
    so the credential survives."""
    doc = [BEG, {'export PASSWORD=SYNThh1 now': 'AQID'}]
    out = redact_json(doc)
    assert out[1] == {'export PASSWORD=[redacted] now': '[redacted]'}   # name kept, value masked
    assert 'SYNThh1' not in dump(out)
    assert scrub_json(doc)[1] == 'json'                                  # the prose name did not close it
    # the same string as a VALUE is prose: it ends the key and the next fragment is plain
    out2 = redact_json([BEG, 'export PASSWORD=SYNThh1 now', 'AQID'])
    assert out2[1] == 'export PASSWORD=[redacted] now' and out2[2] == 'AQID'
    assert scrub_json([BEG, 'export PASSWORD=SYNThh1 now', 'AQID'])[1] is None


# 2 ---------------------------------------------------------------------------

def test_a_keyed_field_name_is_redacted_before_its_value_while_the_key_is_open():
    """scrub 173 `not name and _short(text)` + after 159 name path + scrub_json key
    order (202-215): catches processing values before names (the AQID below would
    then mask after its own key closed the state, or stay plain before it opened),
    or masking keyed names only after the value was already written."""
    doc = {BEG: None, 'Password: SYNThh2': 'AQID'}
    out = redact_json(doc)
    assert out == {'[redacted]': None, 'Password: [redacted]': '[redacted]'}
    assert 'SYNThh2' not in dump(out)
    assert scrub_json(doc)[1] == 'json'                                  # opened by name, kept by name
    # the name's END must reach the state before the value is scrubbed...
    order = redact_json([BEG, {END + ' x': 'AQID'}])
    assert order == ['[redacted]', {'[redacted] x': 'AQID'}]              # value read as plain: name ran first
    # ...and a plain name must not close it, else this control is plain too
    assert redact_json([BEG, {'x': 'AQID'}]) == ['[redacted]', {'x': '[redacted]'}]


# 3 ---------------------------------------------------------------------------

def test_two_keyed_names_collapsing_to_one_field_keep_values_and_order_around_the_end():
    """scrub_json 236-239 clash rename under PEM state (218-225) + after 157-158:
    catches the clash suffix losing document order (indices would shift), dropping a
    colliding value, or an END field name failing to close the state before `tail`."""
    doc = [BEG, {'body': 'AQID', 'Authorization: Bearer SYNThh3a': 1,
                 'Authorization: Bearer SYNThh3b': 2, END: None, 'tail': 'AQID'}]
    out = redact_json(doc)
    inner = out[1]
    assert list(inner) == ['body', 'Authorization: [redacted] #1', 'Authorization: [redacted] #2',
                           '[redacted] #3', 'tail']                       # order and indices are positional
    assert list(inner.values()) == ['[redacted]', 1, 2, None, 'AQID']     # every value kept, tail plain
    assert 'SYNThh3' not in dump(out)
    assert scrub_json(doc)[1] is None                                     # the END name closed it


# 4 ---------------------------------------------------------------------------

def test_a_marker_in_a_nested_field_name_opens_a_key_a_prose_password_value_closes():
    """scrub_json 218-228 (one state threads through nested containers) + after
    155-156 (BEGIN via the name path) and 161 (prose ends it): catches the state being
    taken from the outer dict only, or the prose close happening before the keyed
    value was masked (then the first AQID would be plain)."""
    doc = {'outer': {'inner': {BEG: None}},
           'later': ['AQID', '--password SYNThh4 and more words', 'AQID']}
    out = redact_json(doc)
    assert out['later'] == ['[redacted]', '--password [redacted] and more words', 'AQID']
    assert 'SYNThh4' not in dump(out)
    assert scrub_json(doc)[1] is None                                     # the prose value closed it


# 5 ---------------------------------------------------------------------------

def test_a_key_spelling_the_end_line_ends_the_key_yet_a_later_token_still_masks():
    """after 157-158 (`state in (None, channel)` true side) + _KEYED rules: catches
    an END name that only masks without closing (the AQID would stay masked), or a
    token rule that stops running once a PEM was seen."""
    base = {'a': BEG, 'b': END}
    for pair, want in (('--token SYNThh5', '--token [redacted]'), ('token=SYNThh5', 'token=[redacted]')):
        out = redact_json({**base, 'c': pair, 'd': 'AQID'})
        assert out['c'] == want and out['d'] == 'AQID'
        assert 'SYNThh5' not in dump(out)
        assert scrub_json({**base, 'c': pair, 'd': 'AQID'})[1] is None


# 6 ---------------------------------------------------------------------------

def test_an_end_in_the_stderr_channel_cannot_end_a_json_key_while_its_password_masks():
    """after 158 false side (state='json', channel='stderr') + scrub 171-172: catches
    END closing a key of the other channel (then the follow-up fragment would be
    plain), or the tail after END being pasted back unredacted / the `db_passwd=`
    name being eaten too."""
    state = scrub(BEG, None, 'json')[1]
    assert state == 'json'
    out, state2 = scrub(END + ' tail db_passwd=SYNThh6 here', state, 'stderr')
    assert out == '[redacted] tail db_passwd=[redacted] here'
    assert 'SYNThh6' not in out and 'db_passwd=' in out                    # name kept, credential masked
    assert state2 == 'json'
    assert scrub('AQID', state2, 'json')[0] == '[redacted]'                # the key really is still open
    assert scrub('three plain words now', state2, 'stderr')[1] == 'json'   # prose of the other channel too


# 7 ---------------------------------------------------------------------------

def test_a_structural_lowercase_word_survives_an_open_key_beside_a_keyed_secret_value():
    """_short 148 (isalpha+islower guard) + after 159/161 false sides + pair logic
    212-214: catches the lowercase-word guard (structural `type`/`subtype` values are
    masked) or the keyed pair rule (the password value leaks) — each alone passes the
    shipped structural and keyed tests."""
    doc = {'type': 'result', 'password': 'SYNThh7;legacy', 'frag': 'AQID'}
    out, state = scrub_json(doc, 'json')
    assert out == {'type': 'result', 'password': '[redacted]', 'frag': '[redacted]'}
    assert state == 'json'
    assert 'SYNThh7' not in dump(out)        # the ';' value is not base64: only the pair rule masks it


# 8 ---------------------------------------------------------------------------

def test_a_body_line_with_a_trailing_quote_beside_a_cookie_line_leaks_neither():
    """_BODY 133 (quote/comma suffix still a body line) + scrub 173 + pair logic
    212-214 + _PROSE 135 header lookahead: catches the trailing `",` breaking body
    recognition (KEY would leak), or the Cookie line reading as prose and closing the
    key early (then a later fragment would be plain)."""
    doc = {'t': BEG, 'u': KEY + '",', 'v': 'Cookie: sid=SYNThh8; theme=dark'}
    out = redact_json(doc)
    assert out['u'] == '[redacted]' and KEY[:20] not in dump(out)
    assert out['v'] == 'Cookie: [redacted]' and 'SYNThh8' not in dump(out)   # name kept, whole line masked
    assert scrub_json(doc)[1] == 'json'                                      # a `Cookie:` header is not prose


# 9 ---------------------------------------------------------------------------

def test_scoped_login_flags_redact_around_a_key_on_the_same_text():
    """redact 114-116 (_SCOPED before SECRET, guard true) + _mask 101-102 + _PEM:
    catches the scoped value swallowing the BEGIN marker (the key would leak), the
    mysql glued -p not firing after a PEM consumed the text, or scoped masking
    clobbering the surrounding command words."""
    out = redact('run docker login -u app -p SYNThh9a ' + BEG + '\nSYNTHbody0123456\n'
                 + END + ' x\nmysql -u root -pSYNThh9b db')
    assert 'SYNThh9a' not in out and 'SYNThh9b' not in out and 'SYNTHbody' not in out
    assert out == 'run docker login -u app -p [redacted] [redacted] x\nmysql -u root -p[redacted] db'


# 10 --------------------------------------------------------------------------

def test_a_second_scrub_is_idempotent_across_collisions_and_pem_state():
    """scrub 168-175 + _VALUE `(?![\\[redacted)` + the state returned by scrub_json
    (175): catches a second pass re-masking `[redacted]` (the lookahead inverted), a
    state that no longer round-trips, or scrub_json mutating its input dict."""
    doc = {BEG: 'AQID', 'Password: SYNThh10a': 1, 'Password: SYNThh20b': 2,
           'Password: [redacted]#1': 'keep me'}
    snap = copy.deepcopy(doc)
    out1, state1 = scrub_json(doc)
    assert out1 == {'[redacted] #0': '[redacted]', 'Password: [redacted] #1': 1,
                    'Password: [redacted] #2': 2, 'Password: [redacted]#1 #3': 'keep me'}
    assert state1 == 'json' and doc == snap                                # input object untouched
    out2, state2 = scrub_json(out1, state1)
    assert out2 == out1 and state2 == state1                               # second pass changed nothing
    assert dump(out2) == dump(out1) and 'SYNThh10a' not in dump(out2)


# 11 --------------------------------------------------------------------------

def test_two_producer_threads_relaying_through_events_share_no_scrub_state():
    """after 151-161 + scrub 163-175 as a chain: catches any hidden state carried
    between scrub calls (a memo, a module-level plain cache): with the two chains
    relayed item-by-item through Events, thread J's stderr peer could not keep its
    channel semantics. Every wait is bounded and released in finally; no sleeps."""
    jc = [BEG, 'AQID', END, 'Password: SYNThh4 and words']
    sc = [BEG, 'AQID', 'db_passwd=SYNThh8 keep', 'AQID']
    exp_j = (['[redacted]', '[redacted]', '[redacted]', 'Password: [redacted] and words'], None)
    exp_s = (['[redacted]', '[redacted]', '[redacted]', '[redacted]'], 'stderr')
    ev_j = [threading.Event() for _ in jc]
    ev_s = [threading.Event() for _ in sc]
    got, errs = {}, {}

    def run(tag, channel, items, mine, releases):
        outs, state = [], None
        try:
            for i, text in enumerate(items):
                if not mine[i].wait(10):                                   # bounded, never a sleep
                    raise TimeoutError('%s starved at %d' % (tag, i))
                o, state = scrub(text, state, channel)
                outs.append(o)
                for e in releases[i]:                                      # hand the turn over
                    e.set()
        except BaseException as exc:                                       # noqa: BLE001 - reported below
            errs[tag] = repr(exc)
        finally:
            for evs in releases:                                           # never leave the peer hanging
                for e in evs:
                    e.set()
        got[tag] = (outs, state)

    tj = threading.Thread(target=run, args=('j', 'json', jc, ev_j, [[e] for e in ev_s]))
    ts = threading.Thread(target=run, args=('s', 'stderr', sc, ev_s, [ev_j[1:], ev_j[2:], ev_j[3:], []]))
    ts.start()
    tj.start()
    ev_j[0].set()                                                           # J goes first, then strict relay
    tj.join(20)
    ts.join(20)
    assert not tj.is_alive() and not ts.is_alive()
    assert errs == {}
    assert got['j'] == exp_j and got['s'] == exp_s                          # same as each chain alone
