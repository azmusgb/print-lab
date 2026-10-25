// Version-ID tab (Print lab Stage 1A.1): 10 x 6 x 1 mm with 0.6 mm raised text and a thin bridge (+Y) that joins the
// strip's end at bed level. Total height 1.6 mm = 8 layers at 0.2 mm.
label = "1A";
union() {
  cube([10, 6, 1]);
  translate([5, 3, 1]) linear_extrude(0.6) text(label, size = 3.6, halign = "center", valign = "center");
  translate([4.4, 6, 0]) cube([1.2, 3, 0.6]);
}
