/*
  Parametric Faceted Hex Wall Tile v20 — Safe Rear Envelope
  ---------------------------------------------------------
  Goals:
    - Preserve the bold, borderless 14-facet cosmetic face from v18/v19.
    - Prevent ALL adhesive pads, pad feet, and local braces from crossing the
      projected hex silhouette or becoming visible above/below the sloped edges.
    - Keep the cosmetic face isolated from rear mounting structure.
    - Keep a true open back and four useful adhesive pads.
    - Maintain vertical-print orientation with a full lower flat edge on the bed.

  Construction:
    1) 1.90 mm faceted cosmetic roof.
    2) Profiled hidden perimeter wall clipped below the roof.
    3) Very shallow rear perimeter flange (part of the perimeter structure).
    4) Four smaller adhesive pads, all inside a 12 mm inset keep-out boundary.
    5) Short V braces from each pad to an inner structural ring.
    6) No long cross-tile rails and no central ribs behind the cosmetic face.

  Units: millimeters
*/

// ============================================================
// A) GLOBAL QUALITY / EXPORT
// ============================================================
$fn = 56;
render_orientation = "vertical";   // "flat" or "vertical"

// ============================================================
// B) TILE SIZE
// ============================================================
point_to_point = 254.0;            // 10.000 in vertex-to-vertex

// ============================================================
// C) COSMETIC FACE / RELIEF
// ============================================================
roof_skin        = 1.90;
edge_relief      = 3.20;
peak_relief      = 24.00;
secondary_relief = 15.50;
low_relief       = 7.20;

// Keep the established asymmetric perimeter profile.
corner_z = [
    edge_relief + 0.4,              // right
    edge_relief + 1.2,              // upper-right
    edge_relief + 0.2,              // upper-left
    edge_relief + 0.0,              // left
    edge_relief + 0.6,              // lower-left
    edge_relief + 0.1               // lower-right
];

// ============================================================
// D) HIDDEN PERIMETER STRUCTURE
// ============================================================
perimeter_wall        = 2.40;
roof_overlap          = 0.18;       // positive union into roof underside
rear_flange_height    = 0.70;       // shallow rear-only perimeter flange
rear_keepout_inset    = 12.0;       // mounts/braces cannot enter this edge zone
inner_ring_width      = 4.0;        // low structural ring just inside keep-out

// ============================================================
// E) REAR SUPPORT SYSTEM
// ============================================================
rear_braces_enabled = true;
brace_width         = 6.00;
brace_height        = 0.70;

// ============================================================
// F) HIDDEN ADHESIVE MOUNTS
// ============================================================
mounts_enabled      = true;
mount_pad_width     = 28.0;
mount_pad_height    = 42.0;
mount_pad_radius    = 4.0;
mount_pad_proud     = 0.90;         // adhesive surface behind rear plane
mount_core_height   = 1.00;         // top of pad body remains near rear plane
mount_foot_margin   = 1.50;
mount_foot_height   = 0.70;
mount_x_offset      = 52.0;
mount_y_offset      = 44.0;

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

// Right sloped edge X at |Y| for an inward offset measured normal to the side.
function side_x_at_y_inset(y_abs, inset) =
    R - (2 * inset / sqrt(3)) - y_abs / sqrt(3);

module hex2d(inset=0) {
    if (inset <= 0)
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

// Hard 2D safety envelope for pads, feet, and braces.
module safe_rear_region_2d() {
    hex2d(rear_keepout_inset);
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
// J) HIDDEN PERIMETER WALL + REAR FLANGE
// ============================================================
module perimeter_ring() {
    intersection() {
        linear_extrude(height=peak_relief)
            difference() {
                hex2d();
                hex2d(perimeter_wall);
            }
        under_roof_volume();
    }
}

module rear_perimeter_flange() {
    // This is intentionally part of the perimeter structure and is the ONLY
    // rear feature allowed inside the 12 mm visual keep-out zone.
    linear_extrude(height=rear_flange_height)
        difference() {
            hex2d();
            hex2d(rear_keepout_inset);
        }
}

module inner_structural_ring() {
    // Ring is entirely inside the visual keep-out boundary.
    linear_extrude(height=brace_height)
        difference() {
            hex2d(rear_keepout_inset);
            hex2d(rear_keepout_inset + inner_ring_width);
        }
}

// ============================================================
// K) SAFE REAR MOUNTS + SHORT LOCAL LOAD PATHS
// ============================================================
module rear_mount_raw(x, y) {
    translate([x, y, -mount_pad_proud])
        linear_extrude(height=mount_core_height + mount_pad_proud)
            rounded_rect_2d(mount_pad_width, mount_pad_height, mount_pad_radius);

    linear_extrude(height=mount_foot_height)
        translate([x, y])
            rounded_rect_2d(
                mount_pad_width + 2*mount_foot_margin,
                mount_pad_height + 2*mount_foot_margin,
                mount_pad_radius + mount_foot_margin
            );
}

module rear_mount(x, y) {
    // Hard clipping makes silhouette escape impossible even if parameters are
    // later changed carelessly.
    intersection() {
        rear_mount_raw(x, y);
        translate([0,0,-mount_pad_proud-eps])
            linear_extrude(height=mount_core_height + mount_pad_proud + 2*eps)
                safe_rear_region_2d();
    }
}

module pad_braces_raw(xsign, ysign) {
    x = xsign * mount_x_offset;
    y = ysign * mount_y_offset;

    side_start = [
        x + xsign * (mount_pad_width/2 + mount_foot_margin - brace_width/2),
        y
    ];

    cap_start = [
        x,
        y + ysign * (mount_pad_height/2 + mount_foot_margin - brace_width/2)
    ];

    ring_mid_inset = rear_keepout_inset + inner_ring_width/2;

    side_anchor = [
        xsign * side_x_at_y_inset(abs(y), ring_mid_inset),
        y
    ];

    cap_anchor = [
        x * 0.84,
        ysign * (H - ring_mid_inset)
    ];

    union() {
        capsule_2d(side_start, side_anchor, brace_width);
        capsule_2d(cap_start, cap_anchor, brace_width);
    }
}

module pad_braces(xsign, ysign) {
    if (rear_braces_enabled) {
        linear_extrude(height=brace_height)
            intersection() {
                pad_braces_raw(xsign, ysign);
                safe_rear_region_2d();
            }
    }
}

module rear_support_network() {
    inner_structural_ring();

    pad_braces( 1,  1);
    pad_braces(-1,  1);
    pad_braces( 1, -1);
    pad_braces(-1, -1);
}

// ============================================================
// L) ASSEMBLY
// ============================================================
module tile_flat() {
    union() {
        roof_skin_mesh();
        perimeter_ring();
        rear_perimeter_flange();
        rear_support_network();

        if (mounts_enabled) {
            rear_mount( mount_x_offset,  mount_y_offset);
            rear_mount(-mount_x_offset,  mount_y_offset);
            rear_mount( mount_x_offset, -mount_y_offset);
            rear_mount(-mount_x_offset, -mount_y_offset);
        }
    }
}

module final_model() {
    if (render_orientation == "vertical") {
        // Lower flat hex edge rests on the bed. Rear-most adhesive faces are Y=0.
        translate([0, mount_pad_proud, H])
            rotate([90,0,0])
                tile_flat();
    } else {
        tile_flat();
    }
}

final_model();

// ============================================================
// DEFAULT v20 DIMENSIONS / INTENT
// ============================================================
// point-to-point        = 254.00 mm (10.000 in)
// flat-to-flat          = ~219.97 mm (8.660 in)
// maximum front relief  = 24.00 mm
// overall depth         = ~24.90 mm including adhesive-pad proud
// cosmetic shell        = 1.90 mm
// pad size              = 28 x 42 mm
// pad centers           = +/-52 x +/-44 mm
// hard rear keep-out    = 12 mm from every visible hex edge
// no long ribs/rails cross behind the cosmetic face
