"""Coverage collection from an instrumented target. [implements FR-1 / ticket AFL-002]

Spike (AFL-001): the target's C runtime (targets/cov_rt.c) marks hit
trace-pc-guard ids in a POSIX shared-memory bitmap named by env FUZZ_SHM_NAME.
Exposes: has_new_edges(bitmap) -> bool, and a global seen-edges accumulator.
"""
# TODO(AFL-002): has_new_edges + global seen-edges accumulator.
import subprocess
from multiprocessing import shared_memory

MAP_SIZE = 65536


def run_with_coverage(binary: str, data: bytes, timeout: float = 5.0) -> frozenset[int]:
    """Run `binary` with `data` on stdin; return the set of edge ids it hit."""
    shm = shared_memory.SharedMemory(create=True, size=MAP_SIZE)
    try:
        subprocess.run(
            [binary], input=data, capture_output=True, timeout=timeout,
            check=False,  # non-zero exit / crash is a normal fuzz outcome
            env={"FUZZ_SHM_NAME": shm.name},
        )
        assert shm.buf is not None  # always set for a live segment
        return frozenset(i for i, b in enumerate(bytes(shm.buf)) if b)
    finally:
        shm.close()
        shm.unlink()
