# memcpy backward: same effect as memcpy_fwd but iterates N-1..0.
# Stub structure mirroring _fwd; see README for the intended pair.
MOV  r1 0
BEQ  r1 r2 6
LOAD r0 r1
ADD  r1 r1 r3
STORE r1 r0
MOV  r1 0
HALT
