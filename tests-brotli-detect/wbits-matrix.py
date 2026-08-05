#!/usr/bin/env python3
"""Show which encoder settings can and cannot produce a colliding .br stream.

A collision requires wbits == 16, which is decided by bit 0 of the stream.
This prints the wbits every lgwin setting actually yields, so the claim
"only lgwin=16 can collide" can be checked rather than taken on trust.

Usage:  python3 wbits-matrix.py
Requires: pip install brotli
"""
import sys
import os
import importlib.util

try:
    import brotli
except ImportError:
    sys.exit("needs the 'brotli' module:  pip install brotli")

# brotli-head.py has a dash in its name, so load it by path
_here = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "brotli_head", os.path.join(_here, "brotli-head.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse = _mod.parse

data = b"the quick brown fox jumps over the lazy dog. " * 4000

print(f"{'lgwin':>6}  {'wbits':>8}  {'first 4 bytes':>14}   collision possible?")
print("-" * 58)
for lg in (10, 16, 17, 18, 20, 22, 24):
    out = brotli.compress(data, lgwin=lg)
    info = parse(out)
    first = int.from_bytes(out[:4], "little")
    ok = "YES (wbits==16)" if info.get("wbits") == 16 else "no - bit 0 differs"
    print(f"{lg:>6}  {str(info.get('wbits')):>8}  {first:#010x}       {ok}")

print()
d = brotli.compress(data)
print("brotli defaults (what any normal encoder emits):", parse(d))
print()
print("7-Zip ZS writes its own .br with wbits=24 - check with:")
print("    7z a -tbrotli out.br input && python3 brotli-head.py out.br")
