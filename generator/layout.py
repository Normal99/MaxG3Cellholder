#!/usr/bin/env python3
"""
Layout generator for the Segway Ninebot Max G3 20s4p 21700 cell holder.

Computes, from the envelope / pitch / screw-post parameters below:
  * the staggered (hex) cell grid                     -> 81 slots, 80 cells
  * which slot is left empty for the screw post       -> also used as wire chase
  * the 20s4p series groups (diagonal bands, see GROUP_PATTERN)
  * the copper busbar pieces for the top and bottom face: rectangles (or an
    L of two rectangles) only, and a cutting plan for a 100 mm copper roll
  * balance-tab and main-lead positions, punch hole over every cell
  * split line for printers whose bed is < 270 mm

and writes:
  scad/layout_data.scad      data consumed by scad/cellholder.scad
  docs/wiring_top.svg        wiring diagram, top face (seen from above)
  docs/wiring_bottom.svg     wiring diagram, bottom face (seen from below)
  docs/copper_top.svg        1:1 copper cutting template, top face
  docs/copper_bottom.svg     1:1 copper cutting template, bottom face
  docs/copper_cutlist.svg    one 1:1 drawing per distinct copper shape + count
  docs/copper_roll_plan.svg  all pieces nested on the copper roll (ROLL_W wide)
  docs/layout.md             group / busbar / tab table, cut list

Run:  python3 generator/layout.py        (needs: pip install shapely)

Coordinates: x along the 270 mm length, x = 0 is the DIVIDER end.
             y across the 141 mm width, y = 0 is the deck side wall that the
             screw post is measured from. z up, z = 0 is the deck floor.
"""
import math
import os

from shapely import affinity
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

BORE_D = 21.2              # must match cell_bore in cellholder.scad (picked with the fit test strip)
WINDOW_D = 17.0            # must match window_d in cellholder.scad
WALL_IN = 2.6              # copper keep-out from the outer edge (rim + margin)
BUSBAR_GAP = 2.5           # gap between neighbouring copper pieces
TAB_W = 5.0                # balance tab width
TAB_SLOT = (7.0, 3.2)      # cover-plate slot for the folded tab (must match scad)
LEAD_W = 40.0              # max main lead tongue width (B-, B+); limited by the piece
LEAD_LEN = 35.0            # how far the tongue sticks out past the divider end
ROLL_W = 100.0             # width of the copper roll the pieces are cut from
PUNCH_D = 8.0              # hole punched in the copper over every cell (nickel welds through it)
KERF = 2.0                 # spacing between pieces cut from one strip
STRIP_CUT = 1.0            # allowance for one straight cut across the roll
ROW_LEAN = (-1, -1, -1, -1, 0, 0, 0)   # per row: copper cut between cells 0 = square, +-1 = 60 deg
BAND_ROWS = 4              # rows R0.. that hold the slanted bands (cut together per face)

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
# 20s4p grouping - diagonal bands (same pieces as the reference build)
#
# Rows R4-R6 (B- end): the path runs G1 -> G9 away from the divider in
# short 3-row diagonal groups (5..7 contacts); the copper pieces there are
# 3-row blocks.
#
# Rows R0-R3: every group is a DIAGONAL line of 4, one cell per row (R3 ->
# R0, moving half a cell per row). Two neighbouring diagonals sit side by
# side over their whole length (7 cell contacts), so every copper piece
# there is the same slanted band: 2 cells wide, 4 rows tall. The path
# comes back G10 -> G20 to the divider.
#
#   G1        B-, divider end of rows R5-R6, next to the wire chase
#   G2-G9     3-row diagonals R4-R6, away from the divider (G9 also takes
#             the far-end cells of R2/R3)
#   G10-G19   diagonals R3 -> R0, back to the divider
#   G20       B+, divider end of rows R0-R2
#
# Cells are addressed as (R, u): R = row, u = x position in half pitches
# (even rows: u = 0,2..22, odd rows: u = 1,3..21). The empty slot (screw
# post / wire chase) is (R4, u0). If the post is measured from the other
# side wall the pattern is mirrored (R -> 6 - R).
# --------------------------------------------------------------------------
def diagonal(u0):
    """4 cells, one per row, from (R3, u0) up to (R0, u0 + 3)."""
    return [(3 - k, u0 + k) for k in range(4)]


GROUP_PATTERN = (
    [[(5, 1), (6, 0), (6, 2), (6, 4)],                               # G1      B-
     [(4, 2), (5, 3), (5, 5), (6, 6)],                               # G2
     [(4, 4), (4, 6), (5, 7), (6, 8)],                               # G3
     [(4, 8), (5, 9), (6, 10), (6, 12)],                             # G4
     [(4, 10), (5, 11), (5, 13), (6, 14)],                           # G5
     [(4, 12), (4, 14), (5, 15), (6, 16)],                           # G6
     [(4, 16), (5, 17), (6, 18), (6, 20)],                           # G7
     [(4, 22), (5, 19), (5, 21), (6, 22)],                           # G8
     [(2, 22), (3, 21), (4, 18), (4, 20)]]                           # G9
    + [diagonal(u) for u in range(19, 0, -2)]                        # G10-G19
    + [[(0, 0), (0, 2), (1, 1), (2, 0)]]                             # G20     B+
)


def top_tap(g):  # 0-based group -> tap of its top copper piece (B0, B2 .. B20)
    return 2 * ((g + 1) // 2)


def bot_tap(g):  # 0-based group -> tap of its bottom copper piece (B1 .. B19)
    return 2 * (g // 2) + 1


def solve():
    mirror = round((chase[3] - Y0) / ROW_H) == 2
    global MIRROR
    MIRROR = mirror
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


CLIP = box(WALL_IN, Y0 - ROW_H / 2 + BUSBAR_GAP / 2,
           PACK_L - WALL_IN, Y0 + (N_ROWS - 1) * ROW_H + ROW_H / 2 - BUSBAR_GAP / 2)
MIRROR = False


def lat_xy(R, u):
    return (X0 + u * PITCH / 2, Y0 + R * ROW_H)


def lat_key(slot):
    return (slot[0], 2 * slot[1] + slot[0] % 2)


def build_copper(pcs, face):
    """Copper pieces = one straight bar per row of cells (an L / step shape
    where a piece covers two rows). Each bar runs halfway to the next cell of
    another piece in that row, so every cell is fully covered; neighbouring
    pieces are then pulled apart by one busbar gap. Empty end spots of the
    short rows go to the B-/B+ pieces next to them (wider lead tongues), the
    empty chase slot gets no copper (balance wires pass through it)."""
    owner = {}
    for k, pc in enumerate(pcs):
        for i in pc["cells"]:
            owner[lat_key(cells[i])] = k
    lead = {k for k, pc in enumerate(pcs) if face == "top" and pc["tap"] in (0, SERIES)}
    ch = lat_key(chase)
    g2 = BUSBAR_GAP / 2
    x_lo, x_hi = WALL_IN - g2, PACK_L - WALL_IN + g2
    y_lo, y_hi = CLIP.bounds[1] - g2, CLIP.bounds[3] + g2
    raw = {k: [] for k in range(len(pcs))}
    for r in range(N_ROWS):
        slots_r = sorted(((lat_xy(r, u)[0], owner.get((r, u), "chase" if (r, u) == ch else None))
                          for u in range(-1, 24) if (u - r) % 2 == 0
                          and ((r, u) in owner or (r, u) == ch)), key=lambda t: t[0])
        # empty end spot of a short row next to a lead piece belongs to it
        ends = [(-1, slots_r[0][1]), (23, slots_r[-1][1])] if r % 2 == 1 else []
        for u_end, ks in ends:
            near = [owner.get((r + dr, u_end + (1 if u_end < 0 else -1))) for dr in (-1, 1)]
            ld = [n for n in [ks] + near if n in lead]
            if ld:
                slots_r.append((lat_xy(r, u_end)[0], ld[0]))
        slots_r.sort(key=lambda t: t[0])
        yb = max(Y0 + (r - 0.5) * ROW_H, y_lo)    # same formula for every
        yt = min(Y0 + (r + 0.5) * ROW_H, y_hi)    # row line: no float gaps
        for j, (x, k) in enumerate(slots_r):
            if k in (None, "chase"):
                continue
            # cut between two cells of a row: straight up (lean 0) or along
            # the 60 deg lattice line (lean +-1), so diagonal groups get
            # straight slanted edges instead of steps; pack walls stay square
            t = ROW_LEAN[r] * math.tan(math.radians(30))
            yc = Y0 + r * ROW_H
            if j == 0:
                lb, lt = x_lo, x_lo
            else:
                m = (slots_r[j - 1][0] + x) / 2
                lb, lt = m + t * (yb - yc), m + t * (yt - yc)
            if j == len(slots_r) - 1:
                hb, ht = x_hi, x_hi
            else:
                m = (x + slots_r[j + 1][0]) / 2
                hb, ht = m + t * (yb - yc), m + t * (yt - yc)
            tile = Polygon([(lb, yb), (hb, yb), (ht, yt), (lt, yt)])
            raw[k].append(tile.intersection(box(x_lo, yb, x_hi, yt)))
    for k, pc in enumerate(pcs):
        # pieces touch edge to edge; shrinking each by half a gap leaves one
        # busbar gap everywhere and keeps every edge square
        poly = unary_union(raw[k]).buffer(0.001, join_style=2).buffer(-0.001 - g2, join_style=2)
        if poly.geom_type != "Polygon":
            raise SystemExit(f"{face} B{pc['tap']} copper is not one piece: "
                             + str([[round(v, 1) for v in b.bounds] for b in raw[k]]))
        pc["poly"] = poly.simplify(0.01)

    # main lead tongues: as wide as the piece allows at the divider end
    for k in lead:
        pc = pcs[k]
        strip = pc["poly"].intersection(box(WALL_IN, 0, WALL_IN + 3, PACK_W))
        y0, y1 = strip.bounds[1], strip.bounds[3]
        # two rows wide (no step), against the outer side wall: the BMS dock's
        # lead notches sit there
        w = min(LEAD_W, y1 - y0, 2 * ROW_H - BUSBAR_GAP)
        yc = y0 + w / 2 if (y0 + y1) / 2 < PACK_W / 2 else y1 - w / 2
        pc["lead_y"], pc["lead_w"] = yc, w
        pc["poly"] = unary_union([pc["poly"], box(-LEAD_LEN, yc - w / 2, WALL_IN + 0.5, yc + w / 2)])

    # checks: gap between pieces, and no copper over another piece's window
    for k, pc in enumerate(pcs):
        for j in range(k + 1, len(pcs)):
            d = pc["poly"].distance(pcs[j]["poly"])
            assert d > BUSBAR_GAP - 0.05, (face, pc["tap"], pcs[j]["tap"], d)
        mine = set(pc["cells"])
        for i in range(N):
            if i not in mine:
                d = pc["poly"].distance(Point(pos[i]))
                assert d > WINDOW_D / 2 + 0.5, (face, pc["tap"], i, d)


def pick_tab(pc, face):
    """Slot for the folded balance tab: inside the piece, over plastic only."""
    mine = set(pc["cells"])
    cands = []
    for a_ in pc["cells"]:
        for b_ in nbr[a_]:
            if b_ in mine and b_ > a_:
                cands.append(((pos[a_][0] + pos[b_][0]) / 2, (pos[a_][1] + pos[b_][1]) / 2))
                for c_ in nbr[b_]:
                    if c_ in nbr[a_] and c_ > b_:
                        cands.append(((pos[a_][0] + pos[b_][0] + pos[c_][0]) / 3,
                                      (pos[a_][1] + pos[b_][1] + pos[c_][1]) / 3))
    inside = pc["poly"].buffer(-0.8)
    centres = [Point(q) for q in pos]
    ok = []
    for angles in ((0, 90), (60, 120, 30, 150)):   # square to the piece if at all possible
        if ok:
            break
        ok = slot_options(cands, angles, inside, centres)
    assert ok, ("no room for a balance tab", face, pc["tap"])
    if face == "top":
        key = lambda c: (c[0][0] + 0.15 * abs(c[0][1] - PACK_W / 2), c[1] != 0)
    else:
        key = lambda c: (math.hypot(c[0][0] - chase[2], c[0][1] - chase[3]), c[1] != 0)
    return min(ok, key=key)


def slot_options(cands, angles, inside, centres):
    ok = []
    for (x, y) in cands:
        for ang in angles:
            r = affinity.rotate(box(x - TAB_SLOT[0] / 2, y - TAB_SLOT[1] / 2,
                                    x + TAB_SLOT[0] / 2, y + TAB_SLOT[1] / 2), ang)
            if not r.within(inside):
                continue
            if min(r.distance(c) for c in centres) < WINDOW_D / 2 + 0.6:
                continue
            if r.distance(Point(chase[2], chase[3])) < BORE_D / 2 + 1:
                continue
            ok.append(((x, y), ang))
    return ok


def classify_shapes(all_pcs):
    """Give identical copper pieces the same letter (mirror / turn allowed)."""
    def norm(poly):
        b = poly.bounds
        return affinity.translate(poly, -b[0], -b[1])
    types = []
    for pc in all_pcs:
        if "lead_y" in pc:
            pc["shape"] = None
            continue
        vs = [norm(pc["poly"]), norm(affinity.scale(pc["poly"], -1, 1)),
              norm(affinity.scale(pc["poly"], 1, -1)), norm(affinity.scale(pc["poly"], -1, -1))]
        for t in types:
            if any(v.symmetric_difference(t["poly"]).area < 2.0 for v in vs):
                t["members"].append(pc)
                break
        else:
            types.append(dict(poly=vs[0], members=[pc]))
    types.sort(key=lambda t: -len(t["members"]))
    for n, t in enumerate(types):
        t["letter"] = chr(ord("A") + n)
        for pc in t["members"]:
            pc["shape"] = t["letter"]
    leads = [pc for pc in all_pcs if "lead_y" in pc]
    for pc in leads:
        pc["shape"] = "B-" if pc["tap"] == 0 else "B+"
    return types


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
    print("group compactness (6.73 = diamond):", shapes)
    print("series contacts:", [contact.get((k, k + 1), 0) for k in range(SERIES - 1)])

    tiles = voronoi_tiles()

    # ---- copper pieces (which groups each piece joins)
    def piece_sets(face):
        if face == "top":
            sets = [[0]] + [[k, k + 1] for k in range(1, SERIES - 1, 2)] + [[SERIES - 1]]
            return [(gs, top_tap(gs[0])) for gs in sets]
        return [([k, k + 1], bot_tap(k)) for k in range(0, SERIES, 2)]

    top_pieces = [dict(groups=gs, tap=t, cells=[i for g in gs for i in groups[g]])
                  for gs, t in piece_sets("top")]
    bot_pieces = [dict(groups=gs, tap=t, cells=[i for g in gs for i in groups[g]])
                  for gs, t in piece_sets("bottom")]
    for pc in top_pieces:
        if pc["tap"] in (0, SERIES):
            pc["lead"] = True
    for face, pcs in (("top", top_pieces), ("bottom", bot_pieces)):
        build_copper(pcs, face)

    # ---- balance tabs: a slot position inside the piece, over plastic
    #      (clear of every welding window), close to the wire exit
    for face, pcs in (("top", top_pieces), ("bottom", bot_pieces)):
        for pc in pcs:
            if face == "top" and pc["tap"] in (0, SERIES):
                continue
            pc["tab"], pc["tab_a"] = pick_tab(pc, face)

    # ---- print splits (beds < 270 mm) that LOCK once the cells are in:
    # each seam runs through one "key" cell per row. Each key cell's socket
    # is cut in half across its centre; one half belongs to part A, the
    # other to part B, alternating row by row. With the key cells pushed
    # in, every key cell sits in a socket half of both parts, so A and B
    # cannot slide apart. The top half is split one cell column further
    # along than the bottom half, so the two seams never line up.
    def locking_split(split_x):
        tiles_a, keys = [], []
        for r in range(N_ROWS):
            row = [k for k, s in enumerate(slots) if s[0] == r]
            key = min(row, key=lambda k: (abs(slots[k][2] - split_x), slots[k][2]))
            kx, ky = slots[key][2], slots[key][3]
            keys.append((kx, ky))
            tiles_a += [tiles[k] for k in row if slots[k][2] < kx]
            half = box(-1, ky, PACK_L + 1, PACK_W + 1) if r % 2 == 0 else box(-1, -1, PACK_L + 1, ky)
            tiles_a.append(tiles[key].intersection(half))
        a = unary_union(tiles_a).buffer(0.01, join_style=2).buffer(-0.01, join_style=2)
        b = box(0, 0, PACK_L, PACK_W).difference(a)
        if a.geom_type != "Polygon" or b.geom_type != "Polygon":
            raise SystemExit("print split part is not one piece")
        return a, keys

    part_a, key_cells = locking_split(PACK_L / 2)
    part_a_top, key_cells_top = locking_split(PACK_L / 2 + PITCH)

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
    lines.append("// [y, name, width]  main lead tongues leave over the divider end (x = 0)")
    lines.append("leads = " + fmt([[pc['lead_y'], 'B-' if pc['tap'] == 0 else 'B+', pc['lead_w']]
                                   for pc in top_pieces if 'lead_y' in pc]) + ";")
    lines.append("voids_x0 = " + fmt([list(v) for v in voids_x0]) + ";")
    lines.append("voids_x1 = " + fmt([list(v) for v in voids_x1]) + ";")
    lines.append("split_a = " + fmt(poly_coords(part_a)) + ";          // bottom half")
    lines.append("split_a_top = " + fmt(poly_coords(part_a_top)) + ";  // top half")
    lines.append("// key cells of the print splits (socket shared by both parts)")
    lines.append("split_keys = " + fmt([list(k) for k in key_cells]) + ";")
    lines.append("split_keys_top = " + fmt([list(k) for k in key_cells_top]) + ";")
    lines.append("top_copper = " + fmt([poly_coords(pc['poly']) for pc in top_pieces]) + ";")
    lines.append("bottom_copper = " + fmt([poly_coords(pc['poly']) for pc in bot_pieces]) + ";")
    with open(os.path.join(ROOT, "scad", "layout_data.scad"), "w") as f:
        f.write("\n".join(lines) + "\n")

    types = classify_shapes(top_pieces + bot_pieces)
    print("copper shapes:", ", ".join(f"{t['letter']} x{len(t['members'])}" for t in types))
    maxdv = 0
    for pcs in (top_pieces, bot_pieces):
        for p1 in pcs:
            for p2 in pcs:
                if p1 is not p2 and p1["poly"].distance(p2["poly"]) < BUSBAR_GAP + 1:
                    maxdv = max(maxdv, abs(p1["tap"] - p2["tap"]))
    print("largest voltage step between neighbouring pieces:", maxdv, "taps")
    plan, roll_len = roll_plan([top_pieces, bot_pieces])
    print(f"copper roll: {ROLL_W:.0f} mm wide x {roll_len:.0f} mm long")
    write_roll_svg(plan, roll_len, top_pieces)
    write_svgs(groups, assign, pol_up, top_pieces, bot_pieces, chase, post, types)
    write_md(groups, assign, pol_up, top_pieces, bot_pieces, contact, types, maxdv, roll_len)
    print("chase slot (empty, screw post / wire chase):", (round(chase[2], 1), round(chase[3], 1)))


# --------------------------------------------------------------------------
# SVG output
# --------------------------------------------------------------------------
PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
           "#f032e6", "#bfef45", "#469990", "#9a6324", "#800000", "#808000"]
SHAPE_COL = {"A": "#4363d8", "B": "#3cb44b", "C": "#f58231", "D": "#911eb4", "E": "#f032e6",
             "F": "#469990", "G": "#9a6324", "H": "#808000", "I": "#42d4f4", "J": "#bfef45",
             "B-": "#333333", "B+": "#c00000"}


def svg_poly(poly, **attrs):
    if poly.geom_type == "MultiPolygon":
        return "".join(svg_poly(g, **attrs) for g in poly.geoms)
    a = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in poly.exterior.coords) + " Z"
    for hole in poly.interiors:
        d += " M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in hole.coords) + " Z"
    return f'<path d="{d}" {a} fill-rule="evenodd"/>'


def view(face, geom):
    """SVG y points down: top face seen from above -> flip y; bottom face seen
    from below (pack rolled over its long axis) -> as is."""
    return affinity.scale(geom, 1, -1, origin=(0, PACK_W / 2)) if face == "top" else geom


def with_holes(pc):
    """Copper outline with the punch hole over every cell of the piece."""
    holes = unary_union([Point(pos[i]).buffer(PUNCH_D / 2, quad_segs=8) for i in pc["cells"]])
    return pc["poly"].difference(holes)


def slot_poly(x, y, ang, size=TAB_SLOT):
    return affinity.rotate(box(x - size[0] / 2, y - size[1] / 2, x + size[0] / 2, y + size[1] / 2), ang)


def write_svgs(groups, assign, pol_up, top_pieces, bot_pieces, chase, post, types):
    ML = LEAD_LEN + 12
    for face in ("top", "bottom"):
        pcs = top_pieces if face == "top" else bot_pieces
        my = (lambda y: PACK_W - y) if face == "top" else (lambda y: y)
        Wd, Hd = PACK_L + ML + 15, PACK_W + 75
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{Wd * 4}" height="{Hd * 4}" '
               f'viewBox="{-ML} -55 {Wd} {Hd}" font-family="sans-serif">',
               f'<rect x="{-ML}" y="-55" width="{Wd}" height="{Hd}" fill="white"/>',
               f'<text x="0" y="-38" font-size="7" font-weight="bold">'
               f'{face.upper()} face - seen from {"above" if face == "top" else "BELOW (mirrored)"}'
               f' - 20s4p EVE 40P</text>',
               '<text x="0" y="-27" font-size="4.5">divider end (x = 0) on the LEFT. Coloured areas = copper '
               'pieces, same colour + letter = same shape. Black bar = balance tab slot.</text>',
               '<text x="0" y="-20" font-size="4.5">Cell label: group number / terminal facing you.</text>',
               f'<rect x="0" y="0" width="{PACK_L}" height="{PACK_W}" fill="#f4f4f4" stroke="#333" stroke-width="0.6"/>',
               f'<rect x="-10" y="0" width="10" height="{PACK_W}" fill="#bbb"/>',
               f'<text x="-5" y="{PACK_W / 2}" font-size="4" fill="white" text-anchor="middle" '
               f'transform="rotate(-90 -5 {PACK_W / 2})">DIVIDER (tongues fold down here)</text>']
        for pc in pcs:
            col = SHAPE_COL.get(pc["shape"], "#888")
            out.append(svg_poly(view(face, pc["poly"]), fill=col, fill_opacity="0.30",
                                stroke=col, stroke_width="0.6"))
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
        for pc in pcs:
            if "lead_y" in pc:
                ly = my(pc["lead_y"])
                name = "B-" if pc["tap"] == 0 else "B+"
                out.append(f'<text x="{-LEAD_LEN / 2 - 3:.2f}" y="{ly + 3:.2f}" font-size="9" '
                           f'text-anchor="middle" font-weight="bold" fill="{SHAPE_COL[name]}">{name}</text>')
                continue
            sp = view(face, slot_poly(pc["tab"][0], pc["tab"][1], pc["tab_a"]))
            out.append(svg_poly(sp, fill="#000"))
            c = sp.centroid
            out.append(f'<text x="{c.x:.2f}" y="{c.y - 3:.2f}" font-size="4.5" text-anchor="middle" '
                       f'font-weight="bold" stroke="white" stroke-width="0.25">B{pc["tap"]}</text>')
        out.append("</svg>")
        with open(os.path.join(ROOT, "docs", f"wiring_{face}.svg"), "w") as f:
            f.write("\n".join(out))

    # 1:1 copper cutting templates of the whole face (print at 100 %)
    for face in ("top", "bottom"):
        pcs = top_pieces if face == "top" else bot_pieces
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{PACK_L + ML + 15}mm" height="{PACK_W + 50}mm" '
               f'viewBox="{-ML} -35 {PACK_L + ML + 15} {PACK_W + 50}" font-family="sans-serif">',
               f'<text x="0" y="-25" font-size="5" font-weight="bold">Copper layout - {face.upper()} face '
               f'({"seen from above" if face == "top" else "seen from below"}) - 1:1, print at 100 %</text>',
               '<text x="0" y="-18" font-size="3.5">Letter = shape (see copper_cutlist.svg). Dashed = fold line. '
               'Circles = punch holes (one per cell). Small rectangle = balance tab flap.</text>',
               '<line x1="0" y1="-10" x2="100" y2="-10" stroke="black" stroke-width="0.4"/>'
               '<text x="50" y="-12" font-size="3" text-anchor="middle">100 mm check</text>',
               f'<rect x="0" y="0" width="{PACK_L}" height="{PACK_W}" fill="none" stroke="#bbb" '
               'stroke-width="0.2" stroke-dasharray="2,2"/>']
        for pc in pcs:
            poly = view(face, with_holes(pc))
            out.append(svg_poly(poly, fill="none", stroke="black", stroke_width="0.3"))
            c = poly.representative_point()
            label = f'{pc["shape"]}  B{pc["tap"]}' if pc["shape"] not in ("B-", "B+") else f'{pc["shape"]} (B{pc["tap"]})'
            if "lead_y" in pc:
                ly = PACK_W - pc["lead_y"]
                out.append(f'<line x1="0" y1="{ly - pc["lead_w"] / 2:.2f}" x2="0" y2="{ly + pc["lead_w"] / 2:.2f}" '
                           'stroke="black" stroke-width="0.3" stroke-dasharray="1.5,1"/>')
                out.append(f'<text x="{-LEAD_LEN / 2:.2f}" y="{ly + 1:.2f}" font-size="3" text-anchor="middle">'
                           'solder lead here</text>')
                c = Point(25, ly)
            else:
                out.append(svg_poly(view(face, flap_poly(pc)), fill="none", stroke="black", stroke_width="0.3"))
            out.append(f'<text x="{c.x:.2f}" y="{c.y:.2f}" font-size="4" text-anchor="middle">{label}</text>')
        out.append("</svg>")
        with open(os.path.join(ROOT, "docs", f"copper_{face}.svg"), "w") as f:
            f.write("\n".join(out))

    # cut list: every distinct shape once, 1:1, with count and edge lengths
    items = [(t["letter"], t["members"][0], len(t["members"])) for t in types]
    items += [(pc["shape"], pc, 1) for pc in top_pieces if "lead_y" in pc]
    cw = 150
    placed, x, y, rowh = [], 0, 0, 0
    for k, (letter, pc, n) in enumerate(items):
        poly = view("top" if pc in top_pieces else "bottom", with_holes(pc))
        b = poly.bounds
        poly = affinity.translate(poly, -b[0], -b[1])
        w, h = b[2] - b[0], b[3] - b[1]
        if x + w > 2 * cw:
            x, y, rowh = 0, y + rowh + 30, 0
        placed.append((letter, pc, n, affinity.translate(poly, x, y), w, h))
        x += max(w, 60) + 25
        rowh = max(rowh, h)
    H = y + rowh + 45
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{2 * cw + 20}mm" height="{H + 30}mm" '
           f'viewBox="-10 -30 {2 * cw + 20} {H + 30}" font-family="sans-serif">',
           '<rect x="-10" y="-30" width="100%" height="100%" fill="white"/>',
           '<text x="0" y="-20" font-size="5" font-weight="bold">Copper cut list - one template per shape, 1:1 '
           '(print at 100 %)</text>',
           '<text x="0" y="-13" font-size="3.5">Cut one template, then trace it as many times as the count says. '
           f'Mirrored copies = flip the template over. Circles = {PUNCH_D:.0f} mm punch hole over each cell.</text>',
           '<line x1="0" y1="-6" x2="100" y2="-6" stroke="black" stroke-width="0.4"/>'
           '<text x="50" y="-7.5" font-size="3" text-anchor="middle">100 mm check</text>']
    for letter, pc, n, poly, w, h in placed:
        col = SHAPE_COL.get(letter, "#888")
        out.append(svg_poly(poly, fill=col, fill_opacity="0.15", stroke="black", stroke_width="0.35"))
        coords = list(poly.exterior.coords)
        for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
            L = math.hypot(x2 - x1, y2 - y1)
            if L > 8:
                out.append(f'<text x="{(x1 + x2) / 2:.2f}" y="{(y1 + y2) / 2:.2f}" font-size="2.6" '
                           f'text-anchor="middle" fill="#333">{L:.1f}</text>')
        b = poly.bounds
        faces = {}
        for m in ([pc] if letter in ("B-", "B+") else next(t["members"] for t in types if t["letter"] == letter)):
            f_ = "top" if m in top_pieces else "bottom"
            faces.setdefault(f_, []).append(f'B{m["tap"]}')
        where = "; ".join(f"{f_}: {', '.join(v)}" for f_, v in faces.items())
        out.append(f'<text x="{b[0]:.2f}" y="{b[3] + 7:.2f}" font-size="5" font-weight="bold">'
                   f'{letter}  x {n}</text>')
        out.append(f'<text x="{b[0]:.2f}" y="{b[3] + 12:.2f}" font-size="3">{where}</text>')
    out.append("</svg>")
    with open(os.path.join(ROOT, "docs", "copper_cutlist.svg"), "w") as f:
        f.write("\n".join(out))


def flap_poly(pc):
    """U-flap outline (3 cut sides) for the balance tab, drawn as an open box."""
    x, y = pc["tab"]
    return slot_poly(x, y, pc["tab_a"], (TAB_W, TAB_SLOT[0]))


def roll_plan(faces):
    """Cutting plan for a ROLL_W wide roll, straight cuts only.
    1. Per face, the pieces of rows R0..R(BAND_ROWS-1) (the slanted bands),
       and those of the rows after them, are cut from one strip each, laid
       out exactly as on the pack: cut the strip off the roll, then cut the
       lines between the pieces (only where that saves roll).
    2. Every other piece gets its own strip across the roll (strip width =
       piece height). A piece too long to go across lies along the roll,
       with the piece that saves the most roll next to it.
    Returns placements [(pc, placed_polygon)] and the length; each pc gets
    pc["strip"] = (x0, x1) on the roll."""
    def size(pc):
        b = pc["poly"].bounds
        return b[2] - b[0], b[3] - b[1]

    def place(pc, dx, dy, turn):
        g = with_holes(pc)
        if turn:                                  # long side across the roll
            g = affinity.rotate(g, 90, origin=(0, 0))
            b = g.bounds
            return affinity.translate(g, dx - b[0], dy - b[1])
        return affinity.translate(g, dx, dy)

    def strip_len(pc):
        w, h = size(pc)
        return h if w <= ROLL_W else w

    # row regions: the bands (R0..) and the rows after them; a region's
    # pieces are cut as one strip in pack order if that uses less roll
    cut = Y0 + (BAND_ROWS - 0.5) * ROW_H
    blocks, rest = [], []                         # block: [(pc, turn, dx, dy)]
    for pcs in faces:
        for lo, hi in ((-1e9, cut + 0.01), (cut - 0.01, 1e9)):
            reg = [pc for pc in pcs if lo <= pc["poly"].bounds[1] and pc["poly"].bounds[3] <= hi]
            if not reg:
                continue
            x0 = min(pc["poly"].bounds[0] for pc in reg)
            y0 = min(pc["poly"].bounds[1] for pc in reg)
            x1 = max(pc["poly"].bounds[2] for pc in reg)
            y1 = max(pc["poly"].bounds[3] for pc in reg)
            if y1 - y0 <= ROLL_W and x1 - x0 < sum(strip_len(pc) for pc in reg):
                blocks.append([(pc, False, -x0, -y0) for pc in reg])
            else:
                rest += reg
        rest += [pc for pc in pcs if pc not in rest and not any(pc is q for b in blocks for q, *_ in b)]
    rest.sort(key=lambda pc: (pc["shape"].ljust(3), pc["tap"]))
    for pc in rest:
        assert min(size(pc)) <= ROLL_W, ("piece wider than the roll", pc["tap"])
    for pc in [q for q in rest if size(q)[0] > ROLL_W]:
        if pc not in rest:
            continue
        rest.remove(pc)
        w, h = size(pc)
        b = pc["poly"].bounds
        blk = [(pc, False, -b[0], -b[1])]
        side = [q for q in rest if size(q)[1] <= ROLL_W - h - KERF and size(q)[0] <= w]
        side.sort(key=lambda q: -(size(q)[0] if size(q)[0] > ROLL_W else size(q)[1]))
        if side:
            rest.remove(side[0])
            qb = side[0]["poly"].bounds
            blk.append((side[0], False, -qb[0], h + KERF - qb[1]))
        blocks.append(blk)
    blocks += [[(pc, True, 0.0, 0.0)] for pc in rest]
    out, x = [], 0.0
    for blk in blocks:
        geo = [(pc, place(pc, dx, dy, turn)) for pc, turn, dx, dy in blk]
        ln = max(g.bounds[2] for _, g in geo) - min(g.bounds[0] for _, g in geo)
        sx = x - min(g.bounds[0] for _, g in geo)
        for pc, g in geo:
            out.append((pc, affinity.translate(g, sx, 0)))
            pc["strip"] = (x, x + ln)
        x += ln + STRIP_CUT
    for i, (pa, ga) in enumerate(out):
        assert ga.bounds[1] > -0.01 and ga.bounds[3] < ROLL_W + 0.01, (pa["tap"], ga.bounds)
        for pb, gb in out[i + 1:]:
            assert ga.distance(gb) > min(STRIP_CUT, BUSBAR_GAP) - 0.05, (pa["tap"], pb["tap"])
    return out, x - STRIP_CUT


def write_roll_svg(plan, length, top_pieces):
    L = length + 10
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{L + 10}mm" height="{ROLL_W + 40}mm" '
           f'viewBox="-5 -30 {L + 10} {ROLL_W + 40}" font-family="sans-serif">',
           '<rect x="-5" y="-30" width="100%" height="100%" fill="white"/>',
           f'<text x="0" y="-18" font-size="6" font-weight="bold">Copper roll cutting plan - {ROLL_W:.0f} mm roll, '
           f'{length:.0f} mm long for one pack (1:1)</text>',
           '<text x="0" y="-9" font-size="4">Cut the roll straight across into the sections below, left to right '
           '(number = section length). Multi-piece sections are laid out as on the pack: cut between the pieces.</text>',
           f'<rect x="0" y="0" width="{length:.1f}" height="{ROLL_W}" fill="#f7e3cf" stroke="#b5651d" stroke-width="0.6"/>']
    strips = sorted({pc["strip"] for pc, _ in plan})
    for n, (x0, x1) in enumerate(strips):
        if n < len(strips) - 1:
            xc = x1 + STRIP_CUT / 2
            out.append(f'<line x1="{xc:.1f}" y1="-4" x2="{xc:.1f}" y2="{ROLL_W + 4}" stroke="red" '
                       'stroke-width="0.4" stroke-dasharray="2,1"/>')
        out.append(f'<text x="{(x0 + x1) / 2:.1f}" y="-1.5" font-size="3.5" text-anchor="middle" fill="red">'
                   f'{n + 1}: {x1 - x0:.0f}</text>')
    for pc, g in plan:
        face = "top" if pc in top_pieces else "bottom"
        out.append(svg_poly(g, fill="white", fill_opacity="0.6", stroke="black", stroke_width="0.35"))
        c = g.representative_point()
        lab = pc["shape"] if pc["shape"] in ("B-", "B+") else f'{pc["shape"]} B{pc["tap"]}'
        out.append(f'<text x="{c.x:.1f}" y="{c.y:.1f}" font-size="5" text-anchor="middle">{lab}</text>')
        out.append(f'<text x="{c.x:.1f}" y="{c.y + 5:.1f}" font-size="3" text-anchor="middle">{face}</text>')
    out.append("</svg>")
    with open(os.path.join(ROOT, "docs", "copper_roll_plan.svg"), "w") as f:
        f.write("\n".join(out))


def write_md(groups, assign, pol_up, top_pieces, bot_pieces, contact, types, maxdv, roll_len):
    rows = ["# Generated layout", "",
            "Generated by `generator/layout.py`. Coordinates in mm, x = 0 at the divider, "
            "y = 0 at the side wall the screw post is measured from.", "",
            "## Copper cut list", "",
            "Every copper edge is a straight line. Identical letters = identical pieces "
            "(a mirrored copy is the same template flipped over).", "",
            "| Shape | Count | Pieces |", "|---|---|---|"]
    for t in types:
        names = ", ".join(f'{"top" if m in top_pieces else "bottom"} B{m["tap"]}' for m in t["members"])
        rows.append(f"| {t['letter']} | {len(t['members'])} | {names} |")
    for pc in top_pieces:
        if "lead_y" in pc:
            rows.append(f"| {pc['shape']} | 1 | top B{pc['tap']} + {pc['lead_w']:.0f} x {LEAD_LEN:.0f} mm lead tongue |")
    rows += ["", f"All pieces fit across a {ROLL_W:.0f} mm copper roll; one pack uses about "
             f"{roll_len:.0f} mm of roll per copper layer (see copper_roll_plan.svg)."]
    rows += ["", f"Largest voltage step between neighbouring copper pieces on one face: "
             f"{maxdv} groups (~{maxdv * 4.2:.0f} V at full charge).", "",
             "## Series groups", "",
             "| Group | Top terminal | Cells (x, y) | Contacts to next group |",
             "|---|---|---|---|"]
    for g, members in enumerate(groups):
        cs = ", ".join(f"({pos[i][0]:.0f}, {pos[i][1]:.0f})" for i in sorted(members, key=lambda i: pos[i]))
        nxt = contact.get((g, g + 1), "-") if g < SERIES - 1 else "-"
        rows.append(f"| G{g + 1} | {pol_up[members[0]]} | {cs} | {nxt} |")
    rows += ["", "## Copper pieces", "", "| Face | Tap | Shape | Joins | Tab / lead position (x, y) |",
             "|---|---|---|---|---|"]
    for face, pcs in (("top", top_pieces), ("bottom", bot_pieces)):
        for pc in pcs:
            joins = " + ".join(f"G{g + 1}" for g in pc["groups"])
            if "lead_y" in pc:
                where = f"lead tongue {pc['lead_w']:.0f} mm wide at y = {pc['lead_y']:.1f}"
            else:
                where = f"({pc['tab'][0]:.1f}, {pc['tab'][1]:.1f})"
            rows.append(f"| {face} | B{pc['tap']} | {pc['shape']} | {joins} | {where} |")
    with open(os.path.join(ROOT, "docs", "layout.md"), "w") as f:
        f.write("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
