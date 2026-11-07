/* AFL-001 spike target: input starting with 'A' takes one branch, else another. */
#include <stdio.h>

int main(void) {
  int c = getchar();
  if (c == 'A') puts("branch-A");
  else puts("branch-other");
  return 0;
}
