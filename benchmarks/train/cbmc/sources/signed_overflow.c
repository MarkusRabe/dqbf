// BUGGY: x+1 > x is false at INT_MAX (signed wrap on this target).
#include <limits.h>
int nondet_int(void);
int main(void) {
  int x = nondet_int();
  __CPROVER_assert(x + 1 > x, "succ gt");
  return 0;
}
