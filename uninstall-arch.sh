#!/bin/bash
# arc-rebar uninstaller for Arch Linux / CachyOS (mkinitcpio).
set -e
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
CONF=/etc/mkinitcpio.conf
rm -f /etc/initcpio/install/arc-rebar /etc/initcpio/hooks/arc-rebar /usr/lib/arc-rebar/arc-rebar-boot /var/lib/arc-rebar/hook-origin
rmdir /usr/lib/arc-rebar 2>/dev/null || true
if [ -f "$CONF" ] && sed -n 's/^HOOKS=(\(.*\))[[:space:]]*$/\1/p' "$CONF" | head -1 | tr ' ' '\n' | grep -qx arc-rebar; then
  nh=$(sed -n 's/^HOOKS=(\(.*\))[[:space:]]*$/\1/p' "$CONF" | head -1 | tr ' ' '\n' | grep -vx arc-rebar | tr '\n' ' ' | sed 's/ *$//')
  sed -i -E "s|^HOOKS=\(.*\)$|HOOKS=($nh)|" "$CONF"
  echo "removed arc-rebar from HOOKS"
fi
mkinitcpio -P >/dev/null 2>&1 && echo "initramfs rebuilt without arc-rebar"
echo "pci=realloc left in GRUB (harmless). Remove it from GRUB_CMDLINE_LINUX_DEFAULT and rerun grub-mkconfig to revert."
