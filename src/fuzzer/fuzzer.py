"""Main fuzzing loop. [implements FR-* / ticket AFL-007]

while budget remains:
    seed   = corpus.select()
    energy = schedule.assign_energy(seed, corpus)
    for _ in range(energy):
        candidate = mutator.mutate(seed)
        status, cov = executor.run(candidate)
        if crashed(status): crashes.save(candidate, status)
        if coverage.has_new_edges(cov): corpus.add(candidate, cov)
        metrics.tick(...)
"""
# TODO(AFL-007): wire corpus + mutator + executor + schedule + metrics.
