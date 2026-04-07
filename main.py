from __future__ import annotations

import sys
from pathlib import Path

from interfaces.cli.json_demo import run_json_demo
from interfaces.cli.phase1_demo import run_phase1_demo


def main() -> None:
    if len(sys.argv) == 1:
        run_phase1_demo()
        return

    if len(sys.argv) == 2:
        run_json_demo(Path(sys.argv[1]))
        return

    raise SystemExit("Usage: python main.py [path/to/pattern.json]")


if __name__ == "__main__":
    main()
