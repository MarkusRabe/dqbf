// SAFE: a 3-element bubble pass sorts.
int nondet_int(void);
static void sw(int *a, int *b) { int t = *a; *a = *b; *b = t; }
int main(void) {
  int a = nondet_int(), b = nondet_int(), c = nondet_int();
  if (a > b) sw(&a, &b);
  if (b > c) sw(&b, &c);
  if (a > b) sw(&a, &b);
  __CPROVER_assert(a <= b && b <= c, "sorted");
  return 0;
}
