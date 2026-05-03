// BUGGY: (x << s) >> s == x is false when high bits are shifted out.
unsigned nondet_uint(void);
int main(void) {
  unsigned x = nondet_uint();
  unsigned s = nondet_uint();
  __CPROVER_assume(s < 32u);
  __CPROVER_assert(((x << s) >> s) == x, "shift roundtrip");
  return 0;
}
