# prefix-sum (in-place): A[i] += A[i-1] for i=1..3.  A at 0..3.  Forward.
MOV   r1 0
LOAD  r0 r1
MOV   r1 1
LOAD  r2 r1
ADD   r0 r0 r2
STORE r1 r0
MOV   r1 2
LOAD  r2 r1
ADD   r0 r0 r2
STORE r1 r0
MOV   r1 3
LOAD  r2 r1
ADD   r0 r0 r2
STORE r1 r0
HALT
