"""Power schedules. [implements FR-5 / ticket AFL-006] -- the AFLFast core.

assign_energy(seed, corpus) -> int  (number of mutations to spend on `seed`).

Schedules:
  UNIFORM  -- baseline: equal energy per seed (vanilla AFL behaviour).
  FAST     -- AFLFast exponential schedule: more energy to seeds exercising
              low-frequency (rare) paths, less to high-frequency ones.
The UNIFORM-vs-FAST toggle is the independent variable of the whole experiment.
"""
# TODO(AFL-006): implement UNIFORM and FAST (exponential) power schedules.
