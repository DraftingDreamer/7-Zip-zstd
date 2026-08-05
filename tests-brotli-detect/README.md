# brotli container-detection test kit

Everything behind the numbers quoted in
[issue #538](https://github.com/mcmilk/7-Zip-zstd/issues/538), so they can be
re-run rather than taken on trust.

The question these answer: `.br` may hold either a standard brotli stream or a
brotli-mt container, and raw brotli has no signature, so the decoder has to
decide from content. How often can that decision be wrong, and what does a user
do when it is?

## Scripts

| script | needs | answers |
|---|---|---|
| `brotli-head.py` | stdlib only | What must a raw stream look like to be mistaken for a container? |
| `wbits-matrix.py` | `pip install brotli` | Which encoder settings can produce such a stream at all? |
| `collision-search.py` | `pip install brotli` | Can one actually be built? |
| `decode-matrix.sh` | bash, two 7-Zip ZS builds | Does the change alter any real decode? |

## Reproducing the claims

**A collision needs `wbits == 16`.**

```
python3 brotli-head.py
python3 wbits-matrix.py
```

`brotli-head.py` decodes the magic `50 2a 4d 18` as if it were the start of a
brotli stream: it forces `wbits=16`, `islast=0`, `mnibbles=4`, `mlen=53926`,
`isuncompressed=0`. Bit 0 alone decides `wbits`, so any other window size
cannot collide — `wbits-matrix.py` shows lgwin 10/18/20/22/24 all differ in
bit 0. brotli's own default is 22, and 7-Zip ZS writes its `.br` with 24.

Check a real file, including one 7-Zip ZS produced:

```
7z a -tbrotli sample.br some-input
python3 brotli-head.py sample.br
```

**How close a real stream gets.**

```
python3 collision-search.py 100000 content
python3 collision-search.py 40000 structure
```

`lgwin=16` at quality ≥ 2 on exactly 53926 bytes reproduces bits 0..20 of the
magic exactly. The remaining bits sit in the compressed-metablock header, which
is why the two modes exist: varying payload *content* barely moves them, while
varying its *structure* moves the block-type fields. No exact hit either way —
100k attempts in content mode, then 40k in structure mode, closest 30 of 32
bits. That is not a proof that no such stream exists.

**That the change alters nothing else.**

```
./decode-matrix.sh /path/to/reference/7z /path/to/candidate/7z
```

Compares two builds over tiny `.br` inputs (down to a 1-byte stream, the new
lower boundary of a 16-byte probe), the full `-mmt` spelling matrix on both a
standard and a container `.br`, whether `-mmt=off` can force the raw path,
truncated streams under a forced container path (`-mmt=<n>` skips the field
checks by design, so a stream too short to hold a header must still be
rejected rather than silently succeed), and cross-build read/write. Extracted
bytes are verified by SHA-256 rather than exit code alone, except in the
truncation section, where the exit status *is* the thing under test.

Pass the base revision as the reference, not upstream `master`: `-mmt`
semantics differ between them, and mixing that in makes unrelated cells
disagree.

Needs GNU coreutils (`sha256sum`, `stat -c`); tested on Linux and Git-Bash.

**What this cannot show:** none of it demonstrates the 4-byte → 16-byte
widening directly. A stream that passes the 4-byte check but fails the wider
one is not valid brotli either, so both builds fail on it and the difference
is invisible from outside. Only a genuine collision would separate them, and
`collision-search.py` did not find one.

The upstream suites are the other half of this:

```
cd tests && Z7_PATH=/path/to/7z tclsh 7z-test.tcl -file regression.test
cd tests && Z7_PATH=/path/to/7z tclsh 7z-test.tcl -file main.test
```
