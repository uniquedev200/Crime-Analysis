"""Main CLI entrypoint for ATLAS Dev 3.

Invoked as: python -m atlas <subcommand> [options]
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from atlas.cli import cli_main


def main(argv: Sequence[str] | None = None) -> int:
    """Execute ATLAS command-line application."""
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
