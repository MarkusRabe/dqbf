# prefix-sum REVERSED: i=3..1.  WRONG — loop-carried dep on A[i-1].
# A[3]+=A[2]; A[2]+=A[1]; A[1]+=A[0]  computes a *suffix* contribution.
MOV   r1 2
LOAD  r0 r1
MOV   r1 3
LOAD  r2 r1
ADD   r0 r0 r2
STORE r1 r0
MOV   r1 1
LOAD  r0 r1
MOV   r1 2
LOAD  r2 r1
ADD   r0 r0 r2
STORE r1 r0
MOV   r1 0
LOAD  r0 r1
MOV   r1 1
LOAD  r2 r1
ADD   r0 r0 r2
STORE r1 r0
HALT
