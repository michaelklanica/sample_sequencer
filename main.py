from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sample Sequencer demos and Textual TUI")
    parser.add_argument("pattern_json", nargs="?", type=Path, help="Optional path to pattern JSON")
    parser.add_argument("--tui", action="store_true", help="Launch interactive Textual editor")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.tui:
        from interfaces.textual import launch_textual_app

        launch_textual_app(args.pattern_json)
        return

    if args.pattern_json is None:
        from interfaces.cli.phase1_demo import run_phase1_demo

        run_phase1_demo()
        return

    from interfaces.cli.json_demo import run_json_demo

    run_json_demo(args.pattern_json)


if __name__ == "__main__":
    main()
