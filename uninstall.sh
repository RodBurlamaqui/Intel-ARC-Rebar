#!/bin/bash
# arc-rebar - Copyright (c) 2026 Rod Burlamaqui. All rights reserved.
# Proprietary software, licensed under the LICENSE file. Modifying it or distributing
# modified versions is prohibited (LICENSE §3.2); removing this notice is prohibited (§3.4).
# Official source: https://github.com/RodBurlamaqui/Intel-ARC-Rebar
set -e
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
S=$(dirname "$(readlink -f "$0")")
# Arch / CachyOS: hand over to the mkinitcpio uninstaller.
if [ ! -d /etc/initramfs-tools ] && [ -f /etc/mkinitcpio.conf ]; then exec "$S/uninstall-arch.sh" "$@"; fi
rm -f /etc/initramfs-tools/hooks/arc-rebar /etc/initramfs-tools/scripts/init-premount/arc-rebar /var/lib/arc-rebar/hook-origin
update-initramfs -u >/dev/null 2>&1 && echo "initramfs rebuilt without arc-rebar"
echo "pci=realloc left in GRUB (harmless). To revert it: restore /etc/default/grub.arc-rebar.bak if present, then update-grub."
echo "Old initrd backup, if any: /boot/initrd.img-$(uname -r).arc-rebar.bak"
