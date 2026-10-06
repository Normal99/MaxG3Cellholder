#!/usr/bin/env python3
"""
Layout generator for the Segway Ninebot Max G3 20s4p 21700 cell holder.

Computes, from the envelope / pitch / screw-post parameters below:
  * the staggered (hex) cell grid                     -> 81 slots, 80 cells
  * which slot is left empty for the screw post       -> also used as wire chase
  * the 20s4p series groups (simple 2x2 "diamond" groups, optimised)
  * the copper busbar pieces for the top and bottom face
  * balance-tab and main-lead positions
  * wire grooves for the cover plates
  * split line for printers whose bed is < 270 mm

and writes:
  scad/layout_data.scad      data consumed by scad/cellholder.scad
  docs/wiring_top.svg        wiring diagram, top face (seen from above)
  docs/wiring_bottom.svg     wiring diagram, bottom face (seen from below)
  docs/copper_top.svg        1:1 copper cutting template, top face
  docs/copper_bottom.svg     1:1 copper cutting template, bottom face
  docs/layout.md             group / busbar / tab table

Run:  python3 generator/layout.py        (needs: pip install shapely)

Coordinates: x along the 270 mm length, x = 0 is the DIVIDER end.
             y across the 141 mm width, y = 0 is the deck side wall that the
             screw post is measured from. z up, z = 0 is the deck floor.
"""
import math
import os

from shapely.geometry import MultiPoint, Point, Polygon, box
from shapely.ops import unary_union, voronoi_diagram

# --------------------------------------------------------------------------
# Parameters (mm)
# --------------------------------------------------------------------------
PACK_L = 270.0          # length (x), divider end at x = 0
PACK_W = 141.0          # width (y)
PITCH = 22.2            # cell centre-to-centre distance (EVE 40P: d 21.15 +-0.1)
SERIES = 20
PARALLEL = 4

POST_FROM_SIDE = 80.0      # screw post centre, measured from the y = 0 side wall
POST_FROM_DIVIDER = 6.0    # screw post centre, measured from the divider face
POST_D = 10.0              # screw post diameter (assumed, measure yours!)
POST_H = 10.0              # screw post height
POST_CLEAR = 1.0           # radial clearance around the post

BORE_D = 21.6              # must match cell_bore in cellholder.scad
WINDOW_D = 17.0            # must match window_d in cellholder.scad
WALL_IN = 2.6              # copper keep-out from the outer edge (rim + margin)
BUSBAR_GAP = 2.5           # gap between neighbouring copper pieces
TAB_W = 5.0                # balance tab width

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# --------------------------------------------------------------------------
# Cell grid
# --------------------------------------------------------------------------
ROW_H = PITCH * math.sqrt(3) / 2
N_ROWS = 7
X0 = (PACK_L - 12 * PITCH) / 2 + PITCH / 2
Y0 = (PACK_W - ((N_ROWS - 1) * ROW_H + PITCH)) / 2 + PITCH / 2

slots = []  # (row, col, x, y)
for r in range(N_ROWS):
    n = 12 if r % 2 == 0 else 11
    off = 0.0 if r % 2 == 0 else PITCH / 2
    for c in range(n):
        slots.append((r, c, X0 + off + c * PITCH, Y0 + r * ROW_H))

post = (POST_FROM_DIVIDER, POST_FROM_SIDE)
post_r = POST_D / 2 + POST_CLEAR
hits = [s for s in slots
        if math.hypot(s[2] - post[0], s[3] - post[1]) < post_r + BORE_D / 2]
if len(hits) > 1:
    raise SystemExit(f"screw post collides with {len(hits)} cells: {hits}")
# exactly one slot is left empty: the one hit by the post, or the nearest one
chase = hits[0] if hits else min(
    slots, key=lambda s: math.hypot(s[2] - post[0], s[3] - post[1]))
cells = [s for s in slots if s is not chase]
assert len(cells) == SERIES * PARALLEL, len(cells)
N = len(cells)
pos = [(c[2], c[3]) for c in cells]


def dist(i, j):
    return math.hypot(pos[i][0] - pos[j][0], pos[i][1] - pos[j][1])


nbr = [[j for j in range(N) if j != i and dist(i, j) < PITCH * 1.05]
       for i in range(N)]

# --------------------------------------------------------------------------
# 20s4p grouping - fixed, regular "U" pattern (simple to build)
#
#   rows R0..R3 (lane A, out):  G1..G10 are identical 4-cell zig-zag columns
#                               (one cell per row) - each touches the next
#                               group at 7 points, every copper piece in this
#                               lane is the same 2 x 4 parallelogram.
#   far end (turn):             G11, G12, G13
#   rows R4..R6 (lane B, back): G14..G20 repeat a 3-group pattern
#                               (two "Y" groups + one diamond), 3-5 contacts.
#   B- (G1) and B+ (G20) both end at the divider end.
#
# Cells are addressed as (R, u): R = row, u = x position in half pitches
# (even rows: u = 0,2..22, odd rows: u = 1,3..21). The empty slot (screw
# post / wire chase) is (R4, u0). If the post is measured from the other
# side wall the pattern is mirrored (R -> 6 - R).
# --------------------------------------------------------------------------
GROUP_PATTERN = (
    [[(0, 2 * k), (1, 2 * k + 1), (2, 2 * k), (3, 2 * k + 1)] for k in range(10)]  # G1-G10
    + [[(0, 20), (0, 22), (1, 21), (2, 22)],                                       # G11
       [(2, 20), (3, 21), (4, 20), (4, 22)],                                       # G12
       [(6, 22), (5, 21), (6, 20), (5, 19)]]                                       # G13
    + [g for b in (18, 10, 2) for g in (                                           # G14-G20
        [(4, b), (6, b), (5, b - 1), (4, b - 2)],
        [(6, b - 2), (5, b - 3), (4, b - 4), (6, b - 4)],
        [(5, b - 5), (4, b - 6), (6, b - 6), (5, b - 7)])][:7]
)
# the last group of the repeat would run past u = 0; G20 is closed manually
GROUP_PATTERN[19] = [(4, 2), (6, 2), (5, 1), (6, 0)]


def top_tap(g):  # 0-based group -> tap of its top copper piece (B0, B2 .. B20)
    return 2 * ((g + 1) // 2)


def bot_tap(g):  # 0-based group -> tap of its bottom copper piece (B1 .. B19)
    return 2 * (g // 2) + 1


def solve():
    mirror = round((chase[3] - Y0) / ROW_H) == 2
    if (chase[1] != 0) or round((chase[3] - Y0) / ROW_H) not in (2, 4):
        raise SystemExit("screw post is not at the end of row 2/4 - adjust GROUP_PATTERN")
    lookup = {}
    for i, c in enumerate(cells):
        R = c[0] if not mirror else N_ROWS - 1 - c[0]
        u = 2 * c[1] + (c[0] % 2)
        lookup[(R, u)] = i
    assign = [None] * N
    for g, members in enumerate(GROUP_PATTERN):
        for key in members:
            i = lookup[key]
            assert assign[i] is None, key
            assign[i] = g
    assert None not in assign
    return assign, 0.0


def group_cost(members):
    s = 0.0
    for a in range(4):
        for b in range(a + 1, 4):
            s += dist(members[a], members[b]) / PITCH
    return s - 6.7320508


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def voronoi_tiles():
    """Voronoi tile of every slot (incl. the chase) clipped to the pack."""
    pts = [(s[2], s[3]) for s in slots]
    env = box(-50, -50, PACK_L + 50, PACK_W + 50)
    vd = voronoi_diagram(MultiPoint(pts), envelope=env)
    rect = box(0, 0, PACK_L, PACK_W)
    tiles = {}
    for poly in vd.geoms:
        for k, pnt in enumerate(pts):
            if poly.contains(Point(pnt)):
                tiles[k] = poly.intersection(rect)
                break
    return tiles


def poly_coords(poly):
    if poly.geom_type == "MultiPolygon":
        poly = max(poly.geoms, key=lambda g: g.area)
    return [(round(x, 3), round(y, 3)) for x, y in list(poly.exterior.coords)[:-1]]


def main():
    assign, e = solve()
    groups = [[] for _ in range(SERIES)]
    for i, g in enumerate(assign):
        groups[g].append(i)

    # ---- report quality
    contact = {}
    for i in range(N):
        for j in nbr[i]:
            if assign[i] != assign[j]:
                key = tuple(sorted((assign[i], assign[j])))
                contact[key] = contact.get(key, 0) + 1
    contact = {k: v // 2 for k, v in contact.items()}
    shapes = [round(group_cost(g) + 6.7320508, 2) for g in groups]
    print(f"energy {e:.2f}")
    print("group compactness (6.73 = diamond):", shapes)
    print("series contacts:", [contact.get((k, k + 1), 0) for k in range(SERIES - 1)])

    slot_index = {id(s): k for k, s in enumerate(slots)}
    tiles = voronoi_tiles()
    cell_tile = [tiles[slot_index[id(c)]] for c in cells]
    chase_tile = tiles[slot_index[id(chase)]]
    inner = box(WALL_IN, WALL_IN, PACK_L - WALL_IN, PACK_W - WALL_IN)

    # ---- copper pieces
    def pieces(face):
        out = []
        if face == "top":
            sets = [[0]] + [[k, k + 1] for k in range(1, SERIES - 1, 2)] + [[SERIES - 1]]
            taps = [top_tap(s[0]) for s in sets]
        else:
            sets = [[k, k + 1] for k in range(0, SERIES, 2)]
            taps = [bot_tap(s[0]) for s in sets]
        for gs, tap in zip(sets, taps):
            members = [i for g in gs for i in groups[g]]
            region = unary_union([cell_tile[i] for i in members])
            cu = region.buffer(-BUSBAR_GAP / 2, join_style=2).intersection(inner)
            cu = cu.buffer(-1.0).buffer(1.0)  # round off slivers
            out.append(dict(groups=gs, tap=tap, cells=members, poly=cu))
        return out

    top_pieces = pieces("top")
    bot_pieces = pieces("bottom")

    # ---- tab positions: interstitial point (between 3 cells) inside the piece,
    #      closest to the wire exit. top exits at x = 0, bottom at the chase.
    cx, cy = chase[2], chase[3]

    def interstitials(members):
        ms = set(members)
        out = []
        for a in members:
            for b in nbr[a]:
                if b not in ms or b < a:
                    continue
                for c in nbr[b]:
                    if c in ms and c > b and c in nbr[a]:
                        out.append(((pos[a][0] + pos[b][0] + pos[c][0]) / 3,
                                    (pos[a][1] + pos[b][1] + pos[c][1]) / 3))
        return out

    def pick_tab(pc, face):
        pts = interstitials(pc["cells"])
        if not pts:  # fallback: middle between two cells
            a, b = pc["cells"][0], pc["cells"][1]
            pts = [((pos[a][0] + pos[b][0]) / 2, (pos[a][1] + pos[b][1]) / 2)]
        if face == "top":
            key = lambda p: p[0] + 0.15 * abs(p[1] - PACK_W / 2)
        else:
            key = lambda p: math.hypot(p[0] - cx, p[1] - cy)
        return min(pts, key=key)

    for pc in top_pieces:
        pc["tab"] = pick_tab(pc, "top")
    for pc in bot_pieces:
        pc["tab"] = pick_tab(pc, "bottom")

    # ---- main leads (top face, groups 1 and 20): tongue over the divider end
    for pc in top_pieces:
        if pc["tap"] in (0, SERIES):
            xmin = min(pos[i][0] for i in pc["cells"])
            ends = [pos[i][1] for i in pc["cells"] if pos[i][0] < xmin + 1]
            pc["lead_y"] = sum(ends) / len(ends)

    # ---- wire grooves on the cover plates
    def grooves(pcs, face):
        """Branch groove from every tab to a main channel, channels run to
        the exit (top: divider edge x = 0, bottom: the wire chase)."""
        tabs = sorted((pc["tab"] for pc in pcs
                       if not (face == "top" and pc["tap"] in (0, SERIES))),
                      key=lambda t: t[1])
        clusters = [[tabs[0]]]
        for t in tabs[1:]:
            if t[1] - clusters[-1][-1][1] < 10:
                clusters[-1].append(t)
            else:
                clusters.append([t])
        # lone tabs join the nearest bigger cluster via a branch
        big = [c for c in clusters if len(c) > 1] or clusters
        chans = {id(c): (sum(t[1] for t in c) / len(c), []) for c in big}
        for c in clusters:
            for t in c:
                tgt = min(big, key=lambda b: abs(chans[id(b)][0] - t[1]))
                chans[id(tgt)][1].append(t)
        segs = []  # (x1, y1, x2, y2, width)
        xstart = 0.0 if face == "top" else cx
        ys = [cy]
        for ych, ts in chans.values():
            ych = min(max(ych, 8.0), PACK_W - 8.0)
            ys.append(ych)
            segs.append((xstart, ych, max(t[0] for t in ts), ych, 1.8 * len(ts) + 0.6))
            for tx, ty in ts:
                if abs(ty - ych) > 0.1:
                    segs.append((tx, ty, tx, ych, 2.4))
        if face == "bottom":
            segs.append((cx, min(ys), cx, max(ys), 1.8 * len(tabs) / 2 + 0.6))
        return segs

    top_grooves = grooves(top_pieces, "top")
    bot_grooves = grooves(bot_pieces, "bottom")

    # ---- engraved tap labels: next to the slot, clear of grooves and slots
    def labels(pcs, segs, face):
        from shapely.geometry import LineString
        keep_out = [LineString([(g[0], g[1]), (g[2], g[3])]).buffer(g[4] / 2 + 1.0, cap_style=3)
                    for g in segs]
        out = []
        for pc in pcs:
            if face == "top" and pc["tap"] in (0, SERIES):
                continue
            tx, ty = pc["tab"]
            keep = keep_out + [box(t[0] - 5, t[1] - 3, t[0] + 5, t[1] + 3)
                               for t in [q["tab"] for q in pcs]]
            best = None
            for d in (7, 9, 11, 13, 16, 20):
                for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d), (d, d), (-d, d), (d, -d), (-d, -d)):
                    lb = box(tx + dx - 5, ty + dy - 2.5, tx + dx + 5, ty + dy + 2.5)
                    if (lb.within(box(3, 3, PACK_L - 3, PACK_W - 3))
                            and not any(lb.intersects(k) for k in keep)):
                        best = (tx + dx, ty + dy)
                        break
                if best:
                    break
            out.append([best[0], best[1], f"B{pc['tap']}"] if best else [tx, ty + 7, f"B{pc['tap']}"])
        return out

    top_labels = labels(top_pieces, top_grooves, "top")
    bot_labels = labels(bot_pieces, bot_grooves, "bottom")

    # ---- print split (beds < 270 mm): cells with x < PACK_L/2 -> part A
    split_x = PACK_L / 2
    part_a = unary_union([tiles[k] for k, s in enumerate(slots) if s[2] < split_x])
    part_a = part_a.buffer(0.01).buffer(-0.01)
    # lids split at a column boundary away from the holder split
    lid_split_x = X0 + 7 * PITCH

    # ---- end voids at x = 0 (odd rows): locating pegs + zip-tie anchors
    voids_x0 = [(X0 / 2 + 0.6, Y0 + r * ROW_H) for r in range(1, N_ROWS, 2)]
    voids_x1 = [(PACK_L - X0 / 2 - 0.6, Y0 + r * ROW_H) for r in range(1, N_ROWS, 2)]

    # ---- polarity (which terminal of each cell points UP)
    # group g (0-based): even g -> negative up (B- on top), odd -> positive up
    pol_up = ["-" if assign[i] % 2 == 0 else "+" for i in range(N)]

    # ======================================================================
    # write scad data
    # ======================================================================
    def fmt(v):
        if isinstance(v, (list, tuple)):
            return "[" + ",".join(fmt(x) for x in v) + "]"
        if isinstance(v, str):
            return '"' + v + '"'
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)

    lines = ["// GENERATED by generator/layout.py - do not edit by hand", ""]
    lines.append(f"pack_l = {PACK_L};")
    lines.append(f"pack_w = {PACK_W};")
    lines.append(f"pitch = {PITCH};")
    lines.append("// [x, y, group(1-based), up-terminal]")
    lines.append("cells = " + fmt([[pos[i][0], pos[i][1], assign[i] + 1, pol_up[i]]
                                   for i in range(N)]) + ";")
    lines.append(f"chase = {fmt([chase[2], chase[3]])};")
    lines.append(f"post = {fmt([post[0], post[1], POST_D, POST_H])};")
    lines.append("// [x, y, tap]")
    lines.append("top_tabs = " + fmt([[pc['tab'][0], pc['tab'][1], pc['tap']]
                                      for pc in top_pieces
                                      if pc['tap'] not in (0, SERIES)]) + ";")
    lines.append("bottom_tabs = " + fmt([[pc['tab'][0], pc['tab'][1], pc['tap']]
                                         for pc in bot_pieces]) + ";")
    lines.append("// [y, name]  main lead tongues leave over the divider end (x = 0)")
    lines.append("leads = " + fmt([[pc['lead_y'], 'B-' if pc['tap'] == 0 else 'B+']
                                   for pc in top_pieces if 'lead_y' in pc]) + ";")
    lines.append("// [x1, y1, x2, y2, width]")
    lines.append("top_grooves = " + fmt([list(s) for s in top_grooves]) + ";")
    lines.append("bottom_grooves = " + fmt([list(s) for s in bot_grooves]) + ";")
    lines.append("// [x, y, text] engraved tap labels")
    lines.append("top_labels = " + fmt(top_labels) + ";")
    lines.append("bottom_labels = " + fmt(bot_labels) + ";")
    lines.append("voids_x0 = " + fmt([list(v) for v in voids_x0]) + ";")
    lines.append("voids_x1 = " + fmt([list(v) for v in voids_x1]) + ";")
    lines.append("split_a = " + fmt(poly_coords(part_a)) + ";")
    lines.append(f"lid_split_x = {lid_split_x:.3f};")
    lines.append("top_copper = " + fmt([poly_coords(pc['poly']) for pc in top_pieces]) + ";")
    lines.append("bottom_copper = " + fmt([poly_coords(pc['poly']) for pc in bot_pieces]) + ";")
    with open(os.path.join(ROOT, "scad", "layout_data.scad"), "w") as f:
        f.write("\n".join(lines) + "\n")

    write_svgs(groups, assign, pol_up, top_pieces, bot_pieces, chase, post)
    write_md(groups, assign, pol_up, top_pieces, bot_pieces, contact)
    print("chase slot (empty, screw post / wire chase):", (round(chase[2], 1), round(chase[3], 1)))


# --------------------------------------------------------------------------
# SVG output
# --------------------------------------------------------------------------
PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
           "#f032e6", "#bfef45", "#469990", "#9a6324", "#800000", "#808000"]


def svg_poly(poly, **attrs):
    if poly.geom_type == "MultiPolygon":
        return "".join(svg_poly(g, **attrs) for g in poly.geoms)
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in poly.exterior.coords) + " Z"
    for hole in poly.interiors:
        d += " M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in hole.coords) + " Z"
    return f'<path d="{d}" {a} fill-rule="evenodd"/>'


def write_svgs(groups, assign, pol_up, top_pieces, bot_pieces, chase, post):
    for face in ("top", "bottom"):
        pcs = top_pieces if face == "top" else bot_pieces
        # SVG y points down. Top face seen from above -> flip y,
        # bottom face seen from below (pack rolled over its long axis) -> as is
        my = (lambda y: PACK_W - y) if face == "top" else (lambda y: y)
        margin = 30
        Wd, Hd = PACK_L + 2 * margin, PACK_W + 2 * margin + 40
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wd * 4}" height="{Hd * 4}" '
               f'viewBox="{-margin} {-margin - 30} {Wd} {Hd}" font-family="sans-serif">',
               f'<rect x="{-margin}" y="{-margin - 30}" width="{Wd}" height="{Hd}" fill="white"/>',
               f'<text x="0" y="{-margin + 4 - 30 + 12}" font-size="7" font-weight="bold">'
               f'{face.upper()} face - seen from {"above" if face == "top" else "BELOW (mirrored)"}'
               f' - 20s4p EVE 40P</text>',
               f'<text x="0" y="{-margin - 30 + 24}" font-size="4.5">divider end (x = 0) on the LEFT. '
               'Coloured areas = copper pieces, B# = balance tap. Cell label: group / terminal facing you.</text>',
               f'<rect x="0" y="0" width="{PACK_L}" height="{PACK_W}" fill="#f4f4f4" stroke="#333" stroke-width="0.6"/>',
               f'<rect x="-12" y="0" width="10" height="{PACK_W}" fill="#999"/>',
               f'<text x="-7" y="{PACK_W / 2}" font-size="4" fill="white" text-anchor="middle" '
               f'transform="rotate(-90 -7 {PACK_W / 2})">DIVIDER</text>']
        for k, pc in enumerate(pcs):
            col = PALETTE[pc["tap"] % len(PALETTE)] if False else PALETTE[k % len(PALETTE)]
            poly = pc["poly"]
            if face == "top":
                from shapely.affinity import scale
                poly = scale(poly, 1, -1, origin=(0, PACK_W / 2))
            out.append(svg_poly(poly, fill=col, fill_opacity="0.35", stroke=col, stroke_width="0.5"))
        for i, (x, y) in enumerate(pos):
            g = assign[i] + 1
            up = pol_up[i] if face == "top" else ("+" if pol_up[i] == "-" else "-")
            yy = my(y)
            out.append(f'<circle cx="{x:.2f}" cy="{yy:.2f}" r="{BORE_D / 2 - 0.4:.2f}" fill="none" '
                       f'stroke="#555" stroke-width="0.4"/>')
            out.append(f'<circle cx="{x:.2f}" cy="{yy:.2f}" r="{3.4 if up == "+" else 7.5}" fill="none" '
                       f'stroke="#777" stroke-width="0.3" stroke-dasharray="{"" if up == "+" else "1,1"}"/>')
            out.append(f'<text x="{x:.2f}" y="{yy - 1:.2f}" font-size="5" text-anchor="middle" '
                       f'font-weight="bold">{g}</text>')
            out.append(f'<text x="{x:.2f}" y="{yy + 5.5:.2f}" font-size="6" text-anchor="middle" '
                       f'fill="{"#c00" if up == "+" else "#004"}">{up}</text>')
        cx, cy = chase[2], my(chase[3])
        out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{BORE_D / 2 - 0.4:.2f}" fill="#ddd" '
                   f'stroke="#555" stroke-width="0.4" stroke-dasharray="2,1"/>')
        out.append(f'<text x="{cx:.2f}" y="{cy - 2:.2f}" font-size="3.6" text-anchor="middle">EMPTY</text>')
        out.append(f'<text x="{cx:.2f}" y="{cy + 2.5:.2f}" font-size="3.2" text-anchor="middle">wire chase</text>')
        out.append(f'<circle cx="{post[0]:.2f}" cy="{my(post[1]):.2f}" r="{POST_D / 2}" fill="none" '
                   f'stroke="#a00" stroke-width="0.5" stroke-dasharray="1,0.8"/>')
        out.append(f'<text x="{post[0]:.2f}" y="{my(post[1]) + 8:.2f}" font-size="3" fill="#a00" '
                   f'text-anchor="middle">screw post</text>')
        for pc in pcs:
            if face == "top" and "lead_y" in pc:
                ly = my(pc["lead_y"])
                name = "B-" if pc["tap"] == 0 else "B+"
                out.append(f'<rect x="-14" y="{ly - TAB_W * 2:.2f}" width="16" height="{TAB_W * 4:.2f}" '
                           f'fill="{"#222" if name == "B-" else "#c00"}" opacity="0.85"/>')
                out.append(f'<text x="-6" y="{ly + 2:.2f}" font-size="5" fill="white" '
                           f'text-anchor="middle" font-weight="bold">{name}</text>')
                continue
            tx, ty = pc["tab"][0], my(pc["tab"][1])
            out.append(f'<rect x="{tx - 3.5:.2f}" y="{ty - 1.5:.2f}" width="7" height="3" fill="#000"/>')
            out.append(f'<text x="{tx:.2f}" y="{ty - 2.5:.2f}" font-size="4.5" text-anchor="middle" '
                       f'fill="#000" font-weight="bold" stroke="white" stroke-width="0.25">B{pc["tap"]}</text>')
        out.append("</svg>")
        with open(os.path.join(ROOT, "docs", f"wiring_{face}.svg"), "w") as f:
            f.write("\n".join(out))

    # 1:1 copper cutting templates (print at 100 %, no scaling)
    from shapely.affinity import scale, translate
    for face in ("top", "bottom"):
        pcs = top_pieces if face == "top" else bot_pieces
        items = []
        for pc in pcs:
            poly = pc["poly"]
            if face == "top":  # SVG y points down: flip so the view is from above
                poly = scale(poly, 1, -1, origin=(0, PACK_W / 2))
            items.append((pc, poly))
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PACK_L + 40}mm" height="{PACK_W + 50}mm" '
               f'viewBox="-20 -35 {PACK_L + 40} {PACK_W + 50}" font-family="sans-serif">',
               f'<text x="0" y="-25" font-size="5" font-weight="bold">Copper cutting template - {face.upper()} face '
               f'({"seen from above" if face == "top" else "seen from below"}) - print at 100 % (1:1, mm)</text>',
               '<text x="0" y="-18" font-size="3.5">Solid outline = cut line. Small rectangle = balance tab: '
               'cut a 5 x 7 mm U-flap there and fold it up (or solder the wire there BEFORE welding).</text>',
               '<line x1="0" y1="-10" x2="100" y2="-10" stroke="black" stroke-width="0.4"/>'
               '<text x="50" y="-12" font-size="3" text-anchor="middle">100 mm check</text>',
               f'<rect x="0" y="0" width="{PACK_L}" height="{PACK_W}" fill="none" stroke="#bbb" '
               'stroke-width="0.2" stroke-dasharray="2,2"/>']
        my = (lambda y: PACK_W - y) if face == "top" else (lambda y: y)
        for pc, poly in items:
            out.append(svg_poly(poly, fill="none", stroke="black", stroke_width="0.3"))
            c = poly.representative_point()
            label = f'B{pc["tap"]}'
            if face == "top" and "lead_y" in pc:
                label += " (main lead)"
                ly = my(pc["lead_y"])
                out.append(f'<path d="M {WALL_IN:.2f},{ly - 10:.2f} L -15,{ly - 10:.2f} L -15,{ly + 10:.2f} '
                           f'L {WALL_IN:.2f},{ly + 10:.2f}" fill="none" stroke="black" stroke-width="0.3"/>')
                out.append(f'<text x="-8" y="{ly + 1:.2f}" font-size="2.5" text-anchor="middle">tongue</text>')
            else:
                tx, ty = pc["tab"][0], my(pc["tab"][1])
                out.append(f'<path d="M {tx - 2.5:.2f},{ty - 3.5:.2f} L {tx - 2.5:.2f},{ty + 3.5:.2f} '
                           f'L {tx + 2.5:.2f},{ty + 3.5:.2f} L {tx + 2.5:.2f},{ty - 3.5:.2f}" fill="none" '
                           f'stroke="black" stroke-width="0.3"/>')
            out.append(f'<text x="{c.x:.2f}" y="{c.y:.2f}" font-size="4" text-anchor="middle">{label}</text>')
        out.append("</svg>")
        with open(os.path.join(ROOT, "docs", f"copper_{face}.svg"), "w") as f:
            f.write("\n".join(out))


def write_md(groups, assign, pol_up, top_pieces, bot_pieces, contact):
    rows = ["# Generated layout", "",
            "Generated by `generator/layout.py`. Coordinates in mm, x = 0 at the divider, "
            "y = 0 at the side wall the screw post is measured from.", "",
            "## Series groups", "",
            "| Group | Top terminal | Cells (x, y) | Contacts to next group |",
            "|---|---|---|---|"]
    for g, members in enumerate(groups):
        cs = ", ".join(f"({pos[i][0]:.0f}, {pos[i][1]:.0f})" for i in sorted(members, key=lambda i: pos[i]))
        nxt = contact.get((g, g + 1), "-") if g < SERIES - 1 else "-"
        rows.append(f"| G{g + 1} | {pol_up[members[0]]} | {cs} | {nxt} |")
    rows += ["", "## Copper pieces", "", "| Face | Tap | Joins | Tab / lead position (x, y) |", "|---|---|---|---|"]
    for face, pcs in (("top", top_pieces), ("bottom", bot_pieces)):
        for pc in pcs:
            joins = " + ".join(f"G{g + 1}" for g in pc["groups"])
            if "lead_y" in pc:
                where = f"main lead tongue over divider end, y = {pc['lead_y']:.1f}"
            else:
                where = f"({pc['tab'][0]:.1f}, {pc['tab'][1]:.1f})"
            rows.append(f"| {face} | B{pc['tap']} | {joins} | {where} |")
    with open(os.path.join(ROOT, "docs", "layout.md"), "w") as f:
        f.write("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
