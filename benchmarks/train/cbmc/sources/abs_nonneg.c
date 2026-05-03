// SAFE: abs of a bounded int is non-negative.
int nondet_int(void);
int main(void) {
  int x = nondet_int();
  __CPROVER_assume(x > -1000 && x < 1000);
  int a = x < 0 ? -x : x;
  __CPROVER_assert(a >= 0, "abs nonneg");
  return 0;
}
