/*
  Parametric Faceted Hex Wall Tile v17
  -----------------------------------
  Goals:
    - 10 in point-to-point regular hex by default
    - stronger asymmetric low-poly relief
    - open-back shell for lower weight / faster printing
    - four hidden shallow adhesive mounting pads
    - no perimeter tabs or ears
    - vertical export orientation with a full flat edge on the bed
    - mount load rails separated from general stiffening ribs

  Units: millimeters
*/

$fn = 48;

// ============================================================
// A) GLOBAL QUALITY / EXPORT
// ============================================================
render_orientation  = "vertical"; // "flat" or "vertical"

// ============================================================
// B) TILE SIZE
// ============================================================
point_to_point      = 254.0;   // 10.000 in; left vertex to right vertex

// ============================================================
// C) FACE / RELIEF
// ============================================================
roof_skin           = 1.60;    // vertical skin thickness
edge_relief         = 3.20;    // lower perimeter makes the planes read more strongly
peak_relief         = 24.00;   // dominant architectural peak
secondary_relief    = 15.50;
low_relief          = 7.20;

// Fine-tune the six outer corners clockwise from rightmost.
corner_z = [
    edge_relief + 0.4,  // right
    edge_relief + 1.2,  // upper-right
    edge_relief + 0.2,  // upper-left
    edge_relief + 0.0,  // left
    edge_relief + 0.6,  // lower-left
    edge_relief + 0.1   // lower-right
];

// ============================================================
// D) SHELL
// ============================================================
perimeter_wall      = 2.20;    // wall thickness measured inward
wall_height         = 5.00;    // ensures positive overlap with roof underside

// ============================================================
// E) STRUCTURAL RIBS
// ============================================================
add_cross_ribs      = true;
add_mount_rails     = true;
cross_rib_width     = 1.80;    // general anti-twist ribs
mount_rail_width    = 3.00;    // wider rails carry adhesive-pad loads
rib_height          = 3.50;

// ============================================================
// F) HIDDEN ADHESIVE MOUNTS
// ============================================================
mounts_enabled      = true;
mount_pad_width     = 30.0;
mount_pad_height    = 48.0;
mount_pad_radius    = 4.0;
mount_pad_proud     = 0.90;    // how far pad face sits behind rear plane
mount_core_height   = 3.60;    // core overlaps the structural rails for a positive union
mount_x_offset      = 59.0;
mount_y_offset      = 52.0;

// ============================================================
// G) NUMERICAL / BOOLEAN TOLERANCES
// ============================================================
eps                 = 0.02;

// ============================================================
// H) ADVANCED FACET LAYOUT / DERIVED DIMENSIONS
// ============================================================
R = point_to_point / 2;
H = R * sqrt(3) / 2;
flat_to_flat = 2 * H;

// Normalized XY point set. 0..5 are the regular-hex perimeter.
// 6..10 are deliberately asymmetric interior control points.
xy_norm = [
    [ 1.00,  0.00],
    [ 0.50,  0.8660254038],
    [-0.50,  0.8660254038],
    [-1.00,  0.00],
    [-0.50, -0.8660254038],
    [ 0.50, -0.8660254038],
    [ 0.18,  0.06],   // dominant peak control, pushed off-center
    [-0.38,  0.20],   // left shoulder
    [ 0.36, -0.30],   // lower-right ridge
    [-0.18, -0.40],   // lower basin/transition
    [ 0.02,  0.48]    // upper secondary ridge
];

// Delaunay-style triangulation over the six perimeter and five interior points.
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

// Relief values for all 11 points.
// Interior values are intentionally non-radial to avoid a centered "tent" look.
z_values = [
    corner_z[0],
    corner_z[1],
    corner_z[2],
    corner_z[3],
    corner_z[4],
    corner_z[5],
    peak_relief,              // 6 - dominant peak, slightly right/below center
    secondary_relief,         // 7 - left shoulder
    secondary_relief - 0.5,   // 8 - lower-right ridge
    low_relief,               // 9 - lower transition
    secondary_relief + 1.5    // 10 - upper ridge
];

function pxy(i) = [xy_norm[i][0] * R, xy_norm[i][1] * R];
function p3(i, dz=0) = [pxy(i)[0], pxy(i)[1], z_values[i] + dz];

module hex2d(inset=0) {
    if (inset == 0)
        polygon(points=[for (i=[0:5]) pxy(i)]);
    else
        offset(delta=-inset)
            polygon(points=[for (i=[0:5]) pxy(i)]);
}

module rounded_rect_2d(w, h, r) {
    // offset/square construction stays stable for parameter changes.
    offset(r=r)
        square([max(eps, w-2*r), max(eps, h-2*r)], center=true);
}

module facet_wedge(a, b, c) {
    // A thin, vertically offset triangular roof panel.
    // Unioning all wedges gives a continuous faceted skin.
    pts = [
        p3(a), p3(b), p3(c),
        p3(a, -roof_skin), p3(b, -roof_skin), p3(c, -roof_skin)
    ];

    polyhedron(
        points=pts,
        faces=[
            [0,1,2],      // top
            [5,4,3],      // underside
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

module perimeter_ring() {
    linear_extrude(height=wall_height)
        difference() {
            hex2d();
            hex2d(perimeter_wall);
        }
}

module rear_mount(x, y) {
    // Rear adhesive face is only mount_pad_proud behind the global rear plane.
    // Pads intersect the structural mounting rails.
    // Rails distribute mounting load into the perimeter shell.
    translate([x, y, -mount_pad_proud])
        linear_extrude(height=mount_core_height + mount_pad_proud)
            rounded_rect_2d(mount_pad_width, mount_pad_height, mount_pad_radius);
}

module structural_ribs() {
    // General ribs stabilize the open shell; wider mount rails tie the
    // adhesive pads mechanically into the perimeter.
    if (add_cross_ribs || add_mount_rails) {
        intersection() {
            linear_extrude(height=rib_height)
                union() {
                    if (add_cross_ribs) {
                        square([point_to_point, cross_rib_width], center=true);
                        square([cross_rib_width, flat_to_flat], center=true);
                    }

                    if (add_mount_rails) {
                        // These rails pass directly through the four pad centers
                        // and reach the perimeter ring at both ends.
                        translate([0, mount_y_offset])
                            square([point_to_point, mount_rail_width], center=true);
                        translate([0, -mount_y_offset])
                            square([point_to_point, mount_rail_width], center=true);
                    }
                }
            linear_extrude(height=rib_height)
                hex2d();
        }
    }
}

module tile_flat() {
    union() {
        roof_skin_mesh();
        perimeter_ring();
        structural_ribs();

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
        // Rotate so the original lower flat of the hex becomes the print-bed edge.
        // Move rear-most adhesive faces up to Y=0 for predictable slicer placement.
        translate([0, mount_pad_proud, H])
            rotate([90,0,0])
                tile_flat();
    } else {
        tile_flat();
    }
}

final_model();

// Expected default overall flat dimensions (v17 bold-relief face):
// point-to-point = 254.00 mm (10.000 in)
// flat-to-flat   = ~219.97 mm (8.660 in)
