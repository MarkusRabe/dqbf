// BUGGY: divides by y without ruling out y==0. CBMC's div-by-zero
// check fires (or the assertion fails when y==0 and 10/y is undefined).
int nondet_int(void);
int main(void) {
  int y = nondet_int();
  __CPROVER_assume(y >= 0 && y < 4);
  int q = 10 / (y ? y : y);  // y may be 0
  __CPROVER_assert(q >= 0, "q nonneg");
  return 0;
}
