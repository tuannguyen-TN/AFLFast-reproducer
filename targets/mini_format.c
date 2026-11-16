/* Third target: a tiny record-format parser ("MF") with TWO planted bugs.
 * [ticket AFL-016] Ground truth: targets/ground_truth.json (mfp-1, mfp-2).
 * Reads stdin only (at most 1024 bytes = MAX_INPUT); no other I/O. Every loop is bounded
 * by the input length or by a one-byte count.
 *
 * FORMAT. Header (4 bytes): 'M' 'F' ver flags.
 *   ver   1 or 2 (anything else: stop). ver 2 enables the T and G records (changes parsing).
 *   flags stored; bit 0 only selects an extra message (no effect on parsing).
 * Then records until the input ends, dispatched on the first byte:
 *   'A' len(1) data(len)        data record (len bounded by 8, see mfp-2)
 *   'B' count(1) (key val)*count   pairs; layout/size set by count (nesting)
 *   'C' len(1) data(len)        comment, skipped
 *   'T' size(1)                 ver 2 only: (re)allocate a heap table of `size` bytes, size >= 1
 *   'G' idx(1)                  ver 2 only, needs a table (cross-record state): read table[idx]
 *   other                       reject: parsing stops, exit 0
 * A truncated record or a failed check also stops parsing (exit 0). Cross-record state:
 * the header version and the table set by T.
 *
 * Seed S0 = 4D 46 01 00 41 02 78 79 AB FF 47 00 42 01 6B 76 (targets/seeds/mini_format/S0,
 * clean, 16 bytes). Under ver 1 the unknown type AB stops parsing, so the T/G bytes after it
 * (T = 54, size FF, G = 47, idx 00) are dormant. [ticket AFL-035: retune, the staircase
 * below is reachable by the real mutate(); calibration in the ticket Log.]
 * Depth classes use AFL-016's "Depth definitions", measured through fuzzer.executor.Executor
 * (tests/test_mini_format.py).
 *
 * PLANTED BUG mfp-2 (SHALLOW). Function: rec_data(). Single crash site: the byte store into
 * name[4] in the copy loop. Trigger: A record with len in 5..8 and len bytes present (the
 * guard allows 8 for a 4-byte buffer). Report: ASan "stack-buffer-overflow" WRITE, first
 * in-source frame `rec_data`; SIGABRT under abort_on_error=1 (ADR-0002).
 * Depth: T2 = S0 with byte 5 substituted (0x02 -> 0x05), i.e.
 *   4D 46 01 00 41 05 78 79 AB FF 47 00 42 01 6B 76.
 * Len 5..8 all crash: four single-byte triggers.
 *
 * PLANTED BUG mfp-1 (DEEP). Function: rec_get(). Single crash site: the read of table[idx].
 * Trigger: ver 2, a T record with size n, then a G record with idx == n (the bound check
 * is off by one: idx > n is rejected, idx == n reads one past the heap block).
 * Report: ASan "heap-buffer-overflow" READ, first in-source frame `rec_get`; SIGABRT.
 * Depth: no single-byte substitution of S0 reaches it (needs ver 2, the T type and idx FF:
 * three substitutions). Staircase, each step one byte substituted, clean except the last,
 * each adding edges:
 *   S0 = 4D 46 01 00 41 02 78 79 AB FF 47 00 42 01 6B 76
 *   S1 = S0 with ver 02                 (ver-2 branch; AB still stops parsing)
 *   S2 = S1 with byte 8 AB -> 54        (table allocated, size FF; G idx 0 in range: cross-record use)
 *   S3 = S2 with byte 11 00 -> FF       (idx == size: "one past" edge, then the read crashes)
 * No integer divide anywhere; both bugs are plain ASan-reported memory errors.
 */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int g_ver;
static uint8_t *g_tab;
static size_t g_tsz;

static int rec_data(const uint8_t *p, size_t n) {
    if (n < 1) return -1;
    size_t len = p[0];
    if (len > 8) return -1;              /* flawed bound: the buffer holds 4 */
    if (n < 1 + len) return -1;
    volatile char name[4];
    for (size_t i = 0; i < len; i++) name[i] = (char)p[1 + i];  /* mfp-2: store */
    if (len && name[0] == 'x') puts("x-name");
    return (int)(1 + len);
}

static int rec_pairs(const uint8_t *p, size_t n) {
    if (n < 1) return -1;
    size_t count = p[0];
    if (n < 1 + 2 * count) return -1;
    for (size_t i = 0; i < count; i++) {
        if (p[1 + 2 * i] & 0x80) puts("hi-key");
        if (p[2 + 2 * i] == 0) puts("zero-val");
    }
    return (int)(1 + 2 * count);
}

static int rec_skip(const uint8_t *p, size_t n) {
    if (n < 1) return -1;
    size_t len = p[0];
    if (n < 1 + len) return -1;
    return (int)(1 + len);
}

static int rec_table(const uint8_t *p, size_t n) {
    if (g_ver != 2 || n < 1) return -1;
    if (p[0] == 0) return -1;
    if (g_tab) {
        puts("realloc");
        free(g_tab);
    }
    g_tsz = p[0];
    g_tab = calloc(g_tsz, 1);
    return 1;
}

static int rec_get(const uint8_t *p, size_t n) {
    if (g_ver != 2 || n < 1 || !g_tab) return -1;
    size_t idx = p[0];
    if (idx > g_tsz) return -1;          /* flawed bound: idx == g_tsz is let through */
    if (idx == g_tsz) puts("one-past");
    volatile uint8_t c = g_tab[idx];     /* mfp-1: read */
    (void)c;
    return 1;
}

int main(void) {
    uint8_t in[1024];
    size_t n = fread(in, 1, sizeof(in), stdin);
    if (n < 1 || in[0] != 'M') return 0;
    if (n < 2 || in[1] != 'F') return 0;
    if (n < 4) return 0;
    g_ver = in[2];
    if (g_ver != 1 && g_ver != 2) return 0;
    if (g_ver == 2) puts("v2");
    if (in[3] & 1) puts("flag0");

    size_t i = 4;
    while (i < n) {
        uint8_t type = in[i++];
        int used;
        switch (type) {
        case 'A': used = rec_data(in + i, n - i); break;
        case 'B': used = rec_pairs(in + i, n - i); break;
        case 'C': used = rec_skip(in + i, n - i); break;
        case 'T': used = rec_table(in + i, n - i); break;
        case 'G': used = rec_get(in + i, n - i); break;
        default: used = -1; break;
        }
        if (used < 0) break;
        i += (size_t)used;
    }
    free(g_tab);
    return 0;
}
