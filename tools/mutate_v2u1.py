"""The V2-U1 mutation suite (V2 real build plan §4.4): break each invariant of the
bundle budget, the V2 tokens and the spine, run the test written for it, and
require it to fail.

    py tools/mutate_v2u1.py            every mutation
    py tools/mutate_v2u1.py U01 U05    only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine): each
mutation replaces exact snippets (each must occur once), runs its tests and
restores the files whatever happens; a mutation the tests do not catch
("survived") fails the run. A mutant guarded by the bundle budget or a browser
test rebuilds the SPA before the run and again after the restore. It edits
sources: run it with nothing else running against the tree.
"""

import base64
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

MAIN = 'clients/app/src/main.tsx'
BUDGET = 'node:test/budget.test.ts'
TOK = 'clients/app/tokens/tokens.json'
CSS = 'clients/app/src/styles/tokens.css'
MANIFEST = 'clients/app/public/manifest.webmanifest'
DG = 'tests/v1/design/test_design_gates.py::'
CONTRAST = DG + 'test_every_role_clears_its_contrast_floor_on_every_surface'
HC = DG + 'test_high_contrast_reaches_its_floors_on_every_surface'
CURRENT = DG + 'test_the_generated_ui_files_are_current'
SETS = DG + 'test_t6_only_the_token_sets_are_themes_and_each_has_its_attribute'
HUE = DG + 'test_a_state_keeps_its_one_hue_in_every_look'
BAND = DG + 'test_text_on_the_attention_band_clears_its_floor'
OWNER = DG + 'test_done_is_green_and_blocked_and_focus_are_the_owners_dark_values'
V2 = DG + 'test_the_v2_tokens_hold_their_approved_values_and_reach_the_css'
EMIT = DG + 'test_each_themes_high_contrast_values_are_emitted_under_every_form_that_selects_it'
MANI = DG + 'test_the_manifest_names_what_the_pwa_needs'
DARK_ROLES = ('"bg": "#0C0811", "surface-1": "#0E131C", "surface-2": "#151C2A", "surface-3": "#1C2536", '
              '"line": "#292D33", "line-strong": "#484B4D", "text": "#EFE9DA", "text-2": "#BDB7A8", "text-3": "#ABA699", '
              '"primary": "#EFE9DA", "on-primary": "#0C0811", "thread": "#EFE9DA", "focus": "#FFF3CF", '
              '"state.active": "#6FB1FF", "state.attention": "#F2B544", "state.blocked": "#F07178", '
              '"state.paused": "#9AA5B8", "state.thinking": "#C7B2F0", "state.done": "#6FD39A"')
LIGHT_LAST = '"state.paused": "#5B6982", "state.thinking": "#7947DB", "state.done": "#247647"'


def _padding(n):
    out, h = b'', hashlib.sha256(b'v2u1')
    while len(out) < n:
        h = hashlib.sha256(h.digest())
        out += h.digest()
    return base64.b64encode(out[:n]).decode()


MUTATIONS = [
    ('U01', 'a 50 KB incompressible string shipped in the bundle', [(MAIN,
     "import App from './App';",
     "import App from './App';\nconsole.log('" + _padding(50_000) + "');")],
     [BUDGET]),
    ('U02', 'Dark text-3 lowered to 3.4:1, under the V2 4.5 floor and over the V1 3.0', [(TOK,
     '"text": "#EFE9DA", "text-2": "#BDB7A8", "text-3": "#ABA699",',
     '"text": "#EFE9DA", "text-2": "#BDB7A8", "text-3": "#807C70",')],
     [CONTRAST]),
    ('U03', 'Dark high contrast blocked left at its standard value, 5.4:1 against a 7:1 floor', [(TOK,
     '"state.blocked": "#F4969B"',
     '"state.blocked": "#F07178"')],
     [HC]),
    ('U04', 'tokens.css edited by hand', [(CSS,
     '  --text-3: #ABA699;',
     '  --text-3: #ABA69A;')],
     [CURRENT]),
    ('U05', 'a third theme key', [(TOK,
     LIGHT_LAST,
     LIGHT_LAST + '}, "sepia": {' + DARK_ROLES)],
     [SETS, CURRENT]),
    ('U06', 'Light Done in teal: contrast and deltaE hold, the hue differs between themes', [(TOK,
     '"state.done": "#247647"',
     '"state.done": "#0C6F66"')],
     [HUE]),
    ('U07', 'a high contrast form left out of the CSS', [(CSS,
     "  :root:not([data-theme='light']):not([data-contrast='standard']) {",
     "  :root:not([data-theme='light']):not([data-contrast='standard']):not([data-x]) {")],
     [EMIT]),
    ('U08', 'the manifest background left on the old ground', [(MANIFEST,
     '"background_color": "#0C0811",',
     '"background_color": "#0E1116",')],
     [MANI]),
    ('U09', 'the attention band raised from 12 % to 30 %', [(TOK,
     '"hull": 0.06, "hull-focus": 0.1, "band": 0.12},',
     '"hull": 0.06, "hull-focus": 0.1, "band": 0.30},')],
     [BAND]),
    ('U10', 'the primary desktop target dropped', [(TOK,
     '"targets": {"desktop": 28, "desktop-primary": 44, "phone": 44},',
     '"targets": {"desktop": 28, "phone": 44},')],
     [V2]),
    ('U11', 'Dark focus back to the thread ink', [(TOK,
     '"primary": "#EFE9DA", "on-primary": "#0C0811", "thread": "#EFE9DA", "focus": "#FFF3CF",',
     '"primary": "#EFE9DA", "on-primary": "#0C0811", "thread": "#EFE9DA", "focus": "#EFE9DA",')],
     [OWNER]),
    ('U12', "Dark blocked as the prototype's Stop red, 4.3:1 on surface-3", [(TOK,
     '"state.active": "#6FB1FF", "state.attention": "#F2B544", "state.blocked": "#F07178",',
     '"state.active": "#6FB1FF", "state.attention": "#F2B544", "state.blocked": "#E5585E",')],
     [CONTRAST]),
]

_needs_build = mutate_p18._needs_build
mutate_p18._needs_build = lambda tests: _needs_build(tests) or BUDGET in tests

if __name__ == '__main__':
    unknown = set(sys.argv[1:]) - {m[0] for m in MUTATIONS}
    if unknown:
        raise SystemExit('Unknown mutant IDs: ' + ', '.join(sorted(unknown)))
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
