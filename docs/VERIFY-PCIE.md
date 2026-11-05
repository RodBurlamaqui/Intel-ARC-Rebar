# Read-only PCIe verification

## Community evidence

- [Issue #2, A750 / H11SSL-i / i915 / Proxmox](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/2):
  the reporter describes an assigned 8 GiB BAR, working Jellyfin transcoding,
  GPU DevSta `0008` and upstream DevSta `0019` / CESta `00002000`.
  Manual status clearing reportedly stopped recurrence; the same pattern with
  `norebar` leaves attribution to this workaround unproven.
- [Issue #10, A380 / ThinkCentre M900 / i915 / OpenMediaVault](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/10):
  the reporter describes a successful boot, normal GPU use, an 8 GiB assigned
  BAR, `PLAN: done` and DevSta `0008`. This is accepted community hardware
  evidence; its legacy verifier classification is addressed by the same v1.0.5
  fix as #2. The physical latch's cause remains unknown.
- [Issue #11, B580 / PowerEdge R720 / VFIO](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/11):
  a reported 16 GiB BAR and vfio-pci binding establish resource allocation,
  not the health of guest copy engines. Guest faults still need a comparison
  baseline and relevant guest evidence.

The verifier classification fix is shipped in v1.0.5 through PR #5. Issue #2
is closed for that software correction; closure does not establish the physical
cause or harmlessness of the reported PCIe status. The 14 verifier regression
methods also pass against the checksum-verified published v1.0.5 package with
PCI access intercepted. Reporter confirmation on that release is still welcome.

These reports were not independently reproduced on a physical GPU. Neither a
successful workload nor a latched bit alone establishes the event's cause.

## Released behavior

PCIe Device Status bits are latched write-one-to-clear evidence without an
event timestamp. Bits 0/3 alone yield WARN (exit 2); nonfatal/fatal bits 1/2
remain FAIL (exit 1). Allocation/binding failures, invalid or unreadable
registers, unavailable kernel logs and matching PCIe error logs also fail.
A warning never overrides another failed check. Clean available checks yield
PASS (exit 0), which is not a GPU workload certification.

Verification only reads PCI configuration registers. It never clears status,
modifies bridges or AER masks, or removes evidence. `--recheck-pcie` is not a
stable option and returns usage exit 64 before hardware access.

The earlier one-shot clearing/polling experiment and its tests remain on
[`experimental/pcie-clear-recheck`](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/tree/experimental/pcie-clear-recheck),
pinned at `c6f78cbb1639fdc5451c4850179dc43f0d93cfe6`. It is not included in the
stable package. Its read/clear race and physical hardware validation remain
unresolved; the read-only fix does not approve that experiment.

Primary references:

- [PCIe Device Status layout and W1C semantics](https://edc.intel.com/content/www/us/en/design/publications/core-processors-series-3-cfg-and-mem-registers/001/device-status-devsts-offset-4a/)
  describe generic register semantics, not A750-specific errata.
- [Linux AER handling](https://docs.kernel.org/PCI/pcieaer-howto.html) covers
  ownership, reporting and status clearing.
- [Linux AER counter ABI](https://www.kernel.org/doc/Documentation/ABI/testing/sysfs-bus-pci-devices-aer)
  describes endpoint/link-partner and hierarchy attribution limits.

## Validation and remaining hardware work

Run without root privileges or a GPU:

```bash
python3 -m unittest discover -s tests -v
bash -n verify.sh bin/arc-rebar
```

Fixtures intercept every PCI access and record attempted writes before checking
their target. They cover clean/auxiliary status, unresolved latches, severe
errors, invalid/unreadable registers, incorrect/unassigned BARs, missing drivers,
missing/error-containing kernel logs, a no-GPU machine, and rejected CLI options.
A380/i915 and B580/VFIO fixtures model the reported resource values; they do not
reproduce physical GPU behavior. The boot payload is unchanged by this fix.

Hardware owners can run the default read-only verifier and compare its output
with their assigned BAR, driver, endpoint/upstream status and relevant kernel
logs. Preserve original diagnostics locally; redact host/user identifiers,
network addresses and unrelated log entries before sharing. Cold/warm boot,
`norebar` comparison, representative memory/compute/transfer workloads and
output correctness remain useful hardware evidence. No clearing, error
injection, reinstall or removal is needed to try this verifier correction.
