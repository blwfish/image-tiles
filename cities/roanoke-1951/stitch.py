#!/usr/bin/env python3
"""
Roanoke VA 1951 Sanborn Map Stitch
Composites geographic sheets into a single pyramidal GeoTIFF.

Scale:
  50 ft/in → sheets 1-54   (native resolution, reference)
  100 ft/in → sheets 55-104 (2× upscale to match geographic scale)

Positions derived from pixel centroids in city_map_clean.jpg (870×780),
which covers orig key map x=[400,6200], y=[2000,7467] at 0.15× scale.

Calibration: s1↔s2 (E step) = 29 cm_px, s1↔s5 (S step) = 29 cm_px.
At 50ft/in native sheet size 6537×7635 px → 225 composite_px / cm_px.

Excluded: sheets 91-94 (Vinton), 103 (Am. Viscose Corp detached).
"""

import pyvips, os, sys

WORKDIR = '/Volumes/Files/claude/roanoke-1951'
EXCLUDE = set(range(91, 95)) | {103}

def scale_factor(n):
    return 2.0 if n >= 55 else 1.0

# ─────────────────────────────────────────────────────────────────────────────
# CITY MAP CENTROID POSITIONS (city_map_clean.jpg pixels, 870×780)
# Measured from key map full-city crop at 0.15× scale.
# Calibration: s1=(495,370), s2=(524,360) → Δx=29 = 1 sheet E-W
#              s1=(495,370), s5=(495,399) → Δy=29 = 1 sheet N-S
# ─────────────────────────────────────────────────────────────────────────────
CM = {
    # ── 50ft/in inner city (sheets 1-54) ──────────────────────────────────
    # Core downtown (within/near red CBD box):
     1: (495, 370),    2: (524, 360),    3: (466, 374),    4: (435, 378),
     5: (495, 399),    6: (524, 399),
     7: (378, 375),    8: (408, 375),   12: (378, 404),
    # North inner ring (row above main downtown):
     9: (460, 343),   10: (435, 340),   11: (466, 349),
    39: (454, 313),   40: (426, 308),   41: (457, 318),
    42: (495, 340),   43: (524, 333),   44: (546, 318),
    45: (562, 304),   46: (582, 298),   47: (601, 307),   48: (618, 316),
    # East of downtown:
    25: (553, 361),   26: (581, 356),
    # South of main row (chain-derived y where measured positions were off):
    13: (460, 372),   14: (435, 369),   15: (466, 378),   16: (495, 378),
    17: (435, 398),   18: (408, 412),
    # Further south:
    19: (480, 427),   20: (510, 427),
    21: (450, 412),   22: (480, 414),
    23: (537, 420),   24: (556, 416),
    27: (581, 410),   28: (605, 418),
    # SW area:
    29: (462, 450),   30: (484, 444),   31: (514, 434),   32: (540, 431),
    33: (372, 506),   34: (400, 518),   35: (425, 522),
    36: (522, 471),   37: (547, 471),   38: (530, 490),
    # NW inner:
    49: (410, 324),   50: (384, 334),
    # SE inner:
    69: (568, 435),   70: (572, 458),   71: (570, 478),

    # ── 100ft/in outer ring (sheets 55-104) ───────────────────────────────
    # NW outer:
    75: (205, 332),   76: (218, 230),   77: (260, 244),
    78: (388, 300),   79: (180, 280),   80: (225, 196),
    81: (276, 176),   82: (318, 171),   83: (364, 170),
    # NE outer:
    84: (490, 222),   85: (560, 244),   86: (625, 250),
    87: (634, 328),   88: (680, 278),   89: (706, 222),   90: (710, 178),
    # W outer:
    55: (310, 375),   56: (310, 407),   57: (295, 435),   58: (322, 476),
    # S outer:
    59: (384, 516),   60: (430, 524),   61: (477, 528),   62: (520, 530),
    63: (475, 562),   64: (565, 560),
    # River / park areas:
    65: (335, 460),   66: (650, 440),   67: (642, 492),   68: (600, 548),
    72: (593, 532),   73: (623, 462),   74: (672, 376),
    # Far outer:
   102: (287, 493),  104: (324, 406),
    # Eastern outer:
    95: (682, 348),   96: (696, 392),   97: (698, 428),
    98: (672, 460),   99: (654, 500),  100: (624, 522),  101: (600, 540),
}

# Remove excluded sheets
for n in list(CM.keys()):
    if n in EXCLUDE:
        del CM[n]

# ─────────────────────────────────────────────────────────────────────────────
def run_stitch(dry_run=False):
    os.chdir(WORKDIR)

    # Load sheet 1 to get exact content dimensions
    s1 = pyvips.Image.new_from_file('09065_01_1951-0001.jp2')
    MARGIN = 80
    CW = s1.width  - 2*MARGIN   # content width  (50ft/in)
    CH = s1.height - 2*MARGIN   # content height (50ft/in)
    print(f"50ft/in sheet content: {CW} × {CH} px")

    # Calibration: cm_px → composite_px
    dx_cm = CM[2][0] - CM[1][0]   # s1→s2 E step in cm pixels (=29)
    dy_cm = CM[5][1] - CM[1][1]   # s1→s5 S step in cm pixels (=29)
    SX = CW / dx_cm   # composite px per cm px (x)
    SY = CH / dy_cm   # composite px per cm px (y)
    print(f"cm calibration: Δx={dx_cm}, Δy={dy_cm}")
    print(f"Scale: {SX:.1f}×{SY:.1f} composite_px/cm_px")

    anchor_cm = CM[1]   # s1 = composite origin

    # Compute sheet positions (top-left corner on composite canvas)
    raw = {}
    for n, (cx, cy) in CM.items():
        sf = scale_factor(n)
        w = int(CW * sf)
        h = int(CH * sf)
        # Centroid offset from anchor
        px = (cx - anchor_cm[0]) * SX
        py = (cy - anchor_cm[1]) * SY
        # Top-left = centroid - half size
        x = int(px - w/2)
        y = int(py - h/2)
        raw[n] = (x, y, w, h, sf)

    # Canvas bounds
    min_x = min(p[0]         for p in raw.values())
    min_y = min(p[1]         for p in raw.values())
    max_x = max(p[0]+p[2]    for p in raw.values())
    max_y = max(p[1]+p[3]    for p in raw.values())
    cw = max_x - min_x
    ch = max_y - min_y
    ox, oy = -min_x, -min_y

    print(f"\nCanvas: {cw:,} × {ch:,} px")
    print(f"Offset: ({ox:,}, {oy:,})")
    print(f"Sheets: {len(raw)}")

    # Final positions (shifted positive)
    pos = {n: (p[0]+ox, p[1]+oy, p[2], p[3], p[4]) for n,p in raw.items()}

    # Adjacency verification
    def gap(a, b, axis):
        if a not in pos or b not in pos: return None
        xa,ya,wa,ha,_ = pos[a]
        xb,yb,wb,hb,_ = pos[b]
        if axis=='E': return xb-(xa+wa)
        if axis=='S': return yb-(ya+ha)
    print("\nAdjacency gaps (expect ~0):")
    for a,b,ax in [(1,2,'E'),(3,1,'E'),(1,5,'S'),(2,6,'S'),
                   (42,1,'S'),(39,9,'S'),(40,10,'S'),(41,11,'S'),
                   (9,13,'S'),(10,14,'S')]:
        g = gap(a,b,ax)
        ok = g is not None and abs(g) < CW//4
        print(f"  s{a}→s{b} {ax}: {g:+,}px {'✓' if ok else '✗'}")

    if dry_run:
        print("\n[DRY RUN] Skipping output.")
        return

    # ── Composite ────────────────────────────────────────────────────────────
    # Order: 100ft/in first (background), 50ft/in on top (higher detail)
    order = (sorted([n for n in pos if scale_factor(n)==2.0], key=lambda n:(pos[n][1],pos[n][0]))
           + sorted([n for n in pos if scale_factor(n)==1.0], key=lambda n:(pos[n][1],pos[n][0])))

    print(f"\nBuilding canvas {cw:,}×{ch:,}...")
    canvas = pyvips.Image.black(cw, ch, bands=3).cast('float')

    for i, n in enumerate(order):
        fn = f'09065_01_1951-{n:04d}.jp2'
        x, y, w, h, sf = pos[n]
        print(f"  [{i+1:3d}/{len(order)}] s{n:3d} (sf={sf}): ({x:,},{y:,}) {w}×{h}", end=" ")
        sys.stdout.flush()
        if not os.path.exists(fn):
            print("MISSING"); continue
        img = pyvips.Image.new_from_file(fn)
        img = img.crop(MARGIN, MARGIN, img.width-2*MARGIN, img.height-2*MARGIN)
        if sf != 1.0:
            img = img.resize(sf, kernel='lanczos3')
        if img.bands == 1:
            img = img.bandjoin([img, img, img])
        canvas = canvas.insert(img.cast('float'), x, y, expand=False)
        print("✓")

    outfile = 'composite2.tif'
    print(f"\nSaving {outfile}...")
    canvas.cast('uchar').write_to_file(
        outfile,
        compression='lzw', tile=True, tile_width=256, tile_height=256,
        pyramid=True, bigtiff=True)
    sz = os.path.getsize(outfile)/1024**3
    print(f"Done! {outfile}  ({sz:.2f} GB)")

if __name__ == '__main__':
    run_stitch(dry_run='--dry-run' in sys.argv)
