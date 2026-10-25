from dataclasses import replace
from pathlib import Path

import pytest

from archeus.core.execution.command_allowlist import ROWS
from tools.p21_allowlist_gate import check_gate, generated_table
from tools.p21_classifier_moves import (
    POLICIES, automatic_outcome, compare, extract_archive, strings_from_tests,
    validate_results,
)


def result(unclassified=False, classes=('read',), row='A01', held=False, outcome='allow'):
    return {'unclassified': unclassified, 'classes': list(classes), 'row': row,
            'held_cap': held, 'policies': dict.fromkeys(POLICIES, outcome)}


def test_comparison_rejects_errors_and_missing_results():
    for results in ([], [result(), result()], [{'error': 'parse failed'}], [{}]):
        with pytest.raises(ValueError):
            validate_results(['pwd'], results)


def test_comparison_counts_flag_policy_and_cap_violations():
    _, violations = compare(['pwd'], [result(True, outcome='deny')], [result(held=True)])
    assert ('pwd', 'held-to-allowed') in violations
    assert ('pwd', 'policy-to-allow:all') in violations
    assert ('pwd', 'table-miss-auto-allow:all') in violations


def test_class_set_and_row_moves_are_reported_without_flag_move():
    moves, violations = compare(['pytest'], [result(classes=('exec',))],
                                [result(classes=('read',), row='A14')])
    key = next(iter(moves))
    assert key[:2] == (('exec',), ('read',))
    assert key[4] == 'A14'
    assert not violations


def test_held_cap_cannot_override_deny_or_open_permissive_policy():
    assert automatic_outcome(['ALLOW'], True) == 'halt'
    assert automatic_outcome(['DENY', 'ALLOW'], True) == 'deny'
    assert automatic_outcome(['ASK'], False) == 'halt'
    assert automatic_outcome(['ALLOW'], False) == 'allow'


def test_unavailable_baseline_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_archive(tmp_path / 'missing.tar', tmp_path / 'baseline')


def test_old_test_strings_include_static_adversarial_inputs(tmp_path):
    (tmp_path / 'test_old.py').write_text("x = 'sed ' + '\\\\a' * 30\ny = 'npm pu'\n", encoding='utf-8')
    values = strings_from_tests(tmp_path)
    assert 'npm pu' in values
    assert 'sed ' + '\\a' * 30 in values


def test_gate_allowlist_block_matches_data():
    text = (Path(__file__).resolve().parents[3] / 'docs/architecture/p21-design-gate.md').read_text(encoding='utf-8')
    check_gate(text)


def test_gate_drift_is_rejected_in_both_directions():
    from tools.p21_allowlist_gate import BEGIN, END
    text = BEGIN + '\n' + generated_table() + '\n' + END
    with pytest.raises(ValueError, match='drift'):
        check_gate(text.replace('| A01 | pwd |', '| A01 | env |'))
    with pytest.raises(ValueError, match='drift'):
        check_gate(text, (replace(ROWS[0], program='env'), *ROWS[1:]))


@pytest.mark.parametrize('command,cls', [('pwd', 'read'), ('pytest', 'exec')])
def test_matched_policy_contexts_exercise_real_engine(command, cls):
    from archeus.core.execution.canonical import canonicalise_hook
    from archeus.core.policy.engine import evaluate_item
    from tools.p21_classifier_moves import policies
    from v1.unit.test_command_allowlist import CONTEXT
    (actions, unc), eligibility = canonicalise_hook('Bash', command, {'workdir': '.'}, CONTEXT)
    assert eligibility.status == 'ALLOWED' and not unc
    contexts = policies()
    expected = {'all': 'ALLOW', 'deny_' + cls: 'DENY', 'ask_' + cls: 'ASK',
                'locked_' + cls: 'DENY', 'exclude_' + cls: 'ASK'}
    for name, decision in expected.items():
        assert evaluate_item(actions[0], contexts[name])['decision'] == decision


def test_mutant_ledger_does_not_count_unfinished_or_retired_rows():
    from tools.mutate_p21 import (
        MERGED_REDEFINE, MUTATIONS, NEW_MUTATIONS, NOT_DONE_REDEFINE, REDEFINED,
    )
    ids = [entry[0] for entry in MUTATIONS]
    assert len(ids) == len(set(ids)) == 88 + 85 + 29
    assert len(REDEFINED) == 85
    assert len(NOT_DONE_REDEFINE) == 31
    assert MERGED_REDEFINE == {'Z175': 'Z173', 'Z217': 'Z319'}
    assert len(REDEFINED) + len(NOT_DONE_REDEFINE) + len(MERGED_REDEFINE) == 118
    assert set(MERGED_REDEFINE).isdisjoint(ids)
    assert set(MERGED_REDEFINE).isdisjoint(NOT_DONE_REDEFINE)
    assert set(MERGED_REDEFINE.values()) <= set(ids)
    assert set(ids).isdisjoint(NOT_DONE_REDEFINE)
    assert set(ids).isdisjoint({'Z194', 'Z195', 'Z206', 'Z214', 'Z222', 'Z268', 'Z292'})
    root = Path(__file__).resolve().parents[3]
    for mid, _, edits, _ in REDEFINED + NEW_MUTATIONS:
        for path, before, after in edits:
            assert before != after, mid
            assert (root / path).read_text(encoding='utf-8').count(before) == 1, mid
