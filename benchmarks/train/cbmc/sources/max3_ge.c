// SAFE: max(a,b,c) >= each argument.
int nondet_int(void);
static int max2(int a, int b) { return a > b ? a : b; }
int main(void) {
  int a = nondet_int(), b = nondet_int(), c = nondet_int();
  int m = max2(max2(a, b), c);
  __CPROVER_assert(m >= a && m >= b && m >= c, "max3 ge");
  return 0;
}
