// BUGGY: index may equal N.
#define N 8
int nondet_int(void);
int main(void) {
  int a[N] = {0};
  int i = nondet_int();
  __CPROVER_assume(i >= 0 && i <= N);  // off-by-one: should be < N
  a[i] = 1;
  __CPROVER_assert(a[0] == 0 || a[0] == 1, "a0");
  return 0;
}
