#!/bin/bash
# PCIe error state, AER, temperatures, clocks and throttle reasons for the Intel GPU (xe driver).
[ "$(id -u)" = 0 ] || echo "note: run as root for lspci error registers"
for d in /sys/bus/pci/devices/*; do
  [ "$(cat $d/vendor)" = 0x8086 ] || continue; case "$(cat $d/class)" in 0x0300*) ;; *) continue;; esac
  b=${d##*/}; echo "== $b (driver: $(basename $(readlink -f $d/driver 2>/dev/null) 2>/dev/null || echo none)) =="
  lspci -vv -s ${b#0000:} 2>/dev/null | grep -E 'DevSta' | sed 's/^\s*/  /'
  echo "  (link speed deliberately not shown here: the GPU function's own LnkSta is a virtual port. Use pcie-link-truth.sh)"
  aer=$(dmesg 2>/dev/null | grep -iE 'AER:.*(error|corrected|uncorrect)' | grep -vc _OSC); echo "  AER error reports in log: $aer"
  dmesg 2>/dev/null | grep -ciE 'gpu hang|gpu reset|wedged' | sed 's/^/  GPU hang\/reset lines: /'
  for h in $d/hwmon/hwmon*; do [ -d $h ] || continue
    for f in $h/temp*_input; do l=${f%_input}_label; printf "  %-10s %s C\n" "$(cat $l 2>/dev/null || basename $f)" "$(( $(cat $f)/1000 ))"; done | sort | head -4
    [ -r $h/fan1_input ] && echo "  fan        $(cat $h/fan1_input) rpm"; done
  for g in $d/tile0/gt*/freq0; do [ -d $g ] || continue
    echo "  $(basename $(dirname $g)): act $(cat $g/act_freq) MHz  (min $(cat $g/min_freq) max $(cat $g/max_freq))  throttle: $(cat $g/throttle/reasons 2>/dev/null)"; done
  dmesg 2>/dev/null | grep -E "xe $b.*(GuC firmware|DMC firmware|VISIBLE VRAM)" | tail -3 | sed 's/.*\] /  /'
done
