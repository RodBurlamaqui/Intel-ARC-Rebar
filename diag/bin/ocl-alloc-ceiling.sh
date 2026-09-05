#!/bin/bash
# Measures the REAL single-allocation ceiling and total usable VRAM via OpenCL.
# clinfo's reported "max allocation" is not trustworthy on a small-BAR card; this allocates for real.
S=$(dirname "$(readlink -f "$0")")/..; T=$S/bin/ocl_test
[ -x "$T" ] || { echo "building ocl_test..."; make -s -C "$S" || exit 1; }
export RUSTICL_ENABLE=${RUSTICL_ENABLE:-iris}
echo "== single-allocation sweep =="; ceil=0
for m in 64 128 256 320 512 768 1024 1536 2048; do
  if "$T" 1 $m 2>&1 | grep -q FAILED; then echo "  ${m} MiB : FAIL"; else echo "  ${m} MiB : ok"; ceil=$m; fi
done
echo "  => largest single allocation that worked: ${ceil} MiB"
[ $ceil -le 256 ] && echo "     256 MiB ceiling = the small BAR aperture. Total VRAM may still be usable in chunks:"
echo; echo "== chunked total (many buffers below the ceiling) =="
c=$(( ceil > 256 ? 1024 : 224 )); n=$(( ceil > 256 ? 10 : 40 ))
"$T" $n $c 2>&1 | grep -E 'buffers ok|saxpy|RESULT' | sed 's/^/  /'
