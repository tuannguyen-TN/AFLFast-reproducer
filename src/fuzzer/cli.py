"""Command-line entry point. [implements FR-10 / ticket AFL-008]

Example:
    python -m fuzzer.cli --target targets/bin/tlv_parser \\
        --schedule fast --seconds 600 --seed 1 --out results/run1
"""
# TODO(AFL-008): argparse CLI -> configure and launch fuzzer.run().
