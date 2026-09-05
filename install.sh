#!/bin/bash
# arc-rebar safe installer (Debian/Ubuntu, initramfs-tools).
# Refuses unless the boot script's own dry run says it would act on this machine.
set -e
YES=; LIVE=; REINST=
for a in "$@"; do case "$a" in
  --yes) YES=1;; --live-test) LIVE=1;; --reinstall) REINST=1;;
  *) echo "usage: $0 [--yes] [--live-test] [--reinstall]"; exit 1;; esac; done
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
S=$(dirname "$(readlink -f "$0")"); SCRIPT=$S/scripts/init-premount/arc-rebar
HOOK_DST=/etc/initramfs-tools/hooks/arc-rebar
SCR_DST=/etc/initramfs-tools/scripts/init-premount/arc-rebar
INITRD=/boot/initrd.img-$(uname -r)

echo "== arc-rebar safe install =="
echo; echo "== PRE-CHECKS: environment =="
[ -d /etc/initramfs-tools ] || { echo "no initramfs-tools here. Debian/Ubuntu only; for dracut/mkinitcpio port scripts/init-premount/arc-rebar by hand."; exit 1; }
command -v setpci >/dev/null || { echo "pciutils missing:  apt install pciutils"; exit 1; }
command -v update-initramfs >/dev/null || { echo "update-initramfs missing"; exit 1; }
kv=$(uname -r); kmaj=${kv%%.*}; kmin=$(echo "$kv" | cut -d. -f2)
if [ "$kmaj" -lt 6 ] || { [ "$kmaj" -eq 6 ] && [ "$kmin" -lt 12 ]; }; then
  echo "warning: kernel $kv is older than 6.12; xe ReBAR support may be missing"; fi
if [ -e "$SCR_DST" ] && [ -z "$REINST" ]; then
  echo "already installed: $SCR_DST"; dmesg 2>/dev/null | grep -m1 'arc-rebar: PLAN' | sed 's/^/  this boot: /'
  echo "use --reinstall to refresh, or ./uninstall.sh"; exit 0; fi

echo; echo "== PRE-CHECKS: hardware detection and safety (dry run, nothing changed) =="
out=$(ARC_REBAR_DRYRUN=1 ARC_REBAR_ASSUME_REALLOC=1 sh "$SCRIPT" 2>&1) || true
echo "$out" | sed 's/^/  /'
planline=$(echo "$out" | grep -m1 'PLAN:' | sed 's/.*PLAN: //')
case "$planline" in
  act*)  ;;
  none*) if [ -n "$REINST" ]; then echo; echo "BAR already at target (fix active or firmware ReBAR); reinstalling anyway."
         else echo; echo "Nothing to install: $planline"; exit 0; fi;;
  *)     echo; echo "REFUSING to install: $planline"; echo "This machine fails a safety check. See README: 'Where it does not apply'."; exit 2;;
esac

echo; echo "== PLAN =="; echo "  $planline"
echo "Will:   install hook + script into /etc/initramfs-tools, ensure pci=realloc in GRUB,"
echo "        back up $INITRD, rebuild the initramfs."
echo "Undo:   ./uninstall.sh   |   at the GRUB menu: append 'norebar' to the linux line"
echo; echo "== DISCLAIMER =="
echo "  Provided AS IS, no warranty. The authors accept no liability for data loss,"
echo "  hardware damage, downtime or any other loss. It writes a PCI register and"
echo "  re-enumerates a PCIe root port at boot. Designed to fail safe; not guaranteed."
echo "  Full text: $S/DISCLAIMER.md.  Back up your data first."
echo "  Licence: (c) 2026 Rod Burlamaqui. Personal Use free; commercial and enterprise use"
echo "  requires separate licensing; Modification and resale need approval. Full terms: $S/LICENSE"
if [ -z "$YES" ]; then
  read -r -p "Type ACCEPT to accept the disclaimer and proceed: " a
  [ "$a" = ACCEPT ] || { echo "not accepted; nothing changed"; exit 1; }
else
  echo "  (--yes given: disclaimer accepted non-interactively)"
fi

if [ -n "$LIVE" ]; then
  grep -q 'pci=realloc' /proc/cmdline || { echo; echo "--live-test needs pci=realloc active NOW. Install without --live-test, reboot, then run ./live-test.sh"; exit 1; }
  echo; echo "== live test (stops the display manager; SSH survives) =="
  "$S/live-test.sh" || true
  dmesg | grep -q 'arc-rebar: PLAN: done' || { echo "live test did not report 'done'; NOT installing"; exit 2; }
  echo "live test passed"
fi

echo; echo "== INSTALL =="
[ -f "$INITRD" ] && cp -n "$INITRD" "$INITRD.arc-rebar.bak" && echo "backup: $INITRD.arc-rebar.bak"
install -m 0755 "$S/hooks/arc-rebar" "$HOOK_DST"
install -m 0755 "$SCRIPT" "$SCR_DST"
# Record where the hook came from, so 'apt purge arc-rebar' only removes a hook the .deb installed.
mkdir -p /var/lib/arc-rebar
case "$S" in /usr/share/arc-rebar) echo deb > /var/lib/arc-rebar/hook-origin;; *) echo "source:$S" > /var/lib/arc-rebar/hook-origin;; esac
if ! grep -q 'pci=realloc' /etc/default/grub; then
  cp -n /etc/default/grub /etc/default/grub.arc-rebar.bak
  sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 pci=realloc"/' /etc/default/grub
  update-grub >/dev/null 2>&1 && echo "GRUB: added pci=realloc (backup: /etc/default/grub.arc-rebar.bak)"
fi
update-initramfs -u >/dev/null 2>&1 && echo "initramfs rebuilt"
echo; echo "== POST-CHECKS =="
pc=0
[ -x "$HOOK_DST" ] && echo "  [ok] $HOOK_DST" || { echo "  [FAIL] $HOOK_DST missing"; pc=1; }
[ -x "$SCR_DST" ]  && echo "  [ok] $SCR_DST"  || { echo "  [FAIL] $SCR_DST missing";  pc=1; }
grep -q 'pci=realloc' /etc/default/grub && echo "  [ok] pci=realloc in /etc/default/grub" || { echo "  [FAIL] pci=realloc not in GRUB"; pc=1; }
grep -q 'pci=realloc' /boot/grub/grub.cfg 2>/dev/null && echo "  [ok] pci=realloc in grub.cfg" || { echo "  [FAIL] grub.cfg lacks pci=realloc (run update-grub)"; pc=1; }
lsinitramfs "$INITRD" 2>/dev/null | grep -q 'scripts/init-premount/arc-rebar' && echo "  [ok] boot script inside $INITRD" || { echo "  [FAIL] boot script not in initramfs"; pc=1; }
lsinitramfs "$INITRD" 2>/dev/null | grep -q 'bin/setpci' && echo "  [ok] setpci inside initramfs" || { echo "  [FAIL] setpci not in initramfs"; pc=1; }
lsinitramfs "$INITRD" 2>/dev/null | grep -q 'libpci.so' && echo "  [ok] libpci inside initramfs" || { echo "  [FAIL] libpci not in initramfs"; pc=1; }
if [ $pc = 0 ]; then
  echo "  all post-checks passed"
else
  echo "ERROR: initramfs is missing pieces. Removing the hook and regenerating a clean initramfs."; rm -f "$HOOK_DST" "$SCR_DST" /var/lib/arc-rebar/hook-origin; update-initramfs -u >/dev/null 2>&1 || cp -f "$INITRD.arc-rebar.bak" "$INITRD"; exit 3
fi
echo; echo "Installed. Next:   sudo reboot   then   sudo $S/verify.sh"
echo "Escape hatch if anything goes wrong at boot: GRUB menu -> e -> append 'norebar' -> boot."
