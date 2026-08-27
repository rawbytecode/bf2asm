"""
bf2asm.compiler
================

A small, from-scratch compiler that translates Brainfuck source into
x86-64 assembly (GNU AS / AT&T syntax, Linux syscall ABI, no libc
dependency).

Pipeline
--------
    source text -> tokens -> IR (list of Op) -> optimizer -> asm text

The IR pass folds runs of identical `+ - > <` into single ops carrying
a count (e.g. `+++++` becomes one ADD op with amount=5), and recognises
the extremely common `[-]` / `[+]` "clear cell" idiom, replacing it
with a single CLEAR op. This keeps generated code compact and avoids
emitting thousands of single-byte increments for typical programs.

The generated program uses a 30,000-byte zeroed tape in .bss and
%rbx as the data pointer (a callee-/syscall-saved register, so it
survives read/write syscalls without spilling).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


TAPE_SIZE = 30_000


class BrainfuckSyntaxError(ValueError):
    """Raised when brackets in the source are unbalanced."""


# ---------------------------------------------------------------------------
# IR
# ---------------------------------------------------------------------------

@dataclass
class Op:
    kind: str        # 'ADD', 'MOVE', 'OUT', 'IN', 'LOOP_START', 'LOOP_END', 'CLEAR'
    amount: int = 0   # used by ADD / MOVE
    label: int = 0    # used by LOOP_START / LOOP_END (matching pair id)


def parse(source: str) -> List[Op]:
    """Turn raw Brainfuck source into a run-length-encoded IR."""
    # Strip everything that isn't a BF command; anything else is a comment.
    commands = [c for c in source if c in "+-<>.,[]"]

    ir: List[Op] = []
    loop_stack: List[int] = []
    next_label = 0

    i = 0
    n = len(commands)
    while i < n:
        c = commands[i]

        if c in "+-":
            j = i
            total = 0
            while j < n and commands[j] in "+-":
                total += 1 if commands[j] == "+" else -1
                j += 1
            if total != 0:
                ir.append(Op("ADD", amount=total % 256))
            i = j
            continue

        if c in "<>":
            j = i
            total = 0
            while j < n and commands[j] in "<>":
                total += 1 if commands[j] == ">" else -1
                j += 1
            if total != 0:
                ir.append(Op("MOVE", amount=total))
            i = j
            continue

        if c == ".":
            ir.append(Op("OUT"))
            i += 1
            continue

        if c == ",":
            ir.append(Op("IN"))
            i += 1
            continue

        if c == "[":
            label = next_label
            next_label += 1
            loop_stack.append(label)
            ir.append(Op("LOOP_START", label=label))
            i += 1
            continue

        if c == "]":
            if not loop_stack:
                raise BrainfuckSyntaxError(
                    f"unmatched ']' at command index {i}"
                )
            label = loop_stack.pop()
            ir.append(Op("LOOP_END", label=label))
            i += 1
            continue

    if loop_stack:
        raise BrainfuckSyntaxError(
            f"unmatched '[' ({len(loop_stack)} bracket(s) never closed)"
        )

    return ir


def optimize(ir: List[Op]) -> List[Op]:
    """Collapse the `[-]` / `[+]` clear-cell idiom into one CLEAR op."""
    out: List[Op] = []
    i = 0
    n = len(ir)
    while i < n:
        if (
            i + 2 < n
            and ir[i].kind == "LOOP_START"
            and ir[i + 1].kind == "ADD"
            and ir[i + 1].amount % 256 in (255, 1)  # '-' or '+' by exactly one
            and ir[i + 2].kind == "LOOP_END"
            and ir[i + 2].label == ir[i].label
        ):
            out.append(Op("CLEAR"))
            i += 3
            continue
        out.append(ir[i])
        i += 1
    return out


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

_PROLOGUE = """\
    .section .bss
    .lcomm tape, {tape_size}
    .lcomm inbuf, 1

    .section .text
    .globl _start

_start:
    lea tape(%rip), %rbx
"""

_EPILOGUE = """\
    # exit(0)
    mov $60, %rax
    xor %rdi, %rdi
    syscall
"""


def generate(ir: List[Op]) -> str:
    """Emit GAS (AT&T) x86-64 assembly for the given IR."""
    lines: List[str] = [_PROLOGUE.format(tape_size=TAPE_SIZE)]

    for op in ir:
        if op.kind == "MOVE":
            amt = op.amount
            if amt == 1:
                lines.append("    inc %rbx")
            elif amt == -1:
                lines.append("    dec %rbx")
            elif amt > 0:
                lines.append(f"    add ${amt}, %rbx")
            else:
                lines.append(f"    sub ${-amt}, %rbx")

        elif op.kind == "ADD":
            amt = op.amount % 256
            if amt == 0:
                continue
            if amt <= 128:
                lines.append(f"    addb ${amt}, (%rbx)")
            else:
                lines.append(f"    subb ${256 - amt}, (%rbx)")

        elif op.kind == "CLEAR":
            lines.append("    movb $0, (%rbx)")

        elif op.kind == "OUT":
            lines.append(
                "    mov $1, %rax\n"
                "    mov $1, %rdi\n"
                "    mov %rbx, %rsi\n"
                "    mov $1, %rdx\n"
                "    syscall"
            )

        elif op.kind == "IN":
            # read() leaves the destination byte untouched on EOF (rax==0),
            # so explicitly zero the cell in that case. This matches the
            # common Brainfuck convention (EOF -> 0) relied on by idioms
            # like ",[.,]".  Numeric local labels are safe to reuse across
            # every IN site: GAS resolves "1f"/"1b" to the nearest matching
            # label in the given direction, not globally.
            lines.append(
                "    xor %rax, %rax\n"
                "    xor %rdi, %rdi\n"
                "    mov %rbx, %rsi\n"
                "    mov $1, %rdx\n"
                "    syscall\n"
                "    test %rax, %rax\n"
                "    jnz 1f\n"
                "    movb $0, (%rbx)\n"
                "1:"
            )

        elif op.kind == "LOOP_START":
            lines.append(
                f"L_start_{op.label}:\n"
                f"    cmpb $0, (%rbx)\n"
                f"    je L_end_{op.label}"
            )

        elif op.kind == "LOOP_END":
            lines.append(
                f"    jmp L_start_{op.label}\n"
                f"L_end_{op.label}:"
            )

        else:  # pragma: no cover - defensive
            raise ValueError(f"unknown IR op: {op.kind}")

    lines.append(_EPILOGUE)
    return "\n".join(lines) + "\n"


def compile_source(source: str, optimize_clear_loops: bool = True) -> str:
    """High-level entry point: Brainfuck source -> x86-64 assembly text."""
    ir = parse(source)
    if optimize_clear_loops:
        ir = optimize(ir)
    return generate(ir)
