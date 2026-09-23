#!/usr/bin/env python3
"""Convenience entry point so VS Code can Run/Debug a single file.

Equivalent to ``python -m wecreat_index``.
"""

import sys

from wecreat_index.cli import main

if __name__ == "__main__":
    sys.exit(main())
