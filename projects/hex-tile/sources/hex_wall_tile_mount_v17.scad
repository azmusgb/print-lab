/*
    parametric_faceted_hex_wall_tile_mount_v17.scad
    ------------------------------------------------------------
    Parametric asymmetric low-poly hex wall tile with a truly
    open back and integrated flat double-stick-tape mounting pads.

    Design intent
    -------------
    * The rear of the tile is completely OPEN - no floor plate.
    * Four flat mounting pads sit flush on Z = 0 (the wall plane)
      and rise INTO the hollow interior.
    * Each pad tucks UNDER the inner perimeter shell, so the
      pad-to-shell joint is strong enough to hang the tile.
    * The front is a triangulated low-poly relief with one sharp
      peak (P) and one secondary ridge (Q), both placed at
      user-controlled angles and radial distances.

    Geometry notes
    --------------
    * The outline is a REGULAR POINT-UP hexagon: vertices at
      30, 90, 150, 210, 270, 330 degrees. All six sides are equal,
      all six interior angles are 120 degrees.
    * flat-to-flat  = 2 * circumradius * cos(30)
    * across-corners = 2 * circumradius

    v17 fixes
    ---------
    1. ALL parameters are declared at the top of the file, before
       any computed values. OpenSCAD's Customizer stops scanning
       for parameters at the first non-parameter statement, so
       parameters must come first or the Customizer won't show
       them.
    2. Shell thickness is resolved BEFORE tile dimensions that
       depend on it (OpenSCAD is strictly top-to-bottom).
    3. All assert() messages are single-line strings (OpenSCAD
       does not concatenate adjacent string literals).
    4. Sanity-check echoes confirm the hexagon is regular.

    Export
    ------
        F6 render
        File -> Export -> Export as STL

    Coordinate conventions
    ----------------------
        Z = 0        wall-facing plane (rear face of the tile)
        +Z           away from the wall (front of the tile)
        0 deg        +X axis
        angles CCW   in the XY plane

    Shell polyhedron vertex layout
    ------------------------------
        0..5      outer rear  perimeter   (Z = 0)
        6..11     outer roof  perimeter   (Z = edge_height)
        12        outer peak       P
        13        outer ridge      Q
        14..19    inner rear  perimeter   (Z = 0)
        20..25    inner roof  perimeter   (Z = edge - skin)
        26        inner peak       P
        27        inner ridge      Q
*/

// =============================================================================
// PARAMETERS
// (Everything the OpenSCAD Customizer should see must live in this region,
//  and nothing computed may appear between parameters.)
// =============================================================================

/* [Tile Size] */

// Which measurement tile_size represents.
//   flat_to_flat    distance between opposite flat sides (horizontal)
//   across_corners  distance between opposite vertices
size_reference = "flat_to_flat";  // [flat_to_flat, across_corners]

// Units that tile_size is expressed in.
size_units = "mm";  // [mm, in]

// The measurement of the tile along the chosen reference.
//   mm examples:  152.4 (6"), 203.2 (8"), 228.6 (9"), 254.0 (10")
//   in examples:  6, 8, 9, 10
tile_size = 228.6;

// Rotate the whole finished tile around Z.
tile_rotation_deg = 0;

/* [Front Relief - Mode] */

// How the three relief heights are determined.
//   proportional : heights scale with tile size (using the ratios below)
//   absolute     : heights use the exact mm values below
relief_height_mode = "proportional";  // [proportional, absolute]

// Multiplier applied to whichever relief mode is active.
//   0.5  subtle      1.0  as specified      1.5  dramatic
relief_scale = 1.0;

/* [Front Relief - Proportional] */

// Peak height as a fraction of flat-to-flat.
//   0.040  subtle      0.081  recommended      0.120  dramatic
peak_height_ratio = 0.081;

// Ridge height as a fraction of peak height.
ridge_to_peak_ratio = 0.757;

// Edge height as a fraction of peak height.
edge_to_peak_ratio = 0.097;

/* [Front Relief - Absolute] */

// Used only when relief_height_mode = absolute.
peak_height_mm  = 18.5;
ridge_height_mm = 14.0;
edge_height_mm  = 1.8;

/* [Shell Thickness] */

// Preset shell thicknesses. Choose "custom" to use the two mm values below.
shell_preset = "custom";  // [custom, light, standard, heavy]

// Custom roof skin thickness (mm).
roof_skin_thickness_mm = 0.90;

// Custom perimeter wall thickness (mm).
perimeter_wall_thickness_mm = 1.40;

/* [Facet Layout] */

// Direction of the main peak, CCW from +X.
//
//          90
//           |
//     180 --+-- 0
//           |
//          270
peak_angle_deg = 45;

// Peak distance from center, as a fraction of circumradius.
//   0.20 broad      0.38 recommended      0.50 sharp
peak_radius_ratio = 0.38;

// Direction of the secondary ridge, CCW from +X.
ridge_angle_deg = 208;

// Ridge distance from center, as a fraction of circumradius.
ridge_radius_ratio = 0.34;

/* [Wall Mounting] */

// Enable the four integrated double-stick-tape mounting pads.
add_mount_pads = true;

// Pad width across the flat side (mm).
mount_pad_width = 38.0;

// How far each pad extends inward (mm).
mount_pad_depth = 22.0;

// Pad thickness, rising into the cavity (mm).
// The rear of the pad remains flush at Z = 0.
mount_pad_thickness = 1.60;

// How far each pad tucks under the inner perimeter shell (mm).
// 3-5 mm gives a strong pad-to-shell joint.
mount_pad_overlap = 4.0;

// Directions of the four pads. One per flat side of the hex.
mount_pad_angles = [60, 120, 240, 300];

/* [Optional Screw Holes] */

// Drill a clearance hole through each mounting pad.
add_pad_screw_holes = false;

// Screw clearance diameter (mm).  3.5 = #6,  4.5 = #8.
pad_screw_hole_diameter = 4.5;

/* [Advanced] */

// Convexity hint for the shell polyhedron. Increase if the preview
// shows rendering artifacts.
polyhedron_convexity = 10;

// =============================================================================
// DERIVED: SHELL THICKNESS
// (Must come before tile dimensions, since r_inner uses it.)
// =============================================================================

roof_skin_thickness =
    shell_preset == "light"    ? 0.80 :
    shell_preset == "standard" ? 0.90 :
    shell_preset == "heavy"    ? 1.20 :
                                 roof_skin_thickness_mm;

perimeter_wall_thickness =
    shell_preset == "light"    ? 1.20 :
    shell_preset == "standard" ? 1.40 :
    shell_preset == "heavy"    ? 1.80 :
                                 perimeter_wall_thickness_mm;

// =============================================================================
// DERIVED: TILE DIMENSIONS
// =============================================================================

// Normalise to millimetres.
_tile_size_mm =
    size_units == "in" ? tile_size * 25.4 : tile_size;

// Normalise to flat-to-flat regardless of what the user entered.
tile_flat_to_flat =
    size_reference == "flat_to_flat"
        ? _tile_size_mm
        : _tile_size_mm * cos(30);

tile_across_corners = tile_flat_to_flat / cos(30);

// Regular point-up hexagon:
//     flat-to-flat = 2 * circumradius * cos(30)
r_outer       = (tile_flat_to_flat / 2) / cos(30);
r_inner       = r_outer - perimeter_wall_thickness / cos(30);
outer_apothem = tile_flat_to_flat / 2;
inner_apothem = outer_apothem - perimeter_wall_thickness;

// Length of one inner flat side - upper bound on mount_pad_width.
inner_flat_length = 2 * inner_apothem * tan(30);

// Side length of the outer hexagon (all six are equal for a regular hex).
hex_side_length = 2 * r_outer * sin(30);

// =============================================================================
// DERIVED: RELIEF HEIGHTS
// =============================================================================

_peak_unscaled =
    relief_height_mode == "proportional"
        ? tile_flat_to_flat * peak_height_ratio
        : peak_height_mm;

_ridge_unscaled =
    relief_height_mode == "proportional"
        ? _peak_unscaled * ridge_to_peak_ratio
        : ridge_height_mm;

_edge_unscaled =
    relief_height_mode == "proportional"
        ? _peak_unscaled * edge_to_peak_ratio
        : edge_height_mm;

peak_height  = _peak_unscaled  * relief_scale;
ridge_height = _ridge_unscaled * relief_scale;
edge_height  = _edge_unscaled  * relief_scale;

// =============================================================================
// DIAGNOSTIC ECHO
// =============================================================================

echo("--- Tile summary ---");
echo(str("  flat-to-flat     : ", tile_flat_to_flat,         " mm"));
echo(str("  across-corners   : ", tile_across_corners,       " mm"));
echo(str("  hex side length  : ", hex_side_length,          " mm"));
echo(str("  outer circumrad  : ", r_outer,                   " mm"));
echo(str("  outer apothem    : ", outer_apothem,             " mm"));
echo(str("  inner flat len   : ", inner_flat_length,         " mm"));
echo(str("  edge height      : ", edge_height,              " mm"));
echo(str("  ridge height     : ", ridge_height,             " mm"));
echo(str("  peak height      : ", peak_height,              " mm"));
echo(str("  roof skin        : ", roof_skin_thickness,      " mm"));
echo(str("  perimeter wall   : ", perimeter_wall_thickness, " mm"));

// =============================================================================
// VALIDATION
// =============================================================================

assert(tile_flat_to_flat > 0,
    "Tile size must be > 0.");

assert(edge_height > 0,
    "Computed edge_height must be > 0. Check relief_scale and ratios.");

assert(ridge_height > edge_height,
    "ridge_height must be > edge_height. Check relief_scale and ratios.");

assert(peak_height > ridge_height,
    "peak_height must be > ridge_height. Check relief_scale and ratios.");

assert(roof_skin_thickness > 0,
    "roof_skin_thickness must be > 0.");

assert(roof_skin_thickness < edge_height,
    "roof_skin_thickness must be < edge_height.");

assert(perimeter_wall_thickness > 0,
    "perimeter_wall_thickness must be > 0.");

assert(perimeter_wall_thickness < tile_flat_to_flat / 4,
    "perimeter_wall_thickness is too large for the chosen tile size.");

assert(peak_radius_ratio > 0 && peak_radius_ratio < 0.90,
    "peak_radius_ratio must be in (0, 0.90).");

assert(ridge_radius_ratio > 0 && ridge_radius_ratio < 0.90,
    "ridge_radius_ratio must be in (0, 0.90).");

assert(mount_pad_width > 0,
    "mount_pad_width must be > 0.");

assert(mount_pad_width < inner_flat_length,
    "mount_pad_width exceeds the inner flat length of the tile.");

assert(mount_pad_depth > 0,
    "mount_pad_depth must be > 0.");

assert(mount_pad_thickness > 0,
    "mount_pad_thickness must be > 0.");

assert(mount_pad_overlap >= 0,
    "mount_pad_overlap cannot be negative.");

assert(!add_pad_screw_holes ||
       pad_screw_hole_diameter < mount_pad_width * 0.75,
    "pad_screw_hole_diameter is too large for the pad width.");

// =============================================================================
// HELPERS
// =============================================================================

function polar(angle_deg, radius) =
    [radius * cos(angle_deg), radius * sin(angle_deg)];

// Point-up regular hexagon: vertices at 30 + 60*i degrees.
function hex_vertex(i, radius) =
    [radius * cos(30 + i * 60), radius * sin(30 + i * 60)];

// =============================================================================
// CONTROL POINTS FOR THE FRONT RELIEF
// =============================================================================

P_xy = polar(peak_angle_deg,  r_outer * peak_radius_ratio);
Q_xy = polar(ridge_angle_deg, r_outer * ridge_radius_ratio);

// =============================================================================
// SHELL VERTICES
// =============================================================================

points = concat(
    // --- 0..5 : outer rear perimeter --------------------------------
    [for (i = [0 : 5]) let (p = hex_vertex(i, r_outer))
        [p[0], p[1], 0]],

    // --- 6..11 : outer roof perimeter -------------------------------
    [for (i = [0 : 5]) let (p = hex_vertex(i, r_outer))
        [p[0], p[1], edge_height]],

    // --- 12..13 : outer P, Q ----------------------------------------
    [[P_xy[0], P_xy[1], peak_height],
     [Q_xy[0], Q_xy[1], ridge_height]],

    // --- 14..19 : inner rear perimeter ------------------------------
    [for (i = [0 : 5]) let (p = hex_vertex(i, r_inner))
        [p[0], p[1], 0]],

    // --- 20..25 : inner roof perimeter ------------------------------
    [for (i = [0 : 5]) let (p = hex_vertex(i, r_inner))
        [p[0], p[1], edge_height - roof_skin_thickness]],

    // --- 26..27 : inner P, Q ----------------------------------------
    [[P_xy[0], P_xy[1], peak_height - roof_skin_thickness],
     [Q_xy[0], Q_xy[1], ridge_height - roof_skin_thickness]]
);

// =============================================================================
// FRONT / BACK FACET TRIANGULATIONS
// =============================================================================

// Outer roof: fan around P, diagonal to Q, then fan around Q.
outer_roof_faces = [
    [6, 7, 12],  [7, 8, 12],  [6, 12, 11],
    [8, 13, 12], [11, 12, 13],
    [8, 9, 13],  [9, 10, 13], [10, 11, 13]
];

// Inner roof: same topology, reversed winding, offset by +14.
inner_roof_faces = [
    [26, 21, 20], [26, 22, 21], [25, 26, 20],
    [26, 27, 22], [27, 26, 25],
    [27, 23, 22], [27, 24, 23], [27, 25, 24]
];

// =============================================================================
// COMPLETE SHELL FACE LIST
// =============================================================================

faces = concat(
    // Outer perimeter wall.
    [for (i = [0 : 5]) [i, (i+1)%6, 6 + (i+1)%6, 6 + i]],

    // Outer roof.
    outer_roof_faces,

    // Inner perimeter wall.
    [for (i = [0 : 5]) [14 + i, 20 + i, 20 + (i+1)%6, 14 + (i+1)%6]],

    // Inner roof.
    inner_roof_faces,

    // Rear annular ring - only the narrow shell ring. There is
    // deliberately NO polygon across the center.
    [for (i = [0 : 5]) [i, 14 + i, 14 + (i+1)%6, (i+1)%6]]
);

module tile_shell() {
    polyhedron(
        points    = points,
        faces     = faces,
        convexity = polyhedron_convexity
    );
}

// =============================================================================
// MOUNTING PADS
// =============================================================================
//
// Z = 0 is the wall plane. Each pad is a flat-bottomed prism whose
// underside lies on Z = 0 and whose top rises into the cavity by
// mount_pad_thickness. The outer end of the pad tucks UNDER the
// inner perimeter shell by mount_pad_overlap so the two fuse.

module mount_pad(angle_deg) {
    pad_outer_r = inner_apothem + mount_pad_overlap;
    pad_inner_r = pad_outer_r - mount_pad_depth;

    rotate([0, 0, angle_deg])
        translate([pad_inner_r, -mount_pad_width / 2, 0])
            cube([mount_pad_depth,
                  mount_pad_width,
                  mount_pad_thickness]);
}

module pad_screw_hole(angle_deg) {
    pad_outer_r  = inner_apothem + mount_pad_overlap;
    pad_center_r = pad_outer_r - mount_pad_depth / 2;

    rotate([0, 0, angle_deg])
        translate([pad_center_r, 0, -1])
            cylinder(
                d   = pad_screw_hole_diameter,
                h   = mount_pad_thickness + 2,
                $fn = 32
            );
}

// =============================================================================
// ASSEMBLY
// =============================================================================

module model() {
    rotate([0, 0, tile_rotation_deg]) {
        difference() {
            // ---- positive geometry ---------------------------------
            union() {
                tile_shell();

                if (add_mount_pads) {
                    for (a = mount_pad_angles) mount_pad(a);
                }
            }

            // ---- negative geometry ---------------------------------
            if (add_mount_pads && add_pad_screw_holes) {
                for (a = mount_pad_angles) pad_screw_hole(a);
            }
        }
    }
}

// =============================================================================
// OUTPUT
// =============================================================================

model();