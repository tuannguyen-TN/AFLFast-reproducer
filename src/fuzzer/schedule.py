"""Power schedules. [implements FR-5 / ticket AFL-006, ADR-0004 s8] -- the AFLFast core.

energy(seed, corpus) -> int: number of mutations to spend on `seed`. Pure: no RNG,
no clock, never writes Seed fields or corpus.seeds. UNIFORM (baseline) vs FAST
(AFLFast, rare paths get more energy) is the experiment's independent variable.
Provenance: AFLFast master afl-fuzz.c / config.h (AFL 2.51b base).
"""
from collections.abc import Callable

from fuzzer.corpus import Corpus, Seed

ALPHA = 256  # AFL config.h:79 HAVOC_CYCLES (base perf_score 100, afl-fuzz.c:4711)
BETA = 1  # AFLFast config.h:92 POWER_BETA (code value; paper text says beta > 1)
MAX_FACTOR = 32 * BETA  # AFLFast config.h:93
HAVOC_MAX_MULT = 16  # config.h:85 -> perf cap 1600 (afl-fuzz.c:4827) -> energy cap 4096
HAVOC_MIN = 16  # config.h:89; clamp at afl-fuzz.c:6170
SKIP_QUEUE_THRESHOLD = 10  # afl-fuzz.c:5160: abandon only if queued_paths > 10

EnergyFn = Callable[[Seed, Corpus], int]


def next_p2(n: int) -> int:
    """Smallest power of two >= n (afl-fuzz.c:4471-4480)."""
    p = 1
    while p < n:
        p <<= 1
    return p


def uniform(seed: Seed, corpus: Corpus) -> int:
    """Constant ALPHA == AFLFast EXPLORE (factor 1), not EXPLOIT (saturates at 4096)."""
    return ALPHA


def fast(seed: Seed, corpus: Corpus) -> int:
    """AFLFast FAST schedule, integer arithmetic only; reads s, f, len(corpus.seeds)."""
    s, f = seed.times_selected, seed.path_freq  # f >= 1 by ADR-0004
    factor = (1 << s) // f if s < 16 else MAX_FACTOR // next_p2(f)  # afl-fuzz.c:4803-4806
    factor = min(factor, MAX_FACTOR)  # afl-fuzz.c:4820-4821
    perf = min(100 * (factor // BETA), HAVOC_MAX_MULT * 100)  # :4823 divides first; :4827 cap
    if perf == 0:
        # AFLFast: queued_paths <= 10 -> stage_max 0 clamped to HAVOC_MIN; > 10 -> skip.
        # Deviation (PRD s8): we give 1 exec instead of skipping, so energy stays >= 1.
        return HAVOC_MIN if len(corpus.seeds) <= SKIP_QUEUE_THRESHOLD else 1
    return ALPHA * perf // 100  # afl-fuzz.c:6154, havoc_div dropped


SCHEDULES: dict[str, EnergyFn] = {"uniform": uniform, "fast": fast}
