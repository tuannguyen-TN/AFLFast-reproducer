/* Realistic-ish target: a tiny Type-Length-Value parser with TWO planted bugs.
 * [ticket AFL-010] Ground truth: targets/ground_truth.json (tlv-1, tlv-2).
 *
 * Input (stdin): record 1 = type(1) len(1) payload(len), then optionally an
 * extension record = 0x7E len(1) payload(len), located at offset 2 + len.
 *
 * Seed S0 = 01 04 'A' 'B' 'C' 'D' (targets/seeds/tlv_parser/S0, clean, exit 0).
 * Both bugs are measured against it through fuzzer.executor.Executor
 * (tests/test_tlv_parser.py). Depth classes use AFL-016's "Depth definitions".
 *
 * PLANTED BUG tlv-1 (SHALLOW). Function: main(). Single crash site: the memcpy
 * into `field` (64 bytes) with the attacker-controlled length.
 * Trigger: type 0x01 with len byte 65..128, or any other type with len byte
 * 65..255; type 0x01 with len > 128 is rejected by the guard at line 65.
 * Report: ASan "stack-buffer-overflow" WRITE in __asan_memcpy, first in-source
 * frame `main`; SIGABRT under abort_on_error=1 (ADR-0002).
 * Depth: T1 = S0 with byte 1 substituted (0x04 -> 0x50), i.e.
 *   01 50 41 42 43 44.
 * Guard sides (each measured in tests/test_tlv_parser.py):
 *   crashing            01 50 41 42 43 44   len 80 -> ASan report, SIGABRT
 *   benign-below-bound  01 04 41 42 43 44   (= S0) -> exit 0, no report
 *   rejected-by-guard   01 90 41 42 43 44   len 144 -> exit 0, no report
 * The overflow side takes a distinct edge (the `len > 64` block), which the
 * benign-below-bound and rejected inputs never take.
 *
 * PLANTED BUG tlv-2 (DEEP). Function: parse_ext(). Single crash site: the read
 * of table[p[1]] (a 4-byte heap block indexed by an input byte).
 * Trigger: extension record 7E, len >= 2, payload 'X' then an index byte >= 4.
 * Report: ASan "heap-buffer-overflow" READ -> SIGABRT under abort_on_error=1
 * (ADR-0002). First in-source frame `parse_ext`.
 * Depth: no single-byte substitution of S0 reaches it (it needs both 0x7E and
 * 'X', neither in S0; 01 00 7E 42 58 44 takes 3). Staircase, clean, adding edges:
 *   S0 = 01 04 41 42 43 44
 *   S1 = S0 + 7E 00         (extension record seen)
 *   S2 = S0 + 7E 01 58      ('X' selector seen)
 *   S3 = S0 + 7E 02 58 10   (index byte read -> crash)
 * No integer divide anywhere; the bug is a plain ASan-reported memory error.
 */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void parse_ext(const uint8_t *p, size_t n) {
    if (n >= 1 && p[0] == 'X') {
        if (n >= 2) {
            char *table = malloc(4);
            volatile char c = table[p[1]];  /* tlv-2: unchecked index */
            (void)c;
            free(table);
        }
    }
}

int main(void) {
    uint8_t in[512];
    size_t n = fread(in, 1, sizeof(in), stdin);
    if (n < 2) return 0;

    uint8_t type = in[0];
    uint8_t len  = in[1];          /* attacker-controlled length */
    char field[64];

    if (type == 0x01 && len > 128) return 0;  /* flawed bound: 65..128 passes */
    if (len > 64) {
        printf("long record\n");   /* distinct edge, taken only on the overflow side */
    }
    memcpy(field, in + 2, len);    /* tlv-1: overflow when len > 64 */
    printf("parsed %u bytes\n", len);

    size_t off = 2 + (size_t)len;
    if (off + 2 <= n && in[off] == 0x7E) {
        size_t el = in[off + 1];
        if (off + 2 + el > n) el = n - off - 2;
        parse_ext(in + off + 2, el);
    }
    return 0;
}
