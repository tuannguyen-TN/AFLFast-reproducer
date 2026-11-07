"""Mutation engine. [implements FR-4 / ticket AFL-005]

Deterministic stage (bit/byte flips, arithmetic, interesting values) + havoc
(stacked random mutations) + splice. Mutation is BLIND: coverage never steers
the direction of a mutation, only which results are retained.
"""
# TODO(AFL-005): implement mutation operators + havoc + splice.
