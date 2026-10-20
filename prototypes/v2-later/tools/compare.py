"""Side-by-side comparison sheets from the LE-1 captures, at true relative height (a tall page
stays tall), and the LE-8 before/after sheets. Prototype tooling.   py compare.py
"""
import os

from PIL import Image, ImageDraw

from serve import results

S = results('le1', 'shots', 'x')[:-1]
B = results('le8', 'before', 'x')[:-1]
SHEETS = {
    ('le1', 'compare_phone_now.png'): [('A · V1 structure', S, 'a_phone_now.png'), ('B · three places', S, 'b_phone_now.png')],
    ('le1', 'compare_phone_now_diag.png'): [('A · the D-1 state', S, 'a_phone_now_diag.png'), ('B · the D-1 state', S, 'b_phone_now_diag.png')],
    ('le1', 'compare_desk_now.png'): [('A · 1,440', S, 'a_desk_now.png'), ('B · 1,440', S, 'b_desk_now.png'), ('C · 1,440', S, 'c_desk_now.png')],
    ('le1', 'compare_phone_decision.png'): [('A · mission sheet', S, 'a_phone_m-m-c3e9.png'), ('B · decision page', S, 'b_phone_d-m-91d2.png'), ('B · mission page', S, 'b_phone_m-m-c3e9.png')],
    ('le8', 'dp_phone.png'): [('B Now · before', B, 'b_phone_now.png'), ('B Now · design pass', S, 'b_phone_now.png'),
                              ('Decision · before', B, 'b_phone_d-m-91d2.png'), ('Decision · design pass', S, 'b_phone_d-m-91d2.png')],
    ('le8', 'dp_desk.png'): [('B Now · before', B, 'b_desk_now.png'), ('B Now · design pass', S, 'b_desk_now.png')],
    ('le8', 'dp_desk_c.png'): [('C · before', B, 'c_desk_now.png'), ('C · design pass', S, 'c_desk_now.png')],
}
for (rec, out), cols in SHEETS.items():
    ims = [(t, Image.open(os.path.join(d, f)).convert('RGB')) for t, d, f in cols if os.path.exists(os.path.join(d, f))]
    scale = 0.5
    ims = [(t, im.resize((int(im.width * scale), int(im.height * scale)))) for t, im in ims]
    W = sum(im.width for _, im in ims) + 24 * (len(ims) + 1)
    H = max(im.height for _, im in ims) + 48
    sheet = Image.new('RGB', (W, H), (8, 10, 13))
    d = ImageDraw.Draw(sheet)
    x = 24
    for t, im in ims:
        sheet.paste(im, (x, 36))
        d.text((x, 12), '%s  (%d px tall at 1x)' % (t, im.height / scale / (2 if 'phone' in out else 1)), fill=(200, 205, 214))
        x += im.width + 24
    sheet.save(results(rec, out))
    print(out, sheet.size)
