/* Realistic-ish target: a tiny Type-Length-Value parser.
 * [ticket AFL-010] PLANTED BUG: trusts the length byte -> stack overflow,
 * caught by AddressSanitizer. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    uint8_t in[512];
    size_t n = fread(in, 1, sizeof(in), stdin);
    if (n < 2) return 0;

    uint8_t type = in[0];
    uint8_t len  = in[1];          /* attacker-controlled length */
    char field[64];

    (void)type;
    /* BUG: len can be up to 255 but field is 64 bytes. */
    memcpy(field, in + 2, len);    /* overflow when len > 64 */
    printf("parsed %u bytes\n", len);
    return 0;
}
