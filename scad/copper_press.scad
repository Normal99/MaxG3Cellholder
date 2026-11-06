// Copper press: presses the copper down through the holder's welding window
// onto every cell, right on the pack. The holder itself is the die; nothing
// on the holder changes.
//
//   STENCIL     a guide grid that sits on the copper on the holder face. Its
//               skirt drops over the holder's side walls and ends, so every
//               hole sits exactly over a cell. Two halves (256 mm beds).
//   FAKE CELL   a plunger the size of a cell end. It slides down a stencil
//               hole and pushes the copper through the 17 mm window onto the
//               cell. Its collar lands on the stencil at exactly the right
//               depth: you can't over-press, and the copper thickness doesn't
//               matter (the stencil sits on the copper, the plunger's shoulder
//               lands on the copper too).
//
// Use: cells in, copper piece punched and laid in place, stencil on (skirt
// over the holder edges), a fake cell into every hole over the piece, then
// push each one down until its collar sits on the stencil (thumb, or a flat
// board over all of them and a few mallet taps). Lift the stencil off.
//
// Parts (set `part`):  stencil_a, stencil_b   divider half / far-end half
//                      fake_cell              print ~9 (a piece has up to 8 cells)
//                      stencil_test           corner tile, 4 cells, to try first
// Print as exported: stencils skirt-up (no supports), fake cell tip-down.

include <layout_data.scad>      // cell centres, chase slot (from generator/layout.py)

part = "stencil_a";

// ---- must match the holder as printed (cellholder.scad)
window_d    = 17.0;   // welding window in the holder face
cell_recess = 0.6;    // cell top below the holder face

// ---- press
dish_depth  = cell_recess;  // how far the copper is pushed down (raise ~0.1 if it springs back)
copper_t    = 0.2;    // only sets the tip clearance in the window
tip_d       = window_d - 2 * copper_t - 0.7;   // plunger tip, inside the window with the copper
body_d      = 20.0;   // plunger body (guided by the stencil hole)
hole_d      = body_d + 0.4;
collar_d    = 21.6;   // depth stop on the stencil (neighbours are 22.2 apart)
collar_h    = 3;
knob_d      = 12;
knob_h      = 10;
sight_d     = 9;      // look-through hole: the punched 8 mm hole must be centred in it

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

module fake_cell() {
    // modelled tip down: tip from z = 0, shoulder at dish_depth, collar at
    // dish_depth + T (lands on the stencil top at full depth)
    difference() {
        union() {
            ch = 0.3;
            cylinder(d1 = tip_d - 2 * ch, d2 = tip_d, h = ch);
            translate([0, 0, ch]) cylinder(d = tip_d, h = dish_depth - ch + 0.01);
            translate([0, 0, dish_depth]) cylinder(d = body_d, h = T);
            translate([0, 0, dish_depth + T]) cylinder(d = collar_d, h = collar_h);
            translate([0, 0, dish_depth + T + collar_h]) cylinder(d = knob_d, h = knob_h);
        }
        translate([0, 0, -1]) cylinder(d = sight_d, h = 100);
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
