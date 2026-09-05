#!/bin/bash
# Detects the "integrated switch BAR0 pins the root port window" Small BAR cause.
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
found=0
for d in /sys/bus/pci/devices/*; do
  [ "$(cat $d/vendor)" = 0x8086 ] || continue; case "$(cat $d/class)" in 0x0300*) ;; *) continue;; esac
  b=${d##*/}; cap=$(setpci -s $b ECAP_REBAR+4.l 2>/dev/null) || continue; found=1
  ctl=$(setpci -s $b ECAP_REBAR+8.l 2>/dev/null); [ ${#ctl} -eq 8 ] || { echo "  $b: ReBAR control register unreadable"; continue; }; cur=$(( (0x$ctl >> 8) & 0x3f ))
  bits=$(( 0x$cap >> 4 )); max=0; for i in $(seq 0 27); do [ $(( (bits >> i) & 1 )) = 1 ] && max=$i; done
  set -- $(sed -n 3p $d/resource); sz=$(( ($2-$1+1)>>20 ))
  p=$(readlink -f $d); rel=${p#/sys/devices/pci*/}; rp=${rel%%/*}
  echo "== $b: BAR2 ${sz} MiB, size field $cur of max $max (2^($max+20) B) =="
  echo "  root port $rp: $(lspci -vv -s ${rp#0000:} 2>/dev/null | grep -o 'Prefetchable memory behind bridge: .*')"
  pin=0
  for hop in $(echo $rel | tr / ' '); do [ "$hop" = "$b" ] && continue; set -- $(sed -n 1p /sys/bus/pci/devices/$hop/resource)
    [ "$1" != 0x0000000000000000 ] && { echo "  >> $hop (device $(cat /sys/bus/pci/devices/$hop/device)) has its own BAR0 $1-$2 in the window  <-- pin"; pin=1; }; done
  echo "  MMIO windows above 4G for bus ${rp%:*}:"; grep -E "^[0-9a-f]{9,}-[0-9a-f]+ : PCI Bus ${rp%:*}$" /proc/iomem | sed 's/^/    /'
  echo "  kernel log:"; dmesg 2>/dev/null | grep -E 'was not released|Small BAR device|Failed to resize BAR|VISIBLE VRAM' | tail -4 | sed 's/.*\] /    /'
  if [ $cur -ge $max ]; then echo "  VERDICT: BAR is at the card maximum. No problem here."
  elif dmesg 2>/dev/null | grep -q 'was not released (still contains assigned resources)'; then echo "  VERDICT: PINNED. A bridge BAR0 holds the root port window. Fix: arc-rebar."
  elif [ $pin = 1 ]; then echo "  VERDICT: small BAR and a bridge BAR0 is present in the path; likely the pin (no log line on this boot)."
  else echo "  VERDICT: small BAR, but no pin detected. Different cause (MMIO space? Above 4G off?)."; fi
done
if [ $found = 0 ]; then echo "no Intel GPU with a ReBAR capability found"; fi
exit 0
