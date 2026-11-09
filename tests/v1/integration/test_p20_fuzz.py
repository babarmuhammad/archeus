"""P20 D12 in CI: tools/fuzz_p20.py with a fixed seed and a small budget. The
large budget is `py tools/fuzz_p20.py --budget N --seed S`, on demand."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import fuzz_p20  # noqa: E402

SEED = 20


def test_no_fuzzed_command_body_is_a_500(tc):
    assert fuzz_p20.fuzz_routes(tc.core.api, tc.token, SEED, 3000) == []


def test_the_canonicaliser_answers_every_fuzzed_call_conservatively():
    assert fuzz_p20.fuzz_canonical(SEED, 10000) == []
