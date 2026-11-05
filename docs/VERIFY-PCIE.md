# Issue #2: evidence and acceptance criteria

Source: https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/2
Inspected 2026-11-03 against main cb07b65394eb203e1574c0702ba9e99a6dc53be8.
The issue was open with no comments. The reporter supplies evidence of an
8 GiB assigned BAR2, i915 binding and working Jellyfin transcoding on an A750 /
Supermicro H11SSL-i / Proxmox host. GPU DevSta 0008 and upstream DevSta 0019 /
CESta 00002000 reportedly stop recurring after manual W1C clears. The same
pattern with `norebar` argues against attributing it solely to the workaround.
These are reported hardware results, not independently reproduced results.
Enumeration timing and exact root cause remain unknown.

## Rationale

PCIe Device Status bits are latched W1C evidence, without an event timestamp.
Bits 0/3 alone therefore warrant an unresolved warning rather than a claim that
BAR resizing failed. Nonfatal/fatal bits remain failures, even if potentially
historical. The optional clear is intentionally narrow and does not change the
boot path, bridges, AER status/masks, PCI Command, or PCIe Device Control.
It cannot fully remove the read/clear race: an identical event between the
snapshot and the W1C write can be lost. Keeping the original warning, checking
counter changes and preserving kernel error failures avoids claiming certainty.
No assumption of harmlessness is based on GPU model or an error allowlist.

Primary references:
- Device Status layout and W1C semantics:
  https://edc.intel.com/content/www/us/en/design/publications/core-processors-series-3-cfg-and-mem-registers/001/device-status-devsts-offset-4a/
  (generic PCIe register semantics, not evidence of A750-specific behavior).
- Linux AER handling, firmware ownership, status clearing and reporting:
  https://docs.kernel.org/PCI/pcieaer-howto.html
- Counter ABI, including endpoint/link-partner and hierarchy attribution limits:
  https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-bus-pci-devices-aer

## Hardware validation required before adoption

1. On the reporter's H11SSL-i/A750/i915/Proxmox system, capture hostname, BIOS,
   kernel, driver, boot command line, topology, full kernel log and `lspci -Dvv`
   before any clear. Record DevSta and AER status/masks on the endpoint and each
   upstream port. Check whether Linux owns AER and counters are available.
2. Repeat cold and warm boots with the workaround enabled and `norebar`.
   Record actual BAR2 resource size and ReBAR control size independently.
   A reduced/unassigned BAR must still FAIL even if status is clean.
3. Confirm default `verify` does not alter registers: 0008/0019 produce WARN,
   while nonfatal/fatal evidence and actual kernel PCIe errors produce FAIL.
4. Save diagnostics, explicitly run `sudo arc-rebar verify --recheck-pcie 60`,
   and check the only write is the GPU endpoint's observed 0001/0008/0009 mask.
   Upstream DevSta/CESta, error masks and control registers must stay untouched.
   Original latched evidence remains WARN after a clean observation interval.
5. Run real transcoding plus GPU memory/compute and host/device transfer tests
   (see TESTS.md), during and after observation. Verify output correctness,
   absence of hangs/resets, unchanged BAR allocation and driver binding, and
   endpoint/upstream DevSta, AER counters and logs. Repeat with longer runs;
   a 60-second idle sample is not sufficient acceptance evidence.
6. On a disposable test host only, validate new correctable/uncorrectable reports
   using controlled AER injection if supported. Confirm immediate and delayed
   recurrence fails even if the kernel clears endpoint status. Confirm a
   root-port counter increment is reported without blaming the GPU alone.
7. Regress a known-working B580/xe configuration and a machine without usable
   AER counters. Missing counters must leave explicit rechecks inconclusive.

No hardware tests or injection have been performed for this patch. Automated
regressions mock PCI accesses and time, and cannot establish electrical safety,
A750 errata, or GPU functional stability. Do not merge as hardware-validated.

## Automated regressions

From the repository root, without root privileges or GPU hardware:

```bash
python3 -m unittest discover -s tests -v
bash -n verify.sh bin/arc-rebar
```

Fixtures cover clean/auxiliary status, unresolved latches, one-shot exact W1C
masks, immediate/delayed/new errors, severe errors, read/write failures,
endpoint/parent counter changes and resets, missing/malformed counters,
allocation/driver failures, unavailable/error-containing logs and CLI validation.

## Additional report-shaped software checks (2026-11-05)

The VM regression suite now includes two later community reports:

- [A380 / ThinkCentre M900, issue #10](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/10):
  an 8 GiB assigned BAR, i915 binding and DevSta `0008`. The mocked default
  verifier returns WARN (exit 2), preserves the unresolved latch and performs no
  register writes. This is the expected proposed behavior, not a claim that the
  reported latch is harmless or that the reporter has tested this PR.
- [B580 / PowerEdge R720 with VFIO, issue #11](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/11):
  a 16 GiB assigned BAR and vfio-pci binding. Resource checks can pass with a
  missing boot-verdict warning while explicitly saying that allocation/binding
  do not establish guest GPU workload health. The reported guest copy-engine
  faults need guest-side evidence and a comparison baseline; host PCIe checks
  cannot identify their cause.

A no-GPU fixture must fail rather than imply that a VM validated the hardware.
The fixture now records every attempted register write before validating its
address/register, so read-only assertions also catch unexpected write targets.
All 25 verifier regression methods pass. PCI accesses, sysfs, kernel logs,
counters and time are simulated; the executable verifier is unchanged. Physical
GPU tests and the optional one-shot clear still need the hardware validation
above. No raw machine logs or private infrastructure details are published.
