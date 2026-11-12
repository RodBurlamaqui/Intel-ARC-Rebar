# Changelog

The original 2026-09-05 investigation was developed and verified on a Supermicro X9DRH-7TF
(C602, 2x Xeon E5-2670 v2, AMI BIOS 3.2) with an Intel Arc B580 12 GB,
Debian 13, kernel 7.1.8, xe driver. 1.0.3 is the first published release.

## Unreleased
- Merge the Arch/CachyOS mkinitcpio port as an explicit source-only experiment.
  Both install entrypoints require `--experimental-arch`, including reinstall;
  `--yes` does not bypass the opt-in. Refuse before hardware probing or boot-file
  changes when opt-in is missing. Removal does not require the flag.
- Preserve @hrimfaxi's original contribution and commit. Track physical Arch
  boot/GPU validation separately in issue #15; software coverage does not
  establish kernel boot ordering, hardware stability or workload health.
- Retain Debian/Ubuntu release assets and the earlier Arch preview unchanged.
- Fix a false `PLAN: done` when the kernel refuses the ReBAR write (for example
  Ubuntu kernels in lockdown under Secure Boot). `setpci` exits 0 on a refused
  write, so the boot hook reported `done` at the original size. The hook now
  skips with `kernel-lockdown` when lockdown is visible before any change, and
  reports `done` only if the control register reads back the written value and
  BAR2 has the target size. Otherwise it reports `rebar-write-not-applied` or
  rolls back. Covered by 6 new mocked tests. The register read-back is not yet
  hardware-confirmed on every model.
- When `pci=nocrs` is on the kernel command line, the `no-mmio-window-above-4g`
  refusal now says to remove `pci=nocrs` instead of pointing to Above 4G Decoding
  (also for the combined `pci=...,nocrs` form). The refusal reason is unchanged.
- Make the Debian package build reproducible: `build-deb.sh` sets
  `SOURCE_DATE_EPOCH` to the last commit time in a git checkout (a caller value
  wins; unset outside git) and gives every packaged file that timestamp, so the
  same commit builds a byte-identical `.deb` from any working copy. CI rebuilds
  after touching every file and fails if the hash changes. Already-published
  releases keep their original hashes. Reported by @propstat-dev (#47).

## 1.0.5 — 2026-11-05
- Make PCIe verification explicitly read-only: unresolved correctable/Unsupported
  Request DevSta bits return WARN (exit 2), with their age and cause unknown.
  Severe status, PCIe error logs, invalid/unreadable registers and allocation or
  driver failures retain FAIL (exit 1). A warning never overrides a failure.
- Validate BAR resource values and reject malformed ReBAR registers cleanly.
  Cover the reported A380/i915 and B580/VFIO resource layouts in mocked tests.
- Preserve the optional register-clearing experiment on a separate branch;
  exclude it from this release and reject `--recheck-pcie` before hardware access.
- Include 44 hardware-free regression tests. Physical GPU stability and the
  cause of the community's latched status remain unverified. The GPU boot hook
  and installer/purge behavior are unchanged from v1.0.4.
- Retain v1.0.4 and v1.0.3 downloads unchanged. Thanks to @TheKusja1 and @jacl3
  for the A750/A380 evidence and @CelluloidRacer2 for the B580/VFIO report.

## 1.0.4 — 2026-11-05
- Debian package purge: reject missing rebuild/inspection tools, fail on rebuild
  errors or stale images, and restore prior managed hooks/boot files after
  failure. Retain interrupted-purge recovery for `dpkg --purge` retries, preserve
  source-owned hooks, and clean partial package-owned installations. The
  previous v1.0.3 assets remain available unchanged.
- Surface community hardware reports for A750/A770, Lenovo A380 Debian boots,
  B580/VFIO and pending A380 Arch validation alongside the original B580 tests. Link report evidence, retain
  known limitations, credit contributors/testers and invite additional model
  reports with a hardware-report template.
- Debian/Ubuntu installer: restore previous managed boot files after failures and
  support interrupted-run recovery with `--recover`, including reinstalls.
  Refuse incompatible initramfs backends before probing hardware or changing boot
  files, while retaining compatibility with older initramfs-tools frontends.
- Document disposable-VM rollback validation and use `dmesg` for boot-script
  messages that `journalctl -k` can omit. No new physical GPU
  validation is claimed; the original GPU boot payload is unchanged.
- GPU firmware updates ruled out by direct test, not assumption: FWCODE
  21.1137 → 21.1182 and OptionROM 23.1051.0.0 → 23.1066.0.0 (LVFS, Sept 2026)
  leave the power-up BAR size field unchanged, the kernel resize still fails
  `-ENOSPC`, and the hook still has to fire. Recorded in ROOT-CAUSE and README.

## 1.0.3 — packaging and licence
- Licence: commercial and enterprise use requires separate licensing (§9), and Commercial Use
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
