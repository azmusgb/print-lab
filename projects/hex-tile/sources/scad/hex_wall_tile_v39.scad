// Hexagon wall tile v39 — parametric rebuild of v30
// Front: identical low-poly facets to v30 (same facet angles at every size).
// Edge profile: identical on every size (edge depth, rim width) so tiles butt flush.
// Back: six corner pads for 1" (25 mm) double-sided mounting tape.
// v32: tape pads are flat plates hung from the rim with an air gap to the front skin.
// v33: thinner skin + thinner pads so the air gap is 1.4 mm even right at the edges
//      (v32 had only 0.8 mm there and showed marks along the slanted edges).
// v34: snap-off stabilizer fins behind the bottom edge so the tall, thin tile can't tip over
//      while printing. Break them off afterwards (bend sideways) and the back stays flat.
// v35: 0.6 mm 45° chamfer on the front edge (crisp, consistent shadow line between tiles; hides
//      first-layer squish and brim trim marks) + relief_scale to deepen the facets if wanted.
// v37: much smaller breakaway tabs (0.8 x 0.6 mm, every 8 mm) so the fins snap off easily.
// v38: full-height snap-off BRACE FRAME behind the tile: a thin hex ring + X/vertical bars,
//      1 mm behind the back, tied to the tile rim by tiny tabs all the way round (incl. the top).
//      Tile + brace act as a stiff box while printing; the fins now sit on the brace.
//      Peel the brace off after printing — the tabs only touch the back rim.
// v39: PAIR mode (default): two identical tiles printed back-to-back, 0.4 mm apart, so each
//      cradles the other full-height. Only 12 tiny tabs (corners + mid-sides) join the back
//      rims — twist/peel the tiles apart. No brace, no fins, almost no waste. The pair is
//      turned 90° on the bed so the 'back' seam lands on a side edge, not on either face.
// Prints upright on a flat edge with NO supports (every downward edge is 45° or steeper).
//
// Export one size at a time, e.g.:
//   openscad -D size_in=6 -o hex_pair_v39_6in.stl hex_wall_tile_v39.scad

/* [Size] */
size_in       = 6;      // point-to-point width in inches (3, 6, 10 ...)

/* [Edge profile — keep identical across sizes] */
// Space behind the skin at the edge = edge_depth - skin; it must be >= pad_plate + pad_gap + pad_recess.
edge_depth    = 3.6;    // depth of the outer edge, back plane to front face (mm)
rim           = 2.0;    // perimeter wall thickness at the back plane (mm)
front_chamfer = 0.6;    // 45° chamfer on the front edge (mm); 0 = sharp edge

/* [Look] */
relief_scale  = 1.0;    // 1.0 = v30 facets; 1.5 = 50% deeper facets (same edge profile on all sizes)

/* [Front skin] */
skin          = 1.2;    // front skin thickness (mm) — 3 lines at 0.4 mm, same on all sizes

/* [Tape pads] */
tape_width    = 25.4;   // tape width (mm)
pad_margin    = 3;      // extra pad width beyond the tape (mm)
pad_max_frac  = 0.45;   // pad never larger than this fraction of the tile radius (keeps 3" usable)
pad_plate     = 1.0;    // thickness of the pad plates (mm)
pad_gap       = 1.4;    // minimum air gap between pads and the front skin (mm) — keeps the front clean
pad_recess    = 0;      // pads set back from the rim (mm); >0 lets the rim touch the wall,
                        // but near the edges the plate is then trimmed thinner to keep pad_gap

/* [Print stabilizers (snap off after printing)] */
stabilizers   = false;  // v34-v38 option; not needed in pair mode
fin_count     = 2;      // fins behind the bottom edge, placed symmetrically
fin_thick     = 1.6;    // fin thickness (mm)
fin_height_frac = 0.35; // fin height as a fraction of the tile height
fin_depth_frac  = 0.4;  // fin depth behind the brace as a fraction of fin height
fin_depth_min   = 15;   // (mm)
fin_gap       = 0.5;    // air gap between fin and tile back (mm)
tab_height    = 0.6;    // breakaway tab height (mm, vertical when printing) — 3 layers at 0.2
tab_width     = 0.8;    // breakaway tab width (mm), centred on the fin — 2 lines
tab_pitch     = 8;      // spacing between tabs (mm)

/* [Full-height brace frame (snap off after printing)] */
brace         = false;  // v38 option; not needed in pair mode
brace_gap     = 1.0;    // air gap between tile back and brace (mm)
brace_thick   = 1.6;    // brace thickness (mm)
brace_rim_w   = 4;      // width of the brace's hex ring (mm)
brace_bar_w   = 3;      // width of the X and vertical bars (mm)
brace_tab_pitch = 10;   // spacing of brace tabs along each rim side (mm)
brace_tab     = 0.8;    // brace tab size (mm) — tiny, so the brace peels off

/* [Back-to-back pair (default)] */
pair          = true;
pair_gap      = 0.4;    // gap between the two back planes (mm): close enough to cradle, not fused
pair_tab      = 0.6;    // tab size (mm) — 12 tabs total, tiny so the pair twists apart

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
RELIEF_MAX = 0.091654 * R * relief_scale;
D = edge_depth + RELIEF_MAX + 1;  // max depth used for chamfers

// Solid bounded by the faceted front (shifted by dz) and a flat back at z = zb
module body(dz = 0, zb = 0) {
    pts = concat(
        [for (p = FP) [p[0]*R, p[1]*R, edge_depth + p[2]*R*relief_scale + dz]],
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

// Corner pad footprint (2D), k = corner index 0..5:
// the corner region of the inner hex, PAD wide, long enough to hold a PAD x PAD square of tape
module pad_core(k) {
    U0  = (AP - rim) / cos(30);                    // inner corner distance from centre
    LEN = PAD / (2 * tan(60)) + PAD + 1;           // apex taper + full square + margin
    intersection() {
        hex2d(AP - rim + 0.3);                     // overlap 0.3 mm into the rim to fuse
        rotate(60 * k) translate([U0 - LEN, -PAD / 2]) square([LEN + 5, PAD]);
    }
}

// In-plane self-support: printed upright, a vertical plate needs every downward edge at >= 45°.
// Sweep each pad toward the nearest rim side below it at 45° (or straight down for bottom corners).
SWEEP = [[1, -1], [1, -1], [-1, -1], [-1, -1], [0, -1], [0, -1]];
module pad_fp(k) {
    intersection() {
        hex2d(AP - rim + 0.3);
        hull() { pad_core(k); translate(SWEEP[k] * R) pad_core(k); }
    }
}

module pads() {
    intersection() {
        body(dz = -skin - pad_gap, zb = -1);       // never closer than pad_gap to the skin
        translate([0, 0, pad_recess]) linear_extrude(pad_plate) for (k = [0:5]) pad_fp(k);
    }
}

module chamfer_clip() {
    HB = D + 5;
    union() {
        translate([0, 0, -2]) linear_extrude(edge_depth - front_chamfer + 2) hex2d(AP + 1);
        translate([0, 0, edge_depth - front_chamfer]) linear_extrude(height = HB, scale = (AP - HB) / AP) hex2d(AP);
    }
}

module tile() {
    intersection() {
        union() {
            difference() { body(); cavity(); }
            pads();
        }
        if (front_chamfer > 0) chamfer_clip(); else translate([-2*R, -2*R, -5]) cube([4*R, 4*R, 4*R]);
    }
}

// Triangular fins standing on the bed behind the back (model z < 0), joined to the tile by small tabs
FIN_H = fin_height_frac * 2 * AP;
FIN_L = max(fin_depth_min, fin_depth_frac * FIN_H);
function fin_x(i) = (fin_count == 1) ? 0 : (-1 + 2 * i / (fin_count - 1)) * 0.35 * R;
BZ = brace ? brace_gap + brace_thick : 0;          // fins start behind the brace when it is used
module stabilizer_fins() {
    for (i = [0 : fin_count - 1]) {
        x = fin_x(i);
        fg = brace ? BZ - 0.3 : fin_gap;                // with a brace: fused into it (no tabs needed)
        hull() {                                            // fin: vertical triangle
            translate([x - fin_thick/2, -AP, -fg - FIN_L]) cube([fin_thick, 0.01, FIN_L]);
            translate([x - fin_thick/2, -AP, -fg - 0.01]) cube([fin_thick, FIN_H, 0.01]);
        }
        if (!brace)
            for (y = [0 : tab_pitch : FIN_H - tab_height])  // breakaway tabs into the back plane
                translate([x - tab_width/2, -AP + y, -fin_gap - 0.05]) cube([tab_width, tab_height, fin_gap + 0.35]);
    }
}

// Brace frame (2D, in the tile plane). Printed upright, so every downward-facing edge is >= 45°:
// the top bar is carried by 45° roofs in the two top windows; bars run vertical or at ±60°.
module brace_2d() {
    W  = brace_rim_w;
    Yt = AP - W;                                        // underside of the top ring bar
    difference() {
        hex2d(AP);
        intersection() {                                // the open window, with a 45° roof under the top bar
            hex2d(AP - W);
            // only the two top windows touch the top bar: give them a 45° valley roof
            polygon([[-2*R, -2*R], [2*R, -2*R], [2*R, 2*R], [R/2, 2*R], [R/2, Yt],
                     [0, Yt - R/2], [-R/2, Yt], [-R/2, 2*R], [-2*R, 2*R]]);
        }
    }
    intersection() {
        hex2d(AP);
        union() {
            square([brace_bar_w, 2*AP], center = true);                 // vertical bar
            rotate(60)  square([4*R, brace_bar_w], center = true);      // ±60° diagonals (corner to corner)
            rotate(-60) square([4*R, brace_bar_w], center = true);
        }
    }
}

module brace_frame() {
    translate([0, 0, -BZ]) linear_extrude(brace_thick) brace_2d();
    // tiny tabs across the gap, on the tile's back rim (1 mm in from the outline), all six sides
    for (k = [0:5]) {
        a0 = 60*k; a1 = 60*(k+1);
        p0 = [ (R - 1/sin(60)) * cos(a0), (R - 1/sin(60)) * sin(a0) ];
        p1 = [ (R - 1/sin(60)) * cos(a1), (R - 1/sin(60)) * sin(a1) ];
        L  = norm(p1 - p0);
        n  = floor((L - 6) / brace_tab_pitch);
        for (j = [0 : n]) {
            t = (3 + j * (L - 6) / max(n, 1)) / L;
            p = p0 + t * (p1 - p0);
            translate([p[0], p[1], -brace_gap - 0.3]) rotate(a0 + 120)
                translate([-brace_tab/2, -brace_tab/2, 0]) cube([brace_tab, brace_tab, brace_gap + 0.6]);
        }
    }
}

// 12 tabs across the pair gap: at each rim corner and each rim mid-side (1 mm in from the outline)
module pair_tabs() {
    rr = R - 1/sin(60);
    for (k = [0:5]) for (f = [0.12, 0.5, 0.88]) if (f == 0.5 || f == 0.12) {
        a0 = 60*k; a1 = 60*(k+1);
        p = [rr*cos(a0), rr*sin(a0)] + f * ([rr*cos(a1), rr*sin(a1)] - [rr*cos(a0), rr*sin(a0)]);
        translate([p[0], p[1], -pair_gap - 0.3]) rotate(a0 + 120)
            translate([-pair_tab/2, -pair_tab/2, 0]) cube([pair_tab, pair_tab, pair_gap + 0.6]);
    }
}
module partner() { translate([0, 0, -pair_gap]) rotate([0, 180, 0]) tile(); }   // same tile turned round, not mirrored

module assembly() {
    tile();
    if (pair) { partner(); pair_tabs(); }
    else { if (brace) brace_frame(); if (stabilizers) stabilizer_fins(); }
}

if (orient_for_print)
    rotate([0, 0, pair ? 90 : 0]) translate([0, 0, AP]) rotate([90, 0, 0]) assembly();
else
    assembly();
