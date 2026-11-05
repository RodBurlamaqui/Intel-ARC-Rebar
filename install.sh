#!/bin/bash
# arc-rebar safe installer (Debian/Ubuntu, initramfs-tools).
# Refuses unless the boot script's own dry run says it would act on this machine.
set -e
YES=; LIVE=; REINST=; RECOVER=
for a in "$@"; do case "$a" in
  --recover) RECOVER=1;; --yes) YES=1;; --live-test) LIVE=1;; --reinstall) REINST=1;;
  *) echo "usage: $0 [--yes] [--live-test] [--reinstall] [--recover]"; exit 1;; esac; done
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
S=$(dirname "$(readlink -f "$0")"); SCRIPT=$S/scripts/init-premount/arc-rebar
# Arch / CachyOS: hand over to the mkinitcpio installer.
if [ ! -d /etc/initramfs-tools ] && [ -f /etc/mkinitcpio.conf ]; then exec "$S/install-arch.sh" "$@"; fi
HOOK_DST=/etc/initramfs-tools/hooks/arc-rebar
SCR_DST=/etc/initramfs-tools/scripts/init-premount/arc-rebar
INITRD=/boot/initrd.img-$(uname -r)

# A persistent, root-only journal survives an uncatchable interruption. Never
# overwrite it on a subsequent invocation. No hardware probe is needed to recover.
umask 077
STATE=/var/lib/arc-rebar
TX=$STATE/install-transaction
mkdir -p "$STATE"
exec 9>"$STATE/install.lock"
flock -n 9 || { echo "another installer is running"; exit 1; }
[ ! -d "$STATE/purge-transaction" ] || {
  echo 'Package purge transaction retained: fix the error and retry sudo dpkg --purge arc-rebar before installing.'; exit 1;
}
restore_transaction() {
  local failed=0 n path tmp
  while IFS=' ' read -r n path; do
    tmp="${path}.arc-rebar-restore"
    if [ -e "$TX/files/$n" ]; then
      cp -a -- "$TX/files/$n" "$tmp" && mv -f -- "$tmp" "$path" || failed=1
    else
      rm -f -- "$path" || failed=1
    fi
  done < "$TX/manifest"
  [ "$failed" = 0 ] || return 1
  sync || return 1
  rm -f "$TX/active"
}
if [ -d "$TX" ]; then
  if [ -n "$RECOVER" ]; then
    if [ -f "$TX/active" ]; then
      restore_transaction || { echo "RECOVERY FAILED: do not reboot. Backups: $TX"; exit 1; }
    fi
    rm -rf -- "$TX"
    echo "Recovery complete; inspect boot configuration before rebooting."
    exit 0
  fi
  echo "Previous transaction retained: run sudo $S/install.sh --recover before installing."
  exit 1
fi
[ -z "$RECOVER" ] || { echo "No interrupted transaction."; exit 0; }
transaction_exit() {
  local rc=$?
  trap - EXIT
  trap '' INT TERM HUP
  if [ -f "$TX/active" ]; then
    echo "Installation failed; restoring previous files. Logs/backups: $TX"
    if ! restore_transaction; then
      echo "RECOVERY FAILED: do not reboot; run sudo $S/install.sh --recover after fixing the storage error."
    fi
    [ "$rc" != 0 ] || rc=1
  fi
  exit "$rc"
}

echo "== arc-rebar safe install =="
echo; echo "== PRE-CHECKS: environment =="
[ -d /etc/initramfs-tools ] || { echo "no initramfs-tools here. Debian/Ubuntu only; for dracut/mkinitcpio port scripts/init-premount/arc-rebar by hand."; exit 1; }
command -v setpci >/dev/null || { echo "pciutils missing:  apt install pciutils"; exit 1; }
command -v update-initramfs >/dev/null || { echo "update-initramfs missing"; exit 1; }
# Ubuntu and Debian may provide an update-initramfs command that delegates to
# another image builder. The presence of the command and its config directories
# does not prove that initramfs-tools hooks will be run.
if backend_version=$(update-initramfs --version 2>&1); then
  if [[ ! "$backend_version" =~ ^initramfs-tools[[:space:]]+[^[:space:]]+([[:space:]]|$) ]]; then
    echo "unsupported initramfs backend: ${backend_version:-unknown}; this installer requires initramfs-tools"
    exit 1
  fi
else
  # Older initramfs-tools releases do not implement --version. In that case,
  # verify the resolved frontend is owned by the exact package we support.
  updater=$(command -v update-initramfs)
  updater=$(readlink -f -- "$updater") || { echo "cannot resolve update-initramfs frontend"; exit 1; }
  if ! command -v dpkg-query >/dev/null; then
    echo "cannot verify legacy update-initramfs frontend (dpkg-query missing)"
    exit 1
  fi
  backend_owner=$(dpkg-query -S "$updater" 2>/dev/null) || {
    echo "cannot verify legacy update-initramfs frontend ownership: $updater"
    exit 1
  }
  if [ "$backend_owner" != "initramfs-tools: $updater" ]; then
    echo "unsupported legacy update-initramfs frontend owner: ${backend_owner:-unknown}"
    exit 1
  fi
fi
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
# Refuse unsupported layouts before changing any managed file. In particular,
# do not dereference symlink destinations during install or recovery.
for cmd in update-grub lsinitramfs flock sync; do
  command -v "$cmd" >/dev/null || { echo "missing command: $cmd"; exit 1; }
done
for dir in /etc/initramfs-tools/hooks /etc/initramfs-tools/scripts/init-premount /boot/grub; do
  [ -d "$dir" ] || { echo "missing directory: $dir"; exit 1; }
done
for path in /etc/default/grub /boot/grub/grub.cfg "$INITRD"; do
  [ -f "$path" ] || { echo "missing boot file: $path"; exit 1; }
done
[ "$(grep -c '^GRUB_CMDLINE_LINUX_DEFAULT="[^"$`]*"$' /etc/default/grub)" = 1 ] || {
  echo 'Unsupported GRUB assignment; expected one literal double-quoted GRUB_CMDLINE_LINUX_DEFAULT line.'; exit 1;
}
[ "$(grep -c '^GRUB_CMDLINE_LINUX_DEFAULT=' /etc/default/grub)" = 1 ] || exit 1
trap transaction_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
mkdir -m 0700 "$TX"
mkdir "$TX/files"
n=0
for path in "$HOOK_DST" "$SCR_DST" "$STATE/hook-origin" /etc/default/grub /boot/grub/grub.cfg "$INITRD" "$INITRD.bak" "$INITRD.arc-rebar.bak" /etc/default/grub.arc-rebar.bak; do
  [ ! -L "$path" ] && { [ ! -e "$path" ] || [ -f "$path" ]; } || {
    echo "Unsupported destination: $path"; exit 1;
  }
  n=$((n+1))
  printf '%s %s\n' "$n" "$path" >> "$TX/manifest"
  if [ -e "$path" ]; then cp -a -- "$path" "$TX/files/$n"; fi
done
sync
# Only a complete durable snapshot may authorize mutations.
touch "$TX/active"
sync
# Keep the original escape-hatch backups; transaction backups are per attempt.
if [ ! -e "$INITRD.arc-rebar.bak" ]; then cp -a "$INITRD" "$INITRD.arc-rebar.bak"; fi
if [ ! -e /etc/default/grub.arc-rebar.bak ]; then cp -a /etc/default/grub /etc/default/grub.arc-rebar.bak; fi
install -m 0755 "$S/hooks/arc-rebar" "$HOOK_DST"
install -m 0755 "$SCRIPT" "$SCR_DST"
# Record where the hook came from, so 'apt purge arc-rebar' only removes a hook the .deb installed.
mkdir -p /var/lib/arc-rebar
case "$S" in /usr/share/arc-rebar) echo deb > /var/lib/arc-rebar/hook-origin;; *) echo "source:$S" > /var/lib/arc-rebar/hook-origin;; esac
if ! grep '^GRUB_CMDLINE_LINUX_DEFAULT=' /etc/default/grub | grep -Eq '([ " ])pci=realloc([ " ])'; then
  sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 pci=realloc"/' /etc/default/grub
fi
# Always rebuild: an existing token does not establish that grub.cfg is current.
update-grub >"$TX/grub.log" 2>&1 || { cat "$TX/grub.log"; exit 1; }
echo "GRUB updated"
update-initramfs -u -k "$(uname -r)" >"$TX/initramfs.log" 2>&1 || { cat "$TX/initramfs.log"; exit 1; }
echo "initramfs rebuilt"
lsinitramfs "$INITRD" >"$TX/contents" 2>"$TX/inspect.log" || { cat "$TX/inspect.log"; exit 1; }
echo; echo "== POST-CHECKS =="
pc=0
[ -x "$HOOK_DST" ] && echo "  [ok] $HOOK_DST" || { echo "  [FAIL] $HOOK_DST missing"; pc=1; }
[ -x "$SCR_DST" ]  && echo "  [ok] $SCR_DST"  || { echo "  [FAIL] $SCR_DST missing";  pc=1; }
grep -q 'pci=realloc' /etc/default/grub && echo "  [ok] pci=realloc in /etc/default/grub" || { echo "  [FAIL] pci=realloc not in GRUB"; pc=1; }
grep -q 'pci=realloc' /boot/grub/grub.cfg 2>/dev/null && echo "  [ok] pci=realloc in grub.cfg" || { echo "  [FAIL] grub.cfg lacks pci=realloc (run update-grub)"; pc=1; }
grep -q 'scripts/init-premount/arc-rebar' "$TX/contents" && echo "  [ok] boot script inside $INITRD" || { echo "  [FAIL] boot script not in initramfs"; pc=1; }
grep -q 'bin/setpci' "$TX/contents" && echo "  [ok] setpci inside initramfs" || { echo "  [FAIL] setpci not in initramfs"; pc=1; }
grep -q 'libpci.so' "$TX/contents" && echo "  [ok] libpci inside initramfs" || { echo "  [FAIL] libpci not in initramfs"; pc=1; }
if [ $pc = 0 ]; then
  echo "  all post-checks passed"
else
  echo "ERROR: post-check failed."; exit 3
fi
sync
rm -f "$TX/active"
sync
rm -rf -- "$TX"
trap - EXIT INT TERM HUP
echo; echo "Installed. Next:   sudo reboot   then   sudo $S/verify.sh"
echo "Escape hatch if anything goes wrong at boot: GRUB menu -> e -> append 'norebar' -> boot."
