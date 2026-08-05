#!/usr/bin/env python3
"""Try to build a *standard* brotli stream that starts with the mt-container
magic, i.e. a real false positive for content detection.

Bits 0..20 are pinned by wbits=16 / islast=0 / mlen=53926 / compressed, and
lgwin=16 at quality >= 2 reproduces them exactly. The remaining bits live in
the compressed-metablock header (NBLTYPESL/I/D, NPOSTFIX, NDIRECT, context
mode), so the payload is varied in *structure* to move them.

If it ever succeeds it writes collision.br + collision.expected and verifies
the result with the reference brotli decoder, so the file is a genuine
standard stream and not a byte-patched fake.

Usage:  python3 collision-search.py [attempts] [content|structure]
Requires: pip install brotli

Two search modes, because the interesting bits respond to different things:

  content    fixed quality, payload differs only in its bytes. Cheap, but the
             metablock header barely moves, so it mostly re-tests the same
             header shape.
  structure  payload differs in how many segments it has and what kind they
             are, across four quality levels. This is what actually moves
             NBLTYPESL/I/D and the context mode.

Result so far: no exact hit either way - 100k attempts in content mode at
quality 5, then 40k in structure mode; closest was 30 of 32 bits. That is not
a proof that no such stream exists.
"""
import sys
import random

try:
    import brotli
except ImportError:
    sys.exit("needs the 'brotli' module:  pip install brotli")

MAGIC = bytes([0x50, 0x2A, 0x4D, 0x18])
MLEN = 53926          # forced by bits 4..19 of the magic
LGWIN = 16            # forced by bit 0 of the magic
WORDS = [b"the quick brown fox ", b"lorem ipsum dolor sit amet ", b"aaaaaaaa",
         b"\x00\x01\x02\x03", b"0123456789", b"</div><div class=x>"]


def payload_content(trial):
    """A first metablock of exactly MLEN bytes whose *bytes* differ per
    attempt, but whose shape does not."""
    unit = f"[trial {trial:08d}] ".encode() + \
        b"the quick brown fox jumps over the lazy dog. " * 4
    return (unit * (MLEN // len(unit) + 1))[:MLEN]


def payload_structure(rng):
    """A first metablock of exactly MLEN bytes, structurally different each
    time so the metablock header's block-type fields move."""
    out = bytearray()
    for _ in range(rng.randint(1, 6)):
        kind = rng.randint(0, 3)
        want = rng.randint(1000, MLEN)
        if kind == 0:
            seg = bytes(rng.getrandbits(8) for _ in range(min(want, 3000)))
        elif kind == 1:
            w = rng.choice(WORDS)
            seg = w * (want // len(w) + 1)
        elif kind == 2:
            seg = bytes([rng.randint(0, 255)]) * want
        else:
            seg = bytes(rng.randint(97, 122) for _ in range(min(want, 3000)))
        out += seg
        if len(out) >= MLEN:
            break
    while len(out) < MLEN:
        out += bytes(rng.randint(97, 122) for _ in range(200))
    return bytes(out[:MLEN])


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    mode = sys.argv[2] if len(sys.argv) > 2 else "structure"
    if mode not in ("content", "structure"):
        sys.exit(f"unknown mode {mode!r}: expected 'content' or 'structure'")
    rng = random.Random(20260805)
    best, bestbits = None, -1
    print(f"mode={mode}, {limit} attempts, lgwin={LGWIN}, mlen={MLEN}")

    for trial in range(limit):
        if mode == "content":
            head, q = payload_content(trial), 5
        else:
            head, q = payload_structure(rng), (2, 5, 9, 11)[trial & 3]
        c = brotli.Compressor(quality=q, lgwin=LGWIN)
        out = c.process(head) + c.flush()

        if out[:4] == MAGIC:
            tail = b"second metablock so the stream does not end here.\n" * 400
            out += c.process(tail) + c.finish()
            original = head + tail
            assert brotli.decompress(out) == original, "not a valid brotli stream!"
            with open("collision.br", "wb") as fh:
                fh.write(out)
            with open("collision.expected", "wb") as fh:
                fh.write(original)
            print(f"FOUND at trial {trial}, quality={q}")
            print("  first 8 bytes:",
                  " ".join(f"{b:#04x}" for b in out[:8]))
            print(f"  {len(out)} bytes -> decodes to {len(original)} bytes")
            print("  verified with the reference brotli decoder")
            print("  wrote collision.br / collision.expected")
            return 0

        diff = int.from_bytes(out[:4], "little") ^ int.from_bytes(MAGIC, "little")
        agree = 32 - bin(diff).count("1")
        if agree > bestbits:
            bestbits = agree
            best = (trial, q, int.from_bytes(out[:4], "little"))

    print(f"no exact hit in {limit} attempts")
    print(f"closest: {bestbits}/32 bits, trial={best[0]} quality={best[1]} "
          f"first4={best[2]:#010x}  (magic is 0x184d2a50)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
