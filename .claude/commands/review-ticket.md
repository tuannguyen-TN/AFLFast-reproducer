Act as the **reviewer** subagent. Review the ticket currently in `tickets/review/`
(or the one named: $ARGUMENTS) against each of its acceptance criteria and the
project invariants (variable isolation, blind mutation, reproducibility). Run
`ruff check .`, `mypy src`, and `pytest`. Give a criterion-by-criterion verdict,
then either move it to `tickets/testing/` (approved) or back to
`tickets/in-progress/` (changes requested) with specific reasons appended to its Log.
