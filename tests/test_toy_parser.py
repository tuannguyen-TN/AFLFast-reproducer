"""AFL-009: toy_parser planted bugs, seed S0, depth classes, sweep, ground truth (via Executor)."""
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

TARGETS = Path(__file__).resolve().parent.parent / "targets"
S0 = (TARGETS / "seeds/toy_parser/S0").read_bytes()
STAIRCASE = [S0, b"Baaa", b"BUaa", b"BUGa"]  # toy-1: S0 -> S1 -> S2 -> S3 (crash)
T2 = b"!aaa"  # toy-2: S0 with byte 0 substituted


def site(stderr: bytes) -> str | None:
    """Function of the first ASan frame located in toy_parser.c (AFL-016 depth definition)."""
    m = re.search(rb"#\d+ 0x\w+ in (\w+) \S*toy_parser\.c", stderr)
    return m.group(1).decode() if m else None


@pytest.fixture(scope="module")
def ex() -> Iterator[Executor]:
    subprocess.run(["make", "-C", str(TARGETS), "bin/toy_parser"], check=True)
    e = Executor(TARGETS / "bin" / "toy_parser")
    yield e
    e.close()


def test_seed_and_hash() -> None:
    assert len(S0) <= 32
    assert list((TARGETS / "seeds/toy_parser").iterdir()) == [TARGETS / "seeds/toy_parser/S0"]
    line = (TARGETS / "seeds/SHA256SUMS").read_text().splitlines()
    assert f"{hashlib.sha256(S0).hexdigest()}  toy_parser/S0" in line


def test_ground_truth_and_source_docs() -> None:
    gt = json.loads((TARGETS / "ground_truth.json").read_text())
    assert gt["toy-1"]["function"] != gt["toy-2"]["function"]
    src = (TARGETS / "toy_parser.c").read_text()
    for bug, g in gt.items():
        assert g["target"] == "toy_parser" and g["file"] == "toy_parser.c"
        assert f"PLANTED BUG {bug}" in src and f"static void {g['function']}(" in src
    assert "fopen" not in src and "socket" not in src  # NFR-6: stdin only


@needs_clang
def test_benign_and_seed_clean(ex: Executor) -> None:
    for data in (b"", b"BUX", S0):
        r = ex.run(data)
        assert (r.outcome, r.signal, r.exit_status) == ("clean", None, 0)


@needs_clang
def test_toy1_deep(ex: Executor) -> None:
    r = ex.run(b"BUG")
    assert (r.outcome, r.signal) == ("crash", signal.SIGABRT) and site(r.stderr) == "check"
    assert b"SEGV on unknown address" in r.stderr
    runs = [ex.run(s) for s in STAIRCASE]
    assert all(x.outcome == "clean" for x in runs[:-1])
    assert runs[-1].outcome == "crash" and site(runs[-1].stderr) == "check"
    for prev, cur in pairwise(runs):  # every step adds an edge over the step before
        assert cur.edges - prev.edges


@needs_clang
def test_toy2_shallow(ex: Executor) -> None:
    assert sum(a != b for a, b in zip(S0, T2)) == 1 and len(S0) == len(T2)
    r = ex.run(T2)
    assert (r.outcome, r.signal) == ("crash", signal.SIGABRT)
    assert b"heap-buffer-overflow" in r.stderr and site(r.stderr) == "scan"


@pytest.mark.slow
@needs_clang
def test_single_byte_sweep(ex: Executor) -> None:
    sites: dict[str, int] = {}
    for i in range(len(S0)):
        for v in range(256):
            r = ex.run(S0[:i] + bytes([v]) + S0[i + 1:])
            assert r.outcome != "hang"
            if r.outcome == "crash":
                s = site(r.stderr)
                assert s in ("check", "scan"), r.stderr
                sites[s] = sites.get(s, 0) + 1
    assert "scan" in sites and "check" not in sites  # toy-2 shallow, toy-1 not
