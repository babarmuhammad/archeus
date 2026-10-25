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
    assert ('pwd', 'policy-to-allow:all') in violations
    assert ('pwd', 'table-miss-auto-allow:all') in violations
    assert ('pwd', 'held-to-allowed') not in violations
    _, violations = compare(['pwd'], [result(True, outcome='halt')], [result(outcome='halt')])
    assert ('pwd', 'held-to-allowed') in violations


def test_a_capped_classified_command_is_not_a_held_to_allowed_move():
    _, violations = compare(['curl x'], [result(True, classes=('exec',), outcome='allow')],
                            [result(classes=('web',), row=None, held=True, outcome='halt')])
    assert not violations


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
    assert len(ids) == len(set(ids)) == 88 + 85 + 41
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


def test_executor_corpus_covers_each_tool_and_is_deterministic():
    import hashlib
    from tools.p21_classifier_moves import executor_rows
    rows = executor_rows()
    assert rows == executor_rows()
    assert len(rows) == 18
    # Pin tool names and commands independently of tests/review-derived frozen inputs.
    payload = '\n'.join(tool + '\0' + command for tool, command in rows)
    assert hashlib.sha256(payload.encode()).hexdigest() == (
        'a356ee9966b8bd7149f76ef839fb5cf51a23b0e5aca386717cd06216599522b4')


def test_comparison_rejects_removing_held_cap_for_each_executor():
    for tool in ('PowerShell', 'bash', 'UnknownExecutor'):
        shape = (tool, 'rm -rf x')
        _, violations = compare([shape], [result(True, held=True, outcome='halt')],
                                [result(True, outcome='halt')])
        assert (shape, 'held-cap-removed') in violations


def test_executor_rows_reach_classifier_and_have_held_cap(tmp_path):
    import json
    from tools.p21_classifier_moves import classify, executor_rows, policies
    source, target = tmp_path / 'corpus.json', tmp_path / 'results.json'
    rows = executor_rows()
    source.write_text(json.dumps({'commands': rows, 'context': {'workdir': '.'},
                                 'paths': {'file.txt': {'kind': 'file', 'contained': True}},
                                 'policies': policies()}), encoding='utf-8')
    assert classify(str(Path(__file__).resolve().parents[3]), str(source), str(target), True) == 0
    results = json.loads(target.read_text(encoding='utf-8'))
    validate_results(rows, results)
    for row in results:
        assert row['unclassified'] and row['held_cap'] and row['row'] is None
        assert 'allow' not in row['policies'].values()


def test_classify_counts_a_malformed_corpus_row_as_an_error(tmp_path):
    import json
    from tools.p21_classifier_moves import classify, policies
    source, target = tmp_path / 'corpus.json', tmp_path / 'results.json'
    rows = ['ls', ['Bash'], ['Bash', 'ls', 'x'], ['Bash', 3], ['Bash', 'ls']]
    source.write_text(json.dumps({'commands': rows, 'context': {'workdir': '.'}, 'paths': {},
                                 'policies': policies()}), encoding='utf-8')
    assert classify(str(Path(__file__).resolve().parents[3]), str(source), str(target)) == 1
    results = json.loads(target.read_text(encoding='utf-8'))
    assert ['error' in r for r in results] == [True, True, True, True, False]
