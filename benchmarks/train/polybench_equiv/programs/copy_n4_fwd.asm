# copy: B[i] = A[i] for i=0..3.  A at 0..3, B at 4..7.  Forward order.
MOV   r1 0
LOAD  r0 r1
MOV   r1 4
STORE r1 r0
MOV   r1 1
LOAD  r0 r1
MOV   r1 5
STORE r1 r0
MOV   r1 2
LOAD  r0 r1
MOV   r1 6
STORE r1 r0
MOV   r1 3
LOAD  r0 r1
MOV   r1 7
STORE r1 r0
HALT
