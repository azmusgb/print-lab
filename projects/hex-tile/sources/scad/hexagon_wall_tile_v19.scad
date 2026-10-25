/*
  Parametric Faceted Hex Wall Tile v19 — Isolated Cosmetic Shell
  --------------------------------------------------------------
  Purpose:
    - Preserve the bold, borderless 14-facet front from v18.
    - Eliminate rear-structure telegraphing through the cosmetic face.
    - Keep a true open back with four hidden adhesive pads.
    - Route mounting loads locally into the perimeter instead of across the face.
    - Export vertically with a full flat hex edge on the print bed.

  Design principle:
    The visible faceted roof is a cosmetic shell. Internal mounting structure is
    intentionally kept near the rear plane and away from the roof underside.
    The only normal roof contact is the perimeter wall at the outer silhouette.

  Units: millimeters
*/

// ============================================================
// A) GLOBAL QUALITY / EXPORT
// ============================================================
$fn = 48;
render_orientation = "vertical";   // "flat" or "vertical"

// ============================================================
// B) TILE SIZE
// ============================================================
point_to_point = 254.0;             // 10.000 in, vertex-to-vertex

// ============================================================
// C) COSMETIC FACE / RELIEF
// ============================================================
roof_skin        = 1.90;            // thicker cosmetic face to resist telegraphing
edge_relief      = 3.20;
peak_relief      = 24.00;
secondary_relief = 15.50;
low_relief       = 7.20;

// Outer-corner relief remains intentionally asymmetric.
corner_z = [
    edge_relief + 0.4,              // right
    edge_relief + 1.2,              // upper-right
    edge_relief + 0.2,              // upper-left
    edge_relief + 0.0,              // left
    edge_relief + 0.6,              // lower-left
    edge_relief + 0.1               // lower-right
];

// ============================================================
// D) PERIMETER SHELL
// ============================================================
perimeter_wall = 2.40;              // slightly stronger edge wall; hidden from front
roof_overlap   = 0.18;              // positive union into cosmetic roof

// ============================================================
// E) ISOLATED REAR SUPPORT SYSTEM
// ============================================================
// No cross-tile ribs and no horizontal rails behind the cosmetic face.
// Each pad uses short, low-profile V braces to nearby perimeter segments.
rear_braces_enabled = true;
brace_width         = 7.00;         // wide + shallow is stronger and thermally quieter
brace_height        = 0.80;         // kept near rear plane to preserve air gap
brace_anchor_inset  = 1.20;         // places brace anchors inside perimeter wall

// ============================================================
// F) HIDDEN ADHESIVE MOUNTS
// ============================================================
mounts_enabled     = true;
mount_pad_width    = 30.0;
mount_pad_height   = 48.0;
mount_pad_radius   = 4.0;
mount_pad_proud    = 0.90;          // adhesive face behind rear plane
mount_core_height  = 1.25;          // enough stiffness; stays well below roof locally
mount_x_offset     = 59.0;
mount_y_offset     = 52.0;

// Slightly larger low rear foot under each pad spreads brace load without
// approaching the cosmetic shell.
mount_foot_margin  = 2.0;
mount_foot_height  = 0.80;

// ============================================================
// G) NUMERICAL / BOOLEAN TOLERANCES
// ============================================================
eps = 0.02;

// ============================================================
// H) ADVANCED FACET LAYOUT / DERIVED DIMENSIONS
// ============================================================
R = point_to_point / 2;
H = R * sqrt(3) / 2;
flat_to_flat = 2 * H;

// 0..5 = regular-hex perimeter, 6..10 = asymmetric interior controls.
xy_norm = [
    [ 1.00,  0.00],
    [ 0.50,  0.8660254038],
    [-0.50,  0.8660254038],
    [-1.00,  0.00],
    [-0.50, -0.8660254038],
    [ 0.50, -0.8660254038],
    [ 0.18,  0.06],
    [-0.38,  0.20],
    [ 0.36, -0.30],
    [-0.18, -0.40],
    [ 0.02,  0.48]
];

triangles = [
    [1,6,0],
    [4,9,3],
    [5,9,4],
    [7,2,3],
    [9,7,3],
    [7,9,6],
    [8,5,0],
    [6,8,0],
    [9,8,6],
    [5,8,9],
    [10,7,6],
    [7,10,2],
    [1,10,6],
    [2,10,1]
];

z_values = [
    corner_z[0],
    corner_z[1],
    corner_z[2],
    corner_z[3],
    corner_z[4],
    corner_z[5],
    peak_relief,
    secondary_relief,
    secondary_relief - 0.5,
    low_relief,
    secondary_relief + 1.5
];

function pxy(i) = [xy_norm[i][0] * R, xy_norm[i][1] * R];
function p3(i, dz=0) = [pxy(i)[0], pxy(i)[1], z_values[i] + dz];

// X coordinate of the right-hand sloped perimeter at a given |Y|.
function side_x_at_y(y_abs) = R - y_abs / sqrt(3);

module hex2d(inset=0) {
    if (inset == 0)
        polygon(points=[for (i=[0:5]) pxy(i)]);
    else
        offset(delta=-inset)
            polygon(points=[for (i=[0:5]) pxy(i)]);
}

module rounded_rect_2d(w, h, r) {
    offset(r=r)
        square([max(eps, w - 2*r), max(eps, h - 2*r)], center=true);
}

module capsule_2d(a, b, width) {
    hull() {
        translate(a) circle(d=width);
        translate(b) circle(d=width);
    }
}

// ============================================================
// I) COSMETIC ROOF
// ============================================================
module facet_wedge(a, b, c) {
    pts = [
        p3(a), p3(b), p3(c),
        p3(a, -roof_skin), p3(b, -roof_skin), p3(c, -roof_skin)
    ];

    polyhedron(
        points=pts,
        faces=[
            [0,1,2],
            [5,4,3],
            [0,3,4,1],
            [1,4,5,2],
            [2,5,3,0]
        ],
        convexity=8
    );
}

module roof_skin_mesh() {
    union() {
        for (t = triangles)
            facet_wedge(t[0], t[1], t[2]);
    }
}

module under_roof_volume(overlap=roof_overlap) {
    // Volume from rear plane to just inside the cosmetic shell.
    union() {
        for (t = triangles) {
            a = t[0];
            b = t[1];
            c = t[2];
            pts = [
                [pxy(a)[0], pxy(a)[1], 0],
                [pxy(b)[0], pxy(b)[1], 0],
                [pxy(c)[0], pxy(c)[1], 0],
                p3(a, -roof_skin + overlap),
                p3(b, -roof_skin + overlap),
                p3(c, -roof_skin + overlap)
            ];
            polyhedron(
                points=pts,
                faces=[
                    [0,2,1],
                    [3,4,5],
                    [0,1,4,3],
                    [1,2,5,4],
                    [2,0,3,5]
                ],
                convexity=8
            );
        }
    }
}

// ============================================================
// J) HIDDEN PERIMETER WALL
// ============================================================
module perimeter_ring() {
    // The ring is clipped to the roof underside, so it cannot create a front border.
    intersection() {
        linear_extrude(height=peak_relief)
            difference() {
                hex2d();
                hex2d(perimeter_wall);
            }
        under_roof_volume();
    }
}

// ============================================================
// K) REAR MOUNTS + LOCAL LOAD PATHS
// ============================================================
module rear_mount(x, y) {
    // Adhesive pad itself. It is intentionally isolated from the cosmetic roof.
    translate([x, y, -mount_pad_proud])
        linear_extrude(height=mount_core_height + mount_pad_proud)
            rounded_rect_2d(mount_pad_width, mount_pad_height, mount_pad_radius);

    // Low rear foot spreads the two brace loads into the pad body.
    linear_extrude(height=mount_foot_height)
        translate([x, y])
            rounded_rect_2d(
                mount_pad_width + 2*mount_foot_margin,
                mount_pad_height + 2*mount_foot_margin,
                mount_pad_radius + mount_foot_margin
            );
}

module pad_braces(xsign, ysign) {
    x = xsign * mount_x_offset;
    y = ysign * mount_y_offset;

    // Start points are near the outer/top-or-bottom edges of the pad foot.
    side_start = [
        x + xsign * (mount_pad_width/2 + mount_foot_margin - brace_width/2),
        y
    ];

    cap_start = [
        x,
        y + ysign * (mount_pad_height/2 + mount_foot_margin - brace_width/2)
    ];

    // Side anchor lies inside the nearby diagonal perimeter wall.
    side_outer_x = side_x_at_y(abs(y));
    side_anchor = [
        xsign * (side_outer_x - brace_anchor_inset),
        y
    ];

    // Cap anchor lies just inside the upper/lower horizontal perimeter segment.
    cap_anchor = [
        x * 0.86,
        ysign * (H - brace_anchor_inset)
    ];

    linear_extrude(height=brace_height)
        intersection() {
            union() {
                capsule_2d(side_start, side_anchor, brace_width);
                capsule_2d(cap_start, cap_anchor, brace_width);
            }
            hex2d(perimeter_wall / 2);
        }
}

module rear_support_network() {
    if (rear_braces_enabled) {
        pad_braces( 1,  1);
        pad_braces(-1,  1);
        pad_braces( 1, -1);
        pad_braces(-1, -1);
    }
}

// ============================================================
// L) ASSEMBLY
// ============================================================
module tile_flat() {
    union() {
        roof_skin_mesh();
        perimeter_ring();

        if (mounts_enabled) {
            rear_mount( mount_x_offset,  mount_y_offset);
            rear_mount(-mount_x_offset,  mount_y_offset);
            rear_mount( mount_x_offset, -mount_y_offset);
            rear_mount(-mount_x_offset, -mount_y_offset);
        }

        rear_support_network();
    }
}

module final_model() {
    if (render_orientation == "vertical") {
        // Original lower flat edge becomes the bed-contact edge.
        // Rear-most adhesive faces are shifted to Y=0.
        translate([0, mount_pad_proud, H])
            rotate([90,0,0])
                tile_flat();
    } else {
        tile_flat();
    }
}

final_model();

// ============================================================
// DEFAULT v19 DIMENSIONS
// ============================================================
// point-to-point = 254.00 mm (10.000 in)
// flat-to-flat   = ~219.97 mm (8.660 in)
// maximum relief = 24.00 mm
// overall depth including rear pad proud = ~24.90 mm
// cosmetic shell = 1.90 mm
// no long ribs or rails cross behind the visible face
