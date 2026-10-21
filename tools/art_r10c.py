"""Build the base art for the V2 Mission (03) and Shared (06) frames: the concept raster with all live content removed.

Run: py -I tools/art_r10c.py mission|shared [concept.webp] [out_dir] [review_dir]
Writes <out_dir>/<name>-base.webp (lossless if under 600 KB, else q100); with review_dir also <name>-mask.png (the removal mask).
Glyph pixels are masked by contrast or saturation inside text boxes, so mesh wires and frame lines that cross a
box are kept. Solid mark boxes (icons, pills, buttons) are masked whole and refilled. Same method as
tools/art_desktop.py (round 10e), generalised to two concepts.
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GLYPH_CONTRAST = 14

# Mission 03: master 1244 x 829. Boxes are x0, y0, x1, y1 in master px.
MISSION = {
    "size": (1244, 829),
    "concept": "D:/hub-concepts-codex4/refs/03-mission.webp",
    "text": [
        ((14, 12, 210, 44), "flat"),       # ARCHEUS V2 wordmark
        ((18, 56, 296, 80), "flat"),       # breadcrumb with the back chevron
        ((400, 130, 490, 152), "glyph"),   # ARCHEUS core label, star rays pass by
        ((446, 202, 545, 222), "flat"),    # ORCHESTRATES
        ((240, 316, 312, 340), "glyph"),   # EXECUTES, the arrow runs through the box
        ((550, 332, 625, 352), "glyph"),   # RESULTS IN
        ((28, 384, 150, 478), "flat"),     # Codex execution label and sub-lines
        ((370, 455, 500, 522), "glyph"),   # Fix date test label, links pass by
        ((300, 512, 336, 532), "glyph"),   # USES
        ((532, 512, 596, 532), "glyph"),   # PRODUCES
        ((632, 508, 692, 530), "glyph"),   # VERIFIES
        ((672, 412, 800, 478), "flat"),    # Verification label and sub-lines
        ((222, 696, 345, 754), "flat"),    # Date test suite label and sub-lines
        ((540, 696, 672, 754), "flat"),    # Results label and sub-lines
        ((815, 76, 1050, 140), "flat"),    # MISSION kicker and title
        ((815, 152, 1200, 194), "flat"),   # Project, Branch, Status
        ((815, 286, 1150, 352), "flat"),   # CURRENT PHASE, phase name, phase line
        ((818, 380, 1150, 442), "flat"),   # AGENT label and row text
        ((818, 458, 1200, 532), "flat"),   # CURRENT TASK text
        ((818, 546, 1110, 608), "flat"),   # LATEST RECORD text
        ((818, 630, 1040, 762), "flat"),   # ACTIVITY LOG, items, chevrons, red dot
        ((1050, 630, 1215, 772), "flat"),  # PLAN STEPS, steps, check circles
        ((20, 784, 150, 808), "flat"),     # CONCEPT FIXTURE footer text (footer strip replaces it)
    ],
    "marks": [
        (90, 290, 136, 346),     # Codex execution glyph (document)
        (402, 342, 472, 396),    # Fix date test glyph (terminal)
        (700, 316, 748, 370),    # Verification glyph (check)
        (274, 618, 310, 662),    # Date test suite glyph (document)
        (556, 618, 592, 660),    # Results glyph (bars)
        (826, 398, 872, 440),    # card agent triangle
        (818, 478, 862, 518),    # card current task icon
        (818, 564, 862, 610),    # card latest record icon
        (812, 214, 1222, 270),   # phase stepper line, dots, checks, labels
        (800, 12, 1042, 52),     # status pill
        (1046, 12, 1134, 52),    # Tell button
        (1139, 12, 1229, 52),    # Stop button
    ],
    "flat": [
        (800, 12, 1229, 52, 30, 3),
        (812, 214, 1222, 270, 20, 3),
    ],
}

# Shared 06: master 1382 x 922.
SHARED = {
    "size": (1382, 922),
    "concept": "D:/hub-concepts-codex4/refs/06-shared.webp",
    "text": [
        ((24, 34, 210, 70), "flat"),       # ARCHEUS wordmark
        ((212, 44, 246, 66), "flat"),      # V2
        ((26, 80, 152, 104), "flat"),      # lede line 1
        ((26, 103, 136, 124), "flat"),     # lede line 2
        ((66, 166, 152, 190), "flat"),     # Overview
        ((66, 208, 146, 234), "flat"),     # Missions
        ((66, 252, 120, 276), "flat"),     # Ideas
        ((66, 298, 142, 324), "flat"),     # Projects
        ((66, 344, 138, 370), "flat"),     # Control
        ((26, 418, 120, 444), "flat"),     # PROJECTS kicker
        ((70, 454, 142, 488), "glyph"),    # Archeus row, inside the selected band
        ((336, 250, 420, 282), "flat"),    # Claude
        ((362, 282, 440, 306), "flat"),    # Planning
        ((336, 307, 484, 332), "flat"),    # Search provenance
        ((842, 250, 922, 282), "flat"),    # Codex
        ((866, 282, 944, 308), "flat"),    # Verifying
        ((842, 307, 946, 333), "flat"),    # Fix date test
        ((562, 444, 710, 470), "flat"),   # ARCHEUS core label, rays end above
        ((582, 470, 632, 490), "flat"),    # Shared
        ((638, 470, 692, 490), "flat"),    # records
        ((338, 644, 450, 674), "flat"),    # This desktop
        ((360, 674, 448, 698), "flat"),    # Connected
        ((588, 644, 702, 674), "flat"),    # Paired phone
        ((610, 674, 672, 698), "flat"),    # Recent
        ((828, 644, 942, 674), "flat"),    # Other people
        ((852, 674, 968, 698), "flat"),    # Future contract
        ((852, 696, 972, 718), "flat"),    # Not yet available
        ((1062, 46, 1134, 68), "flat"),    # PROJECT kicker
        ((1062, 66, 1192, 108), "flat"),   # Archeus title
        ((1084, 106, 1152, 134), "flat"),  # Verified
        ((1062, 132, 1350, 160), "flat"),  # lede of the project
        ((1072, 190, 1148, 216), "flat"),  # tab Overview
        ((1176, 190, 1244, 216), "flat"),  # tab Content
        ((1270, 190, 1344, 216), "flat"),  # tab Relations
        ((1062, 484, 1154, 516), "flat"),  # Evidence
        ((1062, 514, 1340, 542), "flat"),  # Same records line
        ((1106, 246, 1222, 270), "flat"),  # Type
        ((1106, 281, 1222, 305), "flat"),  # Status
        ((1106, 316, 1222, 340), "flat"),  # Updated
        ((1106, 351, 1222, 375), "flat"),  # Items
        ((1106, 386, 1222, 410), "flat"),  # Agents
        ((1106, 421, 1222, 445), "flat"),  # Linked projects
        ((1240, 246, 1342, 270), "flat"),  # Core system
        ((1240, 281, 1342, 305), "flat"),  # Verified value
        ((1240, 316, 1342, 340), "flat"),  # Today, 10:24
        ((1240, 351, 1342, 375), "flat"),  # 248
        ((1240, 386, 1342, 410), "flat"),  # 2 active
        ((1240, 421, 1342, 445), "flat"),  # 0
        ((1106, 554, 1226, 582), "flat"),  # Project files
        ((1106, 589, 1226, 616), "flat"),  # Notes
        ((1106, 624, 1226, 650), "flat"),  # Agent logs
        ((1106, 659, 1226, 686), "flat"),  # Build outputs
        ((1106, 695, 1226, 722), "flat"),  # Related content
        ((1268, 554, 1342, 582), "flat"),  # 12 items
        ((1268, 589, 1342, 616), "flat"),  # 34 items
        ((1268, 624, 1342, 650), "flat"),  # 28 items
        ((1268, 659, 1342, 686), "flat"),  # 18 items
        ((1262, 695, 1342, 722), "flat"),  # 156 items
        ((268, 852, 524, 876), "flat"),    # status line in the bottom bar
        ((1148, 848, 1196, 878), "flat"),  # Tell
        ((1284, 848, 1332, 878), "flat"),  # Stop
        ((18, 848, 206, 878), "flat"),     # CONCEPT FIXTURE (footer strip replaces it)
    ],
    "marks": [
        (338, 284, 358, 306),    # Planning dot
        (846, 284, 866, 306),    # Verifying dot
        (338, 674, 358, 696),    # Connected dot
        (590, 674, 610, 696),    # Recent dot
        (830, 674, 850, 696),    # Future contract dot
        (1062, 108, 1082, 128),  # Verified dot
        (364, 576, 416, 620),    # monitor glyph
        (618, 582, 654, 626),    # phone glyph
        (862, 578, 900, 622),    # dashed square glyph
        (28, 162, 54, 190),      # nav: Overview icon
        (28, 205, 54, 234),      # nav: Missions icon
        (28, 248, 54, 278),      # nav: Ideas icon
        (28, 294, 54, 324),      # nav: Projects icon
        (28, 342, 54, 370),      # nav: Control icon
        (186, 422, 206, 442),    # PROJECTS plus
        (28, 456, 56, 486),      # Archeus cube icon
        (1063, 247, 1089, 271), (1063, 282, 1089, 305), (1063, 317, 1089, 339),
        (1063, 352, 1089, 374), (1063, 387, 1089, 409), (1063, 422, 1089, 444),
        (1063, 552, 1089, 581), (1063, 587, 1089, 615), (1063, 622, 1089, 650),
        (1063, 657, 1089, 685), (1063, 693, 1089, 721),
        (1342, 492, 1362, 514),  # Evidence chevron
        (1089, 839, 1214, 886),  # Tell button
        (1223, 839, 1355, 886),  # Stop button
        (240, 852, 262, 874),    # status dot
        (1116, 849, 1144, 874),  # Tell icon
        (1252, 851, 1276, 874),  # Stop icon
    ],
    "flat": [
        (1056, 178, 1162, 226, 12, 2),    # selected tab
    ],
}

CONFIGS = {"mission": MISSION, "shared": SHARED}


def glyph_mask(gray, sat, items):
    h, w = gray.shape
    local_bg = cv2.medianBlur(gray, 21).astype(np.int16)
    contrast = gray.astype(np.int16) - local_bg
    m = np.zeros((h, w), np.uint8)
    for (x0, y0, x1, y1), kind in items:
        if kind == "flat":
            m[y0:y1, x0:x1] = 255
            continue
        hit = (contrast[y0:y1, x0:x1] > GLYPH_CONTRAST) | (sat[y0:y1, x0:x1] > 70)
        m[y0:y1, x0:x1] = np.where(hit, 255, 0)
    return m


def plane_fill(im, out, box, pad, feather):
    x0, y0, x1, y1 = box
    H, W = im.shape[:2]
    ys, xs = np.mgrid[0:H, 0:W]
    ring = np.zeros((H, W), bool)
    rx0, ry0, rx1, ry1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
    ring[ry0:ry1, rx0:rx1] = True
    ring[y0:y1, x0:x1] = False
    lum = im.astype(np.float32).mean(axis=2)
    ring &= lum < np.median(lum[ring]) + 12
    u = (xs - W / 2) / (W / 2)
    v = (ys - H / 2) / (H / 2)
    A = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)
    fit = np.zeros((H, W, 3), np.float32)
    Ar = A[ring]
    for c in range(3):
        coef, *_ = np.linalg.lstsq(Ar, im[:, :, c][ring].astype(np.float64), rcond=None)
        fit[:, :, c] = (A @ coef).astype(np.float32)
    box_m = np.zeros((H, W), np.float32)
    box_m[y0:y1, x0:x1] = 1.0
    soft = cv2.GaussianBlur(box_m, (0, 0), feather) if feather else box_m
    return out * (1 - soft[..., None]) + fit * soft[..., None]


def build(name, concept_path, out_dir, review_dir=None):
    cfg = CONFIGS[name]
    im = cv2.imread(concept_path)
    W, H = cfg["size"]
    assert im.shape[:2] == (H, W), im.shape
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    b, g, r = [im[:, :, i].astype(np.int16) for i in range(3)]
    sat = np.clip(np.maximum(r - b, b - r), 0, 255).astype(np.uint8)

    m = glyph_mask(gray, sat, cfg["text"])
    for x0, y0, x1, y1 in cfg["marks"]:
        m[y0:y1, x0:x1] = 255
    grow = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    clean = cv2.inpaint(im, grow, 3, cv2.INPAINT_TELEA)
    out = clean.astype(np.float32)
    flats = [(x0, y0, x1, y1, 24, 2) for (x0, y0, x1, y1), kind in cfg["text"] if kind == "flat"]
    for bx0, by0, bx1, by1, pad, feather in flats + cfg["flat"]:
        out = plane_fill(im, out, (bx0, by0, bx1, by1), pad, feather)
    out = np.clip(out, 0, 255).astype(np.uint8)

    os.makedirs(out_dir, exist_ok=True)
    if review_dir:
        os.makedirs(review_dir, exist_ok=True)
        cv2.imwrite(os.path.join(review_dir, f"{name}-mask.png"), grow)
    webp = os.path.join(out_dir, f"{name}-base.webp")
    rgb = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    rgb.save(webp, "WEBP", lossless=True, method=6)
    if os.path.getsize(webp) >= 600 * 1024:
        rgb.save(webp, "WEBP", quality=100, method=6)
    print(name, "mask px", int((grow > 0).sum()), "webp bytes", os.path.getsize(webp))


if __name__ == "__main__":
    name = sys.argv[1]
    concept = sys.argv[2] if len(sys.argv) > 2 else CONFIGS[name]["concept"]
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, "clients", "v2-prototype", "art")
    review = sys.argv[4] if len(sys.argv) > 4 else None
    build(name, concept, out, review)
