; EXECUTABLE_BLOCK_START
M73 P0 R5
M201 X20000 Y20000 Z500 E30000
M203 X1000 Y1000 Z20 E30
M204 P20000 R30000 T20000
M205 X9.00 Y9.00 Z3.00 E2.50
M106 S0
M190 S35 ; set bed temperature and wait for it to be reached
M104 S220 ; set nozzle temperature
; FEATURE: Custom
G28 ; home all axes
G1 Z5 F5000 ; lift nozzle
