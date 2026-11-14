"""T-1088: the command corpus for what Archeus persists, pinned against the real `redact`.

tests/fixtures/persisted_secrets/commands.json holds shell commands of the shapes that
land in `.claude/settings.local.json` allow rules, `.archeus/bash-log.txt` and
`.archeus/denied.jsonl` (the apiiro finding, HN 50407882). Each case records what
`archeus.core.redact.redact` returns TODAY and a bucket:
  caught               a secret is masked
  missed               a secret stays in clear
  benign_ok            nothing to hide and nothing changed
  benign_overredacted  nothing to hide but something is masked (a false positive)
T-1089 (owner item 100) flipped the 17 rows missed by T-1088 to caught and the two -u
over-redactions to benign_ok; the rows from p38 measure what the keyed rules cost: the
look-alikes they leave alone, the false positives the owner accepted, and what they still miss.
`redact` is pure, so this file runs no process and no I/O beyond reading the JSON.
"""

import json
import pathlib

import pytest

from archeus.core.redact import redact

PATH = (pathlib.Path(__file__).resolve().parents[2] / 'fixtures' / 'persisted_secrets'
        / 'commands.json')
GHP_TOKEN = 'ghp_' + 'x' * 36  # built here so no token-shaped literal lives in the repo
CASES = [dict(c, cmd=c['cmd'].replace('__GHP_TOKEN__', GHP_TOKEN))
         for c in json.loads(PATH.read_text(encoding='utf-8'))['cases']]
BUCKETS = {'caught', 'missed', 'benign_ok', 'benign_overredacted'}


def test_the_corpus_is_well_formed():
    assert len(CASES) >= 25
    assert len({c['id'] for c in CASES}) == len(CASES)
    assert all(set(c) == {'id', 'bucket', 'cmd', 'expected', 'note'} for c in CASES)
    assert {c['bucket'] for c in CASES} == BUCKETS


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_redact_gives_the_recorded_outcome(case):
    assert redact(case['cmd']) == case['expected']
    changed = case['expected'] != case['cmd']
    assert changed == (case['bucket'] in ('caught', 'benign_overredacted'))
