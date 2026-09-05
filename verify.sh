#!/bin/bash
# arc-rebar verify: POST-check after a reboot. Prints PASS or FAIL with reasons.
fail=0; ok(){ echo "  [ok]   $*"; }; bad(){ echo "  [FAIL] $*"; fail=1; }; warn(){ echo "  [warn] $*"; }
echo "== arc-rebar verify (boot $(uptime -s)) =="
grep -q 'pci=realloc' /proc/cmdline && ok "pci=realloc active" || bad "pci=realloc not on the kernel cmdline"
[ -e /etc/initramfs-tools/scripts/init-premount/arc-rebar ] && ok "hook installed" || warn "hook not installed (live-only run?)"
plan=$(dmesg 2>/dev/null | grep 'arc-rebar: PLAN' | tail -1 | sed 's/.*PLAN: //')
case "$plan" in
  done*)        ok   "boot verdict: $plan";;
  none*)        warn "boot verdict: $plan";;
  rolled-back*) bad  "boot verdict: $plan";;
  FAILED*)      bad  "boot verdict: $plan";;
  skip*)        warn "boot verdict: $plan";;
  "")           warn "no arc-rebar verdict in the kernel log this boot";;
esac
found=0
for d in /sys/bus/pci/devices/*; do
  [ "$(cat $d/vendor 2>/dev/null)" = "0x8086" ] || continue
  case "$(cat $d/class 2>/dev/null)" in 0x0300*) ;; *) continue;; esac
  b=${d##*/}; cap=$(setpci -s $b ECAP_REBAR+4.l 2>/dev/null) || continue
  found=1; ctl=$(setpci -s $b ECAP_REBAR+8.l 2>/dev/null); [ ${#ctl} -eq 8 ] || { bad "$b: ReBAR control register unreadable"; continue; }; cur=$(( (0x$ctl >> 8) & 0x3f ))
  bits=$(( 0x$cap >> 4 )); max=0; for i in $(seq 0 27); do [ $(( (bits >> i) & 1 )) = 1 ] && max=$i; done
  set -- $(sed -n 3p $d/resource); sz=$(( ($2 - $1 + 1) >> 20 ))
  if [ "$1" = "0x0000000000000000" ]; then bad "$b BAR2 is UNASSIGNED"
  elif [ $cur -ge $max ]; then ok "$b BAR2 = ${sz} MiB (size field $cur = card maximum)"
  else bad "$b BAR2 = ${sz} MiB (size field $cur, card supports $max)"; fi
  [ -L $d/driver ] && ok "$b driver: $(basename $(readlink -f $d/driver))" || bad "$b has no driver bound"
  ds=$(setpci -s $b CAP_EXP+0xa.w 2>/dev/null); [ -n "$ds" ] && { [ $(( 0x$ds & 0xf )) = 0 ] && ok "$b DevSta: no correctable/fatal/unsupported-request errors" || bad "$b DevSta error bits set: 0x$ds"; }
done
[ $found = 0 ] && bad "no Intel GPU with a ReBAR capability found"
v=$(dmesg 2>/dev/null | grep 'VISIBLE VRAM' | tail -1 | sed 's/.*VISIBLE VRAM: //'); [ -n "$v" ] && ok "xe last probe VISIBLE VRAM: $v"
aer=$(dmesg 2>/dev/null | grep -iE 'AER:.*(error|corrected|uncorrect)' | grep -vc _OSC); [ "$aer" = 0 ] && ok "no AER error reports" || bad "$aer AER error lines in the kernel log"
if command -v vulkaninfo >/dev/null 2>&1; then
  h=$(vulkaninfo 2>/dev/null | sed -n '/memoryHeaps: count/,/memoryTypes/p' | head -8 | grep -E 'count|size' | tr -s ' ' | tr '\n' ' ')
  [ -n "$h" ] && ok "vulkan: $h"
fi
echo; [ $fail = 0 ] && echo "RESULT: PASS" || { echo "RESULT: FAIL"; exit 1; }
