"""Crash de-duplication. [implements FR-6 / ticket AFL-013]

Klees warns that naive dedup heuristics massively overcount distinct bugs.
Dedup by crash site (faulting instruction / top-of-stack hash) and report the
heuristic used explicitly in the paper.
"""
# TODO(AFL-013): implement stack/PC-based crash bucketing.
