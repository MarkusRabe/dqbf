# tools/bmc2dqbf/ — plain Bounded Model Checking → (DQ)DIMACS

Unroll a sequential AIGER circuit for `k` steps and emit a quantified
formula asserting the bad output is reached at step `k` (or, with
`--safe`, that it is never reached within `k` steps).

There are **no black boxes** here. Per-step primary inputs are
universal; latches and gates at step `t` are existential with deps =
all input universals at steps `0..t`. The dependency sets are linearly
nested, so the result is **QBF** — emitted as DQDIMACS so the rest of
the pipeline consumes it unchanged. For incomplete circuits with
black-box gates (the DQBF-hard case), use `tools/pec2dqbf/`.

The sequential-AIGER reader is shared from `tools/pec2dqbf/aiger_seq.py`.

## Example

A 2-bit counter with `bad = l0 ∧ l1`:

```
aag 5 0 2 1 3
2 3
4 10
6
6 2 4
8 3 5
10 7 9
```

Unroll to bound 3:

```
python -m tools.bmc2dqbf.cli counter2.aag -k 3 -o counter2_k3.dqdimacs
```

Prefix of the output (no inputs ⇒ no universals; pure SAT):

```
c bmc2dqbf source=counter2.aag bound=3 safe=False
c circuit: I=0 L=2 A=3
p cnf 21 52
d 1 0
d 2 0
...
```

With one primary input the prefix becomes a 2QBF:
`a i_0 i_1 ... i_k 0` followed by `d`-lines whose dependency sets grow
monotonically over the input universals.
