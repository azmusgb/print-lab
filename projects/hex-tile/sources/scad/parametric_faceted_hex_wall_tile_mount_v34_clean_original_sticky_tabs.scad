/*
    parametric_faceted_hex_wall_tile_mount_v34_clean_original_sticky_tabs.scad
    ------------------------------------------------------------
    Improved asymmetric low-poly hex wall tile.

    Major v22 changes
    -----------------
    1. ONE master thickness control drives the whole part:
       master_thickness_mm

    2. FIXED mounting tabs showing through the front face.
       - edge height now automatically provides enough cavity depth
         for the full mounting-pad thickness
       - mounting tabs and ribs are also clipped against a safe volume
         below the underside of the faceted front shell
       - tabs therefore remain hidden inside the tile


       It controls:
       - faceted front shell thickness
       - perimeter wall thickness
       - mounting-tab thickness

       Optional multipliers allow advanced tuning without hiding the
       master control.

    2. Thicker shells now work automatically.
       The effective edge height is automatically raised when required
       so shell_thickness_mm is never blocked by a too-small edge height.

    3. Mounting pads cannot protrude outside the hexagon.
       Pads are intersected with a smaller inset hex footprint.

    4. Stronger default mounting geometry.
       - 3.0 mm pad thickness
       - 4.0 mm shell overlap
       - 3.0 mm edge inset
       - optional reinforcing ribs

    5. Open back remains truly open.
       There is no rear floor across the middle.

    Recommended use
    ---------------
    For a 9-inch decorative wall tile printed vertically:

        master_thickness_mm        = 3.0;
        front_shell_multiplier      = 1.0;
        perimeter_multiplier        = 1.0;
        mount_pad_multiplier        = 1.0;
        mount_pad_overlap_mm        = 4.0;
        mount_pad_edge_inset_mm     = 3.0;
        add_mount_ribs              = true;

    Export
    ------
    F6 Render
    File -> Export -> Export as STL
*/


// =============================================================================
// CUSTOMIZER PARAMETERS
// =============================================================================


/* [Tile Size] */

// Which dimension tile_size represents.
size_reference = "across_corners";   // [flat_to_flat, across_corners]

// Units for tile_size.
size_units = "mm";                   // [mm, in]

// Examples:
// 152.4 = 6"
// 203.2 = 8"
// 228.6 = 9"
// 254.0 = 10"
tile_size = 240.0;

// Rotate finished tile around Z.
tile_rotation_deg = 15;


/* [Export / Print Orientation] */

// "flat"     = original CAD orientation.
// "vertical" = stand the tile on one complete flat hex side.
export_orientation = "vertical";          // [flat, vertical]

// Finished face uses 15 degrees. Adding another 15 degrees before standing
// gives an effective 30-degree regular-hex orientation, so a COMPLETE FLAT
// SIDE rests on the build plate.
vertical_edge_angle_deg = 15;



/* [MASTER THICKNESS] */

// MASTER MATERIAL THICKNESS.
//
// THIS is the main control to use if you want the whole printed part
// physically thicker / stronger.
//
// It directly drives:
//   - faceted front shell thickness
//   - perimeter wall thickness
//   - mounting pad thickness
//
// Recommended:
//   1.6 = light
//   2.0 = medium
//   2.5 = strong
//   3.0 = very strong / recommended for a robust wall tile
//   3.5 = heavy duty
//
master_thickness_mm = 3.0;

// Optional multipliers.
//
// Leave these at 1.0 unless you deliberately want one area stronger
// than the master value.
//
// Example:
// perimeter_multiplier = 1.20 makes a 3.0 mm master produce a
// 3.6 mm perimeter.
front_shell_multiplier = 1.0;
perimeter_multiplier   = 1.0;
mount_pad_multiplier   = 1.0;

// Derived thicknesses are calculated later from the master control.


/* [Front Relief] */

// proportional = scales with tile size
// absolute     = exact millimeter heights below
relief_height_mode = "proportional";    // [proportional, absolute]

// Overall relief multiplier.
relief_scale = 1.0;

// Main peak height relative to flat-to-flat size.
peak_height_ratio = 0.081;

// Ridge height relative to peak.
ridge_to_peak_ratio = 0.757;

// Requested outer edge height relative to peak.
//
// IMPORTANT:
// v21 automatically raises edge height if necessary to fit the selected
// front shell thickness. You normally do NOT need to change this anymore.
edge_to_peak_ratio = 0.097;

// Absolute values, used only in absolute mode.
peak_height_mm  = 18.5;
ridge_height_mm = 14.0;
edge_height_mm  = 1.8;

// Minimum empty clearance between the inner roof and Z=0 at the perimeter.
//
// v20 uses:
// effective_edge_height >= front_shell_thickness_mm + edge_clearance_mm
edge_clearance_mm = 0.60;


/* [Facet Layout] */

// Direction of main peak, CCW from +X.
peak_angle_deg = 45;

// Peak distance from center as a fraction of circumradius.
peak_radius_ratio = 0.38;

// Direction of secondary ridge.
ridge_angle_deg = 208;

// Ridge radial position.
ridge_radius_ratio = 0.34;


/* [Wall Mounting] */

// Enable mounting pads.
add_mount_pads = true;

// Width of each pad parallel to the corresponding hex side.
mount_pad_width_mm = 34.0;

// Radial depth of each pad.
mount_pad_depth_mm = 24.0;

// Mounting-tab thickness is now driven by master_thickness_mm.
// Use mount_pad_multiplier above only if the tabs need to be thicker
// or thinner than the rest of the tile.

// How far the pad reaches beneath the inner perimeter shell.
//
// More overlap creates a stronger pad-to-rim union.
mount_pad_overlap_mm = 4.0;

// Pull the ENTIRE usable pad footprint inward from the outside hex edge.
//
// Pads are clipped against this inset hex, so they cannot protrude outside.
mount_pad_edge_inset_mm = 2.0;

// Minimum air gap between the TOP of mounting geometry and the
// UNDERSIDE of the faceted front shell.
//
// This prevents tabs/ribs from becoming visible through the face.
// Recommended: 0.50-1.00 mm.
mount_face_clearance_mm = 0.75;

// Directions of mounting pads.
mount_pad_angles = [60, 120, 240, 300];


/* [Mount Reinforcement] */

// Add small triangular reinforcing ribs where pads meet the perimeter.
//
// Recommended ON for vertical printing.
add_mount_ribs = false;

// Rib thickness across the pad.
mount_rib_width_mm = 3.0;

// Rib height into the cavity.
mount_rib_height_mm = 5.0;

// Rib radial depth.
mount_rib_depth_mm = 8.0;


/* [Optional Screw Holes] */

add_pad_screw_holes = false;

// 3.5 ~= #6
// 4.5 ~= #8
pad_screw_hole_diameter_mm = 4.5;


/* [Advanced] */

// Polyhedron preview hint.
polyhedron_convexity = 12;

// Cylinder quality for screw holes.
screw_hole_fn = 40;


// =============================================================================
// DERIVED MATERIAL THICKNESSES
// =============================================================================
//
// These are the ACTUAL thicknesses used by the model.
//

front_shell_thickness_mm =
    master_thickness_mm * front_shell_multiplier;

perimeter_wall_thickness_mm =
    master_thickness_mm * perimeter_multiplier;

mount_pad_thickness_mm =
    master_thickness_mm * mount_pad_multiplier;


// =============================================================================
// DERIVED TILE DIMENSIONS
// =============================================================================

_tile_size_mm =
    size_units == "in"
        ? tile_size * 25.4
        : tile_size;

tile_flat_to_flat =
    size_reference == "flat_to_flat"
        ? _tile_size_mm
        : _tile_size_mm * cos(30);

tile_across_corners =
    tile_flat_to_flat / cos(30);

outer_apothem =
    tile_flat_to_flat / 2;

r_outer =
    outer_apothem / cos(30);

inner_apothem =
    outer_apothem - perimeter_wall_thickness_mm;

r_inner =
    inner_apothem / cos(30);

inner_flat_length =
    2 * inner_apothem * tan(30);

hex_side_length =
    2 * r_outer * sin(30);


// =============================================================================
// DERIVED VERTICAL-PRINT GEOMETRY
// =============================================================================

vertical_total_rotation_deg =
    tile_rotation_deg + vertical_edge_angle_deg;

vertical_half_y =
    max([
        for (i = [0 : 5])
            abs(
                r_outer
                * sin(
                    30
                    + i * 60
                    + vertical_total_rotation_deg
                )
            )
    ]);

vertical_print_height =
    2 * vertical_half_y;


// =============================================================================
// DERIVED RELIEF HEIGHTS
// =============================================================================

_peak_unscaled =
    relief_height_mode == "proportional"
        ? tile_flat_to_flat * peak_height_ratio
        : peak_height_mm;

_ridge_unscaled =
    relief_height_mode == "proportional"
        ? _peak_unscaled * ridge_to_peak_ratio
        : ridge_height_mm;

_requested_edge_unscaled =
    relief_height_mode == "proportional"
        ? _peak_unscaled * edge_to_peak_ratio
        : edge_height_mm;

peak_height =
    _peak_unscaled * relief_scale;

ridge_height =
    _ridge_unscaled * relief_scale;

requested_edge_height =
    _requested_edge_unscaled * relief_scale;

// AUTO-FIX:
// Guarantee enough vertical room for BOTH:
//   1. the chosen front-shell thickness
//   2. the full mounting-pad thickness
//
// This is the key v22 fix for tabs previously breaking through the face.
minimum_edge_height =
    front_shell_thickness_mm
    + mount_pad_thickness_mm
    + mount_face_clearance_mm;

edge_height =
    max(
        requested_edge_height,
        minimum_edge_height
    );


// =============================================================================
// DERIVED MOUNTING GEOMETRY
// =============================================================================

// Desired outer edge before clipping.
//
// This allows the pad to overlap the inner wall structurally.
mount_pad_desired_outer_r =
    inner_apothem + mount_pad_overlap_mm;

mount_pad_inner_r =
    mount_pad_desired_outer_r - mount_pad_depth_mm;

mount_pad_center_r =
    mount_pad_desired_outer_r - mount_pad_depth_mm / 2;

// Smaller hex used as a hard clipping boundary.
//
// Any mount geometry outside this boundary is removed automatically.
mount_clip_apothem =
    outer_apothem - mount_pad_edge_inset_mm;

mount_clip_radius =
    mount_clip_apothem / cos(30);


// =============================================================================
// VALIDATION
// =============================================================================

assert(
    tile_flat_to_flat > 0,
    "tile_size must produce a positive tile dimension."
);

assert(
    master_thickness_mm > 0,
    "master_thickness_mm must be greater than zero."
);

assert(
    front_shell_multiplier > 0 &&
    perimeter_multiplier > 0 &&
    mount_pad_multiplier > 0,
    "All thickness multipliers must be greater than zero."
);

assert(
    front_shell_thickness_mm > 0,
    "front_shell_thickness_mm must be greater than zero."
);

assert(
    perimeter_wall_thickness_mm > 0,
    "perimeter_wall_thickness_mm must be greater than zero."
);

assert(
    perimeter_wall_thickness_mm < outer_apothem,
    "perimeter_wall_thickness_mm is too large for this tile."
);

assert(
    inner_apothem > 0,
    "The selected perimeter wall leaves no hollow interior."
);

assert(
    edge_height > front_shell_thickness_mm,
    "Internal error: edge_height must exceed front_shell_thickness_mm."
);

assert(
    ridge_height > edge_height,
    "ridge_height must remain greater than the effective edge height."
);

assert(
    peak_height > ridge_height,
    "peak_height must remain greater than ridge_height."
);

assert(
    peak_radius_ratio > 0 && peak_radius_ratio < 0.90,
    "peak_radius_ratio must be between 0 and 0.90."
);

assert(
    ridge_radius_ratio > 0 && ridge_radius_ratio < 0.90,
    "ridge_radius_ratio must be between 0 and 0.90."
);

assert(
    mount_pad_width_mm > 0,
    "mount_pad_width_mm must be greater than zero."
);

assert(
    mount_pad_depth_mm > 0,
    "mount_pad_depth_mm must be greater than zero."
);

assert(
    mount_pad_thickness_mm > 0,
    "mount_pad_thickness_mm must be greater than zero."
);

assert(
    mount_pad_overlap_mm >= 0,
    "mount_pad_overlap_mm cannot be negative."
);

assert(
    mount_pad_edge_inset_mm >= 0,
    "mount_pad_edge_inset_mm cannot be negative."
);

assert(
    mount_face_clearance_mm >= 0,
    "mount_face_clearance_mm cannot be negative."
);

assert(
    mount_clip_apothem > 0,
    "mount_pad_edge_inset_mm is too large."
);

assert(
    mount_pad_inner_r > 0,
    "mount_pad_depth_mm is too large and reaches/passes the tile center."
);

assert(
    !add_pad_screw_holes ||
    pad_screw_hole_diameter_mm < mount_pad_width_mm * 0.75,
    "pad_screw_hole_diameter_mm is too large for the mounting pad."
);

assert(
    !add_mount_ribs ||
    mount_rib_height_mm > 0,
    "mount_rib_height_mm must be greater than zero."
);


// =============================================================================
// DIAGNOSTIC OUTPUT
// =============================================================================

echo("====================================================");
echo("FACETED HEX WALL TILE v22");
echo("====================================================");

echo(str("flat-to-flat             : ", tile_flat_to_flat, " mm"));
echo(str("across-corners           : ", tile_across_corners, " mm"));
echo(str("hex side length          : ", hex_side_length, " mm"));

echo(str("MASTER thickness         : ", master_thickness_mm, " mm"));
echo(str("actual front shell       : ", front_shell_thickness_mm, " mm"));
echo(str("actual perimeter wall    : ", perimeter_wall_thickness_mm, " mm"));
echo(str("actual mount pad         : ", mount_pad_thickness_mm, " mm"));
echo(str("perimeter wall thickness : ", perimeter_wall_thickness_mm, " mm"));

echo(str("requested edge height    : ", requested_edge_height, " mm"));
echo(str("minimum edge height      : ", minimum_edge_height, " mm"));
echo(str("EFFECTIVE edge height    : ", edge_height, " mm"));

echo(str("ridge height             : ", ridge_height, " mm"));
echo(str("peak height              : ", peak_height, " mm"));
echo(str("export orientation       : ", export_orientation));
echo(str("vertical print height    : ", vertical_print_height, " mm"));
echo(str("vertical relief depth    : ", peak_height, " mm"));
echo(str("effective print rotation : ", vertical_total_rotation_deg, " deg"));

echo(str("mount pad width          : ", mount_pad_width_mm, " mm"));
echo(str("mount pad depth          : ", mount_pad_depth_mm, " mm"));
echo(str("mount pad thickness      : ", mount_pad_thickness_mm, " mm"));
echo(str("mount pad overlap        : ", mount_pad_overlap_mm, " mm"));
echo(str("mount edge inset         : ", mount_pad_edge_inset_mm, " mm"));
echo(str("mount/face clearance     : ", mount_face_clearance_mm, " mm"));

echo(str("mount clip apothem       : ", mount_clip_apothem, " mm"));

if (edge_height > requested_edge_height)
    echo(
        str(
            "AUTO EDGE FIX ACTIVE: edge raised from ",
            requested_edge_height,
            " mm to ",
            edge_height,
            " mm so a ",
            front_shell_thickness_mm,
            " mm front shell and ", mount_pad_thickness_mm, " mm mounting tabs fit safely."
        )
    );

echo("====================================================");


// =============================================================================
// HELPERS
// =============================================================================

function polar(angle_deg, radius) =
    [
        radius * cos(angle_deg),
        radius * sin(angle_deg)
    ];

function hex_vertex(i, radius) =
    [
        radius * cos(30 + i * 60),
        radius * sin(30 + i * 60)
    ];


// =============================================================================
// FRONT RELIEF CONTROL POINTS
// =============================================================================

P_xy =
    polar(
        peak_angle_deg,
        r_outer * peak_radius_ratio
    );

Q_xy =
    polar(
        ridge_angle_deg,
        r_outer * ridge_radius_ratio
    );


// =============================================================================
// SHELL VERTICES
// =============================================================================

points =
    concat(

        // 0..5 : outer rear perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_outer))
                [p[0], p[1], 0]
        ],

        // 6..11 : outer front perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_outer))
                [p[0], p[1], edge_height]
        ],

        // 12..13 : outer peak / ridge
        [
            [P_xy[0], P_xy[1], peak_height],
            [Q_xy[0], Q_xy[1], ridge_height]
        ],

        // 14..19 : inner rear perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_inner))
                [p[0], p[1], 0]
        ],

        // 20..25 : inner front perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_inner))
                [p[0], p[1], edge_height - front_shell_thickness_mm]
        ],

        // 26..27 : inner peak / ridge
        [
            [P_xy[0], P_xy[1], peak_height - front_shell_thickness_mm],
            [Q_xy[0], Q_xy[1], ridge_height - front_shell_thickness_mm]
        ]
    );


// =============================================================================
// SHELL FACES
// =============================================================================

outer_roof_faces = [
    [6, 7, 12],
    [7, 8, 12],
    [6, 12, 11],

    [8, 13, 12],
    [11, 12, 13],

    [8, 9, 13],
    [9, 10, 13],
    [10, 11, 13]
];

inner_roof_faces = [
    [26, 21, 20],
    [26, 22, 21],
    [25, 26, 20],

    [26, 27, 22],
    [27, 26, 25],

    [27, 23, 22],
    [27, 24, 23],
    [27, 25, 24]
];

faces =
    concat(

        // Outer vertical perimeter
        [
            for (i = [0 : 5])
                [
                    i,
                    (i + 1) % 6,
                    6 + (i + 1) % 6,
                    6 + i
                ]
        ],

        outer_roof_faces,

        // Inner vertical perimeter
        [
            for (i = [0 : 5])
                [
                    14 + i,
                    20 + i,
                    20 + (i + 1) % 6,
                    14 + (i + 1) % 6
                ]
        ],

        inner_roof_faces,

        // Narrow rear perimeter ring only.
        // Center remains open.
        [
            for (i = [0 : 5])
                [
                    i,
                    14 + i,
                    14 + (i + 1) % 6,
                    (i + 1) % 6
                ]
        ]
    );


// =============================================================================
// TILE SHELL
// =============================================================================

module tile_shell() {
    polyhedron(
        points = points,
        faces = faces,
        convexity = polyhedron_convexity
    );
}


// =============================================================================
// SAFE MOUNTING VOLUME BELOW THE FRONT FACE
// =============================================================================
//
// This volume follows the UNDERSIDE of the faceted front shell, offset
// downward by mount_face_clearance_mm.
//
// Mount pads and ribs are intersected with this volume. Even if a future
// parameter combination becomes aggressive, mounting geometry cannot pass
// through the visible front shell.
//

safe_edge_z =
    max(
        0.01,
        edge_height
        - front_shell_thickness_mm
        - mount_face_clearance_mm
    );

safe_peak_z =
    max(
        0.01,
        peak_height
        - front_shell_thickness_mm
        - mount_face_clearance_mm
    );

safe_ridge_z =
    max(
        0.01,
        ridge_height
        - front_shell_thickness_mm
        - mount_face_clearance_mm
    );

safe_mount_points =
    concat(

        // 0..5: rear outer perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_outer))
                [p[0], p[1], 0]
        ],

        // 6..11: safe ceiling at outer perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_outer))
                [p[0], p[1], safe_edge_z]
        ],

        // 12..13: safe ceiling under peak/ridge
        [
            [P_xy[0], P_xy[1], safe_peak_z],
            [Q_xy[0], Q_xy[1], safe_ridge_z]
        ]
    );

safe_mount_ceiling_faces = [
    [6, 7, 12],
    [7, 8, 12],
    [6, 12, 11],
    [8, 13, 12],
    [11, 12, 13],
    [8, 9, 13],
    [9, 10, 13],
    [10, 11, 13]
];

safe_mount_faces =
    concat(

        // Outer side walls.
        [
            for (i = [0 : 5])
                [
                    i,
                    (i + 1) % 6,
                    6 + (i + 1) % 6,
                    6 + i
                ]
        ],

        // Sloped safe ceiling.
        safe_mount_ceiling_faces,

        // Rear floor used only as a clipping volume closure.
        [[5, 4, 3, 2, 1, 0]]
    );

module safe_mount_volume() {
    polyhedron(
        points = safe_mount_points,
        faces = safe_mount_faces,
        convexity = polyhedron_convexity
    );
}


// =============================================================================
// HEX FOOTPRINT USED TO CLIP MOUNTING TABS
// =============================================================================
//
// This is intentionally smaller than the visible outer hexagon.
// Therefore mount pads/ribs cannot stick out past the visible perimeter.
//

module mount_clip_volume(height_mm) {
    linear_extrude(height = height_mm)
        polygon(
            points = [
                for (i = [0 : 5])
                    hex_vertex(i, mount_clip_radius)
            ]
        );
}


// =============================================================================
// RAW MOUNT PAD
// =============================================================================

module raw_mount_pad(angle_deg) {
    rotate([0, 0, angle_deg])
        translate(
            [
                mount_pad_inner_r,
                -mount_pad_width_mm / 2,
                0
            ]
        )
            cube(
                [
                    mount_pad_depth_mm,
                    mount_pad_width_mm,
                    mount_pad_thickness_mm
                ]
            );
}


// =============================================================================
// CLIPPED MOUNT PAD
// =============================================================================

module mount_pad(angle_deg) {
    intersection() {

        raw_mount_pad(angle_deg);

        // Keep pad inside the inset hex footprint.
        mount_clip_volume(
            mount_pad_thickness_mm + 0.01
        );

        // Hard stop below the underside of the front face.
        safe_mount_volume();
    }
}


// =============================================================================
// OPTIONAL REINFORCING RIBS
// =============================================================================
//
// Two ribs are placed near the left/right sides of each mounting pad.
//
// They rise into the cavity and help resist bending at the pad-to-shell joint.
//

module raw_mount_ribs(angle_deg) {

    rib_center_r =
        mount_pad_desired_outer_r
        - mount_rib_depth_mm / 2;

    rib_side_offset =
        max(
            0,
            mount_pad_width_mm / 2
            - mount_rib_width_mm
            - 2
        );

    rotate([0, 0, angle_deg]) {

        for (side = [-1, 1]) {

            translate(
                [
                    rib_center_r - mount_rib_depth_mm / 2,
                    side * rib_side_offset - mount_rib_width_mm / 2,
                    mount_pad_thickness_mm
                ]
            )

            rotate([90, 0, 90])

            linear_extrude(height = mount_rib_depth_mm)

            polygon(
                points = [
                    [0, 0],
                    [mount_rib_width_mm, 0],
                    [mount_rib_width_mm, mount_rib_height_mm],
                    [0, 0]
                ]
            );
        }
    }
}


module mount_ribs(angle_deg) {
    intersection() {

        raw_mount_ribs(angle_deg);

        mount_clip_volume(
            mount_pad_thickness_mm
            + mount_rib_height_mm
            + 0.1
        );

        // Ribs are also prohibited from crossing the front-shell underside.
        safe_mount_volume();
    }
}


// =============================================================================
// OPTIONAL SCREW HOLE
// =============================================================================

module pad_screw_hole(angle_deg) {

    rotate([0, 0, angle_deg])

        translate(
            [
                mount_pad_center_r,
                0,
                -1
            ]
        )

            cylinder(
                d = pad_screw_hole_diameter_mm,
                h =
                    mount_pad_thickness_mm
                    + mount_rib_height_mm
                    + 2,
                $fn = screw_hole_fn
            );
}


// =============================================================================
// COMPLETE MODEL
// =============================================================================

module model() {

    rotate([0, 0, tile_rotation_deg]) {

        difference() {

            union() {

                tile_shell();

                if (add_mount_pads) {

                    for (a = mount_pad_angles) {

                        mount_pad(a);

                        if (add_mount_ribs)
                            mount_ribs(a);
                    }
                }
            }

            if (
                add_mount_pads &&
                add_pad_screw_holes
            ) {

                for (a = mount_pad_angles)
                    pad_screw_hole(a);
            }
        }
    }
}


// =============================================================================
// OUTPUT
// =============================================================================
//
// CLEAN ORIGINAL-MOUNT VERSION:
// - exact v22-style hidden rectangular sticky pads
// - no stabilizer feet
// - no sacrificial fins
// - no gussets
// - no native vertical replacement pads
// - no screw holes
// - no mount ribs
//
// The model remains a true regular hex. For vertical export, it is stood on a
// complete flat side and translated so the bottom edge sits at Z=0.

module output_model() {

    if (export_orientation == "vertical") {

        translate(
            [
                0,
                peak_height,
                vertical_half_y
            ]
        )

        rotate([90, 0, 0])

        rotate([0, 0, vertical_edge_angle_deg])

            model();

    } else {

        model();
    }
}

output_model();
