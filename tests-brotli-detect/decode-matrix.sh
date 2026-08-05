#!/bin/bash
# Behavioural comparison of two 7-Zip ZS builds on brotli streams.
#
#   ./decode-matrix.sh <reference-7z> <candidate-7z>
#
# e.g.  ./decode-matrix.sh /path/master/7z.exe /path/patched/7z.exe
#
# Checks, by SHA-256 of the extracted bytes except where noted:
#   1.  tiny raw .br streams           - the 16-byte probe's new lower boundary
#   2.  -mmt matrix over st and mt .br - every spelling, both builds
#   3.  -mmt=off escape hatch          - can the user force the raw path?
#   3b. truncated / short + forced mt  - by exit status, not SHA-256
#   4.  cross-compatibility            - either build writes, either reads
set -u

REF="${1:?usage: $0 <reference-7z> <candidate-7z>}"
CAND="${2:?usage: $0 <reference-7z> <candidate-7z>}"
WORK="$(mktemp -d 2>/dev/null || echo ./bd-work-$$)"
mkdir -p "$WORK" && cd "$WORK" || exit 1
trap 'echo; echo "work dir: $WORK"' EXIT

for exe in "$REF" "$CAND"; do
	b=$("$exe" 2>&1 | head -3 | tr '\n' ' ')
	case "$b" in
		*"7-Zip"*ZS*) ;;
		*) echo "not a 7-Zip ZS build: $exe"; exit 1 ;;
	esac
done
echo "reference: $REF"
echo "candidate: $CAND"
echo

# ------------------------------------------------------------------ 1. tiny
echo "=== 1. tiny raw .br streams (new probe boundary) ==="
printf '%-8s %-9s %-12s %-12s %s\n' "input" "br size" "reference" "candidate" "sha"
fail=0
for n in 0 1 2 3 4 5 8 12 15 16 17 32; do
	: > "in$n.bin"
	[ "$n" -gt 0 ] && head -c "$n" /dev/urandom > "in$n.bin" 2>/dev/null
	rm -f "t$n.br"
	"$REF" a -tbrotli "t$n.br" "in$n.bin" >/dev/null 2>&1
	[ -f "t$n.br" ] || { printf '%-8s skipped\n' "$n"; continue; }
	"$REF"  x -so "t$n.br" > "a$n.bin" 2>/dev/null; ra=$?
	"$CAND" x -so "t$n.br" > "b$n.bin" 2>/dev/null; rb=$?
	s=$(sha256sum < "in$n.bin" | cut -d' ' -f1)
	ha=$(sha256sum < "a$n.bin" | cut -d' ' -f1)
	hb=$(sha256sum < "b$n.bin" | cut -d' ' -f1)
	m="ok"; { [ "$s" != "$ha" ] || [ "$s" != "$hb" ]; } && { m="MISMATCH"; fail=1; }
	[ $ra -eq 0 ] || { ra="ERR"; fail=1; }; [ "$ra" = "0" ] && ra=ok
	[ $rb -eq 0 ] || { rb="ERR"; fail=1; }; [ "$rb" = "0" ] && rb=ok
	printf '%-8s %-9s %-12s %-12s %s\n' "$n" "$(stat -c %s "t$n.br")" "$ra" "$rb" "$m"
done
echo "-> $([ $fail -eq 0 ] && echo ALL PASS || echo FAILURES)"
echo

# ---------------------------------------------------------------- 2. matrix
echo "=== 2. -mmt matrix on .br ==="
base64 /dev/urandom 2>/dev/null | head -c 300000 > src.txt
"$REF" a -tbrotli -mmt=off st.br src.txt >/dev/null 2>&1
"$REF" a -tbrotli -mmt=4   mt.br src.txt >/dev/null 2>&1
SRC=$(sha256sum < src.txt | cut -d' ' -f1)
OPTS=" |-mmt|-mmt+|-mmt=on|-mmt=1|-mmt=4|-mmt-|-mmt=off|-mmt=0"
for lbl in reference candidate; do
	exe="$REF"; [ "$lbl" = candidate ] && exe="$CAND"
	echo "--- $lbl ---"
	printf '%-10s' "file"
	IFS='|' read -ra OA <<< "$OPTS"
	for o in "${OA[@]}"; do printf '%-10s' "$(echo "$o" | tr -d ' ' | sed 's/^$/(none)/')"; done
	echo
	for f in st.br mt.br; do
		printf '%-10s' "$f"
		for o in "${OA[@]}"; do
			opt=$(echo "$o" | tr -d ' '); rm -f o.tmp
			if [ -z "$opt" ]; then "$exe" x -so "$f" > o.tmp 2>/dev/null
			else "$exe" x -so "$opt" "$f" > o.tmp 2>/dev/null; fi
			rc=$?; h=$(sha256sum < o.tmp | cut -d' ' -f1)
			if [ $rc -eq 0 ] && [ "$h" = "$SRC" ]; then printf '%-10s' ok
			elif [ $rc -eq 0 ]; then printf '%-10s' BADSHA
			else printf '%-10s' err; fi
		done
		echo
	done
done
echo

# ---------------------------------------------------------- 3. escape hatch
echo "=== 3. escape hatch: does -mmt=off force the raw path? ==="
echo "(mt.br is a container; if -mmt=off truly forces raw, decoding it must FAIL)"
for lbl in reference candidate; do
	exe="$REF"; [ "$lbl" = candidate ] && exe="$CAND"
	rm -f o.tmp; "$exe" x -so -mmt=off mt.br > o.tmp 2>/dev/null
	if [ $? -eq 0 ]; then r="decodes anyway -> NO escape hatch"
	else r="fails -> escape hatch works"; fi
	printf '  %-12s %s\n' "$lbl" "$r"
done
echo

# ------------------------------------------------- 3b. truncated headers
echo "=== 3b. truncated / short streams under a FORCED container path ==="
echo "(-mmt=<n> skips the field checks by design; a stream too short to hold"
echo " a 16-byte header must still be rejected, never silently succeed)"
fail=0
# magic + size=8 + toRead=0 + magicnumber, cut off before the header ends
printf '\x50\x2a\x4d\x18\x08\x00\x00\x00\x00\x00\x00\x00\x42\x52' > trunc14.br
printf '\x50\x2a\x4d\x18\x08\x00\x00\x00' > trunc8.br
head -c 3 /dev/urandom > tiny3.bin; "$REF" a -tbrotli tiny3.br tiny3.bin >/dev/null 2>&1
for f in trunc14.br trunc8.br tiny3.br; do
	[ -f "$f" ] || continue
	for lbl in reference candidate; do
		exe="$REF"; [ "$lbl" = candidate ] && exe="$CAND"
		rm -f o.tmp; "$exe" x -so -mmt=4 "$f" > o.tmp 2>/dev/null; rc=$?
		sz=$(stat -c %s o.tmp 2>/dev/null || echo 0)
		if [ $rc -ne 0 ]; then v="rejected (ok)"
		elif [ "$sz" = "0" ]; then v="SILENT EMPTY SUCCESS"; fail=1
		else v="succeeded, $sz bytes"; fi
		printf '  %-12s %-12s -mmt=4 -> %s\n' "$f" "$lbl" "$v"
	done
done
echo "-> $([ $fail -eq 0 ] && echo ALL PASS || echo FAILURES)"
echo

# --------------------------------------------------------- 4. cross-compat
echo "=== 4. cross-compatibility ==="
fail=0
for w in reference candidate; do
	wexe="$REF"; [ "$w" = candidate ] && wexe="$CAND"
	for mode in "-mmt=off" "-mmt=4"; do
		rm -f x.br; "$wexe" a -tbrotli "$mode" x.br src.txt >/dev/null 2>&1
		for r in reference candidate; do
			rexe="$REF"; [ "$r" = candidate ] && rexe="$CAND"
			rm -f o.tmp; "$rexe" x -so x.br > o.tmp 2>/dev/null; rc=$?
			h=$(sha256sum < o.tmp | cut -d' ' -f1)
			st=ok; { [ $rc -ne 0 ] || [ "$h" != "$SRC" ]; } && { st=FAIL; fail=1; }
			printf '  write=%-10s %-9s read=%-10s %s\n' "$w" "$mode" "$r" "$st"
		done
	done
done
echo "-> $([ $fail -eq 0 ] && echo ALL PASS || echo FAILURES)"
