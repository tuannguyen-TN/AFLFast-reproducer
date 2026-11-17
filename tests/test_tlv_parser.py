"""AFL-010: tlv_parser planted bugs, seed S0, depth classes, sweep, ground truth (via Executor)."""
import hashlib
import json
import re
import signal
import subprocess
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest
from conftest import needs_clang

from fuzzer.executor import Executor
from fuzzer.fuzzer import crash_site, seed_files

TARGETS = Path(__file__).resolve().parent.parent / "targets"
SRC = "tlv_parser.c"
S0 = (TARGETS / "seeds/tlv_parser/S0").read_bytes()
GT = json.loads((TARGETS / "ground_truth.json").read_text())
T1 = S0[:1] + b"\x50" + S0[2:]  # tlv-1: S0 with byte 1 substituted
REJECTED = S0[:1] + b"\x90" + S0[2:]
# tlv-2 (AFL-035): S0 carries a dormant extension record; each step substitutes one byte
S1 = S0[:6] + b"\x7e" + S0[7:]  # marker FE -> 7E
S2 = S1[:8] + b"X" + S1[9:]  # selector Y -> X
S3 = S2[:9] + b"\x10"  # index byte 0x10 >= 4: the trigger
STAIRCASE = [S0, S1, S2, S3]


@pytest.fixture(scope="module")
def ex() -> Iterator[Executor]:
    subprocess.run(["make", "-C", str(TARGETS), "bin/tlv_parser"], check=True)
    e = Executor(TARGETS / "bin" / "tlv_parser", timeout_s=5.0)
    yield e
    e.close()


def test_seed_and_hash() -> None:
    assert len(S0) <= 32
    assert seed_files(TARGETS / "seeds/tlv_parser") == [TARGETS / "seeds/tlv_parser/S0"]
    line = (TARGETS / "seeds/SHA256SUMS").read_text().splitlines()
    assert f"{hashlib.sha256(S0).hexdigest()}  tlv_parser/S0" in line


def test_ground_truth_and_source_docs() -> None:
    src = (TARGETS / SRC).read_text()
    assert GT["tlv-1"]["function"] == "main" and GT["tlv-2"]["function"] != "main"
    for bug in ("tlv-1", "tlv-2"):
        g = GT[bug]
        assert g["target"] == "tlv_parser" and g["file"] == SRC
        assert f"PLANTED BUG {bug}" in src
    assert f"static void {GT['tlv-2']['function']}(" in src
    assert "fopen" not in src and "socket" not in src  # NFR-6: stdin only
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.DOTALL)
    assert "/" not in code.replace("#include", "") and "%" not in re.sub(r'"[^"]*"', "", code)


@needs_clang
def test_trigger_table(ex: Executor) -> None:
    table = json.loads((TARGETS / "triggers.json").read_text())
    for bug in ("tlv-1", "tlv-2"):
        r = ex.run(bytes.fromhex(table[bug]))
        assert r.outcome == "crash"
        assert crash_site(r.stderr, SRC) == GT[bug]["function"]
    assert bytes.fromhex(table["tlv-1"]) == T1 and bytes.fromhex(table["tlv-2"]) == STAIRCASE[-1]


@needs_clang
def test_benign_and_guard_sides(ex: Executor) -> None:
    for data in (b"", S0, REJECTED):
        r = ex.run(data)
        assert (r.outcome, r.signal, r.exit_status) == ("clean", None, 0)
        assert b"AddressSanitizer" not in r.stderr
    r = ex.run(T1)
    assert (r.outcome, r.signal) == ("crash", signal.SIGABRT)
    # (a) the overflow side takes an edge neither benign side takes
    assert ex.run(T1).edges - ex.run(S0).edges - ex.run(REJECTED).edges


@needs_clang
def test_tlv1_shallow(ex: Executor) -> None:
    assert len(T1) == len(S0) and sum(a != b for a, b in zip(S0, T1)) == 1
    r = ex.run(T1)
    assert (r.outcome, r.signal) == ("crash", signal.SIGABRT)
    assert b"stack-buffer-overflow" in r.stderr and crash_site(r.stderr, SRC) == "main"


@needs_clang
def test_tlv2_deep_staircase(ex: Executor) -> None:
    runs = [ex.run(s) for s in STAIRCASE]
    assert all(x.outcome == "clean" for x in runs[:-1])
    last = runs[-1]
    assert (last.outcome, last.signal) == ("crash", signal.SIGABRT)
    assert b"heap-buffer-overflow" in last.stderr
    assert crash_site(last.stderr, SRC) == GT["tlv-2"]["function"]
    for prev, cur in pairwise(runs):
        assert cur.edges - prev.edges


@needs_clang
def test_tlv2_oob_boundary(ex: Executor) -> None:
    """Index 3 is in range; index 4 takes the ext-index-oob edge and crashes (kills `>= 4` -> `> 4`)."""
    in_range, oob = ex.run(S2[:9] + b"\x03"), ex.run(S2[:9] + b"\x04")
    assert in_range.outcome == "clean" and oob.outcome == "crash"
    assert oob.edges - in_range.edges


@pytest.mark.slow
@needs_clang
def test_single_byte_sweep(ex: Executor) -> None:
    sites: dict[str, int] = {}
    for i in range(len(S0)):
        for v in range(256):
            r = ex.run(S0[:i] + bytes([v]) + S0[i + 1:])
            assert r.outcome != "hang"
            if r.outcome == "crash":
                s = crash_site(r.stderr, SRC)
                assert s in (GT["tlv-1"]["function"], GT["tlv-2"]["function"]), r.stderr
                sites[s] = sites.get(s, 0) + 1
    assert GT["tlv-1"]["function"] in sites  # shallow
    assert GT["tlv-2"]["function"] not in sites  # deep
