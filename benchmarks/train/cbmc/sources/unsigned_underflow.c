// BUGGY: 0u - 1u wraps to UINT_MAX.
unsigned nondet_uint(void);
int main(void) {
  unsigned a = nondet_uint();
  __CPROVER_assume(a < 10u);
  unsigned d = a - 5u;  // wraps when a < 5
  __CPROVER_assert(d < 10u, "no wrap");
  return 0;
}
