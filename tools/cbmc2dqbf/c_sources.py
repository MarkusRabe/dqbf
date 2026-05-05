"""C-source text for each cbmc_v2 algorithm × {ok,bug}.

Each source is a single-loop `main()` with `__CPROVER_assume` for
preconditions and one `__CPROVER_assert`. The convention matches
`benchmarks/train/cbmc/`: CBMC's CNF is SAT iff the assertion can fail,
so `_ok.c` → expected unsat, `_bug.c` → expected sat.

Kept in code (not as 24 checked-in `.c` files) so the generator can
sweep `BITS` without source duplication.
"""

from __future__ import annotations

from collections.abc import Callable

PREAMBLE = """\
typedef unsigned __CPROVER_bitvector[{bits}] u_t;
u_t nondet_u(void);
unsigned nondet_bool(void);
#define BITS {bits}
"""


def popcount(bug: bool) -> str:
    sample = "x >>= 1; c += x & 1u;" if bug else "c += x & 1u; x >>= 1;"
    return f"""\
int main(void) {{
  u_t seed = nondet_u();
  u_t x = seed, c = 0;
  while (x) {{ {sample} }}
  u_t ref = 0; for (u_t m = seed; m; m >>= 1) ref += m & 1u;
  __CPROVER_assert(c == ref, "popcount");
  return 0;
}}
"""


def parity(bug: bool) -> str:
    init = "1" if bug else "0"
    return f"""\
int main(void) {{
  u_t seed = nondet_u();
  u_t x = seed, p = {init};
  while (x) {{ p ^= x & 1u; x >>= 1; }}
  u_t ref = 0; for (u_t m = seed; m; m >>= 1) ref ^= m & 1u;
  __CPROVER_assert(p == ref, "parity");
  return 0;
}}
"""


def bitrev(bug: bool) -> str:
    sh = "y >>= 1;" if bug else "y <<= 1;"
    return f"""\
int main(void) {{
  u_t seed = nondet_u();
  u_t x = seed, y = 0;
  for (unsigned i = 0; i < BITS; ++i) {{ {sh} y |= x & 1u; x >>= 1; }}
  u_t ref = 0, m = seed;
  for (unsigned i = 0; i < BITS; ++i) {{ ref <<= 1; ref |= m & 1u; m >>= 1; }}
  __CPROVER_assert(y == ref, "bitrev");
  return 0;
}}
"""


def mul_shiftadd(bug: bool) -> str:
    cond = "1" if bug else "(b & 1u)"
    return f"""\
typedef unsigned __CPROVER_bitvector[2*BITS] uw_t;
int main(void) {{
  u_t a0 = nondet_u(), b0 = nondet_u();
  uw_t aw = a0, p = 0; u_t b = b0;
  for (unsigned i = 0; i < BITS; ++i) {{ if ({cond}) p += aw; aw <<= 1; b >>= 1; }}
  uw_t ref = (uw_t)a0 * (uw_t)b0;
  __CPROVER_assert(p == ref, "mul");
  return 0;
}}
"""


def divmod(bug: bool) -> str:
    cmp = ">" if bug else ">="
    return f"""\
int main(void) {{
  u_t n = nondet_u(), d = nondet_u();
  __CPROVER_assume(d != 0u);
  u_t r = 0, q = 0;
  for (int i = BITS - 1; i >= 0; --i) {{
    r = (r << 1) | ((n >> i) & 1u);
    if (r {cmp} d) {{ r -= d; q |= (u_t)1u << i; }}
  }}
  __CPROVER_assert(r < d, "remainder bound");
  return 0;
}}
"""


def gcd_sub(bug: bool) -> str:
    body = "if (a > b) b -= a; else a -= b;" if bug else "if (a > b) a -= b; else b -= a;"
    return f"""\
int main(void) {{
  u_t a0 = nondet_u(), b0 = nondet_u();
  __CPROVER_assume(a0 > 0u && b0 > 0u);
  u_t a = a0, b = b0, mx = a0 > b0 ? a0 : b0;
  while (a != b) {{ {body} }}
  __CPROVER_assert(a <= mx, "gcd bounded");
  return 0;
}}
"""


def stream_min(bug: bool) -> str:
    upd = "m = x < m ? m : x;" if bug else "m = x < m ? x : m;"
    return f"""\
int main(void) {{
  u_t m = nondet_u();
  for (unsigned i = 0; i < BITS; ++i) {{
    u_t prev = m;
    u_t x = nondet_u();
    {upd}
    __CPROVER_assert(m <= prev, "min non-increasing");
  }}
  return 0;
}}
"""


def sat_ctr(bug: bool) -> str:
    dec = "--c;" if bug else "if (c) --c;"
    return f"""\
int main(void) {{
  u_t c = 0, max = (u_t)~0u;
  for (unsigned i = 0; i < 2*BITS; ++i) {{
    u_t pc = c;
    if (nondet_bool()) {{ {dec} }} else {{ if (c != max) ++c; }}
    __CPROVER_assert(!(pc == 0u && c == max), "no underflow wrap");
  }}
  return 0;
}}
"""


def clz(bug: bool) -> str:
    cond = "!(x >> (BITS-1))" if bug else "x && !(x >> (BITS-1))"
    return f"""\
int main(void) {{
  u_t seed = nondet_u(), x = seed;
  unsigned c = 0;
  for (unsigned i = 0; i < 2*BITS; ++i)
    if ({cond}) {{ x <<= 1; ++c; }}
  __CPROVER_assert(c <= BITS, "clz bounded");
  return 0;
}}
"""


def fib(bug: bool) -> str:
    init = "u_t a = 1, b = 0;" if bug else "u_t a = 0, b = 1;"
    return f"""\
int main(void) {{
  {init}
  for (unsigned i = 0; i < BITS; ++i) {{
    __CPROVER_assert(a <= b, "fib ordered");
    u_t t = a + b; a = b; b = t;
  }}
  return 0;
}}
"""


def token_bucket(bug: bool) -> str:
    add = "++tok;" if bug else "if (tok != (u_t)~0u) ++tok;"
    return f"""\
int main(void) {{
  u_t tok = 0;
  for (unsigned i = 0; i < (1u<<BITS)+1; ++i) {{
    u_t prev = tok; unsigned take = nondet_bool();
    {add}
    if (take && tok) --tok;
    __CPROVER_assert(take || tok >= prev, "no-take ⇒ non-decreasing");
  }}
  return 0;
}}
"""


def onehot_rt(bug: bool) -> str:
    enc = "h |= 1u;" if bug else ""
    return f"""\
int main(void) {{
  for (u_t i = 0; i < BITS; ++i) {{
    u_t h = (u_t)1u << i; {enc}
    u_t j = 0; while (!((h >> j) & 1u)) ++j;
    __CPROVER_assert(j == i, "onehot roundtrip");
  }}
  return 0;
}}
"""


C_SOURCES: dict[str, Callable[[bool], str]] = {
    "popcount": popcount,
    "parity": parity,
    "bitrev": bitrev,
    "mul_shiftadd": mul_shiftadd,
    "divmod": divmod,
    "gcd_sub": gcd_sub,
    "stream_min": stream_min,
    "sat_ctr": sat_ctr,
    "clz": clz,
    "fib": fib,
    "token_bucket": token_bucket,
    "onehot_rt": onehot_rt,
}


def render(name: str, bug: bool, bits: int) -> str:
    return PREAMBLE.format(bits=bits) + C_SOURCES[name](bug)
