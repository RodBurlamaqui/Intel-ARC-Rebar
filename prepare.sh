#!/bin/bash
# Cautious-path step: add pci=realloc to GRUB so live-test can run after ONE reboot.
# Installs nothing else. Safe to skip if you go straight to install.
set -e
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
if grep -q 'pci=realloc' /proc/cmdline; then echo "pci=realloc is already active. You can run live-test now."; exit 0; fi
if grep -q 'pci=realloc' /etc/default/grub; then echo "pci=realloc is already in /etc/default/grub but not active yet. Reboot, then run live-test."; exit 0; fi
cp -n /etc/default/grub /etc/default/grub.arc-rebar.bak
sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 pci=realloc"/' /etc/default/grub
grep -q 'pci=realloc' /etc/default/grub || { echo "ERROR: could not edit GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub. Add pci=realloc by hand, run update-grub, reboot."; exit 1; }
update-grub >/dev/null 2>&1
echo "Added pci=realloc to GRUB (backup: /etc/default/grub.arc-rebar.bak)."
echo "Next:  sudo reboot     then confirm:  grep -o pci=realloc /proc/cmdline     then:  sudo arc-rebar live-test"
