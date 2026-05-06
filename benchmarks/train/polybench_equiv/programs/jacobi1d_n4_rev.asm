# jacobi-1d (integerized, 1 sweep, N=4): same B[i], REVERSED order i=2,1.
# Equivalent — output array B[5],B[6] identical (no loop-carried dep).
MOV   r1 1
LOAD  r0 r1
MOV   r1 2
LOAD  r2 r1
ADD   r0 r0 r2
MOV   r1 3
LOAD  r2 r1
ADD   r0 r0 r2
MOV   r1 6
STORE r1 r0
MOV   r1 0
LOAD  r0 r1
MOV   r1 1
LOAD  r2 r1
ADD   r0 r0 r2
MOV   r1 2
LOAD  r2 r1
ADD   r0 r0 r2
MOV   r1 5
STORE r1 r0
HALT
