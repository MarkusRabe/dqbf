// SAFE: addition is commutative on machine ints.
int nondet_int(void);
int main(void) {
  int a = nondet_int(), b = nondet_int();
  __CPROVER_assert(a + b == b + a, "add comm");
  return 0;
}
