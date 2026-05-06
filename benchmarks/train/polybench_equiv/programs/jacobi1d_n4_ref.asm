# jacobi-1d (integerized, 1 sweep, N=4): B[i] = A[i-1]+A[i]+A[i+1] for i=1,2
# A at addr 0..3, B at addr 4..7. Reference iteration order i=1,2.
# i=1: B[1] = A[0]+A[1]+A[2]
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
# i=2: B[2] = A[1]+A[2]+A[3]
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
HALT
