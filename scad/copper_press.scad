// Copper press: forms a shallow dish in the copper over every cell, so each
// dish drops into the holder's welding window and sits on the cell (the cells
// are recessed cell_recess below the holder face). The dishes also lock the
// copper on the holder so it can't slide while you weld.
//
// Two plates: the DIE (pockets + locating pins) and the PUNCH (bosses).
// Every copper piece sits on the same hex grid, so one plate with a pocket at
// every grid position fits every piece. The 8 mm hole you punch over each
// cell drops over the pin in the middle of its pocket: the piece lines up
// by itself, and the same pins guide the punch onto the die.
//
// Use: punch the 8 mm holes first. Lay the copper on the DIE with the side
// that faces the cells DOWN, holes over the pins. Put the PUNCH on (bosses
// down) and squeeze evenly: vise, clamps, or a wood block and a mallet.
//
// Parts (set `part`):  die, punch          5 x 5 cells, fits every piece
//                      test_die, test_punch  1 cell, to check copper_t /
//                                            dish_depth before the big print
// Print flat, as oriented (die pins up, punch bosses up), 0.1-0.12 mm layers.

part = "die";

// ---- must match the holder (cellholder.scad / generator/layout.py)
pitch       = 22.2;   // cell centre-to-centre
window_d    = 17.0;   // welding window in the holder face
cell_recess = 0.6;    // cell top below the holder face
punch_hole  = 8.0;    // hole punched in the copper over every cell (PUNCH_D)

// ---- the copper and the dish
copper_t    = 0.2;    // copper thickness: MEASURE yours
dish_depth  = cell_recess;  // how far the dish drops (raise by ~0.1 if it springs back)
dish_clear  = 0.4;    // dish outside is this much smaller than the window
wall_clear  = 0.15;   // extra gap between boss and pocket wall, per side
edge_ch     = 0.4;    // chamfer on the pocket edge and the boss edge (no shearing)

// ---- plates
rows = 5;             // grid of pockets: rows x per_row
per_row = 5;          // 5 x 5 fits every copper piece of this layout (checked)
margin = 14;          // plate edge beyond the outer cell centres
plate_t = 6;          // plate thickness
pin_h = 3.0;          // locating pin above the die face
pin_clear = 0.3;      // pin is this much smaller than the punch hole

row_h    = pitch * sqrt(3) / 2;
// Pressed: the copper's underside lies on the die face, exactly as it will lie
// on the holder face; its underside in the pocket drops to the pocket floor =
// the cell top. The punch face sits on the copper (copper_t up), and the boss
// squeezes the copper onto the pocket floor: the same depth every time.
pocket_d = window_d - dish_clear;                 // die pocket = dish outside
pocket_h = dish_depth;
boss_d   = pocket_d - 2 * (copper_t + wall_clear);
boss_h   = dish_depth;                            // = pocket_h + copper_t - copper_t
pin_d    = punch_hole - pin_clear;
pin_hole = pin_d + 0.5;

$fn = 96;

function cells(r, n) = [for (j = [0 : r - 1], k = [0 : n - 1])
    [k * pitch + (j % 2) * pitch / 2, j * row_h]];

function size(r, n) = [(n - 1) * pitch + (r > 1 ? pitch / 2 : 0) + 2 * margin,
                       (r - 1) * row_h + 2 * margin];

module label(t, s = 4) {
    linear_extrude(0.6) text(t, size = s, font = "Liberation Sans:style=Bold", halign = "left", valign = "center");
}

module die(r, n) {
    sz = size(r, n);
    difference() {
        translate([-margin, -margin, 0]) cube([sz[0], sz[1], plate_t]);
        for (c = cells(r, n)) translate([c[0], c[1], plate_t - pocket_h]) {
            cylinder(d = pocket_d, h = pocket_h + 1);
            // chamfered pocket edge so the copper bends instead of shearing
            translate([0, 0, pocket_h - edge_ch])
                cylinder(d1 = pocket_d, d2 = pocket_d + 2 * edge_ch, h = edge_ch + 0.01);
        }
        if (r > 1) translate([-margin + 3, -margin + 2.5, plate_t - 0.6])
            label(str("DIE - copper cell side DOWN   t ", copper_t, "  dish ", dish_depth), 3.5);
    }
    // locating pins: through the punched hole in the copper, into the punch
    for (c = cells(r, n)) translate([c[0], c[1], plate_t - pocket_h]) {
        cylinder(d = pin_d, h = pocket_h + pin_h - 0.8);
        translate([0, 0, pocket_h + pin_h - 0.8]) cylinder(d1 = pin_d, d2 = pin_d - 1.6, h = 0.8);
    }
}

module punch(r, n) {
    sz = size(r, n);
    // printed bosses up; turn it over to use
    difference() {
        union() {
            translate([-margin, -margin, 0]) cube([sz[0], sz[1], plate_t]);
            for (c = cells(r, n)) translate([c[0], c[1], plate_t - 0.01]) {
                cylinder(d = boss_d, h = boss_h - edge_ch + 0.01);
                translate([0, 0, boss_h - edge_ch])
                    cylinder(d1 = boss_d, d2 = boss_d - 2 * edge_ch, h = edge_ch);
            }
        }
        for (c = cells(r, n)) translate([c[0], c[1], -1]) cylinder(d = pin_hole, h = plate_t + boss_h + 2);
        if (r > 1) translate([-margin + 3, -margin + 2.5, plate_t - 0.6])
            label("PUNCH - bosses DOWN onto the die", 3.5);
    }
}

if (part == "die") die(rows, per_row);
if (part == "punch") punch(rows, per_row);
if (part == "test_die") die(1, 1);
if (part == "test_punch") punch(1, 1);
if (part == "view") {          // die with a copper piece on it, punch lifted and turned over
    color("SteelBlue") die(rows, per_row);
    color("Peru") for (c = [[0, 0], [22.2, 0], [11.1, row_h], [33.3, row_h]])
        translate([c[0], c[1], plate_t + 6]) difference() {
            cylinder(d = 20, h = copper_t);
            translate([0, 0, -1]) cylinder(d = punch_hole, h = 2);
        }
    color("Orange") translate([0, 0, 2 * plate_t + 26]) mirror([0, 0, 1]) punch(rows, per_row);
}
