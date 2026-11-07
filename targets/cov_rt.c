/* SanitizerCoverage trace-pc-guard runtime: marks hit guard ids in a POSIX
 * shared-memory bitmap named by env FUZZ_SHM_NAME (AFL-001 spike / FR-1).
 * Presence only: bitmap[guard_id] = 1. Without the env var it is a no-op. */
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

#define MAP_SIZE 65536
#define NO_COV __attribute__((no_sanitize("coverage")))

static volatile uint8_t *bitmap;
static uint32_t next_id = 1;

NO_COV void __sanitizer_cov_trace_pc_guard_init(uint32_t *start, uint32_t *stop) {
  if (start == stop || *start) return;
  const char *name = getenv("FUZZ_SHM_NAME");
  if (name && !bitmap) {
    char path[64]; /* POSIX name needs leading '/'; Python's omits it */
    path[0] = '/';
    size_t i = 0;
    for (; name[i] && i < 62; i++) path[i + 1] = name[i];
    path[i + 1] = 0;
    int fd = shm_open(path, O_RDWR, 0600);
    if (fd >= 0) {
      void *m = mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
      close(fd);
      if (m != MAP_FAILED) bitmap = m;
    }
  }
  for (uint32_t *g = start; g < stop; g++) *g = next_id++ % MAP_SIZE ?: 1;
}

NO_COV void __sanitizer_cov_trace_pc_guard(uint32_t *guard) {
  if (bitmap) bitmap[*guard] = 1;
}
