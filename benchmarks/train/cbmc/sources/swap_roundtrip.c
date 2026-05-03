// SAFE: XOR-swap twice is the identity.
unsigned nondet_uint(void);
static void xswap(unsigned *a, unsigned *b) {
  *a ^= *b; *b ^= *a; *a ^= *b;
}
int main(void) {
  unsigned x = nondet_uint(), y = nondet_uint();
  unsigned ox = x, oy = y;
  xswap(&x, &y);
  xswap(&x, &y);
  __CPROVER_assert(x == ox && y == oy, "swap roundtrip");
  return 0;
}
