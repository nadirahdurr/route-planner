#!/usr/bin/env python3

from pathlib import Path
import sys

PACKAGE_ROOT = Path(__file__).resolve().parent / "packages" / "route_planner_mcp"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from route_planner_mcp.server import mcp, run

__all__ = ["mcp", "run"]


if __name__ == "__main__":
    run()

