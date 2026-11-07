"""Coverage collection from an instrumented target. [implements FR-1 / ticket AFL-002]

Reads an edge-hit bitmap produced by a target compiled with
`-fsanitize-coverage=trace-pc-guard` (shared-memory bitmap, AFL-style).
Exposes: has_new_edges(bitmap) -> bool, and a global seen-edges accumulator.
"""
# TODO(AFL-002): implement shared-memory bitmap read + new-edge detection.
