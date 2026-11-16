"""AFL-035: odds of the retuned tlv-2 / mfp-1 staircases under the real mutate() (slow).

Method (AFL-009 reviewer precedent): for step i (S_{i-1} -> S_i) draw 200,000 mutants
`mutate(S_{i-1}, random.Random(SEED + i), pool=[S_0..S_{i-1}])` (the pool is the corpus a
fuzzer holds at that step, as fuzzer.py passes it). A mutant succeeds at step i iff it executes
an edge in edges(S_i) - edges(S_{i-1}). The predicate is a byte-level Python mirror of the C
parse that emits block labels; a sample is validated against Executor edges (the mirror must
agree exactly). Calibration: the sum of 1/p over the steps lies in [1500, 3000].
Run: pytest -m slow tests/test_retune_odds.py  (not collected by default).
"""
import json
import random
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from conftest import needs_clang

from fuzzer.executor import Executor
from fuzzer.mutator import mutate

TARGETS = Path(__file__).resolve().parent.parent / "targets"
SEED, N = 20261115, 200_000
pytestmark = pytest.mark.slow  # whole module: not collected by the default run
Labels = Callable[[bytes], set[str]]


def tlv_labels(d: bytes) -> set[str]:
    """Mirror of tlv_parser.c (blocks relevant to the staircase)."""
    L: set[str] = set()
    n = len(d)
    if n < 2:
        return L
    t, ln = d[0], d[1]
    if t == 1 and ln > 128:
        L.add("guard")
        return L
    if ln > 64:
        L.add("long")  # tlv-1 side; crashes in main at the memcpy
        return L
    off = 2 + ln
    if off + 2 <= n:
        L.add("ext_cmp")
        if d[off] == 0x7E:
            L.add("marker")
            el = d[off + 1]
            if off + 2 + el > n:
                L.add("clamp")
                el = n - off - 2
            L.add("pe_entry")
            p = d[off + 2:off + 2 + el]
            if el >= 1:
                L.add("pe_n1")
                if p[0] == 0x58 and el >= 2:
                    L.add("oob" if p[1] >= 4 else "inrange")
    return L


def mfp_labels(d: bytes) -> set[str]:
    """Mirror of mini_format.c (blocks relevant to the staircase)."""
    L: set[str] = set()
    n = len(d)
    if n < 1 or d[0] != 0x4D:
        return L
    if n < 2 or d[1] != 0x46:
        L.add("m_bad")
        return L
    if n < 4:
        L.add("short")
        return L
    ver = d[2]
    if ver not in (1, 2):
        L.add("badver")
        return L
    if ver == 2:
        L.add("v2")
    if d[3] & 1:
        L.add("flag0")
    tab: int | None = None
    i = 4
    while i < n:
        typ = d[i]
        i += 1
        p = d[i:]
        m = len(p)
        if typ == 0x41:
            L.add("caseA")
            if m < 1 or p[0] > 8 or m < 1 + p[0]:
                L.add("A_fail")
                break
            if p[0] > 4:
                L.add("A_overflow")
                break
            if p[0] and p[1] == 0x78:
                L.add("x-name")
            used = 1 + p[0]
        elif typ == 0x42:
            L.add("caseB")
            if m < 1 or m < 1 + 2 * p[0]:
                L.add("B_fail")
                break
            for k in range(p[0]):
                if p[1 + 2 * k] & 0x80:
                    L.add("hi-key")
                if p[2 + 2 * k] == 0:
                    L.add("zero-val")
            used = 1 + 2 * p[0]
        elif typ == 0x43:
            L.add("caseC")
            if m < 1 or m < 1 + p[0]:
                L.add("C_fail")
                break
            used = 1 + p[0]
        elif typ == 0x54:
            L.add("caseT")
            if ver != 2 or m < 1 or p[0] == 0:
                L.add("T_fail")
                break
            if tab is not None:
                L.add("realloc")
            tab = p[0]
            L.add("T_ok")
            used = 1
        elif typ == 0x47:
            L.add("caseG")
            if ver != 2 or m < 1 or tab is None:
                L.add("G_fail")
                break
            if p[0] > tab:
                L.add("G_gt")
                break
            if p[0] == tab:
                L.add("one-past")
                break  # crash
            L.add("G_read")
            used = 1
        else:
            L.add("other")
            break
        i += used
    else:
        L.add("loop_end")  # loop left by its condition, not by a break
    return L


@dataclass(frozen=True)
class Cfg:
    binary: str
    labels: Labels
    stairs: list[bytes]


CFGS = {
    "tlv_parser": Cfg("tlv_parser", tlv_labels, [bytes.fromhex(h) for h in (
        "010441424344fe025900", "0104414243447e025900",
        "0104414243447e025800", "0104414243447e025810")]),
    "mini_format": Cfg("mini_format", mfp_labels, [bytes.fromhex(h) for h in (
        "4d46010041027879abff470042016b76", "4d46020041027879abff470042016b76",
        "4d4602004102787954ff470042016b76", "4d4602004102787954ff47ff42016b76")]),
}


def _new_labels(cfg: Cfg) -> list[set[str]]:
    lab = [cfg.labels(s) for s in cfg.stairs]
    return [lab[i] - lab[i - 1] for i in range(1, len(lab))]


def _draw(cfg: Cfg, i: int, n: int) -> list[bytes]:
    rng = random.Random(SEED + i)
    pool = list(cfg.stairs[:i])
    return [mutate(cfg.stairs[i - 1], rng, pool) for _ in range(n)]


@pytest.fixture(params=sorted(CFGS))
def cfg(request: pytest.FixtureRequest) -> Cfg:
    return CFGS[request.param]


@pytest.fixture
def ex(cfg: Cfg) -> Iterator[Executor]:
    subprocess.run(["make", "-C", str(TARGETS), f"bin/{cfg.binary}"], check=True)
    e = Executor(TARGETS / "bin" / cfg.binary, timeout_s=5.0)
    yield e
    e.close()


def test_stairs_start_at_seed_file_and_end_at_trigger(cfg: Cfg) -> None:
    assert cfg.stairs[0] == (TARGETS / "seeds" / cfg.binary / "S0").read_bytes()
    bug = {"tlv_parser": "tlv-2", "mini_format": "mfp-1"}[cfg.binary]
    table = json.loads((TARGETS / "triggers.json").read_text())
    assert cfg.stairs[-1] == bytes.fromhex(table[bug])


def test_sum_of_inverse_odds_in_range(cfg: Cfg) -> None:
    hits = [sum(1 for m in _draw(cfg, i, N) if cfg.labels(m) & new)
            for i, new in enumerate(_new_labels(cfg), start=1)]
    print(cfg.binary, "hits", hits, "p", [h / N for h in hits])
    assert all(hits)
    assert 1500 <= sum(N / h for h in hits) <= 3000, hits


@needs_clang
def test_predicate_matches_executor_edges(cfg: Cfg, ex: Executor) -> None:
    runs = [ex.run(s) for s in cfg.stairs]
    news = _new_labels(cfg)
    ne = [runs[i].edges - runs[i - 1].edges for i in range(1, len(runs))]
    assert all(ne)
    rnd = random.Random(SEED ^ 0x5EED)
    for i in range(1, len(runs)):
        muts = _draw(cfg, i, 20_000)
        pos = [m for m in muts if cfg.labels(m) & news[i - 1]]
        parent = cfg.labels(cfg.stairs[i - 1])
        # near misses: mirror-negative mutants whose labels differ from the parent's (false-negative bait)
        near = [m for m in muts if not cfg.labels(m) & news[i - 1] and cfg.labels(m) != parent]
        sample = {*rnd.sample(pos, min(150, len(pos))), *rnd.sample(near, min(150, len(near))),
                  *rnd.sample(muts, 150)}
        assert len(near) > 0 and len(sample) > 150
        for m in sample:
            want = bool(cfg.labels(m) & news[i - 1])
            assert want == bool(ex.run(m).edges & ne[i - 1]), (i, m.hex())
