// SAFE (at sufficient unwind): Euclid's gcd divides both inputs.
unsigned nondet_uint(void);
int main(void) {
  unsigned a = nondet_uint(), b = nondet_uint();
  __CPROVER_assume(a > 0u && a < 64u && b > 0u && b < 64u);
  unsigned x = a, y = b;
  while (y) { unsigned t = y; y = x % y; x = t; }
  __CPROVER_assert(a % x == 0u && b % x == 0u, "gcd divides");
  return 0;
}
