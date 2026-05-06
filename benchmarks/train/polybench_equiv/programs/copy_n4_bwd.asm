# copy: B[i] = A[i] for i=0..3.  Backward order — equivalent (no carried dep).
MOV   r1 3
LOAD  r0 r1
MOV   r1 7
STORE r1 r0
MOV   r1 2
LOAD  r0 r1
MOV   r1 6
STORE r1 r0
MOV   r1 1
LOAD  r0 r1
MOV   r1 5
STORE r1 r0
MOV   r1 0
LOAD  r0 r1
MOV   r1 4
STORE r1 r0
HALT
