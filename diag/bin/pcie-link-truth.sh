#!/bin/bash
# Which PCIe link is real? Intel Arc cards carry an integrated switch; the GPU function and
# the switch's downstream port report "2.5 GT/s x1" — die-internal virtual ports with no PHY.
# The real link is the hop that completed link equalization. Run as root (lspci needs it).
[ "$(id -u)" = 0 ] || echo "note: run as root for full link registers"
for d in /sys/bus/pci/devices/*; do
  [ "$(cat $d/vendor)" = 0x8086 ] || continue; case "$(cat $d/class)" in 0x0300*) ;; *) continue;; esac
  b=${d##*/}; p=$(readlink -f $d); rel=${p#/sys/devices/pci*/}; rp=${rel%%/*}
  echo "== $b (device $(cat $d/device)) =="
  printf "  %-14s %-10s %-20s %-30s %-3s %s\n" DEVICE ROLE LNKCAP2_SUPPORTED LNKSTA EQ DLACTIVE
  for hop in $(echo $rel | tr / ' '); do
    v=$(lspci -vv -s ${hop#0000:} 2>/dev/null)
    cap2=$(echo "$v" | grep -oP 'Supported Link Speeds: \K[^,]+'); sta=$(echo "$v" | grep -oP 'LnkSta:\s+Speed \K[^,]+, Width x[0-9]+')
    eq=$(echo "$v" | grep -oP 'EqualizationComplete\K[+-]' | head -1); dl=$(echo "$v" | grep -oP 'DLActive\K[+-]' | head -1)
    if [ "$hop" = "$b" ]; then role=GPU; elif [ "$hop" = "$rp" ]; then role=root-port; else role=bridge; fi
    printf "  %-14s %-10s %-20s %-30s %-3s %s\n" "$hop" "$role" "${cap2:-?}" "${sta:-?}" "${eq:-?}" "${dl:-?}"
  done
  echo "  => real link: the hop(s) showing EQ + and DLACTIVE +. Hops advertising only 2.5GT/s with EQ - are virtual."
  dmesg 2>/dev/null | grep -m1 'available PCIe bandwidth' | sed 's/.*kernel: //; s/^/  kernel says: /'
done
