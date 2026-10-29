/* HEX TILE v77 — faceted 6-inch architectural wall tile; millimetres.
   Standalone OpenSCAD source: no imports, no embedded meshes.
   OpenSCAD 2026.10.11 with the Manifold backend; F6 to render, then export STL.

   PRODUCTION UNIT (default output = "pair")
     Two tiles printed upright, back to back, standing on one flat hex edge.
     The pair is held together by small cuttable joins on the solid rim.
     After printing: run a hobby blade around the perimeter slot to cut every
     join, then lift the tiles apart. Do not twist, peel or pry against faces.

   LINEAGE
     v77 = v75 (physically printed pair topology) plus exactly three changes,
     each tied to a requirement and each separable for testing:
       C1  edge_depth 4.1 -> 4.6     face isolation 1.22 -> 1.72 mm (spec §9: >= 1.6)
       C2  flange 15 -> 18 mm         tape land kept clear of the join stubs (spec §8)
       C3  top_closure option         "gusset" stiffens the top rim (spec §12, upper-edge
                                      ripple). Default "none" until a print shows it helps.
     Every other dimension, the facet topology and the join layout are v75's.

   WHAT THIS FILE CAN AND CANNOT PROVE
     The assertions below prove dimensional and clearance relationships.
     They do not prove print stability, face finish or clean separation;
     those need the slicer and physical prints (see the v77 report).

   COORDINATES
     Tile frame:  XY = tile plane, Z = depth; back/wall plane at Z = 0.
     Print frame: X = depth, Y = tile width, Z = height; bed at Z = 0.
*/

/* [Output] */
// pair         production: one back-to-back pair, upright (recommended)
// chain        several independent pairs on one plate (not yet validated)
// single       one finished tile in print orientation (inspection, mesh checks)
// installed    one finished tile, face up, as seen on the wall (inspection)
// section      1 mm slice through the pair at the tile centreline (inspection)
// joins        the join solids only (diagnostic)
// release_test three coupons of real lower rim with 1-, 2-, 3-layer necks
output = "pair"; // [pair, chain, single, installed, section, joins, release_test]
show_markers = false; // Preview only: red dots at join centres. Never exported.

/* [Tile body] */
size_in = 6;          // Corner-to-corner width, inches.
edge_depth = 4.6;     // C1. Depth of the visible side wall at the perimeter. v75: 4.1.
rim = 2.0;            // In-plane width of the solid perimeter wall; joins live inside it.
skin = 1.68;          // Face skin, measured along depth. 4 x 0.42 mm walls in the slicer.
relief_scale = 1.0;   // Facet relief multiplier; 1.0 = the established low-poly pattern.
front_chamfer = 0.6;  // 45-degree chamfer on the face perimeter (not on the bed edge).

/* [Wall-mount flange] */
flange_width = 18;    // C2. In-plane width of the rear band, from the outer edge. v75: 15.
flange_t = 1.2;       // Flange thickness along depth.
// Top edge treatment when printed upright. A full top band would start as an
// unsupported horizontal bridge, so it is never offered.
//   none    v70-v76 behaviour: no flange on the top edge (five-edge flange)
//   gusset  C3 candidate: two self-supporting triangles grown from the upper
//           slanted flanges at gusset_angle, tying the top rim to the flange.
top_closure = "none"; // [none, gusset]
gusset_angle = 45;    // Degrees above horizontal for the gusset's lower edge (print frame).

/* [Mounting tape] */
tape_width = 12.7;          // 1/2 in foam mounting tape.
tape_thickness = 1.6;       // Thinnest foam tape the installer may use.
tape_margin_min = 1.0;      // Minimum placement slack on each side of the tape.
stub_wall_clearance = 0.3;  // Cut join stubs must stay this far off the wall.

/* [Face isolation] */
min_face_isolation = 1.6;   // Spec §9: rear features to visible skin, minimum.

/* [Pair joins (v75 layout)] */
pair_gap = 2.0;       // Back-plane gap. CASE-001: <= 0.75 mm fuses; keep >= 1.0.
root_width = 1.0;     // Join root, along the tile edge.
root_height = 0.6;    // Join root, in print Z (3 layers).
root_overlap = 0.30;  // Root embedded into the rim.
neck_width = 0.60;    // Cuttable neck, along the tile edge.
neck_height = 0.40;   // Cuttable neck, in print Z (2 layers).
neck_length = 0.40;   // Cuttable neck length across the gap.
tab_pitch = 13;       // Max join spacing; 13 gives 6 per side, 36 per pair (v75).

/* [Layer checks: must match the slicer] */
layer_height = 0.20;
first_layer_height = 0.20;
line_width = 0.42;          // Check only; the slicer sets extrusion width.
root_event_limit = 2;       // Max join-root starts/ends on one layer, per pair.
all_event_limit = 3;        // Same, counting neck transitions.
batch_root_event_limit = 6; // Whole-plate caps for chain output.
batch_all_event_limit = 9;

/* [Plate] */
chain_count = 3;
chain_gap = 6;
bed_width = 256;     // Bambu X2D usable plate; set for your printer.
bed_depth = 256;
bed_height = 256;
planned_brim = 10;   // Fit check only; set the brim in the slicer.
bed_margin = 5;

/* [Release coupon] */
sample_width = 24;
sample_height = 18;
sample_spacing = 10;

/* [Hidden] */
eps = 0.01;
integer_tolerance = 0.0001;

// Primary dimensions
R = size_in*25.4/2;                // Corner radius = hex side length.
AP = R*cos(30);                    // Apothem; the upright tile is 2*AP tall.
relief_max = 0.091654*R*relief_scale;
front_max = edge_depth+relief_max; // Overall tile depth.
D = front_max+1;
pair_width = 2*front_max+pair_gap;

// Clearances derived from the parameters (see the guards for the proofs)
face_isolation = edge_depth-skin-flange_t;
root_face_distance = edge_depth-root_overlap-front_chamfer;
tape_land = flange_width-rim;                     // Flange outside the join zone.
stub_protrusion = pair_gap/2+neck_length/2;       // Worst stub past the wall plane.
gusset_half = (AP-flange_width)*tan(30);          // Half-width of the flange's inner top edge.
gusset_center_gap = max(0,2*(gusset_half-flange_width/tan(gusset_angle)));

// Join placement (v75, unchanged)
N = max(2,ceil(R/tab_pitch));
lo = root_height/2+0.10;
hi = rim-root_height/2;
phase = [0,0,0.18,0.33,0,-0.17];
joined_mode = output=="pair" || output=="chain" || output=="section";
uses_tabs = joined_mode || output=="joins";

function dot2(a,b) = a[0]*b[0]+a[1]*b[1];
function lerp(a,b,t) = a+(b-a)*t;
function integer_value(x) = abs(x-round(x))<integer_tolerance;

function hex_point(s,inset) =
    let(rr=(AP-inset)/cos(30))
    [rr*cos(60*s),rr*sin(60*s)];

// Top (s=1) and bottom (s=4) joins lie along a layer, so their insets are
// spread across the rim to put each one on a different layer band.
function inset_at(s,i) =
    s==1 ? lerp(lo,hi-0.1,i/(N-1)) :
    s==4 ? lerp(lo+0.1,hi,i/(N-1)) :
    rim/2;

function raw_center(s,i) =
    let(ins=inset_at(s,i),t=(i+0.5+phase[s])/N)
    lerp(hex_point(s,ins),hex_point(s+1,ins),t);

// Root bottoms snap to bed-aligned layer boundaries.
function bed_layer_index(z) = floor((z-first_layer_height)/layer_height+0.5);
function layer_boundary(k) = first_layer_height+k*layer_height;

function tab_center(s,i) =
    let(p=raw_center(s,i), k=bed_layer_index(p[1]+AP-root_height/2))
    [p[0],layer_boundary(k)+root_height/2-AP];

centers = [for(s=[0:5],i=[0:N-1]) tab_center(s,i)];

function root_bottom_layer(p) = bed_layer_index(p[1]+AP-root_height/2);

root_layers = round(root_height/layer_height);
neck_layers = round(neck_height/layer_height);

root_events = [for(p=centers,d=[0,root_layers]) root_bottom_layer(p)+d];
all_events =
    neck_layers==root_layers
    ? root_events
    : [for(p=centers,d=[0,neck_layers,root_layers]) root_bottom_layer(p)+d];

function event_peak(events) =
    max([for(k=events) len([for(e=events) if(e==k) 1])]);

root_peak = event_peak(root_events);
all_peak = event_peak(all_events);
// Chained pairs are aligned, so their transitions land on the same layers.
effective_root_peak = output=="chain" ? root_peak*chain_count : root_peak;
effective_all_peak = output=="chain" ? all_peak*chain_count : all_peak;

actual_pitch = max(
    max([for(s=[0:5],i=[0:N-2]) norm(tab_center(s,i+1)-tab_center(s,i))]),
    max([for(s=[0:5]) norm(tab_center((s+1)%6,0)-tab_center(s,N-1))])
);

function rim_distance(p) =
    AP-max([for(s=[0:5]) dot2(p,[cos(30+60*s),sin(30+60*s)])]);

root_corners = [for(p=centers,dy=[-1,1],dz=[-1,1]) p+[dy*root_width/2,dz*root_height/2]];
root_outer_margin = min([for(p=root_corners) rim_distance(p)]);
root_inner_distance = max([for(p=root_corners) rim_distance(p)]);

/* Facet topology (v30/v57 lineage). Points are normalised to the corner
   radius; the third value is relief height. Points 0-5 are the hex corners at
   relief 0; 6-10 are interior peaks. FACES 0-13 are the visible facets. */
FP = [
    [ 1.00,  0.000000, 0.000000],
    [ 0.50,  0.866025, 0.000000],
    [-0.50,  0.866025, 0.000000],
    [-1.00,  0.000000, 0.000000],
    [-0.50, -0.866025, 0.000000],
    [ 0.50, -0.866025, 0.000000],
    [ 0.16,  0.050000, 0.091654],
    [-0.16, -0.380000, 0.019428],
    [-0.36,  0.180000, 0.055790],
    [ 0.34, -0.280000, 0.053795],
    [ 0.02,  0.460000, 0.061766]
];

FACES = [
    [0,6,1], [4,3,7], [5,4,7], [8,3,2], [7,3,8], [7,8,6], [5,9,0],
    [9,6,0], [9,7,6], [5,7,9], [6,8,10], [8,2,10], [6,10,1], [10,2,1],
    [1,12,11,0], [2,13,12,1], [3,14,13,2], [4,15,14,3], [5,16,15,4],
    [0,11,16,5], [11,12,13,14,15,16]
];

/* Engineering guards. Each fails with a reason instead of producing
   compromised geometry. */

// Overall size and body
assert(size_in>=3 && size_in<=10, "size_in must be 3-10 inches");
assert(edge_depth>0 && skin>0 && relief_scale>0, "edge_depth, skin and relief_scale must be positive");
assert(rim>=1.5 && rim<AP/4, "rim must be 1.5 mm to a quarter of the apothem");
assert(skin>=3*line_width, "skin is under three slicer walls; the face will be fragile");
assert(front_chamfer>=0 && front_chamfer<min(rim,edge_depth), "front_chamfer must be smaller than rim and edge_depth");

// Face isolation (spec §9). Every relief height in FP is >= 0 and the face is
// piecewise planar between those points, so relief >= 0 everywhere and the
// skin's inner surface is never closer to the flange than face_isolation.
// This is a proof over the whole flange, not a spot check.
assert(min([for(p=FP) p[2]])>=0, "Facet relief below the perimeter plane; the isolation proof no longer holds");
assert(face_isolation>=min_face_isolation,
    str("Flange is ",face_isolation," mm from the face skin; need >= ",min_face_isolation));
assert(root_face_distance>=min_face_isolation,
    str("Join roots are ",root_face_distance," mm from the face; need >= ",min_face_isolation));

// Mounting (spec §8)
assert(flange_t>=2*layer_height && flange_t>=2*line_width, "flange_t too thin to print as a solid band");
assert(flange_width>rim && flange_width<=AP/2, "flange_width must exceed rim and stay under half the apothem");
assert(tape_land>=tape_width+2*tape_margin_min,
    str("Tape land ",tape_land," mm is under tape_width + 2 x tape_margin_min = ",tape_width+2*tape_margin_min));
assert(!joined_mode || stub_protrusion<=tape_thickness-stub_wall_clearance,
    str("Cut join stubs reach ",stub_protrusion," mm past the wall plane; tape_thickness ",tape_thickness," cannot clear them"));
assert(top_closure=="none" || top_closure=="gusset", "top_closure must be none or gusset");
assert(gusset_angle>=40 && gusset_angle<90, "gusset_angle under 40 degrees will not print unsupported");

// Joins
assert(pair_gap>=1.0 && pair_gap<=3, "pair_gap must be 1.0-3.0 mm (CASE-001: smaller gaps fuse)");
assert(root_height>0 && root_height<=1 && root_width>neck_width && root_width<=1.2, "Invalid join root");
assert(neck_width>=line_width && neck_height>=layer_height && neck_height<=root_height, "Neck is not printable");
assert(neck_length>0 && neck_length<pair_gap, "Neck must fit in the gap");
assert(root_overlap>0 && root_overlap<flange_t, "root_overlap must sit inside the rim's back");
assert(integer_value(root_height/layer_height) && integer_value(neck_height/layer_height),
    "Root and neck heights must be whole layers");
assert(tab_pitch>0 && hi>lo+0.1, "Invalid tab_pitch or rim too narrow for staggered joins");
assert(!uses_tabs || actual_pitch<=tab_pitch, "Actual join spacing exceeds tab_pitch");
assert(!uses_tabs || (root_outer_margin>eps && root_inner_distance<=rim+eps),
    "A join root leaves the solid rim");
assert(!uses_tabs || (root_peak<=root_event_limit && all_peak<=all_event_limit),
    "Too many join transitions on one layer (face-line risk, v41)");
assert(output!="chain" || (effective_root_peak<=batch_root_event_limit && effective_all_peak<=batch_all_event_limit),
    "Too many join transitions on one layer across the chain");

// Plate and coupon
assert(integer_value(chain_count) && chain_count>=1 && chain_count<=8, "chain_count must be an integer 1-8");
assert(chain_gap>0, "chain_gap must be positive");
assert(planned_brim>=0 && bed_margin>=0 && min(bed_width,bed_depth,bed_height)>0, "Invalid bed definition");
assert(output!="release_test" ||
    (sample_width>=root_width+4 && sample_width<R && sample_height>8 && sample_height<AP/2),
    "Invalid coupon dimensions");

assert(
    output=="pair" || output=="chain" || output=="single" || output=="installed" ||
    output=="section" || output=="joins" || output=="release_test",
    "Unknown output"
);

// Build-volume fit, including brim and machine margin on every side.
layout_x =
    output=="chain"        ? chain_count*pair_width+(chain_count-1)*chain_gap :
    output=="release_test" ? 3*pair_width+2*sample_spacing :
    output=="installed"    ? 2*R :
    output=="single"       ? front_max :
    pair_width;
layout_y =
    output=="release_test" ? sample_width :
    output=="installed"    ? 2*AP :
    2*R;
layout_z =
    output=="release_test" ? sample_height :
    output=="installed"    ? front_max :
    2*AP;

assert(
    layout_x+2*(planned_brim+bed_margin)<=bed_width &&
    layout_y+2*(planned_brim+bed_margin)<=bed_depth &&
    layout_z<=bed_height,
    "Layout plus brim and margin exceeds the build volume"
);

echo(str("v77 | ",output," | tile ",2*R," x ",2*AP," x ",front_max," mm"));
echo(str("Face isolation ",face_isolation," mm (min ",min_face_isolation,") | join roots to face ",root_face_distance," mm"));
echo(str("Flange ",flange_width," x ",flange_t," mm | tape land ",tape_land," mm for ",tape_width,
    " mm tape | top_closure ",top_closure,
    top_closure=="gusset" ? str(" (open centre ",gusset_center_gap," mm)") : ""));
if(uses_tabs)
    echo(str("Joins ",6*N,"/pair, max pitch ",actual_pitch," mm, worst stub ",stub_protrusion,
        " mm | transitions/layer root ",effective_root_peak,", all ",effective_all_peak));
echo(str("Plate footprint ",layout_x+2*planned_brim," x ",layout_y+2*planned_brim," mm with brim | height ",layout_z," mm"));

/* Geometry */

module hex2d(a) {
    circle(r=a/cos(30),$fn=6);
}

// The faceted body: front facets at edge_depth + relief, flat back at zb.
module faceted_solid(dz=0,zb=0) {
    polyhedron(
        points=concat(
            [for(p=FP) [p[0]*R,p[1]*R,edge_depth+p[2]*R*relief_scale+dz]],
            [for(i=[0:5]) [FP[i][0]*R,FP[i][1]*R,zb]]
        ),
        faces=FACES,
        convexity=12
    );
}

// The hollow: the face offset back by skin, trimmed by a tapered hex so the
// rim walls draft inward toward the face.
module cavity() {
    H = D+2;
    a = AP-rim+1;
    assert(a>H, "Size too small for the cavity depth");
    intersection() {
        faceted_solid(-skin,-1);
        translate([0,0,-1])
            linear_extrude(H,scale=(a-H)/a)
                hex2d(a);
    }
}

// Clips the outside: chamfers the face perimeter but keeps the bed edge
// (local -Y) square. v74: a chamfered bed edge undercut the first layer and
// four upright prints tore off above the brim.
module front_envelope() {
    H = D+5;
    union() {
        translate([0,0,-eps])
            linear_extrude(edge_depth-front_chamfer+eps)
                hex2d(AP+eps);
        translate([0,0,edge_depth-front_chamfer])
            linear_extrude(H,scale=(AP-H)/AP)
                hex2d(AP);
        translate([-R-1,-AP-1,-1])
            cube([2*R+2,1+front_chamfer,D+7]);
    }
}

// Five-edge flange band (top edge open), plus the optional top gussets.
// The band's outer edge stops rim/2 inside the outline, buried in the solid
// rim, so it never shares a surface with the outer side wall (a shared edge
// there exported as zero-area slivers).
module flange_2d() {
    intersection() {
        difference() {
            hex2d(AP-rim/2);
            hex2d(AP-flange_width);
        }
        translate([-2*R,-2*AP])
            square([4*R,3*AP-flange_width]);
    }
    if(top_closure=="gusset")
        intersection() {
            difference() {
                hex2d(AP-rim/2);
                hex2d(AP-flange_width);
            }
            // Region above two lines rising at gusset_angle from the inner
            // corners of the upper slanted flanges toward the centre.
            for(m=[0,1]) mirror([m,0])
                polygon([
                    [gusset_half,AP-flange_width],
                    [gusset_half+2*R,AP-flange_width],
                    [gusset_half+2*R,AP+1],
                    [gusset_half-(flange_width+1)/tan(gusset_angle),AP+1]
                ]);
        }
}

module flange() {
    linear_extrude(flange_t) flange_2d();
}

// One finished tile in the tile frame.
module tile() {
    intersection() {
        union() {
            difference() {
                faceted_solid();
                cavity();
            }
            flange();
        }
        if(front_chamfer>0) front_envelope(); else faceted_solid();
    }
}

// Tile frame -> print frame (X = depth, Y = width, Z = local Y).
module oriented_tile() {
    multmatrix([[0,0,1,0],[1,0,0,0],[0,1,0,0],[0,0,0,1]])
        tile();
}

module first_tile() {
    translate([pair_gap/2,0,0]) oriented_tile();
}

module partner_tile() {
    rotate([0,0,180]) first_tile();
}

// One join: a root embedded in each rim, tapering to a cuttable neck mid-gap.
module connection(h=neck_height) {
    assert(h>0 && h<=root_height+integer_tolerance && integer_value(h/layer_height),
        "Neck must fit the root in whole layers");
    bottom = -root_height/2;
    for(sign=[-1,1])
        hull() {
            translate([sign*(pair_gap/2+root_overlap/2),0,bottom+root_height/2])
                cube([root_overlap,root_width,root_height],center=true);
            translate([sign*neck_length/2,0,bottom+h/2])
                cube([eps,neck_width,h],center=true);
        }
    translate([0,0,bottom+h/2])
        cube([neck_length+eps,neck_width,h],center=true);
}

module joins() {
    for(p=centers) translate([0,p[0],p[1]]) connection();
}

module pair_model() {
    union() {
        first_tile();
        partner_tile();
        joins();
    }
}

module chain_model() {
    for(i=[0:chain_count-1])
        translate([(i-(chain_count-1)/2)*(pair_width+chain_gap),0,0])
            pair_model();
}

module upright() {
    translate([0,0,AP]) children();
}

// A cropped section of the real lower rim, flange, cavity and face skin,
// with one join at a layer-aligned height.
module release_sample(h) {
    sample_join_z = first_layer_height+round(2/layer_height)*layer_height;
    union() {
        intersection() {
            upright() { first_tile(); partner_tile(); }
            translate([-pair_width/2-eps,-sample_width/2,0])
                cube([pair_width+2*eps,sample_width,sample_height]);
        }
        translate([0,0,sample_join_z+root_height/2])
            connection(h);
    }
}

// Left to right: one-, two- and three-layer necks.
module release_test_plate() {
    for(i=[0:2])
        translate([(i-1)*(pair_width+sample_spacing),0,0])
            release_sample((i+1)*layer_height);
}

/* Output selection */

if(output=="installed")
    tile();
else if(output=="release_test")
    release_test_plate();
else
    upright() {
        if(output=="pair") pair_model();
        else if(output=="chain") chain_model();
        else if(output=="single") oriented_tile();
        else if(output=="joins") joins();
        else if(output=="section")
            intersection() {
                pair_model();
                translate([-pair_width,-0.5,-2*AP])
                    cube([2*pair_width,1,4*AP]);
            }

        if($preview && show_markers && uses_tabs)
            for(p=centers)
                %color("red") translate([0,p[0],p[1]]) sphere(r=1,$fn=16);
    }
