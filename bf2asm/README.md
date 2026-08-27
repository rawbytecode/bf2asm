# bf2asm

A small compiler that translates [Brainfuck](https://en.wikipedia.org/wiki/Brainfuck)
source into real x86-64 assembly — not an interpreter, an actual
ahead-of-time compiler that produces a standalone Linux binary.

```
$ python3 -m bf2asm examples/hello.bf
bf2asm: wrote examples/hello.s
$ as -o hello.o examples/hello.s && ld -o hello hello.o
$ ./hello
Hello World!
```

## Why

Brainfuck's eight commands map almost one-to-one onto a handful of x86
instructions, which makes it a good teaching example for how a "real"
compiler pipeline works: **parse → IR → optimize → codegen**, without
the noise of a large language. This repo is meant to be read, not just
run.

## How it works

```
 source.bf → parse() → IR (List[Op]) → optimize() → generate() → source.s
```

1. **Parse** (`bf2asm/compiler.py:parse`) strips everything that isn't
   one of `+ - < > . , [ ]` (anything else is treated as a comment,
   Brainfuck has no formal comment syntax) and produces a run-length
   encoded IR: consecutive `+++++` becomes a single `ADD(amount=5)` op,
   consecutive `>>>` becomes a single `MOVE(amount=3)` op. This avoids
   emitting one instruction per character for dense programs.

2. **Optimize** folds the extremely common `[-]` / `[+]` "zero this
   cell" idiom into a single `CLEAR` op instead of a compare/jump loop.

3. **Codegen** (`generate`) walks the IR once and emits GNU AS
   (AT&T syntax) x86-64 assembly.

### Runtime model

| Brainfuck construct | Register / memory used |
|---|---|
| Data pointer | `%rbx` (survives Linux syscalls unmodified, so no spilling around I/O) |
| Tape | 30,000-byte zeroed buffer in `.bss` |
| `.` / `,` | Raw `write(2)` / `read(2)` syscalls — **no libc dependency** |
| Program exit | `exit(2)` syscall, status 0 |

| Brainfuck | Assembly |
|---|---|
| `>` / `<` | `inc %rbx` / `dec %rbx` (or `add`/`sub` for runs) |
| `+` / `-` | `addb $n, (%rbx)` / `subb $n, (%rbx)` |
| `[` | `cmpb $0, (%rbx)` then `je` to the matching `]` |
| `]` | `jmp` back to the matching `[` |
| `.` | `write(1, %rbx, 1)` |
| `,` | `read(0, %rbx, 1)`, cell forced to `0` on EOF |

Cell values wrap at the byte boundary (`+` on `255` gives `0`), matching
the standard Brainfuck semantics.

## Usage

```
python3 -m bf2asm <source.bf> [-o out.s] [--no-optimize]
```

Then assemble and link with GNU binutils:

```
as -o out.o out.s
ld -o out out.o
./out
```

Or just use the Makefile, which does both steps for every program in
`examples/`:

```
make            # builds build/hello, build/cat, ...
make test       # runs the test suite (compiles, assembles, links, and
                #  diffs output against a reference interpreter)
```

**Requirements:** Python 3.9+ and GNU binutils (`as`, `ld`) — no NASM,
no libc, no external assembler needed beyond what most Linux dev
machines already have (`apt install binutils` if not).

## Examples

- `examples/hello.bf` — the canonical Brainfuck "Hello World!"
- `examples/cat.bf` — `,[.,]`, echoes stdin to stdout until EOF;
  exercises the read syscall and EOF handling

## Testing

`tests/test_compiler.py` compiles each example, assembles + links it
into a real binary, runs it, and compares the output byte-for-byte
against `tests/reference_interpreter.py`, a small pure-Python
Brainfuck interpreter used purely as an oracle. Pure IR/codegen checks
that don't need a toolchain are included too.

```
python3 -m unittest discover -v
```

## Limitations / non-goals

- Targets Linux x86-64 only (relies on the Linux syscall ABI directly).
- No bounds checking on tape pointer movement — a malformed program
  that walks the pointer far enough will read/write outside the
  `.bss` tape, same as most minimal Brainfuck implementations.
- Optimization is intentionally limited (run-length encoding + clear-loop
  folding) to keep the codegen easy to read; it's not meant to compete
  with heavily optimizing BF compilers.

## License

MIT — see [LICENSE](LICENSE).
