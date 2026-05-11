"""Entry point for `python -m markets <subcommand>`."""
from markets.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
