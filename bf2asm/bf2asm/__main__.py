"""Command-line interface: bf2asm.

    python3 -m bf2asm program.bf                # write program.s
    python3 -m bf2asm program.bf -o out.s        # custom output path
    python3 -m bf2asm program.bf --no-optimize   # disable clear-loop folding
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from .compiler import BrainfuckSyntaxError, compile_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bf2asm",
        description="Compile a Brainfuck program to x86-64 assembly (GAS syntax).",
    )
    parser.add_argument("source", type=pathlib.Path, help="path to a .bf source file")
    parser.add_argument(
        "-o", "--output", type=pathlib.Path, default=None,
        help="output .s path (default: <source stem>.s)",
    )
    parser.add_argument(
        "--no-optimize", action="store_true",
        help="disable the [-]/[+] clear-loop optimization",
    )
    args = parser.parse_args(argv)

    try:
        source_text = args.source.read_text()
    except OSError as exc:
        print(f"bf2asm: cannot read {args.source}: {exc}", file=sys.stderr)
        return 1

    try:
        asm = compile_source(source_text, optimize_clear_loops=not args.no_optimize)
    except BrainfuckSyntaxError as exc:
        print(f"bf2asm: syntax error: {exc}", file=sys.stderr)
        return 1

    out_path = args.output or args.source.with_suffix(".s")
    out_path.write_text(asm)
    print(f"bf2asm: wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
