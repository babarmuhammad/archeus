"""T-745: the highest-risk uncovered branches of archeus/core/domain/words.py.

words.py is the generated copy of the clients' words (presentation.json) that
Core's own status verb speaks (R13-06). It holds one literal, LABELS, and both
of its consumers look words up with a fail-OPEN default:
`LABELS.get(machine, {}).get(state, state)` in
archeus/core/application/conversation.py:881 and archeus/cli/tui/present.py:28.
A missing machine or state is therefore never an error: Core says the raw
enum ('Ship the fix (EXECUTING)') and the TUI draws it, so every gap in this
table is silent. The guards here close those branches from the data side:
completeness against states.TABLE (no machine and no state can lack a word,
and no stale key can hide one), the derivation tools/gen_ui.py applies to
clients/app/tokens/presentation.json (a hand-edit of the generated file is a
divergence, not a fix), and the value rules every word must satisfy (a str,
never blank, never the raw enum itself, one printable line, canonical ids).
The style and fixtures are tests/v1/unit/test_state_tables.py and
test_gaps_core_domain_guards.py: pure data, no I/O beyond reading the two
generated/source files of this module, no OS, no clock, platform-neutral.
"""

import ast
import json
import os
import re

import pytest

from archeus.core.domain import states
from archeus.core.domain.words import LABELS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
TOKENS = os.path.join(ROOT, 'clients', 'app', 'tokens', 'presentation.json')
WORDS = os.path.join(ROOT, 'archeus', 'core', 'domain', 'words.py')

STATE_ID = re.compile(r'[A-Z][A-Z0-9_]*')
MACHINE_ID = re.compile(r'[a-z][a-z_]*')


def _tokens():
    with open(TOKENS, encoding='utf-8') as f:
        return json.load(f)


def _derived_labels():
    """Exactly what tools/gen_ui.py puts in words.py: `_labels()` (gen_ui.py:386-387)
    over presentation.json's machines, each word an explicit `labels` override or
    the sentence-case default `_label()` (gen_ui.py:167-168)."""
    p = _tokens()

    def _label(state):
        return state.replace('_', ' ').capitalize()

    return {m: {s: p.get('labels', {}).get(m, {}).get(s) or _label(s) for s in table}
            for m, table in sorted(p['machines'].items())}


# ── fail-closed: the fail-open lookups can never answer from a gap ────────────

@pytest.mark.parametrize('machine', states.MACHINES)
def test_every_machine_core_can_reach_has_its_own_words(machine):
    """conversation.py:881 defaults a missing machine to `{}` (mirror:
    present.py:28), so one absent key makes Core speak EVERY state of that
    machine as a raw enum. Deleting a whole block of words.py:4 must fail here,
    not ship as 'LOST', 'OPEN', 'RETIRED'... in the user's sentences."""
    assert machine in LABELS, 'no words at all for %s' % machine
    assert isinstance(LABELS[machine], dict) and LABELS[machine], \
        '%s: the block exists but is empty, and {} is the same fail-open' % machine


@pytest.mark.parametrize('machine', states.MACHINES)
def test_no_machine_key_that_no_state_machine_declares(machine):
    """A misspelt machine key (words.py:4, e.g. 'acount_health') is never
    looked up, so it neither supplies words nor shows up as missing: the
    fail-open above stays invisible. The key set must equal states.MACHINES,
    not merely overlap it."""
    assert machine in LABELS and machine in set(LABELS)
    assert sorted(LABELS) == sorted(states.MACHINES), \
        'words.py names %s; states.py declares %s' % (
            sorted(set(LABELS) - set(states.MACHINES)),
            sorted(set(states.MACHINES) - set(LABELS)))


@pytest.mark.parametrize('machine', states.MACHINES)
def test_every_state_of_every_machine_has_a_label(machine):
    """conversation.py:881: `.get(state, state)` answers a missing state with
    the enum itself — tests/v1/integration/test_p21_live.py:175 proves that
    text must never contain 'EXECUTING'. Every state states.TABLE can put on a
    row (real states only: START/END excluded by states.states()) must have its
    word, so deleting one entry of words.py:4 fails here."""
    have = set(LABELS.get(machine, {}))
    missing = set(states.states(machine)) - have
    assert not missing, '%s: no word for %s' % (machine, sorted(missing))


@pytest.mark.parametrize('machine', states.MACHINES)
def test_no_state_key_that_the_machine_does_not_have(machine):
    """The inverse gap: a stale key (a renamed or deleted state, or a typo
    that capitalises like the enum but never matches one) sits in LABELS[machine]
    and keeps a naive count check green while the REAL state still falls
    through conversation.py:881 to the raw enum."""
    extra = set(LABELS.get(machine, {})) - set(states.states(machine))
    assert not extra, '%s: words for states the machine cannot be in: %s' % (
        machine, sorted(extra))


def test_the_words_are_exactly_the_derivation_from_the_tokens():
    """words.py:1 says 'Generated by tools/gen_ui.py ... Do not edit' and
    gen_ui.py:386-387 derives it from clients/app/tokens/presentation.json:
    the `labels` override or the `_label()` default (gen_ui.py:167-168).
    Re-deriving and comparing catches any hand-edit of the generated file —
    a softened word ('Degraded' -> 'Fine') passes every other test here."""
    assert LABELS == _derived_labels()


# ── boundary values: the words themselves ─────────────────────────────────────

@pytest.mark.parametrize('machine', states.MACHINES)
def test_no_word_is_blank_or_padded(machine):
    """Boundary values of the one value rule the copy enforces (gen_ui.py's
    `or _label(s)` refuses only falsy overrides): '' embedded by
    conversation.py:881's caller reads 'Ship the fix ()', and a whitespace
    label is truthy, so even present.py:33's `label or state` rescue lets the
    TUI draw an empty badge. No word may be empty, all-space, or padded."""
    for state, word in LABELS[machine].items():
        assert isinstance(word, str) and word.strip(), \
            '%s.%s: blank word %r' % (machine, state, word)
        assert word == word.strip(), '%s.%s: padded word %r' % (machine, state, word)


@pytest.mark.parametrize('machine', states.MACHINES)
def test_every_word_is_a_string(machine):
    """conversation.py:881 hands the value straight to '%s' formatting; a None
    or a number from a hand-edited literal is spoken to the user as 'None' or
    '17' and no lookup fails first. Type is a boundary this table cannot
    enforce by shape alone."""
    for state, word in LABELS[machine].items():
        assert type(word) is str, '%s.%s: %r is not a str' % (machine, state, word)


@pytest.mark.parametrize('machine', states.MACHINES)
def test_keys_are_the_canonical_ids_the_lookup_compares_against(machine):
    """Ids that must be rejected: the lookup is an exact dict hit against
    states.TABLE's strings, so a key like 'Paused ', 'paused' or 'PAUSED-' can
    never match a row — and, invisible, it also hides the missing real key
    behind a looks-complete table. Machine keys likewise against
    states.MACHINES."""
    assert MACHINE_ID.fullmatch(machine), 'machine id %r is not a lowercase id' % machine
    for state in LABELS[machine]:
        assert STATE_ID.fullmatch(state), '%s: state id %r is not [A-Z][A-Z0-9_]*' % (
            machine, state)


@pytest.mark.parametrize('machine', states.MACHINES)
def test_no_word_is_the_raw_state_name_it_labels(machine):
    """The fail-open at conversation.py:881 is self-concealing: if the label
    equals the enum ('FAILED': 'FAILED'), the raw word the fallback speaks is
    indistinguishable from the label, and the R13-06 check
    (test_p21_live.py:175, 'EXECUTING' not in text) can never fire. Words are
    sentence case, states are screaming ids; equality means a gap."""
    for state, word in LABELS[machine].items():
        assert word != state, '%s: the word for %s is the enum itself' % (machine, state)


@pytest.mark.parametrize('machine', states.MACHINES)
def test_no_word_carries_a_control_character_or_a_line_break(machine):
    """Error path in the renderers, not the lookup: present.badge
    (archeus/cli/tui/present.py:31-34) and the chat lines of conversation.py
    print the word on ONE line; a '\\n' or a control character in a word
    (possible only via a hand-edited override — gen_ui's source is JSON but
    JSON permits escapes) splits the row and breaks the table."""
    for state, word in LABELS[machine].items():
        assert word.isprintable() and '\n' not in word and '\t' not in word, \
            '%s.%s: unprintable/control in word %r' % (machine, state, word)


# ── the two copies, and the literal that can hide a value ─────────────────────

def test_core_and_the_tui_say_the_same_words():
    """R13-06 ('use the same words'): words.py and archeus/cli/tui/_tables.py
    are two generated copies of presentation.json and the clients diff them
    (tests/v1/integration/test_p21_live.py:188). At unit level nothing checks
    it, so a regeneration of one file alone — the most likely mistake around
    this module — goes unnoticed until a human sees two vocabularies."""
    from archeus.cli.tui import _tables
    assert LABELS == _tables.LABELS


def test_the_generated_literal_has_no_duplicate_keys():
    """The one failure a *value*-level check cannot see: a regenerated literal
    (pprint, words.py:4) that lists a state twice keeps only the last value and
    everything above still passes — the machine exists, the state exists, the
    surviving word is a fine string. Scan the AST for repeated keys in one
    dict, which a hand-patched or badly merged generation always introduces."""
    with open(WORDS, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=WORDS)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
        seen = set()
        for k in keys:
            assert k not in seen, 'duplicate key %r at line %d of words.py' % (k, node.lineno)
            seen.add(k)
