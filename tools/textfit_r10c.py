"""Solve the live text for the V2 Mission (03) and Shared (06) frames from the concept rasters.

Run: py -I tools/textfit_r10c.py mission|shared
For each text item, the concept ink box is measured (contrast against the local background inside a search box).
The font size is solved so that the PIL ink width of the reference string matches it (spaced caps: the cap height
sets the size and the tracking closes the width). The box origin is then placed so the ink lands on the concept's
ink box. Writes clients/v2-prototype/layout-r10c.js (window.R10C_LAYOUT), which app.js reads. Registration against a
real render is checked with tools/textreg_r10c.py.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_DIR = os.path.join(ROOT, "clients", "v2-prototype", "fonts")
FONTS = {"serif": os.path.join(FONT_DIR, "LibreCaslonText-wght.ttf"), "sans": os.path.join(FONT_DIR, "SourceSans3-wght.ttf")}
WGHT = {"serif": 500, "sans": 400}
MIN_FRAME = 11.0
CONCEPTS = {
    "mission": "D:/hub-concepts-codex4/refs/03-mission.webp",
    "shared": "D:/hub-concepts-codex4/refs/06-shared.webp",
}

# id, font, search box (x0, y0, x1, y1) in master px, reference text (as drawn in the concept), shown text,
# spaced caps (True: size from cap height, tracking closes the width), size_of (copy size and tracking from an id).
MISSION = [
    ("wordmark", "serif", (18, 16, 176, 42), "ARCHEUS", "ARCHEUS", True, None),
    ("v2", "serif", (182, 18, 206, 40), "V2", "V2", True, None),
    ("crumb_ov", "serif", (42, 56, 108, 80), "Overview", "Overview", False, None),
    ("crumb_sl1", "serif", (112, 56, 128, 80), "/", "/", False, None),
    ("crumb_ar", "serif", (132, 56, 190, 80), "Archeus", "Archeus", False, None),
    ("crumb_sl2", "serif", (192, 56, 206, 80), "/", "/", False, None),
    ("crumb_fx", "serif", (210, 56, 296, 80), "Fix date test", "Fix date test", False, None),
    ("status", "sans", (836, 24, 1020, 42), "Not stopped \u00b7 accepts new work", "Not stopped \u00b7 accepts new work", False, None),
    ("tell", "sans", (1088, 24, 1116, 42), "Tell", "Tell", False, None),
    ("stop", "sans", (1180, 24, 1210, 42), "Stop", "Stop", False, None),
    ("core", "serif", (405, 134, 484, 151), "ARCHEUS", "ARCHEUS", True, None),
    ("v_orch", "sans", (448, 205, 544, 220), "ORCHESTRATES", "ORCHESTRATES", True, None),
    ("v_exec", "sans", (244, 320, 308, 336), "EXECUTES", "EXECUTES", True, None),
    ("v_results", "sans", (552, 334, 622, 348), "RESULTS IN", "RESULTS IN", True, None),
    ("v_uses", "sans", (302, 516, 334, 530), "USES", "USES", True, None),
    ("v_produces", "sans", (534, 516, 592, 530), "PRODUCES", "PRODUCES", True, None),
    ("v_verifies", "sans", (634, 512, 690, 526), "VERIFIES", "VERIFIES", True, None),
    ("codex_1", "serif", (28, 384, 100, 404), "CODEX", "Codex \u00b7", True, None),
    ("codex_2", "serif", (28, 405, 112, 424), "Execution", "execution", False, None),
    ("codex_s1", "serif", (34, 425, 146, 442), "Runs checks,", "Runs checks,", False, None),
    ("codex_s2", "serif", (34, 443, 150, 462), "collects evidence,", "collects evidence,", False, None),
    ("codex_s3", "serif", (34, 463, 146, 478), "reports results.", "reports results.", False, None),
    ("mis_title", "serif", (372, 460, 496, 486), "Fix date test", "Fix date test", False, None),
    ("mis_proj", "serif", (370, 486, 490, 504), "Project: Archeus", "Project: Archeus", False, None),
    ("mis_branch", "serif", (370, 504, 496, 522), "Branch: fix/date-test", "Branch: fix/date-test", False, None),
    ("ver_title", "serif", (680, 416, 778, 438), "Verification", "Verification", False, None),
    ("ver_s1", "serif", (676, 442, 792, 458), "Confirms behaviour", "Confirms behaviour", False, None),
    ("ver_s2", "serif", (676, 459, 786, 476), "and closes the fix.", "and closes the fix.", False, None),
    ("suite_title", "serif", (226, 698, 340, 718), "Date test suite", "Date test suite", False, None),
    ("suite_s1", "serif", (226, 719, 322, 737), "Test definitions", "Test definitions", False, None),
    ("suite_s2", "serif", (226, 737, 300, 754), "and inputs.", "and inputs.", False, None),
    ("res_title", "serif", (544, 698, 602, 718), "Results", "Results", False, None),
    ("res_s1", "serif", (544, 719, 636, 737), "Test execution", "Test execution", False, None),
    ("res_s2", "serif", (544, 737, 600, 754), "outputs", "outputs", False, None),
    ("m_kicker", "sans", (816, 78, 878, 92), "MISSION", "MISSION", True, None),
    ("m_title", "serif", (816, 96, 1046, 136), "Fix date test", "Fix date test", False, None),
    ("f_proj", "serif", (816, 156, 862, 170), "Project", "Project", False, None),
    ("f_branch", "serif", (946, 156, 988, 170), "Branch", "Branch", False, None),
    ("f_status", "serif", (1104, 156, 1142, 170), "Status", "Status", False, None),
    ("f_proj_v", "serif", (816, 174, 878, 192), "Archeus", "Archeus", False, None),
    ("f_branch_v", "serif", (944, 174, 1028, 192), "fix/date-test", "fix/date-test", False, None),
    ("f_status_v", "sans", (1126, 174, 1198, 192), "In progress", "In progress", False, None),
    ("ph_1", "serif", (816, 250, 878, 266), "Understand", "Understand", False, None),
    ("ph_2", "serif", (898, 250, 926, 266), "Plan", "Plan", False, None),
    ("ph_3", "serif", (958, 250, 1006, 266), "Approve", "Approve", False, None),
    ("ph_4", "serif", (1040, 250, 1064, 266), "Run", "Run", False, None),
    ("ph_5", "serif", (1102, 250, 1138, 266), "Verify", "Verify", False, None),
    ("ph_6", "serif", (1176, 250, 1216, 266), "Review", "Review", False, None),
    ("p_kicker", "sans", (818, 288, 920, 300), "CURRENT PHASE", "CURRENT PHASE", True, None),
    ("p_name", "serif", (818, 306, 914, 330), "Verifying", "Verifying", False, None),
    ("p_line", "serif", (818, 331, 1144, 350), "Check results, confirm behaviour, and close the fix.", "Check results, confirm behaviour, and close the fix.", False, None),
    ("a_kicker", "sans", (826, 381, 868, 393), "AGENT", "AGENT", True, None),
    ("a_name", "serif", (884, 398, 1014, 420), "Codex \u00b7 execution", "Codex \u00b7 execution", False, None),
    ("a_sub", "serif", (884, 420, 1146, 438), "Runs checks, collects evidence, reports results.", "Runs checks, collects evidence, reports results.", False, None),
    ("t_kicker", "sans", (822, 460, 916, 474), "CURRENT TASK", "CURRENT TASK", True, None),
    ("t_name", "serif", (884, 480, 990, 500), "Run date suite", "Run date suite", False, None),
    ("t_s2", "serif", (884, 518, 1006, 536), "and collect the results.", "and collect the results.", False, None),
    ("t_s1", "serif", (884, 502, 1194, 519), "Execute the date test suite on branch fix/date-test", "Run date suite on fix/date-test", False, "t_s2"),
    ("r_kicker", "sans", (822, 550, 928, 562), "LATEST RECORD", "LATEST RECORD", True, None),
    ("r_name", "serif", (882, 568, 1020, 590), "Tool result received", "Tool result received.", False, None),
    ("r_sub", "serif", (882, 590, 1100, 606), "Test run completed. Results captured.", "Test run completed. Results captured.", False, None),
    ("l_kicker", "sans", (822, 636, 910, 650), "ACTIVITY LOG", "ACTIVITY LOG", True, None),
    ("l_1", "serif", (836, 655, 946, 672), "Tool call received", "Tool call received.", False, None),
    ("l_2", "serif", (836, 673, 956, 690), "Tool result received.", "Tool result received.", False, None),
    ("l_3", "serif", (836, 691, 934, 708), "Not passed tests.", "Not passed tests.", False, None),
    ("l_4", "serif", (836, 708, 930, 725), "Parsing results.", "Parsing results.", False, None),
    ("l_5", "serif", (836, 726, 946, 743), "Recording outcome.", "Recording outcome.", False, None),
    ("l_6", "serif", (836, 744, 1036, 762), "Proceeding to verification checks...", "Proceeding to verification checks...", False, None),
    ("s_kicker", "sans", (1056, 636, 1138, 650), "PLAN STEPS", "PLAN STEPS", True, None),
    ("s_1", "serif", (1080, 655, 1212, 672), "Set up test environment", "Set up test environment", False, None),
    ("s_2", "serif", (1080, 673, 1200, 690), "Run date suite", "Run date suite", False, None),
    ("s_3", "serif", (1080, 692, 1190, 710), "Verify results", "Verify results", False, None),
    ("s_4", "serif", (1080, 712, 1180, 730), "Confirm fix", "Confirm fix", False, None),
    ("s_5", "serif", (1080, 731, 1190, 749), "Document outcome", "Document outcome", False, None),
    ("s_6", "serif", (1080, 751, 1175, 769), "Close mission", "Close mission", False, None),
]

SHARED = [
    ("wordmark", "serif", (26, 36, 206, 68), "ARCHEUS", "ARCHEUS", True, None),
    ("v2", "serif", (212, 44, 246, 66), "V2", "V2", False, None),
    ("lede_1", "serif", (26, 80, 152, 104), "A shared space", "A shared space", False, None),
    ("lede_2", "serif", (26, 103, 136, 124), "for real work", "for real work", False, None),
    ("nav_ov", "serif", (66, 166, 152, 190), "Overview", "Overview", False, None),
    ("nav_mi", "serif", (66, 208, 146, 234), "Missions", "Missions", False, None),
    ("nav_id", "serif", (66, 252, 120, 276), "Ideas", "Ideas", False, None),
    ("nav_pr", "serif", (66, 298, 142, 324), "Projects", "Projects", False, None),
    ("nav_co", "serif", (66, 344, 138, 370), "Control", "Control", False, None),
    ("kick_pr", "sans", (26, 418, 120, 444), "PROJECTS", "PROJECTS", True, None),
    ("p_arch", "serif", (70, 458, 140, 484), "Archeus", "Archeus", False, None),
    ("claude", "serif", (338, 252, 420, 282), "Claude", "Claude", False, None),
    ("claude_st", "sans", (362, 284, 440, 306), "Planning", "Planning", False, None),
    ("claude_sub", "serif", (336, 307, 484, 332), "Search provenance", "Search provenance", False, None),
    ("codex", "serif", (842, 250, 922, 282), "Codex", "Codex", False, None),
    ("codex_st", "sans", (866, 282, 944, 308), "Verifying", "Verifying", False, None),
    ("codex_sub", "serif", (842, 307, 946, 333), "Fix date test", "Fix date test", False, None),
    ("core", "serif", (566, 444, 706, 468), "ARCHEUS", "ARCHEUS", False, None),
    ("core_sub", "serif", (584, 470, 690, 488), "Shared records", "Shared records", False, None),
    ("d_desk", "serif", (338, 644, 450, 674), "This desktop", "This desktop", False, None),
    ("d_desk_st", "sans", (360, 674, 448, 698), "Connected", "Connected", False, None),
    ("d_phone", "serif", (588, 644, 702, 674), "Paired phone", "Paired phone", False, None),
    ("d_phone_st", "sans", (610, 674, 672, 698), "Recent", "Recent", False, None),
    ("d_other", "serif", (828, 644, 942, 674), "Other people", "Other people", False, None),
    ("d_other_st", "sans", (852, 674, 968, 698), "Future contract", "Future contract", False, None),
    ("d_other_sub", "serif", (852, 696, 972, 718), "Not yet available", "Not yet available", False, None),
    ("c_kicker", "sans", (1062, 46, 1134, 68), "PROJECT", "PROJECT", True, None),
    ("c_title", "serif", (1062, 66, 1192, 108), "Archeus", "Archeus", False, None),
    ("c_state", "serif", (1084, 106, 1152, 134), "Verified", "Verified", False, None),
    ("c_lede", "serif", (1062, 132, 1350, 160), "The evolving core of our shared space.", "The evolving core of our shared space.", False, None),
    ("tab_ov", "serif", (1072, 190, 1148, 216), "Overview", "Overview", False, None),
    ("tab_co", "serif", (1176, 190, 1244, 216), "Content", "Content", False, None),
    ("tab_re", "serif", (1270, 190, 1344, 216), "Relations", "Relations", False, None),
    ("k_type", "serif", (1106, 246, 1222, 270), "Type", "Type", False, None),
    ("k_status", "serif", (1106, 281, 1222, 305), "Status", "Status", False, None),
    ("k_updated", "serif", (1106, 316, 1222, 340), "Updated", "Updated", False, None),
    ("k_items", "serif", (1106, 351, 1222, 375), "Items", "Items", False, None),
    ("k_agents", "serif", (1106, 386, 1222, 410), "Agents", "Agents", False, None),
    ("k_linked", "serif", (1106, 421, 1222, 445), "Linked projects", "Linked projects", False, None),
    ("v_type", "serif", (1240, 246, 1342, 270), "Core system", "Core system", False, None),
    ("v_status", "serif", (1240, 281, 1342, 305), "Verified", "Verified", False, None),
    ("v_updated", "serif", (1240, 316, 1342, 340), "Today, 10:24", "Today, 10:24", False, None),
    ("v_items", "serif", (1240, 351, 1342, 375), "248", "248", False, None),
    ("v_agents", "serif", (1240, 386, 1342, 410), "2 active", "2 active", False, None),
    ("v_linked", "serif", (1240, 421, 1342, 445), "0", "0", False, None),
    ("ev_head", "serif", (1062, 484, 1154, 516), "Evidence", "Evidence", False, None),
    ("ev_sub", "serif", (1062, 514, 1340, 542), "Same records · device permissions apply.", "Same records, device permissions apply.", False, None),
    ("e_1", "serif", (1106, 554, 1226, 582), "Project files", "Project files", False, None),
    ("e_2", "serif", (1106, 589, 1226, 616), "Notes", "Notes", False, None),
    ("e_3", "serif", (1106, 624, 1226, 650), "Agent logs", "Agent logs", False, None),
    ("e_4", "serif", (1106, 659, 1226, 686), "Build outputs", "Build outputs", False, None),
    ("e_5", "serif", (1106, 695, 1226, 722), "Related content", "Related content", False, None),
    ("n_1", "serif", (1268, 554, 1342, 582), "12 items", "12 items", False, None),
    ("n_2", "serif", (1268, 589, 1342, 616), "34 items", "34 items", False, None),
    ("n_3", "serif", (1268, 624, 1342, 650), "28 items", "28 items", False, None),
    ("n_4", "serif", (1268, 659, 1342, 686), "18 items", "18 items", False, None),
    ("n_5", "serif", (1262, 695, 1342, 722), "156 items", "156 items", False, None),
    ("status", "sans", (268, 852, 524, 876), "Not stopped · accepts new work", "Not stopped · accepts new work", False, None),
    ("tell", "sans", (1152, 850, 1190, 876), "Tell", "Tell", False, None),
    ("stop", "sans", (1288, 850, 1328, 876), "Stop", "Stop", False, None),
]


def ink_box(gray, box, bg_thresh=40):
    x0, y0, x1, y1 = box
    sub = gray[y0:y1, x0:x1].astype(np.int16)
    med = np.median(sub)
    ys, xs = np.nonzero(sub > med + bg_thresh)
    if len(xs) == 0:
        return None
    return (int(xs.min()) + x0, int(ys.min()) + y0, int(xs.max()) + x0 + 1, int(ys.max()) + y0 + 1)


def font_at(kind, size):
    f = ImageFont.truetype(FONTS[kind], size=size)
    try:
        f.set_variation_by_axes([WGHT[kind]])
    except Exception:
        pass
    return f


def pil_ink(kind, size, text):
    """Ink box of text drawn at size px, origin at the ascender line, left edge at 0. Returns (x0, y0, x1, y1)."""
    ss = 8
    f = font_at(kind, size * ss)
    img = Image.new("L", (int(size * ss * (len(text) + 2) * 0.9) + 40, int(size * ss * 2.4)), 0)
    ImageDraw.Draw(img).text((20, 0), text, font=f, fill=255)
    a = np.array(img) > 110
    ys, xs = np.nonzero(a)
    if len(xs) == 0:
        return (0, 0, 0, 0)
    return ((xs.min() - 20) / ss, ys.min() / ss, (xs.max() + 1 - 20) / ss, (ys.max() + 1) / ss)


def cap_height(kind):
    f = font_at(kind, 400)
    bb = f.getbbox("H")
    return (bb[3] - bb[1]) / 400.0


def solve_size(kind, text, target_w, lo=6.0, hi=90.0):
    for _ in range(22):
        mid = (lo + hi) / 2
        x0, _y0, x1, _y1 = pil_ink(kind, mid, text)
        if (x1 - x0) < target_w:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def solve(name):
    im = cv2.imread(CONCEPTS[name])
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    items = MISSION if name == "mission" else SHARED
    out = {}
    ref = {}
    for iid, kind, box, text_ref, text_show, spaced, size_of in items:
        ib = ink_box(gray, box)
        if ib is None:
            print("NO INK", iid, box)
            continue
        cx0, cy0, cx1, cy1 = ib
        cw, ch = cx1 - cx0, cy1 - cy0
        n = len(text_show)
        if size_of:
            size, track = ref[size_of]["size"], ref[size_of]["track"]
            ink = pil_ink(kind, size, text_show)
            # Track applies between glyphs: fold the width difference into it.
            track = round(track, 2)
        elif spaced and iid.startswith("v_"):
            # Verb labels sit on link arrows, so the ink height is not the cap height: size at the frame minimum and
            # close the width with tracking.
            size = MIN_FRAME
            x0, _, x1, _ = pil_ink(kind, size, text_ref)
            track = round(((cw - (x1 - x0)) / max(1, len(text_ref) - 1)), 2)
        elif spaced:
            size = max(MIN_FRAME, round(ch / cap_height(kind), 2))
            x0, _, x1, _ = pil_ink(kind, size, text_ref)
            track = round(((cw - (x1 - x0)) / max(1, len(text_ref) - 1)), 2)
        else:
            size = max(MIN_FRAME, solve_size(kind, text_ref, cw))
            x0, _, x1, _ = pil_ink(kind, size, text_ref)
            track = 0.0
        if size < MIN_FRAME:
            size = MIN_FRAME
        ref[iid] = {"size": size, "track": track}
        # Placement: pil_ink measures from the ascender line with the left edge at 0 (no tracking). Track is added
        # per gap, so the ink starts at the same left edge.
        x0, y0, _x1, _y1 = pil_ink(kind, size, text_show)
        left = cx0 - x0
        top = cy0 - y0
        if spaced and not size_of:
            ref_ink = pil_ink(kind, size, text_ref)
            top = cy0 - ref_ink[1]
            left = cx0 - ref_ink[0]
        out[iid] = {"f": kind, "x": round(left, 2), "y": round(top, 2), "s": size, "t": track,
                    "w": round(cw, 1), "h": round(ch, 1), "cx": cx0, "cy": cy0, "text": text_show}
    return out


def main():
    name = sys.argv[1]
    if name not in CONCEPTS:
        sys.exit("usage: textfit_r10c.py mission|shared")
    res = solve(name)
    for k, v in res.items():
        print(f"{k:<12}{v['f']:<6}size {v['s']:<7}track {v['t']:<6} x {v['x']:<8} y {v['y']:<8} ink {v['w']}x{v['h']}")
    layout_path = os.path.join(ROOT, "clients", "v2-prototype", "layout-r10c.js")
    data = {}
    if os.path.exists(layout_path):
        raw = open(layout_path, encoding="utf8").read()
        start = raw.index("{")
        data = json.loads(raw[start:raw.rindex("}") + 1])
    data[name] = res
    with open(layout_path, "w", encoding="utf8") as f:
        f.write("/* Round 10c: live text layout for the Mission and Shared frames, solved from the concept rasters\n")
        f.write("   by tools/textfit_r10c.py (ink boxes in master px). Positions are the box origin; s is px, t is tracking px. */\n")
        f.write("window.R10C_LAYOUT = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n")
    print("wrote", layout_path)


if __name__ == "__main__":
    main()
