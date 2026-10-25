// Hexagon wall tile v54 — parametric rebuild of v30
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
// v40: pair tabs spaced evenly every ~pair_tab_pitch mm round the rim on EVERY size. In v39 the
//      tab spacing grew with the tile (3": ~23 mm max gap, 6": ~46 mm, 10": ~79 mm), so the 3" pair
//      printed perfectly but the 6" rims flexed apart between tabs and broke up above mid-height.
//      Now every size has the same tab spacing as a stiff 3" pair (or tighter).
// v42: tabs replaced by one continuous hairline SEAM round the outer edge of the pair gap.
//      Discrete tabs changed the toolpath on every layer that had a tab, leaving a faint line
//      across the tile every ~10 mm of height. With a continuous seam every layer has the same
//      shape, so there is nothing to print differently. Separate the tiles by running a utility
//      knife along the seam line on the edges, then twist apart.
// v43: stiffer tape pads — each pad now grows from the back plane toward the front until it is
//      pad_gap (1.4 mm) from the skin, instead of being a 1 mm plate (the skin stays untouched, so
//      no ghost lines). Larger tiles (>= mid_pad_min_in)
//      get four extra pads at the slanted mid-edges: 10 tape spots on the 10".
// v44: UNIFORM pads. Every pad is the same PAD x PAD tape square, pushed snug into its corner
//      (touching both rims), with only a small 45° gusset beneath it down to the rim so it prints
//      without support. Because a hex corner is the same angle at every size, the 6" and 10" pads
//      are identical in shape and size; the 3" uses the same layout with smaller squares.
//      The 10" adds the same square at the middle of each slanted edge.
// v46: pads are a 1 mm plate with a stiffening LIP round the free edges (like a shallow tray),
//      instead of solid-filled — nearly the stiffness of v44's deep pads at close to v42 print time.
// v47: pair gap 0.4 -> 1.0 mm. At 0.4 mm the squashed back walls of the two tiles touched and
//      fused, so v42-v46 pairs would not come apart. At 1.0 mm only the hairline edge seam joins
//      them: cut it with a utility knife (there is now room for the blade) and they separate.
// v48: seam only on the four SLANTED edges. The top and bottom flat edges are left open (a 1 mm
//      slot), so a putty knife / flat screwdriver can go in and pry the pair open, unzipping the
//      seam. Every layer still crosses the seam at both ends, so the layer shape stays constant.
// v49: "KISS" seam — the seam is printed on ONE tile only and stops seam_kiss short of the other
//      tile's back. The two tiles are never one solid: they only touch where the plastic squashes
//      out, which tacks them lightly (enough to steady them while printing, weak enough to snap by
//      hand). Set seam_kiss = 0 to go back to the fused v48 seam.
// v50: (1) every tape pad gets a 45° pointed top, so pads taper out over many layers instead of
//      ending on one layer. Abrupt pad ends changed the layer time suddenly and left a line across
//      the face (seen at ~14% and ~36% height on the 10").
//      (2) the stiffening lips stay lip_gap (2.5 mm) clear of the skin, not 1.4: near the edges the
//      lips were hugging the skin and ghosting through as ridges parallel to the edge.
// v51: STIFFER, LARGER TAPE PADS without touching the front edge profile:
//      - each tape SQUARE stands pad_proud (1.2 mm) proud of the back rim, so where the tape goes
//        the pad is ~2.2 mm thick (was 1 mm) — roughly 8-10x stiffer. The tile sits on its pads;
//        the rim floats ~1.2 mm + tape thickness off the wall. Support webs stay thin (print time).
//      - pads 30 mm square (fit 1" tape with margin), with a shallow 30° roof instead of a point.
//      - front kept cleaner: pads now stay pad_gap = 1.6 mm from the skin; no lips.
//      - pair gap grows to keep 1 mm between the two tiles' proud pads.
//      - seam now starts right at the bottom corners (no cantilevered start); pry slot along the top.
// v53: seam is FUSED (one printed line) on the two upper slanted edges and stays a light-contact
//      kiss seam on the lower two. The top half is where the pair wobbled (ripples near the top
//      corners); the switch happens at mid-height, where the hex corners already turn.
//      Separate: knife in the top slot, run down both upper edges, twist apart.
// v54: tape squares 0.6 mm proud (was 1.2): ~1.6 mm thick, still ~4x stiffer than v50's 1 mm
//      plates, and about 1 hour less on a 10" pair. Print time goes to the face instead.
// Prints upright on a flat edge with NO supports (every downward edge is 45° or steeper).
//
// Export one size at a time, e.g.:
//   openscad -D size_in=6 -o hex_pair_v54_6in.stl hex_wall_tile_v54.scad

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
pad_margin    = 5;      // extra pad width beyond the tape (mm) -> 30.4 mm pads
pad_max_frac  = 0.45;   // pad never larger than this fraction of the tile radius (keeps 3" usable)
pad_plate     = 1.0;    // pad thickness in front of the back plane (mm), less where the skin is close
pad_proud     = 0.6;    // pads stand this far behind the back rim (mm) -> extra stiffness, no effect on the front
roof_angle    = 30;     // slope of the pad tops (deg) — tapers the pad end over several mm of height
pad_depth     = 0;         // stiffening lip depth (mm); always stops pad_gap from the skin
lip_gap       = 2.5;    // lips stop this far from the skin (plates keep pad_gap)
pad_lip       = 0.9;    // lip thickness (mm) — two lines
mid_pad_min_in = 8;     // tiles this size or larger also get pads at the four slanted mid-edges
pad_gap       = 1.6;    // minimum air gap between pads and the front skin (mm) — keeps the front clean
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
pad_clear     = 1.0;    // air between the two tiles' proud pads (mm)
pair_gap      = pad_clear + 2*pad_proud;   // gap between the two back planes (mm)
pair_tab      = 0.6;    // tab size (mm) — tiny, so the pair twists apart
pair_tab_pitch = 12;    // (v40 tabs, unused when pair_seam_w > 0)
pair_seam_w   = 0.45;   // width of the continuous edge seam bridging the gap (mm) — about one line
seam_kiss     = 0.15;   // gap between the seam tip and the other tile (mm); 0 = fused seam
upper_fused   = true;   // v53: fuse the seam on the two upper slanted edges only
seam_open     = 3;      // leave the seam off this far from the top and bottom flat edges (mm) -> pry slots

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

// ---- Uniform tape pads ----------------------------------------------------------------
PA = AP - rim + 0.3;                    // inner apothem used for pads (0.3 mm overlap fuses them to the rim)
PH = PAD / 2;
function nrm(a) = [cos(a), sin(a)];
function lim(a) = PA - PH * (abs(cos(a)) + abs(sin(a)));     // max n.c for an axis-aligned PAD square
// centre of a PAD square snug in the corner at angle t (touches the two rims meeting there)
function corner_c(t) = let(n1 = nrm(t - 30), n2 = nrm(t + 30), b1 = lim(t - 30), b2 = lim(t + 30), d = sin(60))
    [(b1*n2[1] - b2*n1[1]) / d, (n1[0]*b2 - n2[0]*b1) / d];
// centre of a PAD square snug against the middle of the edge whose normal is at angle a
function edge_c(a) = lim(a) * nrm(a);
// downward 45° (or vertical) gusset direction toward the nearest rim below — printed upright, model -y is down
function gdir(t) = (cos(t) > 0.1) ? [1, -1] : (cos(t) < -0.1) ? [-1, -1] : [0, -1];

module pad_sq(c, dir) {
    intersection() {
        hex2d(PA);
        hull() {
            translate(c) square(PAD, center = true);
            translate(c + [0, PAD/2 + PAD/2*tan(roof_angle)]) square(0.01, center = true);   // shallow roof
            translate(c + dir * R) square(PAD, center = true);
        }
    }
}
module pad_fp(k)  { t = 60*k;      pad_sq(corner_c(t), (k == 4 || k == 5) ? [0, -1] : gdir(t)); }
module mid_fp(k)  { a = 30 + 60*k; pad_sq(edge_c(a),   (k == 3 || k == 5) ? [0, -1] : gdir(a)); }

module pad_fps() {
    for (k = [0:5]) pad_fp(k);
    if (size_in >= mid_pad_min_in) for (k = [0, 2, 3, 5]) mid_fp(k);
}
// proud part of one tape square: only the square itself (not its support web), with a 45° ramp
// at its lower edge so, printed upright, it grows out of the plate instead of starting as a ledge
module proud_sq(c) {
    intersection() {
        translate([0, 0, -pad_proud]) linear_extrude(pad_proud + 0.01)
            intersection() {
                hex2d(PA);
                hull() { translate(c) square(PAD, center = true);
                         translate(c + [0, PAD/2 + PAD/2*tan(roof_angle)]) square(0.01, center = true); }
            }
        translate([0, c[1] - PAD/2, 0])
            multmatrix([[1,0,0,0],[0,1,-1,0],[0,0,1,0]]) translate([-2*R, 0, -5]) cube([4*R, 4*R, 10]);
    }
}
module pads() {
    intersection() {                                       // tape plate in front of the back plane, pad_gap from the skin
        body(dz = -skin - pad_gap, zb = -1);
        linear_extrude(pad_plate) pad_fps();
    }
    for (k = [0:5]) proud_sq(corner_c(60*k));              // stiff proud tape squares behind it
    if (size_in >= mid_pad_min_in) for (k = [0, 2, 3, 5]) proud_sq(edge_c(30 + 60*k));
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

// Tabs across the pair gap, evenly spaced along each rim side (1 mm in from the outline)
module pair_tabs() {
    rr = R - 1/sin(60);
    n  = max(2, ceil(rr / pair_tab_pitch));          // side length = rr
    for (k = [0:5]) for (i = [0:n-1]) {
        f  = (i + 0.5) / n;
        a0 = 60*k; a1 = 60*(k+1);
        p = [rr*cos(a0), rr*sin(a0)] + f * ([rr*cos(a1), rr*sin(a1)] - [rr*cos(a0), rr*sin(a0)]);
        translate([p[0], p[1], -pair_gap - 0.3]) rotate(a0 + 120)
            translate([-pair_tab/2, -pair_tab/2, 0]) cube([pair_tab, pair_tab, pair_gap + 0.6]);
    }
}
// Continuous hairline seam round the outline, bridging the gap between the two back planes
// Seam strip along the slanted edges, between z0 (partner side) and +0.3 (into this tile)
module seam_strip(z0, ylo, yhi) {
    translate([0, 0, z0]) linear_extrude(0.3 - z0)
        intersection() {
            difference() { hex2d(AP); hex2d(AP - pair_seam_w); }
            translate([-2*R, ylo]) square([4*R, yhi - ylo]);
        }
}
module pair_seam() {
    ybot = -AP + pair_seam_w + 0.05;       // just off the bed (bottom corners)
    ytop =  AP - seam_open;                // top pry slot
    // lower half: light-contact "kiss" seam (stops seam_kiss short of the partner)
    seam_strip((seam_kiss > 0) ? -pair_gap + seam_kiss : -pair_gap - 0.3, ybot, 0);
    // upper half: fused hairline seam (one printed line) — braces the top, where the pair wobbles
    seam_strip(upper_fused ? -pair_gap - 0.3 : -pair_gap + seam_kiss, 0, ytop);
}
module partner() { translate([0, 0, -pair_gap]) rotate([0, 180, 0]) tile(); }   // same tile turned round, not mirrored

module assembly() {
    tile();
    if (pair) { partner(); if (pair_seam_w > 0) pair_seam(); else pair_tabs(); }
    else { if (brace) brace_frame(); if (stabilizers) stabilizer_fins(); }
}

if (orient_for_print)
    rotate([0, 0, pair ? 90 : 0]) translate([0, 0, AP]) rotate([90, 0, 0]) assembly();
else
    assembly();
