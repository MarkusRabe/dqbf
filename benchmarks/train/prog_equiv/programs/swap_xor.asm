# swap mem[0], mem[1] via XOR (no temporary)
MOV   r1 0
MOV   r2 1
LOAD  r0 r1
LOAD  r3 r2
XOR   r0 r0 r3
XOR   r3 r0 r3
XOR   r0 r0 r3
STORE r1 r3
STORE r2 r0
LOAD  r0 r1
HALT
