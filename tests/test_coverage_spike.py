"""AFL-001 spike: edge ids reach Python and differ per branch."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fuzzer.coverage import run_with_coverage

TARGETS = Path(__file__).resolve().parent.parent / "targets"


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang unavailable")
def test_edge_sets_differ_per_branch() -> None:
    subprocess.run(["make", "-C", str(TARGETS), "bin/spike"], check=True)
    binary = str(TARGETS / "bin" / "spike")
    a = run_with_coverage(binary, b"A")
    b = run_with_coverage(binary, b"B")
    assert a and b
    assert a != b
