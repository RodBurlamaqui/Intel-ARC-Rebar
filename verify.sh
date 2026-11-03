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
# Observe endpoint and parent counters: Linux may clear status between polls.
# Root-port counters cover a shared hierarchy, so changes are not GPU attribution.
aer_snapshot(){
  local path file value
  path=$(readlink -f "$1") || return 1
  while [[ ${path##*/} =~ ^[[:xdigit:]]{4}:[[:xdigit:]]{2}:[[:xdigit:]]{2}\.[0-7]$ ]]; do
    for file in "$path"/aer_dev_{correctable,nonfatal,fatal} "$path"/aer_rootport_total_err_{cor,nonfatal,fatal}; do
      [[ -e $file ]] || continue
      if [[ $file == */aer_dev_* ]]; then
        value=$(awk '/^TOTAL_ERR_/ {print $2}' "$file" 2>/dev/null) || return 1
      else
        value=$(cat "$file" 2>/dev/null) || return 1
      fi
      [[ $value =~ ^[0-9]+$ ]] || return 1
      printf '%s=%s\n' "$file" "$value"
    done
    path=${path%/*}
  done
}
check_pcie(){
  local device=$1 seconds=$2 ds mask write_value before after sample
  local bdf=${device##*/}
  ds=$(read_devsta "$bdf") || { bad "$bdf DevSta unreadable/invalid"; return; }
  ok "$bdf DevSta snapshot: 0x$ds"
  mask=$((16#$ds & 0xf))
  if (( mask & 0x6 )); then
    bad "$bdf DevSta nonfatal/fatal error evidence: 0x$ds (not cleared)"
    return
  fi
  if (( mask )); then
    uncertain "$bdf latched correctable/Unsupported Request status; age and cause unknown"
  fi
  (( seconds )) || return 0
  if (( fail )); then
    uncertain "$bdf recheck skipped because verification already failed; no status cleared"
    return
  fi
  before=$(aer_snapshot "$device") || { bad "$bdf AER counters unreadable/invalid"; return; }
  if [[ -z $before ]]; then
    uncertain "$bdf AER counters unavailable; polling cannot detect kernel-cleared events"
  else
    printf '  AER baseline (endpoint/parents):\n%s\n' "$before"
  fi
  if (( mask )); then
    # Direct 16-bit W1C write: ONLY observed bits 0/3. Never write back the
    # whole register or use setpci's read/modify/write mask syntax on W1C.
    printf -v write_value '%04x' "$((mask & 0x9))"
    warn "$bdf clearing observed DevSta bits once: 0x$write_value"
    setpci -s "$bdf" "CAP_EXP+0xa.w=$write_value" || { bad "$bdf DevSta clear failed"; return; }
  fi
  echo "  Observing $bdf for $seconds seconds; run a GPU workload in another terminal."
  for ((sample=0; sample<=seconds; sample++)); do
    if (( sample )); then sleep 1 || { bad 'observation interrupted'; return; }; fi
    ds=$(read_devsta "$bdf") || { bad "$bdf DevSta unreadable during recheck"; return; }
    if (( 16#$ds & 0xf )); then
      bad "$bdf DevSta persists/recurs during recheck: 0x$ds (not cleared again)"
      return
    fi
    after=$(aer_snapshot "$device") || { bad "$bdf AER counters unreadable during recheck"; return; }
    if [[ $after != "$before" ]]; then
      bad "$bdf endpoint/parent AER counters changed (new reports or reset); investigate hierarchy"
      printf '  AER after:\n%s\n' "$after"
      return
    fi
  done
  ok "$bdf no new PCIe evidence observed in ${seconds}s; not proof of workload health or boot-time origin"
}
check_kernel_log(){
  local log=$1 count
  count=$(printf '%s\n' "$log" | grep -iE 'AER:.*(error|corrected|uncorrect)|PCIe Bus Error:|DPC:.*containment' | grep -vc _OSC)
  if [[ $count == 0 ]]; then ok 'no PCIe error reports in available kernel log'
  else bad "$count PCIe error lines in kernel log (not necessarily caused by ReBAR)"; fi
}

main(){
fail=0; inconclusive=0; recheck=0
case "$#:${1-}" in
  0:) ;;
  1:--help) echo 'usage: verify.sh [--recheck-pcie SECONDS]'; echo 'Read-only by default. Recheck clears observed GPU DevSta bits 0/3 once, then polls (1-3600s).'; echo 'Exit: 0 PASS, 1 FAIL, 2 WARN/inconclusive, 64 usage.'; return 0;;
  2:--recheck-pcie)
    [[ $2 =~ ^[1-9][0-9]{0,3}$ ]] && (( 10#$2 <= 3600 )) || { echo 'SECONDS must be 1-3600' >&2; return 64; }
    recheck=$2;;
  *) echo 'usage: verify.sh [--recheck-pcie SECONDS]' >&2; return 64;;
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
  found=1; ctl=$(setpci -s $b ECAP_REBAR+8.l 2>/dev/null); [ ${#ctl} -eq 8 ] || { bad "$b: ReBAR control register unreadable"; continue; }; cur=$(( (0x$ctl >> 8) & 0x3f ))
  bits=$(( 0x$cap >> 4 )); max=0; for i in $(seq 0 27); do [ $(( (bits >> i) & 1 )) = 1 ] && max=$i; done
  set -- $(sed -n 3p $d/resource); sz=$(( ($2 - $1 + 1) >> 20 ))
  if [ "$1" = "0x0000000000000000" ]; then bad "$b BAR2 is UNASSIGNED"
  elif [ $cur -eq $max ] && [ $sz -eq $((1 << cur)) ]; then ok "$b BAR2 = ${sz} MiB (size field $cur = card maximum)"
  else bad "$b BAR2 = ${sz} MiB (size field $cur, card supports $max)"; fi
  [ -L $d/driver ] && ok "$b driver: $(basename $(readlink -f $d/driver))" || bad "$b has no driver bound"
  check_pcie "$d" "$recheck"
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
