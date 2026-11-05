# Debian/Ubuntu installer VM validation

This document records installer plumbing tests for draft PR #8. It does not
establish Intel Arc functionality, PCIe safety, or release readiness. Arch and
PCIe-verifier changes remain separate.

## Completed baseline run

The rollback implementation at commit
`7e12428f5ee2a5514b2528c63641a7f0285666ac` was exercised on a disposable Ubuntu
26.04.1 KVM guest, with no GPU passthrough. Repository history, boot files and
local recovery evidence were backed up. Backups and raw machine logs remain
private; they are not repository artifacts.

The boot payload in a private test copy was replaced with this inert script:

```sh
#!/bin/sh
case "${1:-}" in prereqs) exit 0 ;; esac
if [ "${ARC_REBAR_DRYRUN:-0}" = 1 ]; then
    echo 'arc-rebar: PLAN: act VM installer integration test only'
    exit 0
fi
echo 'arc-rebar: VM TEST ONLY - no PCI changes' > /dev/kmsg
exit 0
```

The upstream PCI script was not executed for installation or boot, and was not
replaced in the repository. The real initramfs hook and installer were used.
The built `.deb` was inspected but not installed or released.

| Check | Baseline result |
| --- | --- |
| Python regression suite | All 8 test methods passed |
| Shell syntax and whitespace checks | Passed |
| Debian package build | Passed |
| Real GRUB and initramfs-tools installation | All installer post-checks passed |
| GRUB command runs successfully, then reports failure | All saved checksums restored |
| Initramfs command rebuilds successfully, then reports failure | All saved checksums restored |
| Second hook/script installation command fails | All saved checksums restored |
| Installer killed after real GRUB update; explicit `--recover` | All saved checksums restored |
| Reboot after the failure/recovery tests | Guest booted; `pci=realloc` active; inert marker ran |
| Post-reboot inspection | Installation checksums unchanged; no recovery transaction retained |

## Backend mismatch found during testing

The guest initially supplied a dracut-backed `update-initramfs` even though
initramfs-tools directories and core utilities existed. Its rebuild succeeded
without including the project's initramfs-tools payload. Installer content checks
caught that failure and restored the original GRUB defaults, generated menu and
initramfs byte for byte.

The documented initramfs-tools frontend was then installed in this disposable
guest and a fresh baseline taken before the successful run above. This backend
switch was VM preparation, not an installer feature. It is not evidence of
dracut support or a recommendation to convert production systems.

The follow-up preflight check rejects incompatible or unidentified updaters before
hardware probing and boot-file mutation. Recovery remains available regardless of
the current backend. Older Debian frontends do not implement `--version`, so that
case also needs regression coverage rather than assuming every updater supports
the flag.

## Repeating integration checks

Use a disposable VM with console access and a verified hypervisor snapshot or
equivalent restoration plan. A file backup is not a full VM disk snapshot. Do not
run this procedure on a production boot configuration.

1. Confirm the active updater is provided by initramfs-tools; ensure `setpci`,
   `update-grub`, `update-initramfs` and `lsinitramfs` exist. Confirm the running
   kernel's initramfs, GRUB defaults/menu and hook directories exist and that
   `/boot` and `/` have room for images and backups. Stop on any missing prerequisite.
2. Check out the exact PR revision. Run `python3 -m unittest discover -s tests -v`,
   `bash -n install.sh`, `git diff --check` and `bash build-deb.sh`.
3. Make a private copy of the source and replace only that copy's
   `scripts/init-premount/arc-rebar` with the inert payload above. Keep the original
   checkout unchanged. Never use `--live-test` in the VM plumbing test.
4. Run the private copy's installer with `--yes`. Stop unless all post-checks pass.
   Record checksums for the hooks, origin marker, GRUB defaults/menu, running
   initramfs and all corresponding pre-existing backup files.
5. Reinstall with temporary command wrappers that execute the real `update-grub`
   or `update-initramfs` update and then exit nonzero. A wrapper must forward
   read-only backend probes unchanged, so the test reaches the intended failure.
   Check the installer fails and every saved checksum matches. Preserve the
   transaction evidence privately before using `--recover` to clear it.
6. Repeat with the second `install` command failing, then with SIGKILL immediately
   after the real GRUB update. After SIGKILL, require an active journal, run
   `--recover` and compare all checksums. Do not reboot while recovery is pending
   or if any comparison fails.
7. Check GRUB syntax, image contents and the inert script's execution order. Reboot
   through the console. Confirm `pci=realloc` and the marker:

   ```bash
   grep -w 'pci=realloc' /proc/cmdline
   sudo dmesg | grep -F 'arc-rebar: VM TEST ONLY - no PCI changes'
   ```

   The marker is a userspace `/dev/kmsg` message; `journalctl -k` did not include
   it on the tested system. Recheck saved checksums and confirm no recovery
   transaction remains. Restore the VM snapshot after testing if desired.

## Release gates still open

- Repeat supported-backend integration on disposable Debian and Ubuntu 24.04 VMs.
- Have an affected Intel Arc hardware tester validate cold/warm boots, BAR size,
  driver binding, a real workload, reinstallation, `norebar` recovery and removal.
- Review those results before merging or releasing. This VM run used an inert
  payload and cannot establish the real GPU script's correctness.

Publish only reviewed test summaries. Keep IP addresses, hostnames, local account
names, credentials and raw machine logs out of commits and issue comments.
