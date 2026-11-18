"""Mutation-verify the Phase 4 stage gates. Each mutation must turn the named
test red; a gate that survives its own mutation is testing the bug."""
import shutil
import subprocess
import sys

SRC = 'claude_sessions/web/stage.js'
BAK = SRC + '.mutbak'

MUTS = [
    ('new TH.IcosahedronGeometry(1, 1)', 'new TH.DodecahedronGeometry(1, 0)',
     'test_the_clusters_are_geodesic_cages_not_platonic_solids'),
    ('Math.pow(h, 4) * 1.50', 'Math.pow(h, 3) * 1.15',
     'test_the_clusters_vary_in_size_and_collide_by_mass'),
    ('u_calm + 0.18', 'u_calm + 0.34',
     'test_a_link_is_duller_than_a_strut_and_a_node_is_the_brightest_thing'),
    ('core * 0.75', 'core * 0.40',
     'test_the_nodes_are_white_cored_with_a_coloured_halo'),
    ('0.55 * n.r * Math.pow(hr, 0.45)', '0.55 * n.r * hr',
     'test_a_cluster_is_made_of_clusters'),
    ('vec3 a = u_np[int(li)], b = u_np[int(lo)];', 'vec3 a = u_np[int(li)], b = a;',
     'test_a_link_joins_two_nodes_and_never_crosses_a_hull'),
    ('col = mix(u_bg, col, vF);', 'col = col;',
     'test_depth_washes_toward_the_background_before_calm_not_instead_of_it'),
    ('const TONES = [0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.95];',
     'const TONES = [0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0];',
     'test_gold_and_green_reach_the_constellation'),
    ('mix(hue5(vN.y), hue5(vN.y + 0.28), vJ * 0.45)', 'hue5(vN.y)',
     'test_a_cage_is_one_hue_but_not_only_one_hue'),
    ('const seen = new Set(), V = [];', 'const seen = new Map(), V = [];',
     'test_the_joints_are_deduplicated_to_the_distinct_hull_vertices'),
]


def run(test):
    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--no-header',
                        f'tests/test_stage.py::{test}'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    return r.returncode


shutil.copy2(SRC, BAK)
bad = []
try:
    for old, new, test in MUTS:
        src = open(BAK, encoding='utf-8').read()
        assert old in src, f'mutation target gone: {old}'
        open(SRC, 'w', encoding='utf-8').write(src.replace(old, new))
        rc = run(test)
        print(('RED  ' if rc else 'GREEN') + f'  {test}  <- {old[:44]}')
        if rc == 0:
            bad.append(test)
finally:
    shutil.copy2(BAK, SRC)
    import os
    os.remove(BAK)

print()
if bad:
    print('NOT A GATE:', *bad, sep='\n  ')
    sys.exit(1)
print(f'all {len(MUTS)} mutations caught')
