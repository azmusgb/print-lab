/*
    parametric_faceted_hex_wall_tile_mount_v23_10x10_vertical.scad
    ----------------------------------------------------------------
    Regular asymmetric low-poly hex wall tile.

    v23 goals
    ---------
    1. Exact 10.00" x 10.00" finished face bounding box by default.
    2. Preserve a TRUE regular hexagon -- no X/Y stretching.
    3. Vertical-print-first export option:
       - model can export standing on one edge
       - finished wall geometry is unchanged
    4. Open back remains fully open.
    5. Hidden mounting pads remain clipped below the visible face.
    6. One master thickness controls shell, perimeter, and pads.
    7. Optional breakaway vertical-print feet are available but OFF by default.

    Recommended default
    -------------------
    face_size_reference      = "bounding_square";
    face_size_units          = "mm";
    face_size                = 254.0;   // exact 10" x 10" envelope
    tile_rotation_deg        = 15;      // makes regular-hex X/Y envelope equal

    export_orientation       = "vertical";
    vertical_edge_angle_deg  = 0;

    master_thickness_mm      = 3.0;
    add_mount_pads           = true;
    add_mount_ribs           = false;

    Export
    ------
    F6 Render
    File -> Export -> Export as STL
*/


// =============================================================================
// CUSTOMIZER PARAMETERS
// =============================================================================


/* [Finished Face Size] */

// "bounding_square"
//     face_size is the maximum X and Y envelope.
//     At the default 15-degree rotation, a regular hex fills the square exactly.
//
// "flat_to_flat"
//     face_size is the traditional hex flat-to-flat dimension.
//
// "across_corners"
//     face_size is the regular-hex corner-to-corner dimension.
face_size_reference = "bounding_square"; // [bounding_square, flat_to_flat, across_corners]

// Units used by face_size.
face_size_units = "mm";                   // [mm, in]

// Default = exact 10.00 inches.
face_size = 254.0;

// Rotation of the finished hex within its face plane.
//
// IMPORTANT:
// 15 degrees gives a regular hex an equal X/Y bounding envelope.
// With bounding_square + 254 mm this produces approximately:
//     X = 254.0 mm
//     Y = 254.0 mm
tile_rotation_deg = 15;


/* [Export / Print Orientation] */

// "flat"     = conventional CAD orientation; decorative face points +Z.
// "vertical" = rotate final part onto an edge for vertical printing.
export_orientation = "vertical";          // [flat, vertical]

// Additional in-plane rotation used ONLY before standing the part vertically.
//
// Keep 0 for the default v23 geometry. The transformed model is automatically
// moved so its lowest point rests at Z=0.
vertical_edge_angle_deg = 0;

// Add small breakaway stabilizer feet after the model is stood vertically.
// Normally leave OFF and use a slicer brim if required.
add_vertical_breakaway_feet = false;

// Breakaway-foot dimensions.
vertical_foot_length_mm = 20.0;
vertical_foot_depth_mm = 8.0;
vertical_foot_height_mm = 0.60;
vertical_foot_neck_mm = 0.80;


/* [MASTER THICKNESS] */

// Main material thickness control.
master_thickness_mm = 3.0;

// Optional tuning multipliers.
front_shell_multiplier = 1.0;
perimeter_multiplier   = 1.0;
mount_pad_multiplier   = 1.0;


/* [Front Relief] */

// "proportional" scales relief with the true flat-to-flat dimension.
// "absolute" uses explicit millimeter values.
relief_height_mode = "proportional";      // [proportional, absolute]

relief_scale = 1.0;

// Relative relief proportions.
peak_height_ratio = 0.081;
ridge_to_peak_ratio = 0.757;
edge_to_peak_ratio = 0.097;

// Used only in absolute mode.
peak_height_mm   = 18.5;
ridge_height_mm = 14.0;
edge_height_mm  = 1.8;

// Minimum air gap between inner roof and mounting geometry.
edge_clearance_mm = 0.60;


/* [Facet Layout] */

peak_angle_deg = 45;
peak_radius_ratio = 0.38;

ridge_angle_deg = 208;
ridge_radius_ratio = 0.34;


/* [Wall Mounting] */

add_mount_pads = true;

// Width parallel to local hex edge.
mount_pad_width_mm = 34.0;

// Radial depth into the cavity.
mount_pad_depth_mm = 24.0;

// Structural overlap beneath the inner perimeter shell.
mount_pad_overlap_mm = 4.0;

// Pull mounting geometry inward from the visible outside perimeter.
mount_pad_edge_inset_mm = 3.0;

// Clearance below underside of visible face.
mount_face_clearance_mm = 0.75;

// Mount-pad directions in the tile's local coordinate system.
mount_pad_angles = [60, 120, 240, 300];


/* [Mount Reinforcement] */

add_mount_ribs = false;

mount_rib_width_mm  = 3.0;
mount_rib_height_mm = 5.0;
mount_rib_depth_mm  = 8.0;


/* [Optional Screw Holes] */

add_pad_screw_holes = false;

pad_screw_hole_diameter_mm = 4.5;


/* [Advanced] */

polyhedron_convexity = 12;
screw_hole_fn = 40;

// Small numerical tolerance.
eps = 0.01;


// =============================================================================
// HELPERS
// =============================================================================

function polar(angle_deg, radius) =
    [
        radius * cos(angle_deg),
        radius * sin(angle_deg)
    ];

function hex_vertex_unrotated(i, radius) =
    [
        radius * cos(30 + i * 60),
        radius * sin(30 + i * 60)
    ];

function rotate2d(p, angle_deg) =
    [
        p[0] * cos(angle_deg) - p[1] * sin(angle_deg),
        p[0] * sin(angle_deg) + p[1] * cos(angle_deg)
    ];

function hex_vertex(i, radius) =
    rotate2d(
        hex_vertex_unrotated(i, radius),
        tile_rotation_deg
    );

// Half-width / half-height of a unit-circumradius rotated regular hex.
function unit_hex_half_x(rotation_deg) =
    max([
        for (i = [0 : 5])
            abs(
                cos(30 + i * 60 + rotation_deg)
            )
    ]);

function unit_hex_half_y(rotation_deg) =
    max([
        for (i = [0 : 5])
            abs(
                sin(30 + i * 60 + rotation_deg)
            )
    ]);

// Bounding box of a regular hex with circumradius r.
function hex_bbox_x(r, rotation_deg) =
    2 * r * unit_hex_half_x(rotation_deg);

function hex_bbox_y(r, rotation_deg) =
    2 * r * unit_hex_half_y(rotation_deg);


// =============================================================================
// DERIVED MATERIAL THICKNESSES
// =============================================================================

front_shell_thickness_mm =
    master_thickness_mm * front_shell_multiplier;

perimeter_wall_thickness_mm =
    master_thickness_mm * perimeter_multiplier;

mount_pad_thickness_mm =
    master_thickness_mm * mount_pad_multiplier;


// =============================================================================
// DERIVED FACE DIMENSIONS
// =============================================================================

_face_size_mm =
    face_size_units == "in"
        ? face_size * 25.4
        : face_size;

// If bounding_square is selected, choose the largest regular-hex radius that
// fits inside both the requested X and Y dimensions.
//
// At tile_rotation_deg = 15, unit X and Y extents are equal, so both dimensions
// become exactly face_size.
r_outer =
    face_size_reference == "flat_to_flat"
        ? (_face_size_mm / 2) / cos(30)
        : face_size_reference == "across_corners"
            ? _face_size_mm / 2
            : min(
                _face_size_mm / (2 * unit_hex_half_x(tile_rotation_deg)),
                _face_size_mm / (2 * unit_hex_half_y(tile_rotation_deg))
              );

tile_flat_to_flat =
    2 * r_outer * cos(30);

tile_across_corners =
    2 * r_outer;

finished_bbox_x =
    hex_bbox_x(r_outer, tile_rotation_deg);

finished_bbox_y =
    hex_bbox_y(r_outer, tile_rotation_deg);

outer_apothem =
    tile_flat_to_flat / 2;

inner_apothem =
    outer_apothem - perimeter_wall_thickness_mm;

r_inner =
    inner_apothem / cos(30);

inner_flat_length =
    2 * inner_apothem * tan(30);

hex_side_length =
    r_outer;


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

// Enough vertical room for front shell + complete pad + clearance.
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

mount_pad_desired_outer_r =
    inner_apothem + mount_pad_overlap_mm;

mount_pad_inner_r =
    mount_pad_desired_outer_r - mount_pad_depth_mm;

mount_pad_center_r =
    mount_pad_desired_outer_r - mount_pad_depth_mm / 2;

mount_clip_apothem =
    outer_apothem - mount_pad_edge_inset_mm;

mount_clip_radius =
    mount_clip_apothem / cos(30);


// =============================================================================
// VERTICAL-EXPORT DERIVED VALUES
// =============================================================================
//
// The tile is first rotated around Z by vertical_edge_angle_deg, then stood up
// by +90 degrees around X.
//
// We calculate the local Y envelope AFTER that optional Z rotation so the
// final model can be translated to put its lowest point exactly on Z=0.

vertical_rotation_total_deg =
    vertical_edge_angle_deg;

vertical_half_y =
    max([
        for (i = [0 : 5])
            abs(
                r_outer
                * sin(
                    30
                    + i * 60
                    + tile_rotation_deg
                    + vertical_rotation_total_deg
                )
            )
    ]);

vertical_print_height =
    2 * vertical_half_y;

// After rotate([90,0,0]), original +Z becomes -Y.
// Translate by peak_height so all relief lies in positive Y.
vertical_print_depth =
    peak_height;


// =============================================================================
// VALIDATION
// =============================================================================

assert(
    _face_size_mm > 0,
    "face_size must produce a positive dimension."
);

assert(
    master_thickness_mm > 0,
    "master_thickness_mm must be greater than zero."
);

assert(
    front_shell_multiplier > 0
    && perimeter_multiplier > 0
    && mount_pad_multiplier > 0,
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
    !add_pad_screw_holes
    || pad_screw_hole_diameter_mm < mount_pad_width_mm * 0.75,
    "pad_screw_hole_diameter_mm is too large for the mounting pad."
);

assert(
    !add_mount_ribs
    || mount_rib_height_mm > 0,
    "mount_rib_height_mm must be greater than zero."
);

assert(
    !add_vertical_breakaway_feet
    || export_orientation == "vertical",
    "Vertical breakaway feet require export_orientation = \"vertical\"."
);


// =============================================================================
// DIAGNOSTIC OUTPUT
// =============================================================================

echo("====================================================");
echo("FACETED HEX WALL TILE v23 - 10x10 / VERTICAL");
echo("====================================================");

echo(str("face size reference      : ", face_size_reference));
echo(str("requested face size      : ", _face_size_mm, " mm"));
echo(str("tile rotation            : ", tile_rotation_deg, " deg"));

echo(str("finished bbox X          : ", finished_bbox_x, " mm"));
echo(str("finished bbox Y          : ", finished_bbox_y, " mm"));
echo(str("finished bbox X inches   : ", finished_bbox_x / 25.4, " in"));
echo(str("finished bbox Y inches   : ", finished_bbox_y / 25.4, " in"));

echo(str("flat-to-flat             : ", tile_flat_to_flat, " mm"));
echo(str("across-corners           : ", tile_across_corners, " mm"));
echo(str("hex side length          : ", hex_side_length, " mm"));

echo(str("MASTER thickness         : ", master_thickness_mm, " mm"));
echo(str("actual front shell       : ", front_shell_thickness_mm, " mm"));
echo(str("actual perimeter wall    : ", perimeter_wall_thickness_mm, " mm"));
echo(str("actual mount pad         : ", mount_pad_thickness_mm, " mm"));

echo(str("requested edge height    : ", requested_edge_height, " mm"));
echo(str("minimum edge height      : ", minimum_edge_height, " mm"));
echo(str("EFFECTIVE edge height    : ", edge_height, " mm"));

echo(str("ridge height             : ", ridge_height, " mm"));
echo(str("peak height              : ", peak_height, " mm"));
echo(str("peak height inches       : ", peak_height / 25.4, " in"));

echo(str("mount pad width          : ", mount_pad_width_mm, " mm"));
echo(str("mount pad depth          : ", mount_pad_depth_mm, " mm"));
echo(str("mount pad thickness      : ", mount_pad_thickness_mm, " mm"));
echo(str("mount pad overlap        : ", mount_pad_overlap_mm, " mm"));
echo(str("mount edge inset         : ", mount_pad_edge_inset_mm, " mm"));
echo(str("mount/face clearance     : ", mount_face_clearance_mm, " mm"));

echo(str("export orientation       : ", export_orientation));

if (export_orientation == "vertical") {
    echo(str("vertical print height    : ", vertical_print_height, " mm"));
    echo(str("vertical print depth     : ", vertical_print_depth, " mm"));
}

if (edge_height > requested_edge_height)
    echo(
        str(
            "AUTO EDGE FIX ACTIVE: edge raised from ",
            requested_edge_height,
            " mm to ",
            edge_height,
            " mm."
        )
    );

echo("====================================================");


// =============================================================================
// FRONT RELIEF CONTROL POINTS
// =============================================================================

P_xy =
    polar(
        peak_angle_deg + tile_rotation_deg,
        r_outer * peak_radius_ratio
    );

Q_xy =
    polar(
        ridge_angle_deg + tile_rotation_deg,
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
            [
                P_xy[0],
                P_xy[1],
                peak_height - front_shell_thickness_mm
            ],
            [
                Q_xy[0],
                Q_xy[1],
                ridge_height - front_shell_thickness_mm
            ]
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
        // Center remains fully open.
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
// SAFE MOUNTING VOLUME BELOW FRONT FACE
// =============================================================================

safe_edge_z =
    max(
        eps,
        edge_height
        - front_shell_thickness_mm
        - mount_face_clearance_mm
    );

safe_peak_z =
    max(
        eps,
        peak_height
        - front_shell_thickness_mm
        - mount_face_clearance_mm
    );

safe_ridge_z =
    max(
        eps,
        ridge_height
        - front_shell_thickness_mm
        - mount_face_clearance_mm
    );

safe_mount_points =
    concat(

        // 0..5 : rear outer perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_outer))
                [p[0], p[1], 0]
        ],

        // 6..11 : safe ceiling at outer perimeter
        [
            for (i = [0 : 5])
                let(p = hex_vertex(i, r_outer))
                [p[0], p[1], safe_edge_z]
        ],

        // 12..13 : safe ceiling under peak/ridge
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

        // Rear floor used only to close clipping volume.
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
// HEX FOOTPRINT FOR MOUNT CLIPPING
// =============================================================================

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
//
// Mount-pad angles are local tile angles. tile_rotation_deg is applied so the
// pads remain attached to the same visual positions when the face rotates.

module raw_mount_pad(angle_deg) {
    rotate([0, 0, angle_deg + tile_rotation_deg])
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

        // Keep pad inside inset hex footprint.
        mount_clip_volume(
            mount_pad_thickness_mm + eps
        );

        // Hard stop below underside of front shell.
        safe_mount_volume();
    }
}


// =============================================================================
// OPTIONAL REINFORCING RIBS
// =============================================================================

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

    rotate([0, 0, angle_deg + tile_rotation_deg]) {

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

        safe_mount_volume();
    }
}


// =============================================================================
// OPTIONAL SCREW HOLE
// =============================================================================

module pad_screw_hole(angle_deg) {

    rotate([0, 0, angle_deg + tile_rotation_deg])

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
// COMPLETE FINISHED TILE
// =============================================================================

module finished_tile() {

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
            add_mount_pads
            && add_pad_screw_holes
        ) {

            for (a = mount_pad_angles)
                pad_screw_hole(a);
        }
    }
}


// =============================================================================
// VERTICAL-PRINT TRANSFORM
// =============================================================================
//
// Transform order in OpenSCAD is inside-out:
//
// 1. finished_tile()
// 2. optional extra Z rotation for selecting another edge
// 3. rotate +90 degrees around X so the face stands vertically
// 4. translate so:
//      - relief depth occupies positive Y
//      - lowest tile point is exactly at Z=0

module vertical_tile() {

    translate(
        [
            0,
            peak_height,
            vertical_half_y
        ]
    )

    rotate([90, 0, 0])

    rotate([0, 0, vertical_edge_angle_deg])

        finished_tile();
}


// =============================================================================
// OPTIONAL BREAKAWAY VERTICAL FEET
// =============================================================================
//
// These are intentionally simple sacrificial tabs.
// They are added only in vertical export mode.
// Leave OFF unless a brim alone is not sufficient.

module vertical_breakaway_feet() {

    // Two feet spread across X.
    foot_x =
        finished_bbox_x * 0.28;

    for (x = [-foot_x, foot_x]) {

        // Main foot.
        translate(
            [
                x - vertical_foot_length_mm / 2,
                0,
                0
            ]
        )
            cube(
                [
                    vertical_foot_length_mm,
                    vertical_foot_depth_mm,
                    vertical_foot_height_mm
                ]
            );

        // Narrow neck connecting foot to the tile plane.
        translate(
            [
                x - vertical_foot_neck_mm / 2,
                vertical_foot_depth_mm - vertical_foot_neck_mm,
                0
            ]
        )
            cube(
                [
                    vertical_foot_neck_mm,
                    vertical_foot_neck_mm,
                    min(edge_height, 3.0)
                ]
            );
    }
}


// =============================================================================
// OUTPUT
// =============================================================================

module output_model() {

    if (export_orientation == "vertical") {

        union() {

            vertical_tile();

            if (add_vertical_breakaway_feet)
                vertical_breakaway_feet();
        }

    } else {

        finished_tile();
    }
}

output_model();
