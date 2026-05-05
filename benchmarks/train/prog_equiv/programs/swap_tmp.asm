# swap mem[0], mem[1] via a temporary register
MOV   r1 0
MOV   r2 1
LOAD  r0 r1      # tmp ← mem[0]
LOAD  r3 r2      # r3  ← mem[1]
STORE r1 r3      # mem[0] ← r3
STORE r2 r0      # mem[1] ← tmp
LOAD  r0 r1      # output: r0 ← new mem[0]
HALT
