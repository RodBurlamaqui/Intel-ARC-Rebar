# Hardware compatibility and community testing

Evidence last updated on 2026-11-09. This is a record of reported setups, not a model
certification list. More Intel Arc model and motherboard reports are welcome.

The project began with B580 hardware tests. Its boot script selects a qualifying
Intel GPU using ReBAR capability and PCIe topology checks rather than a B580-only
model allowlist. Passing those checks is a prerequisite, not proof that an
unreported model/platform combination will work.

## Recorded evidence

| GPU / platform | What was demonstrated or reported | Evidence and remaining limits |
|---|---|---|
| B580 12 GB; Supermicro X9DRH-7TF, Debian 13, `xe` | Maintainer hardware testing: boot persistence, full BAR window and Vulkan/OpenCL workload measurements | [Original test record](TESTS.md) and [root-cause investigation](ROOT-CAUSE.md). These measurements apply to that setup. |
| A750 8 GB; Supermicro H11SSL-i, Proxmox/Debian, `i915` | @TheKusja1 describes live and persistent boot operation; a direct v1.0.3 → v1.0.5 `.deb` upgrade was completed without boot-hook reinstall or configuration changes. After reboot, BAR2 remains 8 GiB, the default read-only verifier returns WARN, and Jellyfin HEVC Main10 HDR10 → AV1 (`av1_qsv`, VA-API tone mapping) completes with no observed hangs/resets or AER log reports. | [Original report #2](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/2) and [2026-11-07 hardware confirmation](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/2#issuecomment-6707332319). The legacy verifier classification correction is now reporter-confirmed on this setup. The latch's age/cause and general harmlessness remain unknown. The reported 5.09x / ~122 FPS run is an observation, not a controlled ReBAR performance comparison. |
| A310 4 GB; Fujitsu RX2540 M2, BIOS V5.0.0.11 R1.31.0, Proxmox host / VFIO guest passthrough | @optiz0r reports first-card guest access to the full 4 GiB BAR. Boot logs show a 256 MiB to 4 GiB resize and `PLAN: done` for that card; its resource and ReBAR control agree. | [Issue #3 follow-up](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/3#issuecomment-6722498363) and [diagnostics](https://gist.github.com/optiz0r/7cd12c10d971fc3fcc8549abe4eb9731). Two A310 endpoints appear on separate root ports; the second remains at 256 MiB. This confirms first-card operation on the reported setup, not upstream dual-GPU support. The text mentions four cards but the supplied inventory/diagnostics show two; total installed count needs clarification. |
| A770 16 GB / A750 8 GB; Asus Z9PA-D8, E5-2697 v2, Debian SID / forced `xe` | Reporter describes appropriate BAR sizes with a locally modified multi-card loop and an LLM workload | [Issue #3 follow-up](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/3#issuecomment-6649456377). Unmodified diagnostics and three-card testing are planned, not completed. This does not validate an upstream multi-GPU implementation. |
| A380 6 GB; Lenovo ThinkCentre M900, OpenMediaVault/Debian, `i915`, initramfs-tools | Reporter describes boot persistence, an 8 GiB BAR at the card's advertised maximum, a `PLAN: done` boot verdict and normal GPU use | [Issue #10](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/10). Before-size, BIOS/kernel versions and installed revision were not recorded; reinstall/removal were untested. The legacy verifier FAIL was triggered by DevSta `0008`, with no AER reports in the supplied excerpt. A matching test against the released v1.0.5 verifier returns unresolved WARN without writes; the physical latch's age/cause and reporter confirmation on that version remain unknown. This is Debian evidence, separate from the Arch port. |
| B580 12 GB; Dell PowerEdge R720, Proxmox host / VFIO, Ubuntu guest / `xe` | Reporter describes a 256 MiB to 16 GiB BAR change, persistence across reported reboots, full guest-visible VRAM and llama.cpp workloads | [Issue #11](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/11), closed by its author as a completed hardware report. The boot verdict is missing; the exact hook execution on that boot is unconfirmed. Guest copy-engine faults/hangs and slow pageable transfers are reported, with cause unassigned and no comparison baseline. These limits remain despite resource-check PASS. |
| A380; CachyOS, `i915`, experimental mkinitcpio port | Contributor describes image contents and dry-run topology resolution inside the built image | [Original PR #4](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/pull/4), preserved in [PR #6](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/pull/6). Installation requires `--experimental-arch`. Successful real boot/runtime, workload, reinstall and removal validation are tracked in [#15](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/15). |

These rows reflect project tests and first-hand reports. Repeated articles about
the original B580 test and GitHub stars are not additional hardware validations.
The [H11SSL-i/B580 gist](https://gist.github.com/andersevenrud/eec93e9151117bc0d6b6133b40eaffa5)
documents the underlying method credited to @andersevenrud; it is a separate
method report, not a test of this repository's installer.

### A750 Jellyfin performance observation

In the [2026-11-07 follow-up](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/2#issuecomment-6707332319),
@TheKusja1 reports about **122 FPS / 5.09x real time** for a 4K HEVC Main10
HDR10 source transcoded to AV1 with `av1_qsv` and VA-API HDR tone mapping.
Their usual results on comparable workloads are around 4.5x. This is an
encouraging observation, but it is **not a controlled ReBAR-on/off benchmark**
of the same input and settings. It does not establish a causal 13% gain from
ReBAR or from v1.0.5, whose verifier correction does not change the boot payload.
No additional benchmark is required to accept the verifier confirmation.

## Other cards and known limits

Additional Arc models may qualify when they have the same relevant topology and
resource-allocation problem. Unlisted models remain unverified until someone
reports their actual configuration and results. A report about another tool or
a modified fork does not automatically validate this project's version.

- Check Above 4G Decoding, available MMIO space, the pinned-window signature and
  the full `diagnose` verdict. Do not force a safety refusal.
- Card model, firmware, motherboard topology, kernel/driver and initramfs backend
  all affect applicability. Working on one machine does not validate every
  machine with the same card.
- The script processes the first qualifying GPU. A successful verdict does not
  establish that every card in a multi-GPU host was handled; [#3](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/3)
  remains open.
- A750/A380 BAR/workload success does not establish that their PCIe latches are harmless.
  Report the actual verifier result/exit code and relevant kernel evidence as observed.
- An [experimental Arch source preview](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/tag/arch-preview-2026.11.05.1)
  remains public and unchanged. The current source installer requires
  `--experimental-arch`; its hardware follow-up is [#15](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/15).
  Mocked tests and isolated moduleless Arch userspace builds with an inert payload
  validate installer plumbing, not a physical GPU or real Arch kernel boot.

## Share a result for your setup

Use the [hardware-report template](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/new?template=hardware-report.md)
for success, partial success, refusal or failure. Reports of additional models
are useful even when the tool declines to act.

Start with the read-only diagnosis described in [INSTALL.md](../INSTALL.md).
An existing working system does not need another installation just to submit a
report. If you choose to perform a real installation, use the documented backup,
console and recovery precautions. Stop if recovery fails; do not inject failures
on production hardware to gather a report.

Please include the model/VRAM, board and BIOS version, OS/kernel/driver, project
version or commit, initramfs backend, GPU count/topology and the actual stage you
tested. Distinguish diagnosis/image inspection from live operation, reboot,
workload, reinstall and removal. Describe BAR2 before/after and any verifier or
driver errors; mark observations you did not make as untested.

Share only relevant excerpts. Redact IP addresses, hostnames, local account
names, serial numbers, credentials, private paths and unrelated devices. Full
raw machine logs are not required. Thank you for helping expand the evidence.
