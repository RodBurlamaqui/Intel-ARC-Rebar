#!/bin/bash
# arc-rebar safe installer for Arch Linux / CachyOS (mkinitcpio).
# Same contract as install.sh: refuses unless the boot script's own dry run says
# it would act on this machine. Configuration/hooks are backed up before edits.
set -e
YES=; LIVE=; REINST=
for a in "$@"; do case "$a" in
  --yes) YES=1;; --live-test) LIVE=1;; --reinstall) REINST=1;;
  *) echo "usage: $0 [--yes] [--live-test] [--reinstall]"; exit 1;; esac; done
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
S=$(dirname "$(readlink -f "$0")"); SCRIPT=$S/scripts/init-premount/arc-rebar
BOOT_DST=/usr/lib/arc-rebar/arc-rebar-boot
HOOK_DST=/etc/initcpio/install/arc-rebar
RUN_DST=/etc/initcpio/hooks/arc-rebar
CONF=/etc/mkinitcpio.conf
source "$S/arch-transaction.sh"

echo "== arc-rebar safe install (mkinitcpio) =="
echo; echo "== PRE-CHECKS: environment =="
[ -f "$CONF" ] || { echo "no $CONF: not an mkinitcpio system. Debian/Ubuntu: use install.sh."; exit 1; }
command -v setpci >/dev/null || { echo "pciutils missing:  pacman -S pciutils"; exit 1; }
command -v mkinitcpio >/dev/null || { echo "mkinitcpio missing:  pacman -S mkinitcpio"; exit 1; }
command -v lsinitcpio >/dev/null || { echo "lsinitcpio missing:  pacman -S mkinitcpio"; exit 1; }
kv=$(uname -r); kmaj=${kv%%.*}; kmin=$(echo "$kv" | cut -d. -f2)
case "$kmaj" in ''|*[!0-9]*) ;; *)
  if [ "$kmaj" -lt 6 ] || { [ "$kmaj" -eq 6 ] && [ "$kmin" -lt 12 ]; }; then
    echo "warning: kernel $kv is older than 6.12; xe ReBAR support may be missing"; fi;;
esac
# Drop-ins override this file; refuse rather than edit an ineffective setting.
for override in /etc/mkinitcpio.conf.d/*.conf; do
  [ ! -e "$override" ] || { echo "Unsupported config override: $override" >&2; exit 1; }
done
hooks_line(){ arch_hooks; }
cur=$(hooks_line) || exit 1
case " $cur " in
  *" systemd "*) echo 'The runtime hook requires busybox/udev; systemd initramfs is not supported.' >&2; exit 1;;
esac
case " $cur " in
  *" udev "*) ;;
  *) echo 'The runtime hook requires udev in HOOKS.' >&2; exit 1;;
esac
case " $cur " in
  *" kms "*) ;;
  *) echo 'Expected kms in HOOKS so hook ordering can be checked.' >&2; exit 1;;
esac
seen_udev=
for hook in $cur; do
  [ "$hook" != udev ] || seen_udev=1
  if [ "$hook" = kms ] && [ -z "$seen_udev" ]; then
    echo 'Expected udev before kms.' >&2; exit 1
  fi
done
if [ -e "$HOOK_DST" ] && [ -z "$REINST" ]; then
  echo "already installed: $HOOK_DST"; dmesg 2>/dev/null | grep -m1 'arc-rebar: PLAN' | sed 's/^/  this boot: /'
  echo "use --reinstall to refresh, or ./uninstall-arch.sh"; exit 0; fi

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
echo "Will:   install $BOOT_DST plus the mkinitcpio hook ($HOOK_DST) and its runtime half"
echo "        ($RUN_DST), put 'arc-rebar' into HOOKS before 'kms' in $CONF,"
echo "        ensure pci=realloc in GRUB, rebuild the initramfs."
echo "Undo:   sudo ./uninstall-arch.sh   |   at the GRUB menu: append 'norebar' to the linux line"
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

arch_begin
echo; echo "== INSTALL =="
install -d -m 0755 /usr/lib/arc-rebar /etc/initcpio/install /etc/initcpio/hooks
install -m 0755 "$SCRIPT" "$BOOT_DST"
echo "boot script: $BOOT_DST"
install -m 0755 "$S/mkinitcpio/install/arc-rebar" "$HOOK_DST"
echo "mkinitcpio hook: $HOOK_DST"
install -m 0755 "$S/mkinitcpio/hooks/arc-rebar" "$RUN_DST"
echo "runtime hook: $RUN_DST"
mkdir -p /var/lib/arc-rebar; echo arch > /var/lib/arc-rebar/hook-origin

if ! grep -q 'pci=realloc' /proc/cmdline; then
  if grep -q 'pci=realloc' /etc/default/grub 2>/dev/null; then
    echo "pci=realloc already in /etc/default/grub (not active this boot: reboot after install)"
  elif [ -f /etc/default/grub ] && command -v grub-mkconfig >/dev/null; then
    sed -i -E "s|^GRUB_CMDLINE_LINUX_DEFAULT=['\"](.*)['\"]|GRUB_CMDLINE_LINUX_DEFAULT='\1 pci=realloc'|" /etc/default/grub
    grep -q 'pci=realloc' /etc/default/grub || { echo "ERROR: could not edit GRUB_CMDLINE_LINUX_DEFAULT. Add pci=realloc by hand."; exit 1; }
    if ! grub-mkconfig -o /boot/grub/grub.cfg > "$ARCH_BACKUP/grub-build.log" 2>&1; then
      echo "ERROR: grub-mkconfig failed; see $ARCH_BACKUP/grub-build.log" >&2
      exit 1
    fi
    echo "GRUB: added pci=realloc"
  else
    echo "ERROR: pci=realloc is not active and no GRUB config was found to edit."
    echo "       Add pci=realloc to your bootloader's kernel command line first, then rerun."
    exit 1
  fi
fi

# Reposition an existing hook too, rather than accepting one after kms.
cur=$(hooks_line)
nh=
for hook in $cur; do
  [ "$hook" != arc-rebar ] || continue
  [ "$hook" != kms ] || nh="${nh:+$nh }arc-rebar"
  nh="${nh:+$nh }$hook"
done
sed -i -E "s|^HOOKS=\(.*\)[[:space:]]*$|HOOKS=($nh)|" "$CONF"
echo "HOOKS: $nh"
if ! mkinitcpio -P > "$ARCH_BACKUP/build.log" 2>&1; then
  echo "ERROR: mkinitcpio failed; see $ARCH_BACKUP/build.log" >&2
  exit 1
fi
echo "initramfs rebuilt"

echo; echo "== POST-CHECKS =="
pc=0
[ -f "$BOOT_DST" ] && echo "  [ok] $BOOT_DST" || { echo "  [FAIL] $BOOT_DST missing"; pc=1; }
[ -x "$HOOK_DST" ] && echo "  [ok] $HOOK_DST" || { echo "  [FAIL] $HOOK_DST missing"; pc=1; }
[ -x "$RUN_DST" ]  && echo "  [ok] $RUN_DST"  || { echo "  [FAIL] $RUN_DST missing";  pc=1; }
case " $(hooks_line) " in
  *" arc-rebar "*) echo "  [ok] arc-rebar in $CONF";;
  *) echo "  [FAIL] arc-rebar not in HOOKS"; pc=1;;
esac
{ grep -q 'pci=realloc' /proc/cmdline || grep -q 'pci=realloc' /etc/default/grub 2>/dev/null; } && echo "  [ok] pci=realloc active or configured" || { echo "  [FAIL] pci=realloc missing"; pc=1; }
grep -q 'pci=realloc' /proc/cmdline && echo "  [ok] pci=realloc active this boot" || echo "  [warn] pci=realloc not active yet: reboot before verify"
imgs=$(ls -1 /boot/initramfs-*.img /efi/EFI/Linux/*.efi 2>/dev/null || true)
[ -n "$imgs" ] || { echo "  [FAIL] no initramfs images found"; pc=1; }
for img in $imgs; do
  l=$(lsinitcpio -l "$img" 2>/dev/null) || { echo "  [FAIL] cannot list $img"; pc=1; continue; }
  echo "$l" | grep -qx 'arc-rebar-boot' && echo "  [ok] boot script inside $img" || { echo "  [FAIL] boot script not in $img"; pc=1; }
  echo "$l" | grep -qx 'usr/bin/setpci' && echo "  [ok] setpci inside $img" || { echo "  [FAIL] setpci not in $img"; pc=1; }
  echo "$l" | grep -qx 'usr/bin/tr' && echo "  [ok] tr inside $img" || { echo "  [FAIL] tr not in $img (mkinitcpio busybox has no such applet)"; pc=1; }
  echo "$l" | grep -qx 'hooks/arc-rebar' && echo "  [ok] hook inside $img" || { echo "  [FAIL] hook not in $img"; pc=1; }
done
if [ $pc = 0 ]; then
  echo "  all post-checks passed"
else
  echo "ERROR: post-checks failed; restoring the previous installation." >&2
  exit 3
fi
echo; echo "Installed. Next:   sudo reboot   then   sudo $S/verify.sh"
echo "Escape hatch if anything goes wrong at boot: GRUB menu -> e -> append 'norebar' -> boot."
