// SAFE: popcount of a 32-bit word is at most 32.
unsigned nondet_uint(void);
int main(void) {
  unsigned x = nondet_uint();
  int c = 0;
  for (int i = 0; i < 32; ++i) c += (x >> i) & 1u;
  __CPROVER_assert(c <= 32, "popcount bound");
  return 0;
}
