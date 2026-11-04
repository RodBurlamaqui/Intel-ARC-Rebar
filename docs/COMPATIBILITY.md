# Hardware compatibility and community testing

Evidence reviewed on 2026-11-04. This is a record of reported setups, not a model
certification list. More Intel Arc model and motherboard reports are welcome.

The project began with B580 hardware tests. Its boot script selects a qualifying
Intel GPU using ReBAR capability and PCIe topology checks rather than a B580-only
model allowlist. Passing those checks is a prerequisite, not proof that an
unreported model/platform combination will work.

## Recorded evidence

| GPU / platform | What was demonstrated or reported | Evidence and remaining limits |
|---|---|---|
| B580 12 GB; Supermicro X9DRH-7TF, Debian 13, `xe` | Maintainer hardware testing: boot persistence, full BAR window and Vulkan/OpenCL workload measurements | [Original test record](TESTS.md) and [root-cause investigation](ROOT-CAUSE.md). These measurements apply to that setup. |
| A750 8 GB; Supermicro H11SSL-i, Proxmox/Debian, `i915` | Reporter describes successful live and persistent boot operation, 8 GiB BAR2 and Jellyfin hardware transcoding | [Issue #2](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/2). Latched PCIe status causes verifier FAIL; the cause remains unresolved. Proposed verifier behavior in [#5](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/pull/5) awaits hardware results. |
| A770 / A750; E5-2697 v2 LLM-server setup | Reporter states the workaround works on these cards and describes an LLM workload | [Issue #3](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/3). Motherboard, driver and per-card validation details are not provided there. The report also identifies the first-GPU-only limitation. |
| A380; CachyOS, `i915`, proposed mkinitcpio port | Contributor describes image contents and dry-run topology resolution inside the built image | [Original PR #4](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/pull/4), preserved in [draft PR #6](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/pull/6). Successful real boot/runtime, workload, reinstall and removal validation remain pending. |

These rows reflect project tests and first-hand reports. Repeated articles about
the original B580 test and GitHub stars are not additional hardware validations.
The [H11SSL-i/B580 gist](https://gist.github.com/andersevenrud/eec93e9151117bc0d6b6133b40eaffa5)
documents the underlying method credited to @andersevenrud; it is a separate
method report, not a test of this repository's installer.

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
- A750 BAR/workload success does not establish that its PCIe latches are harmless.
  Report verifier failures and relevant kernel evidence as observed.
- Arch/mkinitcpio support remains a draft in #6. Debian/Ubuntu VM tests with an
  inert boot payload validate installer plumbing, not GPU behavior or Arch.

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
