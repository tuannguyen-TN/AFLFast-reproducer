"""Blind mutation engine: havoc + splice, no deterministic stage. [FR-4 / AFL-005]

Mutation is BLIND (CLAUDE.md s2): functions take raw bytes and an injected
random.Random, never coverage, edges, Seeds or the corpus. Coverage acts only
through retention (FR-3) and energy (FR-5). Every candidate comes from mutate();
the flip/arith/interesting operators run only as havoc steps (NFR-1: the injected
rng is the sole randomness source).
"""
import random
from collections.abc import Callable, Sequence
from typing import Literal

HAVOC_STACK_POW2 = 7  # AFL constant: stack is 1 << randint(1, 7) = 2..128 ops
ARITH_MAX = 35  # AFL constant: arithmetic delta in +/-1..35
INTERESTING_8 = (-128, -1, 0, 1, 16, 32, 64, 100, 127)  # AFL set
INTERESTING_16 = (-32768, -129, 128, 255, 256, 512, 1000, 1024, 4096, 32767)  # AFL set
INTERESTING_32 = (-2147483648, -100663046, -32769, 32768, 65535, 65536,
                  100663045, 2147483647)  # AFL set
SPLICE_PROB = 0.1  # project choice: per-mutant splice chance (AFL has a separate stage)
MAX_INPUT = 1024  # project choice: maximum candidate size in bytes
_MAX_BLOCK = 32  # project choice: longest block insert_bytes adds or delete_bytes removes
_WIDTHS = (1, 2, 4)


def bit_flip(data: bytes, rng: random.Random) -> bytes:
    """Flip one random bit; empty input is returned unchanged."""
    if not data:
        return data
    out = bytearray(data)
    out[rng.randrange(len(out))] ^= 1 << rng.randrange(8)
    return bytes(out)


def byte_flip(data: bytes, rng: random.Random) -> bytes:
    """Invert (XOR 0xFF) one random byte."""
    # AFL's deterministic flip8 is XOR 0xFF; AFL's havoc XORs a random 1..255.
    # Using 0xFF is part of the six-op project choice (arm-neutral).
    if not data:
        return data
    out = bytearray(data)
    out[rng.randrange(len(out))] ^= 0xFF
    return bytes(out)


def _put(data: bytes, rng: random.Random, pick: Callable[[int, int], int]) -> bytes:
    """Rewrite a random 1/2/4-byte window (random endianness) with pick(width, old)."""
    widths = [w for w in _WIDTHS if w <= len(data)]
    if not widths:
        return data
    # Project choice: pick uniformly among widths that fit; AFL instead no-ops
    # when the input is too short for a width (arm-neutral).
    w = rng.choice(widths)
    pos = rng.randrange(len(data) - w + 1)
    order: Literal["little", "big"] = rng.choice(("little", "big"))
    old = int.from_bytes(data[pos:pos + w], order)
    new = pick(w, old) % (1 << (8 * w))
    return data[:pos] + new.to_bytes(w, order) + data[pos + w:]


def arith(data: bytes, rng: random.Random) -> bytes:
    """Add a random delta in +/-1..ARITH_MAX to a random 8/16/32-bit window (wraps)."""
    delta = rng.randint(1, ARITH_MAX) * rng.choice((-1, 1))
    return _put(data, rng, lambda _w, old: old + delta)


# AFL's wider interesting sets include the narrower ones.
_INTERESTING = {1: INTERESTING_8,
                2: INTERESTING_8 + INTERESTING_16,
                4: INTERESTING_8 + INTERESTING_16 + INTERESTING_32}


def interesting(data: bytes, rng: random.Random) -> bytes:
    """Overwrite a random 8/16/32-bit window with an AFL interesting value."""
    return _put(data, rng, lambda w, _old: rng.choice(_INTERESTING[w]))


def insert_bytes(data: bytes, rng: random.Random) -> bytes:
    """Insert 1.._MAX_BLOCK bytes at a random offset, capped at MAX_INPUT.

    Project choice (arm-neutral): the block content is uniformly random bytes. AFL
    instead clones an existing block of the input (75%) or inserts a constant-byte
    block (25%).
    """
    room = MAX_INPUT - len(data)
    if room <= 0:
        return data
    n = rng.randint(1, min(_MAX_BLOCK, room))
    block = bytes(rng.randrange(256) for _ in range(n))
    pos = rng.randint(0, len(data))
    return data[:pos] + block + data[pos:]


def delete_bytes(data: bytes, rng: random.Random) -> bytes:
    """Delete a random block, always leaving at least one byte; len<=1 unchanged.

    "Never empties" is AFL behaviour: AFL breaks out when the length is under 2 and
    caps del_len at len-1.
    """
    if len(data) <= 1:
        return data
    n = rng.randint(1, min(_MAX_BLOCK, len(data) - 1))
    pos = rng.randint(0, len(data) - n)
    return data[:pos] + data[pos + n:]


_HAVOC_OPS: tuple[Callable[[bytes, random.Random], bytes], ...] = (
    bit_flip, byte_flip, arith, interesting, insert_bytes, delete_bytes)


def havoc(data: bytes, rng: random.Random) -> bytes:
    """Stack 1 << randint(1, HAVOC_STACK_POW2) uniformly drawn operators."""
    for _ in range(1 << rng.randint(1, HAVOC_STACK_POW2)):
        data = rng.choice(_HAVOC_OPS)(data, rng)
    return data


def splice(data: bytes, other: bytes, rng: random.Random) -> bytes:
    """AFL-style splice: data[:k] + other[k:] at one shared k, 1 <= k < min(len).

    If either input is shorter than 2 bytes, return data unchanged (the caller then
    just havocs). The result is never empty. Project choices (arm-neutral): no
    locate_diffs retry (AFL only splices at a differing region), and `other` may be
    the seed itself.
    """
    n = min(len(data), len(other))
    if n < 2:
        return data
    k = rng.randint(1, n - 1)
    return data[:k] + other[k:]


def mutate(data: bytes, rng: random.Random, pool: Sequence[bytes]) -> bytes:
    """One candidate: with prob SPLICE_PROB (and len(pool) >= 2) splice, then havoc.

    The result is truncated to MAX_INPUT, so an S0 seed longer than 1024 bytes is
    truncated on its first mutant.
    """
    if len(pool) >= 2 and rng.random() < SPLICE_PROB:
        data = splice(data, rng.choice(pool), rng)
    return havoc(data, rng)[:MAX_INPUT]
