# memcpy forward: copy mem[0..N) → mem[N..2N), r1 is the index.
# Assumes N in r2 (caller-set; generator MOVs it), dst base in r3.
MOV  r1 0
BEQ  r1 r2 6       # while r1 != N
LOAD r0 r1         #   r0 ← mem[r1]
ADD  r1 r1 r3      #   (r1+dst) for store addr — generator picks r3=N
STORE r1 r0        #   mem[r1+N] ← r0
MOV  r1 0          # (stub: real loop needs r1++ then jump back; left
HALT               #  intentionally simple for the bounded encoding)
