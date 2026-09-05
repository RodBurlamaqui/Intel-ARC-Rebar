# Changelog

All revisions on 2026-09-05, developed and verified on a Supermicro X9DRH-7TF
(C602, 2x Xeon E5-2670 v2, AMI BIOS 3.2) with an Intel Arc B580 12 GB,
Debian 13, kernel 7.1.8, xe driver. 1.0.3 is the first published release.

## 1.0.3 — packaging and licence
- Licence: commercial licences are explicitly for sale (§9), and Commercial Use
  expressly covers hardware/GPU/platform vendors, driver/OS vendors, and any
  incorporation of the code into another product, driver, firmware, kernel or
  package (§3.1).
- Security/robustness review: `rebar.dev=` is format-validated; unreadable ReBAR
  registers now produce a clean `skip` instead of a shell arithmetic error (boot
  script, verify, diagnose, bar-pin-check); the initramfs hook fails loudly if
  `setpci` is missing; `ARC_REBAR_HOME` is honoured only as an absolute existing
  directory; a failed install regenerates a clean initramfs rather than restoring
  a possibly stale backup; `ocl_test` rejects nonsensical arguments.
- `apt purge` removes the boot hook only if the .deb installed it (tracked in
  `/var/lib/arc-rebar/hook-origin`); a hook installed from source is left alone.
  Found by purging a test .deb on a source-installed machine and losing the hook.
- The diagnostics (formerly a separate arc-smallbar-diag tree) merged in under
  `diag/`: five read-only tools + `ocl_test`, shipped in the .deb and reachable as
  `arc-rebar diag <tool>`. One app for the small-BAR problem and its false alarms.
- Proprietary licence (LICENSE): personal use free; Commercial Use, Modification
  and resale require written approval. DISCLAIMER.md. Installer requires typing
  ACCEPT.
- `.deb` package: `arc-rebar` command in `/usr/bin` with subcommands
  diagnose | prepare | live-test | install | verify | uninstall. Installing the
  package enables nothing; `apt remove` keeps an enabled boot hook, `apt purge`
  removes it.
- `prepare` subcommand: adds `pci=realloc` only, so the live test can run after
  one reboot (Path B).
- INSTALL.md: step-by-step with expected output for Path A (one reboot) and
  Path B (prove it live first). README install/layout/contributing sections.

## 1.0.2 — fixes found by verification
- Dry-run mode (diagnose, installer pre-check) no longer writes its verdict to
  the kernel log; it was overwriting the boot verdict that `verify` reads.
- `diagnose` recognises a boot where the fix already ran and reports FIXED
  instead of "you have this problem" (xe's first probe always logs Small BAR
  before the hook runs).
- Installer POST-CHECKS silence `lsinitramfs` stderr noise
  (`unmkinitramfs: zstd failed`) that made passing checks look alarming.

## 1.0.1 — hardened: auto-detect, refuse rather than guess, roll back
- Finds the GPU (any Intel VGA with a ReBAR capability), its root port and
  the card's maximum size from sysfs; no hardcoded bus numbers.
- Measures the MMIO window above 4 GB from `/proc/iomem`; steps the target
  down to what fits; refuses if nothing >= 512 MB fits or no window exists.
- Refuses when the root port carries anything other than the card's own
  switch/GPU/audio, when the path is deeper than root port -> switch -> GPU
  (external switch, riser, Thunderbolt), or when a thunderbolt driver is bound.
- Rolls back to the original size and rescans again if BAR2 comes back
  unassigned. Every exit logs `arc-rebar: PLAN: <verdict>` and returns 0.
- `norebar`, `rebar.dev=`, `rebar.size=` kernel command-line knobs.
- Safe installer: runs the boot script's own dry run as PRE-CHECK and refuses
  unless it would act; backs up the initrd; POST-CHECKS the rebuilt initramfs
  and restores the backup on failure. `verify.sh` PASS/FAIL after reboot.
- Boot-verified: `PLAN: done gpu=0000:86:00.0 bar2=16384M` at 11.5 s.

## 1.0.0 — the fix
- Root cause identified from the kernel log: the B580's integrated switch
  upstream port (8086:e2ff) has an 8 MB BAR0 inside the root port's
  prefetchable window; `pci_resize_resource()` releases bridge windows but not
  that BAR0, so the root port logs "was not released (still contains assigned
  resources)" and the 16 GB request fails with -ENOSPC despite 63 GB free.
- Fix, after andersevenrud's H11SSL-i approach: program the ReBAR control
  register, remove the root port, rescan, from the initramfs before xe binds.
- Proven live over SSH (BAR2 256M -> 16G, Vulkan 256 MiB host-visible heap ->
  one 11.93 GiB heap, OpenCL single allocation 256 MiB -> 1 GiB+, measured
  VRAM bandwidth 15 -> 392 GB/s), then installed as an initramfs hook and
  verified across a reboot. The live-test script was hardcoded to this machine;
  the first boot script already auto-detected GPU, root port and size, but had
  no safety checks and no rollback yet.
