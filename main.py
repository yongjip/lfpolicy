"""Compatibility entry point for local CLI execution.

The primary installed command is ``lfpolicy``.
"""

from lfpolicy.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
