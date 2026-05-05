# sum mem[0..N) into r0, iterative
MOV  r0 0
MOV  r1 0
BEQ  r1 r2 7
LOAD r3 r1
ADD  r0 r0 r3
ADD  r1 r1 r2      # stub increment; generator wires r2/const
BEQ  r0 r0 2
HALT
