"""AFL-001 spike: edge ids reach Python and differ per branch."""
import subprocess
from pathlib import Path

from conftest import needs_clang

from fuzzer.coverage import run_with_coverage

TARGETS = Path(__file__).resolve().parent.parent / "targets"


@needs_clang
def test_edge_sets_differ_per_branch() -> None:
    subprocess.run(["make", "-C", str(TARGETS), "bin/spike"], check=True)
    binary = str(TARGETS / "bin" / "spike")
    a = run_with_coverage(binary, b"A")
    b = run_with_coverage(binary, b"B")
    assert a and b
    assert a != b
