"""AFL-016: mini_format planted bugs, seed S0, depth classes, path diversity, sweep (via Executor)."""
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

from fuzzer.coverage import path_id
from fuzzer.executor import Executor
from fuzzer.fuzzer import crash_site, seed_files

TARGETS = Path(__file__).resolve().parent.parent / "targets"
SRC = "mini_format.c"
S0 = (TARGETS / "seeds/mini_format/S0").read_bytes()
GT = json.loads((TARGETS / "ground_truth.json").read_text())
H1, H2 = b"MF\x01\x00", b"MF\x02\x00"
T2 = S0[:5] + b"\x05" + S0[6:]  # mfp-2: S0 with byte 5 substituted
S1 = S0[:2] + b"\x02" + S0[3:]
S2 = S1[:8] + b"T" + S1[9:]  # AFL-035: dormant T/G bytes after the unknown type AB come alive
S3 = S2[:11] + b"\xff" + S2[12:]  # idx == table size 0xFF
STAIRCASE = [S0, S1, S2, S3]  # last = mfp-1 trigger
BENIGN = [
    b"", b"M", b"MF", b"XF\x01\x00", b"MX\x01\x00",  # empty, magic-only, bad magic
    H1, H2, b"MF\x03\x00", b"MF\x01\x01",  # header variants
    H1 + b"A", H1 + b"A\x00", H1 + b"A\x02x", H1 + b"A\x02xy", H1 + b"A\x01z", H1 + b"A\x09" + b"z" * 9,
    H1 + b"B", H1 + b"B\x00", H1 + b"B\x01k", H1 + b"B\x01kv", H1 + b"B\x01\x80\x00",
    H1 + b"C\x01q", H1 + b"C\x03q", H1 + b"?", H1 + b"T\x02", H1 + b"G\x00",
    S0, H1 + b"A\x00B\x00C\x00",
    H2 + b"T", H2 + b"T\x00", H2 + b"T\x04", H2 + b"T\x04T\x02", H2 + b"G\x00", H2 + b"T\x04G\x00",
    H2 + b"T\x04G\x05", H2 + b"T\x04G", H2 + b"T\x04A\x01aG\x01",
]


@pytest.fixture(scope="module")
def ex() -> Iterator[Executor]:
    subprocess.run(["make", "-C", str(TARGETS), "bin/mini_format"], check=True)
    e = Executor(TARGETS / "bin" / "mini_format", timeout_s=5.0)
    yield e
    e.close()


def test_seed_and_hash() -> None:
    assert 0 < len(S0) <= 32
    assert seed_files(TARGETS / "seeds/mini_format") == [TARGETS / "seeds/mini_format/S0"]
    line = (TARGETS / "seeds/SHA256SUMS").read_text().splitlines()
    assert f"{hashlib.sha256(S0).hexdigest()}  mini_format/S0" in line


def test_ground_truth_and_source_docs() -> None:
    src = (TARGETS / SRC).read_text()
    f1, f2 = GT["mfp-1"]["function"], GT["mfp-2"]["function"]
    assert f1 != f2 and "main" not in (f1, f2)
    for bug in ("mfp-1", "mfp-2"):
        assert GT[bug]["target"] == "mini_format" and GT[bug]["file"] == SRC
        assert f"PLANTED BUG {bug}" in src
        assert f"static int {GT[bug]['function']}(" in src
    assert "fopen" not in src and "socket" not in src  # NFR-6: stdin only
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.DOTALL)
    assert "/" not in code.replace("#include", "") and "%" not in re.sub(r'"[^"]*"', "", code)


@needs_clang
def test_path_diversity(ex: Executor) -> None:
    assert len(set(BENIGN)) == len(BENIGN) >= 20
    ids = set()
    for data in BENIGN:
        r = ex.run(data)
        assert (r.outcome, r.signal, r.exit_status) == ("clean", None, 0), data
        assert b"AddressSanitizer" not in r.stderr
        ids.add(path_id(r.hits))
    assert len(ids) == len(BENIGN), (len(ids), len(BENIGN))


@needs_clang
def test_trigger_table(ex: Executor) -> None:
    table = json.loads((TARGETS / "triggers.json").read_text())
    for bug in ("mfp-1", "mfp-2"):
        r = ex.run(bytes.fromhex(table[bug]))
        assert r.outcome == "crash"
        assert crash_site(r.stderr, SRC) == GT[bug]["function"]
    assert bytes.fromhex(table["mfp-1"]) == STAIRCASE[-1]
    assert bytes.fromhex(table["mfp-2"]) == T2


@needs_clang
def test_mfp2_shallow(ex: Executor) -> None:
    assert len(T2) == len(S0) and sum(a != b for a, b in zip(S0, T2)) == 1
    r = ex.run(T2)
    assert (r.outcome, r.signal) == ("crash", signal.SIGABRT)
    assert b"ERROR: AddressSanitizer:" in r.stderr and b"stack-buffer-overflow" in r.stderr
    assert crash_site(r.stderr, SRC) == GT["mfp-2"]["function"]


@needs_clang
def test_mfp1_deep_staircase(ex: Executor) -> None:
    runs = [ex.run(s) for s in STAIRCASE]
    assert all((x.outcome, x.exit_status) == ("clean", 0) for x in runs[:-1])
    last = runs[-1]
    assert (last.outcome, last.signal) == ("crash", signal.SIGABRT)
    assert b"ERROR: AddressSanitizer:" in last.stderr and b"heap-buffer-overflow" in last.stderr
    assert crash_site(last.stderr, SRC) == GT["mfp-1"]["function"]
    for prev, cur in pairwise(runs):
        assert cur.edges - prev.edges


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
                assert s in (GT["mfp-1"]["function"], GT["mfp-2"]["function"]), r.stderr
                sites[s] = sites.get(s, 0) + 1
    assert GT["mfp-2"]["function"] in sites  # shallow
    assert GT["mfp-1"]["function"] not in sites  # deep
