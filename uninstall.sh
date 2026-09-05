#!/bin/bash
set -e
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
rm -f /etc/initramfs-tools/hooks/arc-rebar /etc/initramfs-tools/scripts/init-premount/arc-rebar /var/lib/arc-rebar/hook-origin
update-initramfs -u >/dev/null 2>&1 && echo "initramfs rebuilt without arc-rebar"
echo "pci=realloc left in GRUB (harmless). To revert it: restore /etc/default/grub.arc-rebar.bak if present, then update-grub."
echo "Old initrd backup, if any: /boot/initrd.img-$(uname -r).arc-rebar.bak"
