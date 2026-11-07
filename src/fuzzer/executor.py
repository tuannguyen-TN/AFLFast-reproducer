"""Target execution harness. [implements FR-2 / ticket AFL-003]

Runs the instrumented target on one input, enforces a timeout, and reports
(exit_status, signal, coverage_bitmap). A crash = termination by SIGSEGV/SIGABRT.
"""
# TODO(AFL-003): implement fork/exec + timeout + signal capture.
