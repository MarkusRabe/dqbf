// BUGGY: sum 0..n-1 but loop runs to n inclusive.
int nondet_int(void);
int main(void) {
  int n = nondet_int();
  __CPROVER_assume(n >= 1 && n <= 6);
  int s = 0;
  for (int i = 0; i <= n; ++i) s += i;  // should be i < n
  __CPROVER_assert(s == n * (n - 1) / 2, "triangular");
  return 0;
}
