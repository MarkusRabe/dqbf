# sum mem[0..2) into r0, manually unrolled (pair for sum_iter at N=2)
MOV  r1 0
LOAD r0 r1
MOV  r1 1
LOAD r3 r1
ADD  r0 r0 r3
HALT
