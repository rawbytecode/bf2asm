"""
End-to-end tests.

For every case we:
  1. Compile the Brainfuck source with bf2asm.
  2. Assemble + link the result with GNU `as` / `ld` into a real ELF binary.
  3. Run the binary (optionally feeding it stdin).
  4. Compare its stdout against a trusted pure-Python reference interpreter.

These tests are skipped (not failed) if `as`/`ld` aren't available, since
that's an environment issue rather than a compiler bug.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bf2asm.compiler import BrainfuckSyntaxError, compile_source  # noqa: E402
from tests.reference_interpreter import run as interpret  # noqa: E402

TOOLCHAIN_AVAILABLE = shutil.which("as") is not None and shutil.which("ld") is not None

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parent.parent / "examples"


def build_and_run(source: str, stdin: bytes = b"") -> bytes:
    asm = compile_source(source)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        asm_path = tmp / "prog.s"
        obj_path = tmp / "prog.o"
        bin_path = tmp / "prog"
        asm_path.write_text(asm)

        subprocess.run(["as", "-o", str(obj_path), str(asm_path)], check=True)
        subprocess.run(["ld", "-o", str(bin_path), str(obj_path)], check=True)

        result = subprocess.run(
            [str(bin_path)], input=stdin, stdout=subprocess.PIPE, check=True
        )
        return result.stdout


@unittest.skipUnless(TOOLCHAIN_AVAILABLE, "requires GNU as/ld")
class TestEndToEnd(unittest.TestCase):
    def _check(self, source: str, stdin: bytes = b""):
        expected = interpret(source, stdin)
        actual = build_and_run(source, stdin)
        self.assertEqual(actual, expected)

    def test_hello_world_example(self):
        source = (EXAMPLES_DIR / "hello.bf").read_text()
        self._check(source)
        # Also pin the exact expected bytes for this well-known program.
        self.assertEqual(build_and_run(source), b"Hello World!\n")

    def test_cat_example_echoes_stdin(self):
        source = (EXAMPLES_DIR / "cat.bf").read_text()
        self._check(source, stdin=b"the quick brown fox\n")

    def test_cat_example_handles_empty_stdin(self):
        source = (EXAMPLES_DIR / "cat.bf").read_text()
        self._check(source, stdin=b"")

    def test_simple_addition(self):
        # cell0 = 'A' (65), print it, then increment to 'B' and print.
        source = "+" * 65 + ".+."
        self._check(source)

    def test_wraparound_arithmetic(self):
        # 255 increments then one more should wrap 0 -> 255 -> print as a byte.
        source = "-" * 1 + "."
        self._check(source)

    def test_nested_loops(self):
        # 3 * 4 = 12 -> print as raw byte (unprintable but byte-comparable).
        source = "+++[>++++<-]>."
        self._check(source)

    def test_clear_loop_idiom(self):
        source = "+++++[-]."
        self._check(source)
        self.assertEqual(build_and_run(source), b"\x00")

    def test_move_run_length_negative(self):
        source = ">>>>+<<<<."  # net move should return to origin; prints 0
        self._check(source)


class TestCompilerUnit(unittest.TestCase):
    """Pure IR/codegen tests that don't need a toolchain."""

    def test_unmatched_open_bracket_raises(self):
        with self.assertRaises(BrainfuckSyntaxError):
            compile_source("[+")

    def test_unmatched_close_bracket_raises(self):
        with self.assertRaises(BrainfuckSyntaxError):
            compile_source("+]")

    def test_output_contains_expected_sections(self):
        asm = compile_source("+.")
        self.assertIn(".section .bss", asm)
        self.assertIn(".lcomm tape, 30000", asm)
        self.assertIn("_start:", asm)
        self.assertIn("syscall", asm)

    def test_clear_loop_folds_to_single_movb(self):
        asm_optimized = compile_source("[-]", optimize_clear_loops=True)
        asm_unoptimized = compile_source("[-]", optimize_clear_loops=False)
        self.assertIn("movb $0, (%rbx)", asm_optimized)
        self.assertNotIn("L_start_0", asm_optimized)
        self.assertIn("L_start_0", asm_unoptimized)

    def test_comments_are_ignored(self):
        # Only + - < > . , [ ] are commands; everything else is a comment.
        asm_with_comments = compile_source("this is a comment + and this too")
        asm_plain = compile_source("+")
        self.assertEqual(asm_with_comments, asm_plain)


if __name__ == "__main__":
    unittest.main()
