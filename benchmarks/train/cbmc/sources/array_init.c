// SAFE: after the init loop every cell holds its index.
#define N 8
int main(void) {
  int a[N];
  for (int i = 0; i < N; ++i) a[i] = i;
  for (int i = 0; i < N; ++i) __CPROVER_assert(a[i] == i, "init");
  return 0;
}
