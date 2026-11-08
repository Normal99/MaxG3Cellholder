// Copper press: presses the copper down through the holder's welding window
// onto every cell, right on the pack. The holder itself is the die; nothing
// on the holder changes.
//
//   STENCIL     a guide grid that sits on the copper on the holder face. Its
//               skirt drops over the holder's side walls and ends, so every
//               hole sits exactly over a cell. Two halves (256 mm beds).
//   FAKE CELL   a double-ended plunger that slides snugly down a stencil
//               hole, with a FLAT stamp face on each end. The "-" end presses
//               a big 15.9 mm patch flat onto the negative end of the cell;
//               the "+" end presses a 12 mm patch flat onto the + cap only,
//               so the copper never comes down onto the crimp round it (that's
//               the can = negative). Both stamps stick out past the 0.6 mm
//               cell recess, so they bottom on the cell itself.
//
// Use: cells in, copper piece punched and laid in place, stencil on (skirt
// over the holder edges), a fake cell into every hole over the piece, then
// push each one down until it bottoms on the cell (thumb, or a flat board
// over all of them and a few mallet taps). Lift the stencil off.
//
// Parts (set `part`):  stencil_a, stencil_b   divider half / far-end half
//                      fake_cell              print ~9 (a piece has up to 8 cells), double ended
//                      stencil_test           corner tile, 4 cells, to try first
// Print as exported: stencils skirt-up (no supports), fake cell standing on its - end.

include <layout_data.scad>      // cell centres, chase slot (from generator/layout.py)

part = "stencil_a";

// ---- must match the holder as printed (cellholder.scad)
window_d    = 17.0;   // welding window in the holder face
cell_recess = 0.6;    // cell top below the holder face

// ---- press
copper_t    = 0.2;    // only sets clearances
punch_hole  = 8.0;    // hole punched in the copper over every cell (PUNCH_D)

// fake cell = double ended, a FLAT stamp face on each end (no recess, no
// hole: the copper must be pressed flat and evenly or the welds suffer).
// Over the punched 8 mm hole the flat face simply stays one copper thickness
// clear of the cell; it bears on the copper ring round the hole.
// Put the end that matches the cell end facing up into the stencil hole.
//   - end : the whole flat negative end of the cell: big stamp, the full window
//   + end : the raised + cap only, so the copper never comes down onto the
//           crimp/shoulder round it (that's the can = negative)
// Both stamps stick out further than the 0.6 mm the cells sit below the face,
// so the stamp always bottoms on the cell itself (copper squeezed flat onto
// it) instead of on a collar.
neg_tip_d   = window_d - 2 * copper_t - 0.7;   // 15.9: big flat patch on the - end
neg_tip_h   = 1.0;    // sticks out 1.0 (cells sit 0.6 down): always reaches the can
pos_tip_d   = 12.0;   // + stamp: inside the crimp (~14-15 mm on a 21700), well over the
                      // 8 mm punch hole. MEASURE the flat raised + area of your cell and
                      // use that diameter - 0.5 if it is smaller than 12.5
pos_tip_h   = 1.5;    // sticks out further: bottoms on the + cap
body_len    = 8;      // guided part each side (stencil is 6 thick)
grip_h      = 12;     // middle grip ring
hole_d      = 20.4;   // stencil hole (as printed - unchanged)
fake_fit    = 0.1;    // clearance per side in the stencil hole: snug, slides without play
body_d      = hole_d - 2 * fake_fit;   // 20.2
grip_d      = 21.6;   // grip ring (neighbouring fake cells are 22.2 apart)
mark_h      = 0.6;    // engraved + / - on the grip ring ends

T           = 6;      // stencil thickness = guided length
fit         = 0.3;    // skirt clearance to the holder walls, per side
skirt_t     = 2.4;
skirt_h     = 5;      // how far the skirt hangs down the holder walls (holder half = 9.6)
seam        = 0.5;    // gap between the two halves

$fn = 96;

slots = concat([for (c = cells) [c[0], c[1]]], [chase]);   // every cell + the chase slot

// stencil, modelled in use: holder face / copper top at z = 0, plate above,
// skirt hanging down the holder walls (both side walls and the far end in
// full; at the divider end only the two corners - the lead tongues and the
// BMS dock live there)
module stencil_full() {
    lo = -fit - skirt_t;
    difference() {
        union() {
            translate([0, lo, 0]) cube([pack_l - lo, pack_w - 2 * lo, T]);   // plate runs out over the skirts
            translate([0, lo, -skirt_h]) cube([pack_l, skirt_t, skirt_h + T]);                 // y = 0 wall
            translate([0, pack_w + fit, -skirt_h]) cube([pack_l, skirt_t, skirt_h + T]);       // y = W wall
            translate([pack_l + fit, lo, -skirt_h]) cube([skirt_t, pack_w - 2 * lo, skirt_h + T]);   // far end
            for (y = [lo, pack_w - 3]) translate([lo, y, -skirt_h]) cube([skirt_t, 3 - lo, skirt_h + T]);  // divider-end corners
            translate([lo, lo, 0]) cube([-lo + 0.01, pack_w - 2 * lo, T]);                        // ties the corners on
            for (x = [lo, pack_l]) for (y = [lo, pack_w]) translate([x, y, 0]) cube([-lo + 0.01, -lo, T]);
        }
        for (s = slots) translate([s[0], s[1], -1]) {
            cylinder(d = hole_d, h = T + 2);
            translate([0, 0, T + 1 - 0.6]) cylinder(d1 = hole_d, d2 = hole_d + 1.2, h = 0.61);   // lead-in
        }
    }
}

// the two halves split along the holder's own zig-zag seam (through cell
// centres, like holder_bottom_a / _b), so no thin slivers are left
// divider-end half in 2D: the seam polygon, carried on past both side walls
// (so each half keeps its own stretch of side skirt) and past the divider end
module region_a() {
    union() {
        polygon(split_a);
        translate([-50, pack_w - 0.01]) square([50 + split_a[1][0], 50]);                 // seam meets y = W here
        translate([-50, -50]) square([50 + split_a[len(split_a) - 2][0], 50.01]);         // seam meets y = 0 here
        translate([-50, -50]) square([50.01, pack_w + 100]);
    }
}

module half(which) {
    intersection() {
        stencil_full();
        translate([0, 0, -50]) linear_extrude(100)
            if (which == "a") offset(delta = -seam / 2) region_a();
            else offset(delta = -seam / 2) difference() { translate([-60, -60]) square([pack_l + 120, pack_w + 120]); region_a(); }
    }
}

// one end, modelled pointing down: flat stamp face at z = 0, tip_h tall,
// then the guided body
module stamp_end(tip_d, tip_h) {
    ch = 0.3;   // edge chamfer only - the face itself stays flat
    cylinder(d1 = tip_d - 2 * ch, d2 = tip_d, h = ch);
    translate([0, 0, ch]) cylinder(d = tip_d, h = tip_h - ch + 0.01);
    translate([0, 0, tip_h]) cylinder(d = body_d, h = body_len + 0.01);
}

module mark(m) {    // + or -, 4 mm, engraved
    linear_extrude(mark_h + 0.01) if (m == "+") { square([4, 1], center = true); square([1, 4], center = true); }
                                  else square([4, 1], center = true);
}

module fake_cell() {
    // printed standing on the - stamp: that face is on the bed, dead flat.
    // Use ironing (or a smooth top layer) for the + face on top.
    z_grip = neg_tip_h + body_len;
    z_top = z_grip + grip_h + body_len + pos_tip_h;
    difference() {
        union() {
            stamp_end(neg_tip_d, neg_tip_h);
            translate([0, 0, z_grip]) cylinder(d = grip_d, h = grip_h);
            translate([0, 0, z_top]) mirror([0, 0, 1]) stamp_end(pos_tip_d, pos_tip_h);
        }
        // big marks on the grip side (readable): + near the + end, - near the - end
        for (a = [0, 180]) rotate(a) {
            translate([grip_d / 2 - mark_h, 0, z_grip + grip_h * 0.75]) rotate([0, 90, 0]) mark("+");
            translate([grip_d / 2 - mark_h, 0, z_grip + grip_h * 0.25]) rotate([0, 90, 0]) mark("-");
        }
    }
}

// printable orientation: stencils upside down (top face on the bed, skirt up)
module print_flip() { translate([0, 0, T]) rotate([180, 0, 0]) children(); }

if (part == "stencil_a") print_flip() half("a");
if (part == "stencil_b") print_flip() half("b");
if (part == "stencil_test") print_flip() intersection() {   // corner tile: divider end, y = 0 side
    stencil_full();
    translate([-20, -20, -50]) cube([80, 86, 100]);
}
if (part == "fake_cell") fake_cell();
if (part == "view") {          // README render: holder face, copper, stencil, fake cells
    color("DimGray") translate([0, 0, -9.6]) cube([pack_l, pack_w, 9.6 - 0.05]);
    // from the exported STLs (previewing the intersections directly glitches)
    color("SteelBlue") rotate([180, 0, 0]) translate([0, 0, -T]) import("../stl/copper_press_stencil_a.stl");
    color("LightSteelBlue") rotate([180, 0, 0]) translate([0, 0, -T]) import("../stl/copper_press_stencil_b.stl");
    for (s = [slots[0], slots[1], slots[12], slots[23]]) color("Orange")
        translate([s[0], s[1], 25]) fake_cell();
}
