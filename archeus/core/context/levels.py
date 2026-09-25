"""The context engine's policy: levels, budget shares, the relevance formula and
its weights (context-and-knowledge §2.1–§2.2; p5-design-gate §5). Every tunable
number the engine uses is in this module and nowhere else.
"""

#: Levels, in the order they are filled (context-and-knowledge §2.1).
LEVELS = ('L0', 'L1', 'L2', 'L3', 'L4')
LEVEL_NAMES = {'L0': 'immediate', 'L1': 'project', 'L2': 'related', 'L3': 'historical',
               'L4': 'global'}
#: Default share of the token budget per level. Unused budget flows down.
SHARES = {'L0': 0.40, 'L1': 0.30, 'L2': 0.15, 'L3': 0.10, 'L4': 0.05}
assert abs(sum(SHARES.values()) - 1.0) < 1e-9

#: The three stores of truth, in the order a level lists them (§1: current
#: state before knowledge before history, so a stale fact never reads first).
STORES = ('state', 'knowledge', 'history')

#: §2.3's example budget; a caller may ask for another.
DEFAULT_BUDGET_TOKENS = 12000

#: Temporal retrieval (§2.2): the project's recent events. The window is also
#: the recency horizon: an item observed a window ago or earlier scores 0.
HISTORY_WINDOW_DAYS = 7
#: Candidate bound for that retrieval, newest first. A retrieval bound, not a
#: ranking input: the level budget decides what of it is included.
HISTORY_CANDIDATES = 50

#: The relevance formula (§2.2), one weight per term. A term whose input no
#: phase produces yet is kept at 0 so the formula never changes shape: anchor
#: (task files, P7+), link (relation proximity, P6), confidence and useless
#: (knowledge usage signals, P6).
WEIGHTS = {'lex': 1.0, 'anchor': 0.0, 'link': 0.0, 'rec': 0.5, 'auth': 1.0, 'conf': 0.0,
           'stale': 0.5, 'useless': 0.0}
#: Terms the formula subtracts.
PENALTIES = ('stale', 'useless')

#: Authority (§2.2): explicit user item > CONFIRMED decision/standard >
#: EXTRACTED fact > INFERRED fact > CANDIDATE.
AUTHORITY = {'explicit': 1.0, 'confirmed': 0.9, 'extracted': 0.8, 'inferred': 0.5,
             'candidate': 0.3}


def relevance(signals):
    """score = Σ w·signal, penalties subtracted (§2.2)."""
    return sum(WEIGHTS[k] * v * (-1 if k in PENALTIES else 1) for k, v in signals.items())
