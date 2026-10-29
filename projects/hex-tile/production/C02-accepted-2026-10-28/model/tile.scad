/* Faceted architectural hex tile — candidate C02, NOT production released.
 * Standalone; OpenSCAD >= 2021.01. Units: mm.
 * Read ENGINEERING.md before printing or installing.
 * Local coordinates: XY = wall plane; rear tape plane Z=0; display +Z.
 * Upright output: local +Y becomes printer +Z; display faces printer -Y.
 * No temporary connections, supports, or adhesion geometry are in this CAD.
 */

/* [Output] */
mode = "trial_single"; // [trial_single,trial_pair,inspect,section]

/* [Product] */
corner_diameter = 152.4;
edge_depth = 9;
facet_rise = 10;

/* [Face pattern] */
// Relative rises of junctions A, B, C, D. Pattern XY is fixed and reproducible.
// A=upper-left interior, B=upper-center, C=right-center, D=lower-left interior.
// E=lower-right interior is derived to keep the broad right-hand face planar.
facet_profile = [0.80, 0.55, 1.00, 0.60];

/* [Shell] */
skin_axial = 2.4;       // Offset along local Z, NOT the facet-normal thickness.
perimeter_wall = 2.4;   // In-plane normal offset of the cavity hexagon.
roof_slope = 1;         // Local Z advance per local Y rise: 1 = 45 degrees.

/* [Mounting] */
land_width = 17.7;      // In-plane normal width; U-shaped, open at the top.
land_thickness = 2.4;
tape_width = 12.7;
tape_edge_allowance = 2.5; // Per side, for width placement tolerance.

/* [Manufacturing] */
pair_gap = 20;          // Minimum raw-model gap, along printer Y.
planned_brim = 8;       // Slicer allowance only; actual brim must be added there.
machine_margin = 5;    // In addition to brim, each XY side.
build_x = 256;         // Assumed machine envelope; replace with actual usable size.
build_y = 256;
build_z = 256;
z_clearance = 5;
nominal_line_width = 0.45;

/* [Validation limits] */
minimum_face_isolation = 1.6; // Conservative CLEAR AIR to underside of face skin.
minimum_skin_normal = 2;
minimum_cavity_radius = 20;
maximum_overhang_step_ratio = 1; // Horizontal layer advance / vertical layer rise.
nominal_size_tolerance = 1.524; // +/-1% of 152.4; resizing needs a new product review.

/* [Hidden] */
eps = 0.02;
r = corner_diameter/2;
a = r*cos(30);
depth = edge_depth + facet_rise;
// Six boundary corners followed by five image-inspired interior junctions.
// All XY coordinates below are normalized to corner radius, not apothem.
pattern_xy = concat([for (i=[0:5]) [cos(60*i),sin(60*i)]],
                    [[-0.36,0.18],[0.02,0.46],[0.16,0.05],
                     [-0.16,-0.38],[0.34,-0.28]]);
right_normal = [cos(30),-sin(30)];
function dot2(u,v) = u[0]*v[0]+u[1]*v[1];
valid_profile = assert(len(facet_profile) == 4 && min(facet_profile) > 0 &&
                       max(facet_profile) == 1,
                       "Face profile needs four positive fractions, max exactly 1.")
                facet_profile;
e_fraction = valid_profile[2]*(cos(30)-dot2(right_normal,pattern_xy[10]))/
                             (cos(30)-dot2(right_normal,pattern_xy[8]));
pattern_heights = concat([0,0,0,0,0,0],valid_profile,[e_fraction]);
// Explicit CCW triangles in XY; two adjacent triangles intentionally form
// one coplanar broad right-hand facet. No runtime/random triangulation.
pattern_triangles = [[1,8,0],[4,9,3],[5,9,4],[1,7,8],[2,7,1],
                     [9,10,8],[5,10,9],[8,10,0],[10,5,0],
                     [6,2,3],[6,7,2],[9,6,3],[6,9,8],[7,6,8]];
function cross2(u,v) = u[0]*v[1]-u[1]*v[0];
function triangle_gradient(t) =
    let(u=(pattern_xy[t[1]]-pattern_xy[t[0]])*r,
        v=(pattern_xy[t[2]]-pattern_xy[t[0]])*r,
        du=(pattern_heights[t[1]]-pattern_heights[t[0]])*facet_rise,
        dv=(pattern_heights[t[2]]-pattern_heights[t[0]])*facet_rise,
        det=cross2(u,v))
    [(du*v[1]-dv*u[1])/det,(u[0]*dv-v[0]*du)/det];
facet_gradient = max([for (t=pattern_triangles) norm(triangle_gradient(t))]);
normal_factor = sqrt(1 + facet_gradient*facet_gradient);
skin_normal = skin_axial/normal_factor;
air_gap_bound = (edge_depth-skin_axial-land_thickness)/normal_factor;
cavity_r = (a-perimeter_wall)/cos(30);
open_r = (a-land_width)/cos(30);
count = mode == "trial_pair" ? 2 : 1;
envelope_x = corner_diameter+2*(planned_brim+machine_margin);
envelope_y = count*depth+(count-1)*pair_gap+2*(planned_brim+machine_margin);
envelope_z = 2*a+z_clearance;

assert(mode == "trial_single" || mode == "trial_pair" ||
       mode == "inspect" || mode == "section", "Unknown output mode.");
assert(abs(corner_diameter-152.4) <= nominal_size_tolerance &&
       nominal_size_tolerance >= 0 && nominal_size_tolerance <= 1.524,
       "Size must retain the 6-inch identity (+/-1% maximum).");
assert(edge_depth > 0 && facet_rise > 0 && depth <= 25,
       "Depth must be positive and <=25 mm for this candidate family.");
assert(e_fraction > 0 && e_fraction <= 1,
       "Derived E junction must remain in (0,1].");
assert(min([for(t=pattern_triangles)
            cross2(pattern_xy[t[1]]-pattern_xy[t[0]],
                   pattern_xy[t[2]]-pattern_xy[t[0]])]) > 0,
       "Face topology has a reversed or degenerate triangle.");
assert(skin_axial > 0 && minimum_skin_normal >= 2 &&
       skin_normal >= minimum_skin_normal, "Facet-normal skin is too thin.");
assert(nominal_line_width >= 0.25 && nominal_line_width <= 0.8 &&
       perimeter_wall >= 4*nominal_line_width &&
       land_thickness >= 4*nominal_line_width,
       "Perimeter and land need at least four nominal extrusion widths.");
assert(land_width > perimeter_wall && perimeter_wall >= skin_normal/2,
       "Invalid land / perimeter relationship.");
assert(minimum_face_isolation >= 1.6 && air_gap_bound >= minimum_face_isolation,
       "Rear land has insufficient conservative face-skin air isolation.");
assert(tape_width >= 12.7 && tape_edge_allowance >= 2 &&
       land_width >= tape_width+2*tape_edge_allowance,
       "Tape land cannot accommodate tape plus placement tolerance.");
assert(minimum_cavity_radius >= 20 && open_r >= minimum_cavity_radius &&
       cavity_r > open_r, "Cavity/land opening invalid or insufficiently hollow.");
assert(roof_slope > 0 && roof_slope <= maximum_overhang_step_ratio &&
       maximum_overhang_step_ratio > 0 && maximum_overhang_step_ratio <= 1 &&
       facet_gradient <= maximum_overhang_step_ratio,
       "Roof or facet exceeds the allowed geometric layer advance.");
assert(edge_depth/roof_slope + perimeter_wall < a-land_width,
       "Roof transition consumes too much of the upper cavity.");
assert(planned_brim >= 0 && machine_margin >= 0 && z_clearance >= 0 &&
       pair_gap >= 2*planned_brim+2,
       "Negative allowance, or pair brims overlap / have <2 mm clearance.");
assert(build_x > 0 && build_y > 0 && build_z > 0,
       "Build volume must be positive.");
if (mode == "trial_single" || mode == "trial_pair") {
    assert(envelope_x <= build_x && envelope_y <= build_y &&
           envelope_z <= build_z, "Print layout plus allowances exceeds build volume.");
}

echo(candidate="C02", output=mode, readiness="UNRELEASED GEOMETRY CANDIDATE");
echo(product_dimensions=[corner_diameter,2*a,depth],
     skin_normal_mm=skin_normal, face_air_gap_lower_bound_mm=air_gap_bound,
     maximum_face_gradient=facet_gradient, junction_fractions=pattern_heights);
echo(raw_upright_dimensions=[corner_diameter,count*depth+(count-1)*pair_gap,2*a],
     allowed_print_envelope=[envelope_x,envelope_y,envelope_z]);

function hex_points(radius) = [for (i=[0:5]) [radius*cos(60*i),radius*sin(60*i)]];

// Closed piecewise-planar height field plus straight perimeter skirt.
// Interior heights are selected design values, not recovered image depths.
// The same entire topology is translated for the inner skin, including valleys.
module faceted_volume(bottom, face_offset=0) {
    n = len(pattern_xy);
    polyhedron(
        points=concat([for (i=[0:5]) [r*pattern_xy[i][0],r*pattern_xy[i][1],bottom]],
                      [for (i=[0:n-1]) [r*pattern_xy[i][0],r*pattern_xy[i][1],
                                        edge_depth+facet_rise*pattern_heights[i]-face_offset]]),
        faces=concat([[0,1,2,3,4,5]],
                     [for (i=[0:5]) [i,6+i,6+(i+1)%6,(i+1)%6]],
                     [for (t=pattern_triangles) [6+t[2],6+t[1],6+t[0]]]), convexity=10);
}

// Cavity limit: y + z/roof_slope <= a-perimeter_wall.
// As print height increases, roof grows continuously FROM the face toward rear.
// Reversing this plane would create a floating rear lip; keep this sign.
module below_roof() {
    multmatrix([[0,0,1,0],[1,0,0,0],[0,1,0,0],[0,0,0,1]])
        linear_extrude(height=4*r,center=true)
            polygon([[-2*r,-eps],
                     [a-perimeter_wall+eps/roof_slope,-eps],
                     [a-perimeter_wall-2*depth/roof_slope,2*depth],
                     [-2*r,2*depth]]);
}

module shell() {
    difference() {
        faceted_volume(0);
        intersection() {
            faceted_volume(-eps,skin_axial);
            translate([0,0,-eps])
                linear_extrude(height=depth+2*eps)
                    polygon(hex_points(cavity_r));
            below_roof();
        }
    }
}

// Integral rear land. No top crossbar: avoids a long bridge across the opening.
// Top cutoff only removes material as upright layers rise, creating no islands.
module tape_land() {
    linear_extrude(height=land_thickness)
        intersection() {
            difference() {
                polygon(hex_points(r));
                polygon(hex_points(open_r));
            }
            translate([-2*r,-2*r]) square([4*r,2*r+a-land_width]);
        }
}

module tile() {
    union() { shell(); tape_land(); }
}

module upright() {
    translate([0,0,a]) rotate([90,0,0]) tile();
}

// Trial layouts centered on the configured rectangular usable build surface.
// Brim/margins are reserved numerically; they are not exported as plastic.
module trial_layout() {
    for (i=[0:count-1])
        translate([build_x/2,
                   build_y/2-(count*depth+(count-1)*pair_gap)/2+depth+i*(depth+pair_gap),0])
            upright();
}

if (mode == "trial_single" || mode == "trial_pair") trial_layout();
else if (mode == "inspect") tile();
else if (mode == "section")
    intersection() {
        tile();
        translate([0,-2*r,-eps]) cube([2*r,4*r,depth+2*eps]);
    }
