"""LE-7 (LD-8): measure, do not change. The six state colours' perceived weight in OKLCH, and a
warm-neutral candidate for the greys, against V1's own floors (4.5:1 body, 3:1 state and
secondary). Pure computation over the V1 token values. Prototype tooling.

    py colour.py   -> results/le7/colour.json
"""
import json
import math

from serve import results

DARK = dict(bg='#0E1116', s1='#141922', s2='#1A2130', s3='#202838', line='#2A3344', line_strong='#3A4558', text='#E6EAF0', text2='#AAB3C0', text3='#8A94A3',
            active='#5AA9FF', attention='#F2B544', blocked='#F07178', paused='#A7B0BD', thinking='#B79CFF', done='#5FD08B')
LIGHT = dict(bg='#F7F8FA', s1='#FFFFFF', s2='#F1F3F6', s3='#FFFFFF', line='#DDE1E7', line_strong='#B9C0CB', text='#11151C', text2='#4A5463', text3='#6A7382',
             active='#0B63CE', attention='#8A5600', blocked='#B3261E', paused='#5B6472', thinking='#6A45C9', done='#1E7F45')
STATES = ('active', 'attention', 'blocked', 'paused', 'thinking', 'done')
NEUTRALS = ('bg', 's1', 's2', 's3', 'line', 'line_strong', 'text', 'text2', 'text3')


def srgb(h):
    return [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def unlin(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def oklab(h):
    r, g, b = (lin(x) for x in srgb(h))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def from_oklch(L, C, H):
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return '#' + ''.join('%02X' % round(unlin(c) * 255) for c in rgb)


def lch(h):
    L, a, b = oklab(h)
    return round(L, 4), round(math.hypot(a, b), 4), round(math.degrees(math.atan2(b, a)) % 360, 1)


def lum(h):
    r, g, b = (lin(x) for x in srgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return round((x + 0.05) / (y + 0.05), 2)


def de(a, b):  # deltaE OK, x100
    return round(100 * math.dist(oklab(a), oklab(b)), 1)


def warm(p, hue=70.0, chroma_scale=0.6):
    """Re-hue every neutral to `hue` at its own OKLCH lightness, with chroma kept low
    ('charcoal, not steel'): only hue changes and chroma shrinks; lightness is held exactly."""
    out = dict(p)
    for k in NEUTRALS:
        L, C, _ = lch(p[k])
        out[k] = from_oklch(L, min(C, 0.02) * chroma_scale + 0.004, hue)
    return out


def report(p):
    st = {k: dict(zip(('L', 'C', 'H'), lch(p[k])), on_bg=contrast(p[k], p['bg']), on_s1=contrast(p[k], p['s1']), on_s3=contrast(p[k], p['s3'])) for k in STATES}
    Ls = [st[k]['L'] for k in STATES]
    Cs = [st[k]['C'] for k in STATES if k != 'paused']
    pairs = {f'{a}/{b}': de(p[a], p[b]) for i, a in enumerate(STATES) for b in STATES[i + 1:]}
    neu = {k: dict(zip(('L', 'C', 'H'), lch(p[k])), hex=p[k]) for k in NEUTRALS}
    floors = {'text/bg': contrast(p['text'], p['bg']), 'text2/s1': contrast(p['text2'], p['s1']), 'text3/s3': contrast(p['text3'], p['s3']),
              'text3/bg': contrast(p['text3'], p['bg'])}
    return dict(states=st, L_spread=round(max(Ls) - min(Ls), 4), L_range=[min(Ls), max(Ls)], chroma_range=[min(Cs), max(Cs)],
                min_state_deltaE=min(pairs.values()), min_pair=min(pairs, key=pairs.get), state_floor_3_1=min(min(v['on_bg'], v['on_s1'], v['on_s3']) for v in st.values()),
                neutrals=neu, floors=floors, floors_pass=floors['text/bg'] >= 4.5 and floors['text2/s1'] >= 4.5 and floors['text3/s3'] >= 3 and floors['text3/bg'] >= 3)


def main():
    R = {'dark': report(DARK), 'light': report(LIGHT)}
    for hue in (60, 70, 80):
        R['dark_warm_%d' % hue] = report(warm(DARK, hue))
        R['light_warm_%d' % hue] = report(warm(LIGHT, hue))
    json.dump(R, open(results('le7', 'colour.json'), 'w', encoding='utf-8'), indent=1)
    for k, r in R.items():
        print('%-14s L %s spread %.3f  C %s  minΔE %s (%s)  state≥3:1 %s  floors %s %s' % (k, r['L_range'], r['L_spread'], r['chroma_range'], r['min_state_deltaE'], r['min_pair'],
                                                                                         r['state_floor_3_1'], r['floors'], 'PASS' if r['floors_pass'] else 'FAIL'))
    for k in ('dark', 'dark_warm_70', 'light', 'light_warm_70'):
        print(k, {n: v['hex'] for n, v in R[k]['neutrals'].items()})


if __name__ == '__main__':
    main()
