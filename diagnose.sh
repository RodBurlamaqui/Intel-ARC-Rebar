#!/bin/bash
# arc-rebar diagnose: do you have the pinned-window Small BAR problem, and would the fix apply safely?
S=$(dirname "$(readlink -f "$0")")
echo "== Intel GPUs with a Resizable BAR capability =="
found=0
for d in /sys/bus/pci/devices/*; do
  [ "$(cat $d/vendor)" = "0x8086" ] || continue
  case "$(cat $d/class)" in 0x0300*) ;; *) continue;; esac
  b=${d##*/}; setpci -s $b ECAP_REBAR+4.l >/dev/null 2>&1 || continue
  found=1; ctl=$(setpci -s $b ECAP_REBAR+8.l 2>/dev/null); cap=$(setpci -s $b ECAP_REBAR+4.l 2>/dev/null); [ ${#ctl} -eq 8 ] && [ ${#cap} -eq 8 ] || { echo "  $b: ReBAR registers unreadable"; continue; }
  cur=$(( (0x$ctl >> 8) & 0x3f )); set -- $(sed -n 3p $d/resource)
  echo "  $b  device $(cat $d/device)  BAR2=$(( ($2-$1+1)/1048576 )) MiB  size_field=$cur  cap=0x$cap"
  p=$(readlink -f $d); rel=${p#/sys/devices/pci*/}; rp=${rel%%/*}
  echo "  root port $rp: $(lspci -vv -s ${rp#0000:} 2>/dev/null | grep -o 'Prefetchable memory behind bridge: .*')"
  echo "  path: $(echo $rel | tr '/' ' ')"
  for hop in $(echo $rel | tr '/' ' '); do
    [ "$hop" = "$b" ] && continue; set -- $(sed -n 1p /sys/bus/pci/devices/$hop/resource)
    [ "$1" != "0x0000000000000000" ] && echo "  >> bridge $hop (device $(cat /sys/bus/pci/devices/$hop/device)) has its own BAR0: $1-$2   <-- the pin"
  done
done
[ $found = 0 ] && { echo "  none found. arc-rebar does not apply."; exit 0; }
echo; echo "== kernel log signature (this boot) =="
dmesg 2>/dev/null | grep -E 'was not released|Small BAR device|Failed to resize BAR|arc-rebar: PLAN' | sed 's/^/  /'
echo; echo "== would arc-rebar act here? (boot script dry run) =="
ARC_REBAR_DRYRUN=1 ARC_REBAR_ASSUME_REALLOC=1 sh "$S/scripts/init-premount/arc-rebar" 2>&1 | sed 's/^/  /'
echo; echo "== verdict =="
if dmesg 2>/dev/null | grep -q 'arc-rebar: PLAN: done'; then
  echo "  FIXED by arc-rebar this boot. (The 'Small BAR' lines above are xe's first probe, before the fix ran.)"
elif dmesg 2>/dev/null | grep -q 'arc-rebar: PLAN: rolled-back'; then
  echo "  arc-rebar ran but had to ROLL BACK: not enough MMIO space for the BAR. Try rebar.size=N or free MMIO in BIOS."
else
  planline=$(ARC_REBAR_DRYRUN=1 ARC_REBAR_ASSUME_REALLOC=1 sh "$S/scripts/init-premount/arc-rebar" 2>/dev/null | grep -m1 PLAN: | sed 's/.*PLAN: //')
  case "$planline" in
    act*)  echo "  YES: pinned window, all safety checks pass. Run ./live-test.sh, then ./install.sh";;
    none*) echo "  BAR already at full size (firmware ReBAR, or a live fix is active). Nothing to do.";;
    *)     echo "  NOT SAFE / NOT APPLICABLE here: $planline";;
  esac
fi
