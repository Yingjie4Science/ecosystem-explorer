"""Run with python -m plus_inspired. No truth argument in fit/allocate."""
import argparse
import sys

from .runner import execute, verify


def main():
    parser = argparse.ArgumentParser(description="Experimental PLUS-inspired engine, not official PLUS")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ["fit", "predict", "allocate", "validate"]:
        child = commands.add_parser(command)
        child.add_argument("--config", required=True)
        child.add_argument("--output", required=True, help="fresh directory; existing directories refused")
    child = commands.add_parser("verify")
    child.add_argument("--run", required=True)
    child.add_argument("--check-inputs", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            print(verify(args.run, check_inputs=args.check_inputs))
            return 0
        receipt = execute(args.command, args.config, args.output)
    except Exception as error:
        print(f"Rejected: {error}", file=sys.stderr)
        return 2
    print(f"{receipt['status']}; production_release=false; outputs: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
