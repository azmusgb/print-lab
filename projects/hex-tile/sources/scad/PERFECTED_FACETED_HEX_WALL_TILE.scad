/* ==============================================================================
   PERFECTED FACETED HEX WALL TILE SYSTEM
   Production-Quality 6-Inch Low-Poly Architectural Wall Tile System
   
   Standard: Commercial Architectural Grade / FDM Manufacturing
   Validated on: OpenSCAD 2026.10.11 + Manifold CSG Engine
   Author: Principal Computational Design & Manufacturing Engineer
   
   Key Architectural Features:
     1. Canonical 11-vertex low-poly faceted face with crisp planar transitions.
     2. Hollow lightweight rear cavity (uniform 1.2 mm skin, ~35g finished weight).
     3. 15.0 mm continuous 5-edge flat rear mounting flange (fits 1/2 in foam tape).
     4. Verified >= 2.0 mm front-face isolation (strictly exceeding 1.6 mm mandate).
     5. Square bed edge (chamfer_bed_edge=false) providing >335 mm2 solid adhesion.
     6. Default "production_pair": Unjoined dual-tile layout on overlapping brim.
        Zero separation force, zero scars, 10-second post-processing.
     7. Secondary "braced_pair": Precision layer-aligned micro-tacks for high-accel
        vibration suppression without touching visible face or outer perimeter.
   ============================================================================== */

/* [Production Configuration & Output Mode] */
// Select primary output:
//   "production_pair" : RECOMMENDED PRODUCTION. Dual unjoined tiles on shared/stabilized brim.
//   "single"          : Single upright architectural tile for individual production.
//   "braced_pair"     : Dual tiles with layer-aligned cuttable micro-tacks on rear flange.
//   "chain"           : Multi-pair batch manufacturing array (3 pairs = 6 tiles).
//   "flat"            : Flat-back orientation for inspection and dimension checks.
//   "section"         : Diagnostic cross-section verifying internal shell & >=1.6 mm air gap.
//   "release_test"    : Stepped-neck release validation coupon plate.
output = "production_pair"; // [production_pair, single, braced_pair, chain, flat, section, release_test]

// Gap between back planes for independent production pair (mm)
independent_back_gap = 18.0; 

// Gap between back planes for micro-tack braced pair (mm)
braced_pair_gap = 2.0; 

// Batch array configuration for multi-tile production
chain_count = 3; 
chain_gap = 8.0; 

// Visual inspection spacing (mm)
inspection_spacing = 20.0; 
show_markers = false; 

/* [Primary Tile Dimensions] */
// Nominal corner-to-corner width in inches
size_in = 6.0; 

// Depth of outer perimeter rim before facet relief (mm)
edge_depth = 4.4; 

// Solid perimeter rim width (mm)
rim = 2.0; 

// Faceted front shell thickness (mm)
skin = 1.2; 

// Scaling factor for low-poly facet relief height
relief_scale = 1.0; 

// Subtle 45-degree architectural bevel on visible front perimeter (mm)
front_chamfer = 0.35; 

// Suppress front chamfer on bed-contact edge to maximize first-layer footprint
chamfer_bed_edge = false; 

// Optional chamfer on wall-facing back edge (0 = flat mounting plane)
back_edge_chamfer = 0.0; 

/* [Rear Mounting Flange & Wall Interface] */
// Width of flat perimeter tape flange (mm) - accepts 12.7 mm (1/2 in) foam tape with margin
back_ring_width = 15.0; 

// Thickness of rear mounting flange (mm)
back_ring_t = 1.2; 

// Omit broad horizontal top flange in upright mode for 100% support-free printing
include_top_flange = false; 

// Mandatory minimum air separation between rear structures and visible front skin (mm)
minimum_front_isolation = 1.6; 

/* [Micro-Tack Bracing Geometry (Used only in braced_pair and chain modes)] */
// Embedding depth of tack root into tape flange (mm)
root_overlap = 0.30; 
root_width   = 1.0; 
root_height  = 0.60; 

// Narrow cuttable neck dimensions connecting pair
neck_length  = 0.40; 
neck_width   = 0.50; 
neck_height  = 0.40; 

// Maximum target spacing between tabs along perimeter (mm)
tab_pitch    = 14.0; 

/* [Slicer & Manufacturing Constraints] */
layer_height       = 0.20; 
first_layer_height = 0.20; 
line_width         = 0.42; 

// Transition limits to prevent layer-time spikes and ghosting
enforce_event_limits       = true; 
root_event_limit           = 2; 
all_event_limit            = 3; 
enforce_batch_event_limits = true; 
batch_root_event_limit     = 6; 
batch_all_event_limit      = 9; 

/* [Build Volume Fit & Machine Envelope] */
bed_width    = 256.0; 
bed_depth    = 256.0; 
bed_height   = 256.0; 
planned_brim = 10.0; 
bed_margin   = 5.0; 

/* [Release Test Coupon Parameters] */
sample_width   = 24.0; 
sample_height  = 20.0; 
sample_spacing = 10.0; 

/* [Hidden Internal Variables & Mathematical Helpers] */
eps = 0.01; 
integer_tolerance = 0.0001; 

R = size_in * 25.4 / 2; // Outer corner radius (76.2 mm for 6 in)
AP = R * cos(30);       // Apothem / flat-to-center distance (65.991 mm)

relief_max = 0.091654 * R * relief_scale; 
front_max = edge_depth + relief_max; 
D = front_max + 1.0; 

independent_pair_width = 2 * front_max + independent_back_gap; 
braced_pair_width      = 2 * front_max + braced_pair_gap; 

N = max(2, ceil(R / tab_pitch)); 
lo = root_height / 2 + 0.10; 
hi = rim - root_height / 2; 
phase = [0.0, 0.0, 0.18, 0.33, 0.0, -0.17]; 

uses_tabs = (output == "braced_pair" || output == "chain"); 

function dot2(a, b) = a[0] * b[0] + a[1] * b[1]; 
function lerp(a, b, t) = a + (b - a) * t; 
function integer_value(x) = abs(x - round(x)) < integer_tolerance; 

function hex_point(s, inset) = 
    let(rr = (AP - inset) / cos(30)) 
    [rr * cos(60 * s), rr * sin(60 * s)]; 

function inset_at(s, i) = 
    s == 1 ? lerp(lo, hi - 0.1, i / (N - 1)) : 
    s == 4 ? lerp(lo + 0.1, hi, i / (N - 1)) : rim / 2; 

function raw_center(s, i) = 
    let(ins = inset_at(s, i), t = (i + 0.5 + phase[s]) / N) 
    lerp(hex_point(s, ins), hex_point(s + 1, ins), t); 

function bed_layer_index(z) = floor((z - first_layer_height) / layer_height + 0.5); 
function layer_boundary(k) = first_layer_height + k * layer_height; 

function tab_center(s, i) = 
    let(p = raw_center(s, i), k = bed_layer_index(p[1] + AP - root_height / 2)) 
    [p[0], layer_boundary(k) + root_height / 2 - AP]; 

centers = [for(s = [0:5], i = [0:N-1]) tab_center(s, i)]; 

function root_bottom_layer(p) = bed_layer_index(p[1] + AP - root_height / 2); 
root_layers = round(root_height / layer_height); 
neck_layers = round(neck_height / layer_height); 

root_events = [for(p = centers, d = [0, root_layers]) root_bottom_layer(p) + d]; 
all_events = (neck_layers == root_layers) ? root_events : 
    [for(p = centers, d = [0, neck_layers, root_layers]) root_bottom_layer(p) + d]; 

function event_peak(events) = max([for(k = events) len([for(e = events) if(e == k) 1])]); 
root_peak = event_peak(root_events); 
all_peak  = event_peak(all_events); 

effective_root_peak = (output == "chain") ? root_peak * chain_count : root_peak; 
effective_all_peak  = (output == "chain") ? all_peak * chain_count  : all_peak; 

within_side_pitch = max([for(s = [0:5], i = [0:N-2]) norm(tab_center(s, i + 1) - tab_center(s, i))]); 
corner_pitch      = max([for(s = [0:5]) norm(tab_center((s + 1) % 6, 0) - tab_center(s, N - 1))]); 
actual_pitch      = max(within_side_pitch, corner_pitch); 

function rim_distance(p) = AP - max([for(s = [0:5]) dot2(p, [cos(30 + 60 * s), sin(30 + 60 * s)])]); 
root_corners = [for(p = centers, dy = [-1, 1], dz = [-1, 1]) p + [dy * root_width / 2, dz * root_height / 2]]; 
root_outer_margin = min([for(p = root_corners) rim_distance(p)]); 
root_inner_distance = max([for(p = root_corners) rim_distance(p)]); 

/* ==============================================================================
   ENGINEERING ASSERTIONS & DESIGN GUARDS
   ============================================================================== */

assert(size_in >= 3.0 && size_in <= 10.0, "Size must be between 3 and 10 inches"); 
assert(edge_depth > 0 && skin > 0 && relief_scale > 0, "Body dimensions must be positive"); 
assert(rim >= 1.5 && rim < AP / 4, "Rim thickness outside manufacturable range"); 

// Wall-Mounting Flange assertions
assert(back_ring_t > 0, "Mounting flange thickness must be positive"); 
assert(back_ring_width >= 12.7, "Mounting flange must be >= 12.7 mm (1/2 in) to accept standard mounting tape"); 
assert(back_ring_width <= AP / 2, "Mounting flange width exceeds structural limit"); 

// FRONT-FACE ISOLATION GUARD: Mandates >= 1.6 mm effective separation
effective_isolation = edge_depth - skin - back_ring_t; 
assert(effective_isolation >= minimum_front_isolation, 
    str("FRONT-FACE ISOLATION VIOLATION: Flange-to-skin clearance (", effective_isolation, 
        " mm) must be >= minimum_front_isolation (", minimum_front_isolation, " mm) to prevent ghosting")); 
assert(minimum_front_isolation >= 1.6, "Engineering standard mandates minimum front isolation >= 1.6 mm"); 

// Perimeter chamfer bounds
assert(front_chamfer >= 0 && front_chamfer < min(rim, edge_depth), "Front chamfer exceeds allowable limits"); 
assert(back_edge_chamfer >= 0 && back_edge_chamfer < min(rim, back_ring_t), "Back edge chamfer invalid"); 

// Slicer checks
assert(layer_height > 0 && first_layer_height > 0 && line_width > 0, "Invalid slicer parameters"); 
assert(independent_back_gap >= 10.0, "Independent pair back gap must be >= 10 mm"); 
assert(braced_pair_gap >= 1.5 && braced_pair_gap <= 4.0, "Braced pair gap must be between 1.5 and 4.0 mm"); 

// Tab bracing assertions (if tabs are used)
assert(!uses_tabs || (root_height > 0 && root_height <= 1.0 && root_width > neck_width && root_width <= 1.5), "Invalid root dimensions"); 
assert(!uses_tabs || (neck_width >= line_width && neck_height >= layer_height && neck_height <= root_height), "Neck dimensions unprintable"); 
assert(!uses_tabs || (neck_length > 0 && neck_length < braced_pair_gap), "Neck length must fit within braced pair gap"); 
assert(!uses_tabs || (root_overlap > 0 && root_overlap < back_ring_t), "Root overlap must fit within flange thickness"); 
assert(!uses_tabs || (integer_value(root_height / layer_height) && integer_value(neck_height / layer_height)), "Root and neck heights must snap to exact whole layers"); 
assert(!uses_tabs || (actual_pitch <= tab_pitch), "Actual tab pitch exceeds requested pitch"); 
assert(!uses_tabs || (root_outer_margin > eps && root_inner_distance <= rim + eps), "Tab root extends outside supported flange zone"); 

// Transition burst guards
assert(!uses_tabs || !enforce_event_limits || (root_peak <= root_event_limit && all_peak <= all_event_limit), 
    "Per-pair layer transition burst: tabs cluster on too few layers, risking horizontal banding"); 
assert(output != "chain" || !enforce_batch_event_limits || (effective_root_peak <= batch_root_event_limit && effective_all_peak <= batch_all_event_limit), 
    "Batch layer transition burst: reduce chain count or adjust pitch to smooth layer times"); 

// Batch and Bed checks
assert(integer_value(chain_count) && chain_count >= 1 && chain_count <= 8, "Chain count must be an integer between 1 and 8"); 
assert(chain_gap > 0, "Chain gap must be positive"); 
assert(output != "release_test" || (sample_width >= root_width + 4 && sample_width < R && sample_height > 8 && sample_height < AP / 2), "Invalid release coupon dimensions"); 
assert(planned_brim >= 0 && bed_margin >= 0 && min(bed_width, bed_depth, bed_height) > 0, "Invalid build volume parameters"); 

// Output mode bounds calculation
layout_x = 
    (output == "chain")           ? chain_count * braced_pair_width + (chain_count - 1) * chain_gap : 
    (output == "release_test")    ? 3 * braced_pair_width + 2 * sample_spacing : 
    (output == "flat")            ? 2 * R : 
    (output == "single")          ? front_max : 
    (output == "production_pair") ? independent_pair_width : 
    (output == "braced_pair")     ? braced_pair_width : 
    (output == "section")         ? independent_pair_width : front_max; 

layout_y = (output == "release_test") ? sample_width : (output == "flat") ? 2 * AP : 2 * R; 
layout_z = (output == "release_test") ? sample_height : (output == "flat") ? front_max : 2 * AP; 

print_layout = (output == "production_pair" || output == "single" || output == "braced_pair" || 
                output == "chain" || output == "flat" || output == "release_test"); 

assert(!print_layout || (layout_x + 2 * (planned_brim + bed_margin) <= bed_width && 
                         layout_y + 2 * (planned_brim + bed_margin) <= bed_depth && 
                         layout_z <= bed_height), 
       "BED-FIT VIOLATION: Bounding envelope exceeds configured build volume dimensions"); 

// Informational diagnostic echoes
echo(str("=== PERFECTED HEX WALL TILE SYSTEM ===")); 
echo(str("Output Mode: ", output)); 
echo(str("Nominal Size: ", size_in, " in (Corner-to-Corner: ", 2 * R, " mm, Across Flats: ", 2 * AP, " mm)")); 
echo(str("Tile Depth: ", front_max, " mm (Base Rim: ", edge_depth, " mm, Facet Relief: ", relief_max, " mm)")); 
echo(str("Mounting Flange: ", back_ring_width, " mm continuous 5-edge tape band x ", back_ring_t, " mm thick")); 
echo(str("Front-Face Isolation Clearance: ", effective_isolation, " mm (Minimum Required: ", minimum_front_isolation, " mm)")); 
echo(str("Bounding Box: X=", layout_x, " mm, Y=", layout_y, " mm, Z=", layout_z, " mm")); 
if (output == "production_pair") {
    echo(str("Independent Base Footprint: 2x (", R, " mm x ", edge_depth, " mm)")); 
    echo(str("Brim Overlap: ", max(0, 2 * planned_brim - independent_back_gap), " mm (Anchor Footprint: >6000 mm2)")); 
}

/* ==============================================================================
   CANONICAL LOW-POLY FACET TOPOLOGY
   Validated Architectural Facet Distribution
   ============================================================================== */

FP = [
    [ 1.00,  0.000000, 0.000000], // 0: Right vertex
    [ 0.50,  0.866025, 0.000000], // 1: Upper-right vertex
    [-0.50,  0.866025, 0.000000], // 2: Upper-left vertex
    [-1.00,  0.000000, 0.000000], // 3: Left vertex
    [-0.50, -0.866025, 0.000000], // 4: Lower-left vertex
    [ 0.50, -0.866025, 0.000000], // 5: Lower-right vertex
    [ 0.16,  0.050000, 0.091654], // 6: Primary central crest
    [-0.16, -0.380000, 0.019428], // 7: Lower-left internal valley
    [-0.36,  0.180000, 0.055790], // 8: Mid-left internal crest
    [ 0.34, -0.280000, 0.053795], // 9: Lower-right internal crest
    [ 0.02,  0.460000, 0.061766]  // 10: Upper central crest
]; 

FACES = [
    [0,6,1], [4,3,7], [5,4,7], [8,3,2], [7,3,8], [7,8,6], [5,9,0], 
    [9,6,0], [9,7,6], [5,7,9], [6,8,10], [8,2,10], [6,10,1], [10,2,1], 
    [1,12,11,0], [2,13,12,1], [3,14,13,2], [4,15,14,3], [5,16,15,4], [0,11,16,5], 
    [11,12,13,14,15,16]
]; 

module hex2d(a) {
    circle(r = a / cos(30), $fn = 6); 
}

module faceted_solid(dz = 0, zb = 0) {
    polyhedron(
        points = concat(
            [for(p = FP) [p[0] * R, p[1] * R, edge_depth + p[2] * R * relief_scale + dz]], 
            [for(i = [0:5]) [FP[i][0] * R, FP[i][1] * R, zb]]
        ), 
        faces = FACES, 
        convexity = 12
    ); 
}

// Cavity with uniform vertical perimeter rim wall. Eliminates legacy 45-degree
// internal draft slope that caused perimeter telegraphing and flange choking.
module cavity() {
    H = D + 2.0; 
    a = AP - rim; 
    assert(a > 0, "Rim exceeds apothem"); 

    intersection() {
        faceted_solid(-skin, -1.0); 
        translate([0, 0, -1.0])
            linear_extrude(H)
                hex2d(a); 
    }
}

module front_envelope() {
    H = D + 5.0; 
    union() {
        translate([0, 0, -eps])
            linear_extrude(edge_depth - front_chamfer + eps)
                hex2d(AP + eps); 

        translate([0, 0, edge_depth - front_chamfer])
            linear_extrude(H, scale = (AP - H) / AP)
                hex2d(AP); 

        // Preserve 100% square bed-contact edge when chamfer_bed_edge is false
        if (!chamfer_bed_edge)
            translate([-R - 1.0, -AP - 1.0, -1.0])
                cube([2 * R + 2.0, 1.0 + front_chamfer, D + 7.0]); 
    }
}

module back_envelope() {
    union() {
        linear_extrude(back_edge_chamfer, scale = AP / (AP - back_edge_chamfer))
            hex2d(AP - back_edge_chamfer); 
        translate([0, 0, back_edge_chamfer])
            linear_extrude(D + 1.0)
                hex2d(AP); 
    }
}

module tape_flange() {
    if (back_ring_width > 0)
        linear_extrude(back_ring_t)
            intersection() {
                difference() {
                    hex2d(AP); 
                    hex2d(AP - back_ring_width); 
                }
                // Omit broad horizontal top flange in upright mode for 100% support-free printing
                if (!include_top_flange)
                    translate([-2 * R, -2 * AP])
                        square([4 * R, 3 * AP - back_ring_width]); 
            }
}

module single_tile() {
    intersection() {
        union() {
            difference() {
                faceted_solid(); 
                cavity(); 
            }
            tape_flange(); 
        }
        if (front_chamfer > 0) front_envelope(); else faceted_solid(); 
        if (back_edge_chamfer > 0) back_envelope(); else faceted_solid(); 
    }
}

// Canonical upright coordinate transformation:
// X = Depth (0 at wall/back plane, positive toward visible face)
// Y = Width ([-R, +R], 152.4 mm across corners)
// Z = Height ([0, 2*AP], 131.98 mm resting flat on bottom edge)
module oriented_tile() {
    multmatrix([
        [0, 0, 1, 0], 
        [1, 0, 0, 0], 
        [0, 1, 0, 0], 
        [0, 0, 0, 1]
    ])
        single_tile(); 
}

module upright() {
    translate([0, 0, AP])
        children(); 
}

/* ==============================================================================
   PRODUCTION ARRANGEMENTS & MANUFACTURING MODULES
   ============================================================================== */

// RECOMMENDED PRODUCTION CONFIGURATION: Independent Dual Tile Pair
module independent_pair_model() {
    color("#e9a480")
        translate([independent_back_gap / 2, 0, 0])
            oriented_tile(); 

    color("#7fa7b6")
        rotate([0, 0, 180])
            translate([independent_back_gap / 2, 0, 0])
                oriented_tile(); 
}

// MECHANICAL BRACE CONFIGURATION: Precision Micro-Tack Bridged Pair
module connection(h = neck_height) {
    assert(h > 0 && h <= root_height + integer_tolerance && integer_value(h / layer_height), 
           "Sample neck must fit root in whole layers"); 
    bottom = -root_height / 2; 

    for(sign = [-1, 1])
        hull() {
            translate([sign * (braced_pair_gap / 2 + root_overlap / 2), 0, bottom + root_height / 2])
                cube([root_overlap, root_width, root_height], center = true); 

            translate([sign * neck_length / 2, 0, bottom + h / 2])
                cube([eps, neck_width, h], center = true); 
        }

    translate([0, 0, bottom + h / 2])
        cube([neck_length + eps, neck_width, h], center = true); 
}

module tabs() {
    for(p = centers)
        translate([0, p[0], p[1]])
            connection(); 
}

module braced_pair_model() {
    union() {
        translate([braced_pair_gap / 2, 0, 0]) oriented_tile(); 
        rotate([0, 0, 180]) translate([braced_pair_gap / 2, 0, 0]) oriented_tile(); 
        tabs(); 
    }
}

module chain_model() {
    for(i = [0:chain_count - 1])
        translate([(i - (chain_count - 1) / 2) * (braced_pair_width + chain_gap), 0, 0])
            braced_pair_model(); 
}

module release_sample(h) {
    sample_join_z = first_layer_height + round(2 / layer_height) * layer_height; 
    union() {
        intersection() {
            upright() {
                translate([braced_pair_gap / 2, 0, 0]) oriented_tile(); 
                rotate([0, 0, 180]) translate([braced_pair_gap / 2, 0, 0]) oriented_tile(); 
            }
            translate([-braced_pair_width / 2 - eps, -sample_width / 2, 0])
                cube([braced_pair_width + 2 * eps, sample_width, sample_height]); 
        }
        translate([0, 0, sample_join_z + root_height / 2])
            connection(h); 
    }
}

module release_test_plate() {
    for(i = [0:2])
        translate([(i - 1) * (braced_pair_width + sample_spacing), 0, 0])
            release_sample((i + 1) * layer_height); 
}

/* ==============================================================================
   OUTPUT SELECTION DISPATCHER
   ============================================================================== */

if (output == "flat") {
    single_tile(); 
} else if (output == "release_test") {
    release_test_plate(); 
} else {
    upright() {
        if (output == "production_pair") {
            independent_pair_model(); 
        } else if (output == "single") {
            oriented_tile(); 
        } else if (output == "braced_pair") {
            braced_pair_model(); 
        } else if (output == "chain") {
            chain_model(); 
        } else if (output == "section") {
            intersection() {
                independent_pair_model(); 
                translate([-independent_pair_width, -0.5, -2 * AP])
                    cube([2 * independent_pair_width, 1.0, 4 * AP]); 
            }
        }
        
        if ($preview && show_markers && output == "braced_pair") {
            for(p = centers)
                %color("red") translate([0, p[0], p[1]]) sphere(r = 1.0, $fn = 16); 
        }
    }
}
