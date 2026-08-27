"""A tiny, deliberately naive Brainfuck interpreter.

Used only as a test oracle: we run each example program through both
this interpreter and the real compiled x86-64 binary, and assert the
two outputs match byte-for-byte.
"""
from __future__ import annotations

import sys


def run(source: str, input_bytes: bytes = b"", tape_size: int = 30_000) -> bytes:
    code = [c for c in source if c in "+-<>.,[]"]
    # Precompute matching bracket pairs.
    match = {}
    stack = []
    for i, c in enumerate(code):
        if c == "[":
            stack.append(i)
        elif c == "]":
            j = stack.pop()
            match[i] = j
            match[j] = i

    tape = bytearray(tape_size)
    ptr = 0
    ip = 0
    in_pos = 0
    out = bytearray()

    while ip < len(code):
        c = code[ip]
        if c == "+":
            tape[ptr] = (tape[ptr] + 1) % 256
        elif c == "-":
            tape[ptr] = (tape[ptr] - 1) % 256
        elif c == ">":
            ptr += 1
        elif c == "<":
            ptr -= 1
        elif c == ".":
            out.append(tape[ptr])
        elif c == ",":
            if in_pos < len(input_bytes):
                tape[ptr] = input_bytes[in_pos]
                in_pos += 1
            else:
                tape[ptr] = 0  # EOF convention matches the compiler
        elif c == "[":
            if tape[ptr] == 0:
                ip = match[ip]
        elif c == "]":
            if tape[ptr] != 0:
                ip = match[ip]
        ip += 1

    return bytes(out)


if __name__ == "__main__":
    path = sys.argv[1]
    with open(path) as f:
        sys.stdout.buffer.write(run(f.read()))
