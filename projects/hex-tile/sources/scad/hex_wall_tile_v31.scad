// Hexagon wall tile v31 — parametric rebuild of v30
// Front: identical low-poly facets to v30 (same facet angles at every size).
// Edge profile: identical on every size (edge depth, rim width) so tiles butt flush.
// Back: six corner pads for 1" (25 mm) double-sided mounting tape.
// Prints upright on a flat edge with NO supports (all internal overhangs are 45° chamfers).
//
// Export one size at a time, e.g.:
//   openscad -D size_in=6 -o hex_tile_v31_6in.stl hex_wall_tile_v31.scad

/* [Size] */
size_in       = 6;      // point-to-point width in inches (3, 6, 10 ...)

/* [Edge profile — keep identical across sizes] */
edge_depth    = 3.6;    // depth of the outer edge, back plane to front face (mm)
rim           = 2.0;    // perimeter wall thickness at the back plane (mm)

/* [Front skin] */
skin          = 1.6;    // front skin thickness (mm) — 4 lines at 0.4 mm, same on all sizes

/* [Tape pads] */
tape_width    = 25.4;   // tape width (mm)
pad_margin    = 3;      // extra pad width beyond the tape (mm)
pad_max_frac  = 0.45;   // pad never larger than this fraction of the tile radius (keeps 3" usable)
pad_plate     = 1.2;    // thickness of the flat pad face (mm)
pad_wall      = 0.8;    // pad side-wall thickness (mm)
pad_recess    = 0.5;    // pads sit this far behind the rim so the rim meets the wall
                        // (use 0 for very thin tape; foam tape is ~1–1.6 mm)

/* [Output] */
orient_for_print = true; // stand upright on a flat edge, back facing +Y

/* [Hidden] */
R   = size_in * 25.4 / 2;         // corner radius
AP  = R * cos(30);                // apothem
PAD = min(tape_width + pad_margin, R * pad_max_frac);

// Normalised front geometry from v30 (x, y in units of R; z = relief above edge, units of R)
FP = [[1,0,0],[0.5,0.866025,0],[-0.5,0.866025,0],[-1,0,0],[-0.5,-0.866025,0],[0.5,-0.866025,0],
      [0.16,0.05,0.091654],[-0.16,-0.38,0.019428],[-0.36,0.18,0.05579],[0.34,-0.28,0.053795],[0.02,0.46,0.061766]];
FACES = [[0,6,1],[4,3,7],[5,4,7],[8,3,2],[7,3,8],[7,8,6],[5,9,0],[9,6,0],[9,7,6],[5,7,9],
         [6,8,10],[8,2,10],[6,10,1],[10,2,1],
         [1,12,11,0],[2,13,12,1],[3,14,13,2],[4,15,14,3],[5,16,15,4],[0,11,16,5],
         [11,12,13,14,15,16]];
RELIEF_MAX = 0.091654 * R;
D = edge_depth + RELIEF_MAX + 1;  // max depth used for chamfers

// Solid bounded by the faceted front (shifted by dz) and a flat back at z = zb
module body(dz = 0, zb = 0) {
    pts = concat(
        [for (p = FP) [p[0]*R, p[1]*R, edge_depth + p[2]*R + dz]],
        [for (i = [0:5]) [FP[i][0]*R, FP[i][1]*R, zb]]);
    polyhedron(points = pts, faces = FACES, convexity = 4);
}

module hex2d(apothem) { circle(r = apothem / cos(30), $fn = 6); }

// Back cavity: behind the skin, inside the rim; rim inner faces slope 45° so nothing needs support
module cavity(extra = 0) {
    H  = D + 2;
    a0 = AP - rim - extra + 1;             // apothem at z = -1
    intersection() {
        body(dz = -skin - extra, zb = -1);
        translate([0, 0, -1]) linear_extrude(height = H, scale = (a0 - H) / a0) hex2d(a0);
    }
}

// Corner pad footprint (2D), k = corner index 0..5
module pad_fp(k) {
    U0 = R - rim / sin(60);                // inner corner distance from centre
    uo = U0 - PAD / (2 * sqrt(3)) - 0.5;   // outer edge of the square
    intersection() {
        hex2d(AP - rim);
        rotate(60 * k) hull() {
            translate([uo - PAD, -PAD / 2]) square([PAD, PAD]);
            translate([U0 - 0.01, 0]) circle(r = 0.01, $fn = 8);
        }
    }
}

// Sweep a footprint from the back plane toward the front, sliding 1:1 "down" (−Y) → 45° undersides
module chamfer_sweep(z0) {
    hull() {
        translate([0, 0, z0]) linear_extrude(0.01) children();
        translate([0, -D, z0 + D]) linear_extrude(0.01) children();
    }
}

module pads() {
    for (k = [0:5]) difference() {
        intersection() { body(); chamfer_sweep(pad_recess) pad_fp(k); }
        intersection() { cavity(pad_wall); chamfer_sweep(pad_recess + pad_plate) offset(delta = -pad_wall) pad_fp(k); }
    }
}

module tile() {
    union() {
        difference() { body(); cavity(); }
        pads();
    }
}

if (orient_for_print)
    translate([0, 0, AP]) rotate([90, 0, 0]) tile();
else
    tile();
