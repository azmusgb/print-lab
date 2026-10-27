/* HEX TILE v73 — reviewed native parametric OpenSCAD; millimetres.
   Standalone: no imports, missing modules, embedded STL or fused base rail.
   Default is ONE 6-inch candidate pair. 'chain' lays out independent pairs.
   F5 = preview. F6 = render; then File > Export > STL.
   Cut center necks before separating. Do not twist, peel or pry tile faces.
   Geometry checks cannot certify clean release, finish or print stability.
   OpenSCAD 2026.10.11 + Manifold tested; slicer remains authoritative.
*/

/* [Output] */
output = "pair"; // [pair, chain, wall, flat, separated, tabs, section, release_test]
inspection_spacing = 18;
show_markers = false; // Preview only; excluded from exported geometry.

/* [Tile geometry] */
size_in = 6;
edge_depth = 4.1;
rim = 2.0;
skin = 1.68; // v73: was 1.2 (v70–v72); 1.7 trips the clearance assert by float rounding. Vertical offset of faceted surface; not normal wall thickness.
relief_scale = 1.0;
front_chamfer = 0.6; // v73: back to v70 (v72 had 0.15, chip-prone edge).
back_edge_chamfer = 0; // Maximize flat mounting surface; optional small bevel.
/* [Open back and wall-mounting flange] */
back_ring_width = 15;    // Wide enough for ~1/2 in (12.7 mm) foam tape with placement margin.
back_ring_t = 1.2;

// Keep the broad horizontal top flange omitted for upright printing.
// The other five continuous flange segments remain supported as they grow.
include_top_flange = false;
minimum_front_clearance = 1.2;

/* [Cuttable connections] */
pair_gap = 2.0;
root_width = 1.0;
root_height = 0.6;
root_overlap = 0.30; // Embed into flange, not a prediction of residual stub height.
neck_width = 0.60;
neck_height = 0.40;
neck_length = 0.40;
tab_pitch = 12;

/* [Layer checks — match slicer] */
layer_height = 0.20;
first_layer_height = 0.20;
line_width = 0.42; // Check only; SCAD cannot set slicer extrusion width/nozzle.
enforce_event_limits = true;
root_event_limit = 2;       // Per-pair root transition cap.
all_event_limit = 3;        // Per-pair root + neck transition cap.

// Preserve the proven v70 three-pair chain while making its aggregate
// transition budget explicit. Lower these if slicer testing supports it.
enforce_batch_event_limits = true;
batch_root_event_limit = 6;
batch_all_event_limit = 9;

/* [Batch and bed — conservative rectangular check] */
chain_count = 3;
chain_gap = 6;
bed_width = 256;
bed_depth = 256;
bed_height = 256;
planned_brim = 10; // Used only in fit check; set brim separately in the slicer.
bed_margin = 5;

/* [Release sample — real lower rim, flange and front skin] */
sample_width = 24;
sample_height = 18;
sample_spacing = 10;

/* [Hidden] */
eps = 0.01;
R = size_in*25.4/2;
AP = R*cos(30);
relief_max = 0.091654*R*relief_scale;
front_max = edge_depth+relief_max;
D = front_max+1;
pair_width = 2*front_max+pair_gap;
N = max(2,ceil(R/tab_pitch));
lo = root_height/2+0.10;
hi = rim-root_height/2;
phase = [0,0,0.18,0.33,0,-0.17];
joined_mode = output=="pair" || output=="chain" || output=="section";
uses_tabs = joined_mode || output=="tabs";
integer_tolerance = 0.0001;

function dot2(a,b) = a[0]*b[0]+a[1]*b[1];
function lerp(a,b,t) = a+(b-a)*t;
function integer_value(x) = abs(x-round(x))<integer_tolerance;

function hex_point(s,inset) =
    let(rr=(AP-inset)/cos(30))
    [rr*cos(60*s),rr*sin(60*s)];

function inset_at(s,i) =
    s==1 ? lerp(lo,hi-0.1,i/(N-1)) :
    s==4 ? lerp(lo+0.1,hi,i/(N-1)) :
    rim/2;

function raw_center(s,i) =
    let(ins=inset_at(s,i),t=(i+0.5+phase[s])/N)
    lerp(hex_point(s,ins),hex_point(s+1,ins),t);

// Root bottom snaps to a BED-ALIGNED layer boundary.
// Its width coordinate remains unchanged.
function bed_layer_index(z) =
    floor((z-first_layer_height)/layer_height+0.5);

function layer_boundary(k) =
    first_layer_height+k*layer_height;

function tab_center(s,i) =
    let(
        p=raw_center(s,i),
        k=bed_layer_index(p[1]+AP-root_height/2)
    )
    [p[0],layer_boundary(k)+root_height/2-AP];

centers = [
    for(s=[0:5],i=[0:N-1])
        tab_center(s,i)
];

function root_bottom_layer(p) =
    bed_layer_index(p[1]+AP-root_height/2);

root_layers = round(root_height/layer_height);
neck_layers = round(neck_height/layer_height);

root_events = [
    for(p=centers,d=[0,root_layers])
        root_bottom_layer(p)+d
];

// Count each distinct transition once per join:
// root start, neck end, root end.
all_events =
    neck_layers==root_layers
    ? root_events
    : [
        for(p=centers,d=[0,neck_layers,root_layers])
            root_bottom_layer(p)+d
    ];

function event_peak(events) =
    max([
        for(k=events)
            len([for(e=events) if(e==k) 1])
    ]);

root_peak = event_peak(root_events);
all_peak = event_peak(all_events);

// For chain output, all independent pairs are aligned and therefore
// transition on the same bed layers. Enforce limits against the full batch.
effective_root_peak = output=="chain" ? root_peak*chain_count : root_peak;
effective_all_peak = output=="chain" ? all_peak*chain_count : all_peak;

within_side_pitch = max([
    for(s=[0:5],i=[0:N-2])
        norm(tab_center(s,i+1)-tab_center(s,i))
]);

corner_pitch = max([
    for(s=[0:5])
        norm(tab_center((s+1)%6,0)-tab_center(s,N-1))
]);

actual_pitch = max(within_side_pitch,corner_pitch);

function rim_distance(p) =
    AP-max([
        for(s=[0:5])
            dot2(p,[cos(30+60*s),sin(30+60*s)])
    ]);

root_corners = [
    for(p=centers,dy=[-1,1],dz=[-1,1])
        p+[dy*root_width/2,dz*root_height/2]
];

root_outer_margin =
    min([for(p=root_corners) rim_distance(p)]);

root_inner_distance =
    max([for(p=root_corners) rim_distance(p)]);

/* Dimension and topology guards */

assert(
    size_in>=3 && size_in<=10,
    "Size must be 3–10 inches"
);

assert(
    edge_depth>0 && skin>0 && relief_scale>0,
    "Invalid body dimensions"
);

assert(
    rim>=1.5 && rim<AP/4,
    "Rim outside supported range"
);

assert(
    back_ring_t>0 &&
    back_ring_width>=0 &&
    back_ring_width<=AP/2,
    "Invalid flange"
);
assert(
    edge_depth-skin-back_ring_t>=minimum_front_clearance,
    "Flange too close to front skin"
);

assert(
    minimum_front_clearance>0,
    "Front clearance must be positive"
);

assert(
    front_chamfer>=0 &&
    front_chamfer<min(rim,edge_depth),
    "Invalid front chamfer"
);

assert(
    back_edge_chamfer>=0 &&
    back_edge_chamfer<min(rim,back_ring_t),
    "Invalid back bevel"
);

assert(
    layer_height>0 &&
    first_layer_height>0 &&
    line_width>0,
    "Invalid slicer check values"
);

assert(
    pair_gap>=1.5 && pair_gap<=3,
    "Pair gap must be 1.5–3 mm"
);

assert(
    root_height>0 &&
    root_height<=1 &&
    root_width>neck_width &&
    root_width<=1.2,
    "Invalid root"
);

assert(
    neck_width>=line_width &&
    neck_height>=layer_height &&
    neck_height<=root_height,
    "Unprintable neck dimensions"
);

assert(
    neck_length>0 && neck_length<pair_gap,
    "Neck must fit in gap"
);

assert(
    root_overlap>0 && root_overlap<back_ring_t,
    "Root overlap must fit flange thickness"
);

assert(
    integer_value(root_height/layer_height) &&
    integer_value(neck_height/layer_height),
    "Root/neck heights must be whole layers"
);

assert(
    tab_pitch>0 && hi>lo+0.1,
    "Invalid tab spacing or rim allowance"
);

assert(
    !uses_tabs || actual_pitch<=tab_pitch,
    "Actual tab spacing exceeds requested pitch"
);

assert(
    !uses_tabs ||
    (
        root_outer_margin>eps &&
        root_inner_distance<=rim+eps
    ),
    "A root extends outside the supported rim; revise dimensions"
);

assert(
    !joined_mode || back_ring_width>=rim,
    "Joined outputs require a supporting tape flange"
);

assert(
    !uses_tabs ||
    !enforce_event_limits ||
    (
        root_peak<=root_event_limit &&
        all_peak<=all_event_limit
    ),
    "Per-pair layer transition burst: adjust layout or deliberately revise limits"
);

assert(
    output!="chain" ||
    !enforce_batch_event_limits ||
    (
        effective_root_peak<=batch_root_event_limit &&
        effective_all_peak<=batch_all_event_limit
    ),
    "Whole-chain layer transition burst: reduce chain count or revise batch limits deliberately"
);

assert(
    integer_value(chain_count) &&
    chain_count>=1 &&
    chain_count<=8,
    "Batch count must be integer 1–8"
);

assert(
    chain_gap>0 && inspection_spacing>=0,
    "Invalid spacing"
);

assert(
    output!="release_test" ||
    (
        sample_width>=root_width+4 &&
        sample_width<R &&
        sample_height>8 &&
        sample_height<AP/2
    ),
    "Invalid sample dimensions"
);

assert(
    back_ring_width>=4 || output!="release_test",
    "Sample needs at least 4 mm tape flange"
);

assert(
    planned_brim>=0 &&
    bed_margin>=0 &&
    min(bed_width,bed_depth,bed_height)>0,
    "Invalid bed check"
);

assert(
    output=="pair" ||
    output=="chain" ||
    output=="wall" ||
    output=="flat" ||
    output=="separated" ||
    output=="tabs" ||
    output=="section" ||
    output=="release_test",
    "Unknown output"
);

/* Conservative layout bounds.
   Includes planned brim and margins.
   Does not model printer exclusion zones. */

layout_x =
    output=="chain"
        ? chain_count*pair_width+(chain_count-1)*chain_gap :
    output=="release_test"
        ? 3*pair_width+2*sample_spacing :
    output=="flat"
        ? 2*R :
    output=="wall"
        ? front_max :
    output=="separated"
        ? pair_width+inspection_spacing :
    pair_width;

layout_y =
    output=="release_test"
        ? sample_width :
    output=="flat"
        ? 2*AP :
    2*R;

layout_z =
    output=="release_test"
        ? sample_height :
    output=="flat"
        ? front_max :
    2*AP;

print_layout =
    output=="pair" ||
    output=="chain" ||
    output=="wall" ||
    output=="flat" ||
    output=="separated" ||
    output=="tabs" ||
    output=="section" ||
    output=="release_test";

assert(
    !print_layout ||
    (
        layout_x+2*(planned_brim+bed_margin)<=bed_width &&
        layout_y+2*(planned_brim+bed_margin)<=bed_depth &&
        layout_z<=bed_height
    ),
    "Layout plus brim/margin exceeds bed; resize or reduce batch count"
);

echo(str(
    "v72 | ",output,
    " | ",6*N," joins/pair",
    " | max actual pitch ",actual_pitch," mm"
));

echo(str(
    "BED-ALIGNED transitions: pair root=",root_peak,
    "; pair including neck=",all_peak,
    "; effective root=",effective_root_peak,
    "; effective including neck=",effective_all_peak
));

if(output=="chain")
    echo(str(
        "Chain contains ",chain_count,
        " independent pairs; aggregate caps root=",batch_root_event_limit,
        ", including neck=",batch_all_event_limit,"."
    ));

if(output=="flat")
    echo(
        "Flat mode is inspection/export only until support/bridging behavior is validated."
    );

if(include_top_flange)
    echo(
        "Full top flange enabled: inspect unsupported starts in the actual slice."
    );

echo(str(
    "Wall-mount flange: ",back_ring_width,
    " mm wide x ",back_ring_t,
    " mm thick on the printable five-edge perimeter; top flange omitted=",
    !include_top_flange
));

/* Native front geometry.
   Inherited v30/v57 low-poly facet topology.
   Coordinates are normalized to the corner radius. */

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
    [0,6,1],
    [4,3,7],
    [5,4,7],
    [8,3,2],
    [7,3,8],
    [7,8,6],
    [5,9,0],
    [9,6,0],
    [9,7,6],
    [5,7,9],
    [6,8,10],
    [8,2,10],
    [6,10,1],
    [10,2,1],
    [1,12,11,0],
    [2,13,12,1],
    [3,14,13,2],
    [4,15,14,3],
    [5,16,15,4],
    [0,11,16,5],
    [11,12,13,14,15,16]
];

module hex2d(a) {
    circle(r=a/cos(30),$fn=6);
}

module faceted_solid(dz=0,zb=0) {
    polyhedron(
        points=concat(
            [
                for(p=FP)
                    [
                        p[0]*R,
                        p[1]*R,
                        edge_depth+p[2]*R*relief_scale+dz
                    ]
            ],
            [
                for(i=[0:5])
                    [FP[i][0]*R,FP[i][1]*R,zb]
            ]
        ),
        faces=FACES,
        convexity=12
    );
}

module cavity() {
    H = D+2;
    a = AP-rim+1;

    assert(
        a>H,
        "Size too small for requested cavity depth"
    );

    intersection() {
        faceted_solid(-skin,-1);

        translate([0,0,-1])
            linear_extrude(H,scale=(a-H)/a)
                hex2d(a);
    }
}

module front_envelope() {
    H = D+5;

    union() {
        translate([0,0,-eps])
            linear_extrude(
                edge_depth-front_chamfer+eps
            )
                hex2d(AP+eps);

        translate([0,0,edge_depth-front_chamfer])
            linear_extrude(
                H,
                scale=(AP-H)/AP
            )
                hex2d(AP);
    }
}

// Keeps the interior while beveling the outside.
// Unlike v68, this does not subtract the center.
module back_envelope() {
    union() {
        linear_extrude(
            back_edge_chamfer,
            scale=AP/(AP-back_edge_chamfer)
        )
            hex2d(AP-back_edge_chamfer);

        translate([0,0,back_edge_chamfer])
            linear_extrude(D+1)
                hex2d(AP);
    }
}

module tape_flange() {
    if(back_ring_width>0)
        linear_extrude(back_ring_t)
            intersection() {
                difference() {
                    hex2d(AP);
                    hex2d(AP-back_ring_width);
                }

                // Preserve v70's proven open-top flange behavior for upright printing.
                if(!include_top_flange)
                    translate([-2*R,-2*AP])
                        square([
                            4*R,
                            3*AP-back_ring_width
                        ]);
            }
}

module tile() {
    intersection() {
        union() {
            difference() {
                faceted_solid();
                cavity();
            }

            tape_flange();
        }

        if(front_chamfer>0)
            front_envelope();
        else
            faceted_solid();

        if(back_edge_chamfer>0)
            back_envelope();
        else
            faceted_solid();
    }
}

// Canonical frame:
// X = depth, Y = tile width, Z = height.
// Back plane is X=0.
module oriented_tile() {
    multmatrix([
        [0,0,1,0],
        [1,0,0,0],
        [0,1,0,0],
        [0,0,0,1]
    ])
        tile();
}

module first_tile() {
    translate([pair_gap/2,0,0])
        oriented_tile();
}

module partner_tile() {
    rotate([0,0,180])
        first_tile();
}

module bodies() {
    first_tile();
    partner_tile();
}

module connection(h=neck_height) {
    assert(
        h>0 &&
        h<=root_height+integer_tolerance &&
        integer_value(h/layer_height),
        "Sample neck must fit the root in whole layers"
    );

    // Shared bottom plane.
    // The short arms taper toward the cuttable middle.
    bottom = -root_height/2;

    for(sign=[-1,1])
        hull() {
            translate([
                sign*(pair_gap/2+root_overlap/2),
                0,
                bottom+root_height/2
            ])
                cube([
                    root_overlap,
                    root_width,
                    root_height
                ],center=true);

            translate([
                sign*neck_length/2,
                0,
                bottom+h/2
            ])
                cube([
                    eps,
                    neck_width,
                    h
                ],center=true);
        }

    translate([0,0,bottom+h/2])
        cube([
            neck_length+eps,
            neck_width,
            h
        ],center=true);
}

module tabs() {
    for(p=centers)
        translate([0,p[0],p[1]])
            connection();
}

module pair_model() {
    union() {
        bodies();
        tabs();
    }
}

module chain_model() {
    for(i=[0:chain_count-1])
        translate([
            (i-(chain_count-1)/2)*
            (pair_width+chain_gap),
            0,
            0
        ])
            pair_model();
}

module separated_model() {
    color("#e9a480")
        translate([inspection_spacing/2,0,0])
            first_tile();

    color("#7fa7b6")
        translate([-inspection_spacing/2,0,0])
            partner_tile();
}

module upright() {
    translate([0,0,AP])
        children();
}

module release_sample(h) {
    // A cropped section of the actual lower rim,
    // flange, cavity and visible front skin.
    // One join at a layer-aligned height.
    sample_join_z =
        first_layer_height+
        round(2/layer_height)*layer_height;

    union() {
        intersection() {
            upright()
                bodies();

            translate([
                -pair_width/2-eps,
                -sample_width/2,
                0
            ])
                cube([
                    pair_width+2*eps,
                    sample_width,
                    sample_height
                ]);
        }

        translate([
            0,
            0,
            sample_join_z+root_height/2
        ])
            connection(h);
    }
}

module release_test_plate() {
    // Left to right: one-, two-, three-layer necks.
    for(i=[0:2])
        translate([
            (i-1)*(pair_width+sample_spacing),
            0,
            0
        ])
            release_sample((i+1)*layer_height);
}

/* Output selection */

if(output=="flat")
    tile();

else if(output=="release_test")
    release_test_plate();

else
    upright() {
        if(output=="pair")
            pair_model();

        else if(output=="chain")
            chain_model();

        else if(output=="wall")
            oriented_tile();

        else if(output=="separated")
            separated_model();

        else if(output=="tabs")
            tabs();

        else if(output=="section")
            intersection() {
                pair_model();

                translate([
                    -pair_width,
                    -0.5,
                    -2*AP
                ])
                    cube([
                        2*pair_width,
                        1,
                        4*AP
                    ]);
            }

        if(
            $preview &&
            show_markers &&
            output!="wall"
        )
            for(p=centers)
                %color("red")
                    translate([0,p[0],p[1]])
                        sphere(r=1,$fn=16);
    }