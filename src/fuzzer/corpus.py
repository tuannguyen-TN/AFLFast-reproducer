"""Seed corpus / queue management. [implements FR-3 / ticket AFL-004]

Holds retained seeds, each with metadata (times_selected, exec_time, size,
coverage). Add a candidate only when it reveals new edges (AFL retention rule).
"""
# TODO(AFL-004): implement corpus add/select/persist.
