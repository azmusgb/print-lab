/*
    Hexagon-Rev-v40-reference-wrapper.scad

    Uses the uploaded Hexagon-Rev.stl as the master geometry.

    IMPORTANT:
    - No mounting geometry has been redesigned.
    - No tabs, rails, gussets, feet, or supports are added.
    - Scaling is UNIFORM in X/Y/Z so the original proportions and
      back/mounting concept are preserved exactly.

    Original measured size:
      X = 202.97201 mm
      Y = 14.25800 mm
      Z = 175.77600 mm

    Default target:
      X = 240.00 mm

    Resulting uniform scale factor:
      1.18242904
*/

target_width_mm = 240.00;

// Measured X width of the uploaded master STL.
source_width_mm = 202.97201;

uniform_scale = target_width_mm / source_width_mm;

scale([uniform_scale, uniform_scale, uniform_scale])
    import("Hexagon-Rev.stl", convexity = 20);
