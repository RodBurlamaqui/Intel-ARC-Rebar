# Arch userspace integration tests

Recorded 2026-11-05 against the installer and hooks at
`ac2e4de918ffde55ec8efb86b898cda1d76750f2` (PR #6). These tests build and inspect
real images and exercise an inert runtime payload. They do not validate kernel
boot ordering, PCIe changes, driver binding or GPU workloads.

## Environment and isolation

- Disposable Ubuntu VM, with no Intel Arc GPU and no nested KVM device.
- Arch bootstrap release 2026.11.01 in a separate root filesystem, inside a
  private mount namespace. The bootstrap checksum and release signature were
  verified before extraction. Pacman retained package signature checks.
- Arch tools: mkinitcpio 42.2-1, mkinitcpio-busybox 1.36.1-1 and pciutils 3.15.0-1.
- The test root had private device nodes, empty PCI sysfs and its own `/boot`.
  No host boot directory or host PCI sysfs was mounted into it.
- Repository/history, working trees and VM boot configuration were backed up
  before experiments. Host boot-file checksums matched before and after.

The original GPU payload was retained separately and replaced only in the
private test copy with an inert script. Its dry run printed an `act` verdict;
its runtime printed a test marker and exited without PCI operations. The real
project build/runtime hooks and installer/uninstaller were used unchanged.

## What was exercised

The test preset used `ALL_kver="none"`, one conventional
`/boot/initramfs-*.img` output, and busybox/udev/kms/filesystems hooks. Per the
[mkinitcpio manual](https://man.archlinux.org/man/core/mkinitcpio/mkinitcpio.8.en),
`-k none` omits kernel modules. This intentionally tests image plumbing and
userspace dependencies rather than a bootable, hardware-specific image.

`pci=realloc` was already active in the VM's read-only command line. The private
GRUB files were placeholders; real Arch GRUB generation was not tested here.

| Experiment | Result |
| --- | --- |
| Baseline image build with real `mkinitcpio -P` | Passed |
| Real Arch installer with inert payload | All post-checks passed |
| Image contents and extraction with `lsinitcpio` | Payload, runtime hook, setpci and tr present; extracted payload matched |
| Runtime hook in extracted-image BusyBox environment | Inert marker executed |
| Extracted setpci version probe and tr execution | Passed with actual image libraries; no PCI register operations |
| Successful reinstall | Managed checksums/modes preserved; extracted hook still executed |
| Real rebuild followed by injected nonzero status, then successful recovery rebuild | Installer failed; previous managed files, modes and payload restored |
| Both attempt and recovery rebuild reported failure | Installer failed and explicitly said not to reboot; managed files/modes restored |
| Explicit repair rebuild after that reported recovery failure | Image/payload and runtime smoke test passed |
| Real uninstaller and image rebuild | Hook/payload removed from configuration, filesystem and image |
| Host VM boot-file checksum comparison | Unchanged |

Failure wrappers ran the real mkinitcpio command before returning nonzero. The
candidate payload contained a harmless distinguishing change so restoration
could be checked against the prior installed payload. Configurations and hook
files were compared byte for byte and by mode/ownership. Image checks used
extraction and execution rather than filenames alone. Arch transactions rebuild
images during recovery; they do not restore a saved boot-image checksum.

The private package setup initially hit chroot-specific resolver permissions and
mount-point detection problems. Resolver readability and a bind-mounted chroot
root fixed the test setup; no host network configuration or project runtime
change was needed. Private evidence and raw logs remain local.

## Automated topology and dry-run checks

Eleven additional regression methods run the unchanged boot script with fake
sysfs/proc paths and `ARC_REBAR_DRYRUN=1`. Mocked capabilities are per device,
and the setpci mock logs/rejects register writes. Sentinels check that config,
bind/unbind, device removal/rescan and kernel-log files remain unchanged.

Coverage includes A380/A750- and B580-shaped capability profiles, already-sized
BARs, `norebar`, missing `pci=realloc`, external-depth/shared-root/non-Intel
descendant refusals, absent/insufficient MMIO, size step-down and malformed
registers. A two-card fixture verifies default first-device selection and an
explicit `rebar.dev` selection. It also preserves evidence of the existing
first-GPU-only limitation: the default selection does not automatically advance
to a second card needing a resize. This adds no multi-GPU implementation.

All 39 combined methods pass (14 Debian installer, 14 Arch/dispatch and 11 boot
dry-run methods), along with syntax, whitespace and package-build checks. The
production boot payload, Arch hooks and Arch installer/uninstaller are unchanged.

## Remaining validation

These results strengthen software integration coverage. Since 1.0.8 the port is a normal
install from the Arch package (no opt-in flag). Real
Arch/CachyOS installation and cold/warm boot tests on affected Intel Arc hardware,
including hook timing, BAR allocation, driver/workload, reinstall and removal,
are tracked in [#15](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/15). Kernel modules, custom presets, UKIs, systemd initramfs, non-GRUB paths
and real Arch GRUB generation are outside this run. Do not cite these tests as
proof of electrical safety or GPU correctness.

## Opt-in flag (historical)

Before 1.0.8 the install dispatcher and the direct Arch installer required
`--experimental-arch`. From 1.0.8 Arch is a normal install; the flag is still accepted
and ignored, so older instructions keep working.
