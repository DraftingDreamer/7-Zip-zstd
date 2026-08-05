#!/usr/bin/env python3
"""Parse the opening bits of a raw brotli stream (RFC 7932 sections 9.1/9.2).

Answers two questions:

  * what must a raw brotli stream look like for its first four bytes to equal
    BROTLIMT_MAGIC_SKIPPABLE, i.e. for content detection to misfire?
  * what do real .br files actually look like there?

Brotli reads bits LSB-first within each byte.

Usage:  python3 brotli-head.py [file.br ...]

Requires nothing but the standard library.
"""
import sys
import pathlib

MAGIC = 0x184D2A50  # BROTLIMT_MAGIC_SKIPPABLE, little-endian on disk


class Bits:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def read(self, n):
        v = 0
        for i in range(n):
            byte = self.data[self.pos >> 3]
            v |= ((byte >> (self.pos & 7)) & 1) << i
            self.pos += 1
        return v


def parse(data):
    """Decode WBITS plus the first metablock header prefix."""
    b = Bits(data)
    out = {}

    # WBITS (section 9.1): a leading 0 bit means wbits == 16
    if b.read(1) == 0:
        out["wbits"] = 16
    else:
        n = b.read(3)
        if n != 0:
            out["wbits"] = 17 + n
        else:
            n = b.read(3)
            out["wbits"] = 8 + n if n != 0 else "reserved"

    out["islast"] = b.read(1)
    if out["islast"]:
        out["isempty"] = b.read(1)
        if out["isempty"]:
            return out
    nib = b.read(2)
    out["mnibbles"] = [4, 5, 6, 0][nib]
    if out["mnibbles"] == 0:
        out["mlen"] = 0
        return out
    out["mlen"] = b.read(out["mnibbles"] * 4) + 1
    if not out["islast"]:
        out["isuncompressed"] = b.read(1)
    return out


def main(argv):
    magic_bytes = MAGIC.to_bytes(4, "little")
    print("BROTLIMT_MAGIC_SKIPPABLE on disk:",
          " ".join(f"{x:#04x}" for x in magic_bytes))
    print()
    print("For detection to misfire, a raw brotli stream must open with exactly")
    print("these bits, which decode as:")
    for k, v in parse(magic_bytes).items():
        print(f"    {k:16s} = {v}")
    print()
    print("Note bit 0 alone decides wbits. Any encoder not using lgwin=16")
    print("therefore cannot produce a colliding stream at all.")

    if len(argv) > 1:
        print()
        print("Real files:")
        for path in argv[1:]:
            p = pathlib.Path(path)
            data = p.read_bytes()
            if len(data) < 4:
                print(f"    {p.name:24s} {len(data):>9} bytes  (too short)")
                continue
            try:
                info = parse(data)
            except Exception as exc:  # noqa: BLE001
                print(f"    {p.name:24s} parse failed: {exc}")
                continue
            first4 = int.from_bytes(data[:4], "little")
            print(f"    {p.name:24s} {len(data):>9} bytes  "
                  f"first4={first4:#010x}  {info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
