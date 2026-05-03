// SAFE: x ^ x == 0.
unsigned nondet_uint(void);
int main(void) {
  unsigned x = nondet_uint();
  __CPROVER_assert((x ^ x) == 0u, "xor self");
  return 0;
}
