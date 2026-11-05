#!/bin/bash
# arc-rebar verify: POST-check. PASS=0, FAIL=1, inconclusive PCIe WARN=2.
# DevSta is sticky W1C status, not a timestamped health measurement.
ok(){ echo "  [ok]   $*"; }
bad(){ echo "  [FAIL] $*"; fail=1; }
warn(){ echo "  [warn] $*"; }
uncertain(){ warn "$*"; inconclusive=1; }
result(){
  if (( fail )); then echo 'RESULT: FAIL'; return 1
  elif (( inconclusive )); then echo 'RESULT: WARN (PCIe health inconclusive)'; return 2
  else echo 'RESULT: PASS'; return 0; fi
}
read_devsta(){
  local value
  value=$(setpci -s "$1" CAP_EXP+0xa.w 2>/dev/null) || return 1
  [[ $value =~ ^[[:xdigit:]]{4}$ && ${value,,} != ffff ]] || return 1
  printf '%s\n' "$value"
}
# A snapshot cannot establish when a latched event occurred or its cause.
# This verifier never clears status or writes PCI configuration registers.
check_pcie(){
  local device=$1 ds mask
  local bdf=${device##*/}
  ds=$(read_devsta "$bdf") || { bad "$bdf DevSta unreadable/invalid"; return; }
  ok "$bdf DevSta snapshot: 0x$ds"
  mask=$((16#$ds & 0xf))
  if (( mask & 0x6 )); then
    bad "$bdf DevSta nonfatal/fatal error evidence: 0x$ds"
  elif (( mask )); then
    uncertain "$bdf latched correctable/Unsupported Request status; age and cause unknown"
  fi
}
check_kernel_log(){
  local log=$1 count
  count=$(printf '%s\n' "$log" | grep -iE 'AER:.*(error|corrected|uncorrect)|PCIe Bus Error:|DPC:.*containment' | grep -vc _OSC)
  if [[ $count == 0 ]]; then ok 'no PCIe error reports in available kernel log'
  else bad "$count PCIe error lines in kernel log (not necessarily caused by ReBAR)"; fi
}

main(){
fail=0; inconclusive=0
case "$#:${1-}" in
  0:) ;;
  1:--help) echo 'usage: verify.sh [--help]'; echo 'Read-only PCIe/BAR checks; no register clearing.'; echo 'Exit: 0 PASS, 1 FAIL, 2 WARN/inconclusive, 64 usage.'; return 0;;
  *) echo 'usage: verify.sh [--help]' >&2; return 64;;
esac
echo "== arc-rebar verify (boot $(uptime -s)) =="
grep -q 'pci=realloc' /proc/cmdline && ok "pci=realloc active" || bad "pci=realloc not on the kernel cmdline"
[ -e /etc/initramfs-tools/scripts/init-premount/arc-rebar ] && ok "hook installed" || warn "hook not installed (live-only run?)"
bootlog=$(dmesg 2>/dev/null) || bad 'kernel log unavailable; cannot verify PCIe reports'
check_kernel_log "$bootlog"
plan=$(printf '%s\n' "$bootlog" | grep 'arc-rebar: PLAN' | tail -1 | sed 's/.*PLAN: //')
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
  found=1
  [[ $cap =~ ^[[:xdigit:]]{8}$ && ${cap,,} != ffffffff ]] || { bad "$b: ReBAR capability invalid"; continue; }
  ctl=$(setpci -s "$b" ECAP_REBAR+8.l 2>/dev/null) || { bad "$b: ReBAR control register unreadable"; continue; }
  [[ $ctl =~ ^[[:xdigit:]]{8}$ && ${ctl,,} != ffffffff ]] || { bad "$b: ReBAR control register invalid"; continue; }
  cur=$(( (16#$ctl >> 8) & 0x3f ))
  bits=$(( 16#$cap >> 4 )); (( bits )) || { bad "$b: ReBAR capability has no supported sizes"; continue; }; max=0; for i in $(seq 0 27); do [ $(( (bits >> i) & 1 )) = 1 ] && max=$i; done
  read -r start end flags < <(sed -n 3p "$d/resource")
  [[ $start =~ ^0x[[:xdigit:]]{16}$ && $end =~ ^0x[[:xdigit:]]{16}$ ]] && (( end >= start )) || { bad "$b: BAR2 resource unreadable/invalid"; continue; }
  sz=$(( (end - start + 1) >> 20 ))
  if (( start == 0 )); then bad "$b BAR2 is UNASSIGNED"
  elif [ $cur -eq $max ] && [ $((end - start + 1)) -eq $((1 << (cur + 20))) ]; then ok "$b BAR2 = ${sz} MiB (size field $cur = card maximum)"
  else bad "$b BAR2 = ${sz} MiB (size field $cur, card supports $max)"; fi
  [ -L "$d/driver" ] && [ -d "$d/driver" ] && ok "$b driver: $(basename $(readlink -f $d/driver))" || bad "$b has no driver bound"
  check_pcie "$d"
done
[ $found = 0 ] && bad "no Intel GPU with a ReBAR capability found"
v=$(dmesg 2>/dev/null | grep 'VISIBLE VRAM' | tail -1 | sed 's/.*VISIBLE VRAM: //'); [ -n "$v" ] && ok "xe last probe VISIBLE VRAM: $v"
endlog=$(dmesg 2>/dev/null) || bad 'kernel log unavailable after checks'
check_kernel_log "$endlog"
warn 'Driver binding/BAR allocation do not establish GPU workload health.'

if command -v vulkaninfo >/dev/null 2>&1; then
  h=$(vulkaninfo 2>/dev/null | sed -n '/memoryHeaps: count/,/memoryTypes/p' | head -8 | grep -E 'count|size' | tr -s ' ' | tr '\n' ' ')
  [ -n "$h" ] && ok "vulkan: $h"
fi
echo
result
}

# Allow the regression harness to source functions without touching hardware.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
