#!/usr/bin/env python3
"""Convenience entry point so VS Code can Run/Debug the web UI as a single file.

Equivalent to ``python -m wecreat_index.server``.
"""

import sys

from wecreat_index.server import main

if __name__ == "__main__":
    sys.exit(main())
