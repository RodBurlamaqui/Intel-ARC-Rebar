#!/bin/bash
# Prove the fix on your hardware without rebooting. Stops the display manager
# (SSH survives), runs the boot script for real, restarts the display manager.
# If the machine hangs at the rescan: power cycle; nothing persistent changed.
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
echo "WARNING: this stops your display manager. Run it over SSH and save your work first."
echo "         If the machine hangs at the rescan, power cycle. Nothing persistent is changed."
echo "         AS IS, no warranty — see DISCLAIMER.md."
S=$(dirname "$(readlink -f "$0")")
grep -q 'pci=realloc' /proc/cmdline || { echo "pci=realloc is not active. Add it to GRUB_CMDLINE_LINUX_DEFAULT, update-grub, reboot, then retry."; exit 1; }
echo "== dry run first =="
out=$(ARC_REBAR_DRYRUN=1 sh "$S/scripts/init-premount/arc-rebar" 2>&1); echo "$out" | sed 's/^/  /'
case "$(echo "$out" | grep -m1 PLAN:)" in *"PLAN: act"*) ;; *) echo; echo "boot script would not act here; not running live."; exit 2;; esac
echo; read -r -p "Run for real now? Display goes dark until done. [y/N] " a; case "$a" in y|Y) ;; *) exit 1;; esac
systemctl stop display-manager 2>/dev/null; sleep 2
sh "$S/scripts/init-premount/arc-rebar"
systemctl start display-manager 2>/dev/null
echo; echo "== result =="; dmesg | grep 'arc-rebar: PLAN' | tail -1
gpu=$(dmesg | grep -o 'arc-rebar: PLAN: done gpu=[0-9a-f:.]*' | tail -1 | sed 's/.*gpu=//')
[ -n "$gpu" ] && lspci -vv -s "${gpu#0000:}" | grep -E 'Region 2|current size'
