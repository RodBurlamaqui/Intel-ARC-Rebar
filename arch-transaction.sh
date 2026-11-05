#!/bin/bash
# Shared by the source-tree Arch installer/uninstaller. Never run standalone.
# Keep backups after success or failure so an operator can inspect/recover them.
# Parse only the simple array form we can safely edit; never eval config text.
arch_hooks(){
  local line raw count
  count=$(grep -c '^HOOKS=' "$CONF") || true
  [[ $count == 1 ]] || { echo 'Expected exactly one HOOKS assignment' >&2; return 1; }
  line=$(sed -n 's/^HOOKS=(\(.*\))[[:space:]]*$/\1/p' "$CONF")
  raw=${line//\"/}; raw=${raw//\'/}
  [[ $raw =~ ^[a-zA-Z0-9_[:space:]-]+$ ]] || { echo 'Unsupported HOOKS syntax' >&2; return 1; }
  local -a hooks
  read -r -a hooks <<< "$raw"
  printf '%s\n' "${hooks[*]}"
}
arch_begin(){
  local file
  mkdir -p /var/lib/arc-rebar/backups
  ARCH_BACKUP=$(mktemp -d /var/lib/arc-rebar/backups/change.XXXXXXXX)
  chmod 0700 "$ARCH_BACKUP"
  ARCH_FILES=(/etc/mkinitcpio.conf /etc/default/grub /boot/grub/grub.cfg
    /usr/lib/arc-rebar/arc-rebar-boot /etc/initcpio/install/arc-rebar
    /etc/initcpio/hooks/arc-rebar /var/lib/arc-rebar/hook-origin)
  for file in "${ARCH_FILES[@]}"; do
    # Refuse managed symlinks: copying/restoring the link would not undo a
    # command that followed it and modified its target.
    [[ ! -L $file ]] || { echo "Refusing managed symlink: $file" >&2; return 1; }
    [[ ! -e $file || -f $file ]] || { echo "Not a regular file: $file" >&2; return 1; }
    if [[ -e $file ]]; then
      mkdir -p "$ARCH_BACKUP/files$(dirname "$file")"
      cp -a -- "$file" "$ARCH_BACKUP/files$file"
    fi
  done
  echo "Configuration/hook backups: $ARCH_BACKUP"
  # No managed file has changed before the backup completes.
  trap arch_finish EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
}
arch_finish(){
  local status=$? file restore_failed=0
  trap - EXIT INT TERM
  if (( status == 0 )); then return; fi
  echo "ERROR: operation failed (exit $status); restoring previous configuration/hooks." >&2
  for file in "${ARCH_FILES[@]}"; do
    if [[ -f $ARCH_BACKUP/files$file ]]; then
      cp -a -- "$ARCH_BACKUP/files$file" "$file" || restore_failed=1
    else
      rm -f -- "$file" || restore_failed=1
    fi
  done
  if (( restore_failed )); then
    echo "ERROR: restoration incomplete. Do not reboot; recover from $ARCH_BACKUP." >&2
  elif mkinitcpio -P > "$ARCH_BACKUP/recovery-build.log" 2>&1; then
    echo 'Previous configuration restored and initramfs rebuild completed.' >&2
  else
    echo "ERROR: recovery rebuild failed. Do not reboot; inspect $ARCH_BACKUP/recovery-build.log." >&2
  fi
  # Never turn a failed operation into success, even if recovery worked.
  exit "$status"
}
