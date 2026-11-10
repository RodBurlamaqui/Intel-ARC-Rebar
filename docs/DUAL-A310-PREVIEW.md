# Experimental two-A310 Debian preview

Version: **1.0.6~dual-a3101**. Hardware acceptance is **pending** in
[issue #3](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/3).
This is a separate prerelease; v1.0.5 remains the stable download.

## Scope and evidence

Thank you to @optiz0r for the Fujitsu RX2540 M2 / Proxmox report and diagnostics.
They show the first A310 resized from 256 MiB to 4 GiB and usable through VFIO
in the guest. The second remains at 256 MiB. This preview addresses the
first-card-only selection, but has **not been tested on physical GPUs**.

The opt-in accepts exactly **two Intel Arc A310 endpoints (8086:56a6)**, each
advertising a maximum 4 GiB BAR2, on distinct root ports. Each root must contain
only that card's expected integrated Intel switch/GPU/audio hierarchy. Both GPUs
must be non-console devices, unbound or bound to `vfio-pci`. Other models,
three/four cards, shared roots, external switches and host graphics drivers are
refused. `rebar.dev` and `rebar.size` cannot be combined with dual mode.

Before changing either card, the script checks both cards and reserves aligned
space for every required expansion in each shared host memory window. It counts
existing allocations, conservatively using only the contiguous tail above them.
It repeats the checks after each rescan, stops on a failure or changed topology,
and reports overall success only after both BARs are 4 GiB and do not overlap.
This is a conservative resource check, not a guarantee about firmware or kernel
allocation. A failed second card can leave the first resized; this is not an
atomic two-card transaction. The existing per-card rollback is attempted when
the resized BAR is not assigned correctly.

Without `rebar.dual=1`, normal first-card selection remains the default. Installing
the package does not replace an already-enabled boot hook: `--reinstall` below
is required. Live resizing is unsupported for this preview; do not run the boot
payload manually without `ARC_REBAR_DRYRUN=1`, especially while guests use VFIO.

## 1. Read-only preflight, before installation

Download the `.deb` and `SHA256SUMS` from the
[dual-A310 prerelease](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/tag/dual-a310-preview-2026.11.09.1).
Use a fresh directory. GitHub changes `~` to `.` in uploaded asset names;
these download commands save the original Debian-version filenames expected by
`SHA256SUMS` and the commands below. If downloading through the browser instead,
rename `arc-rebar_1.0.6.dual-a3101_all.deb` to
`arc-rebar_1.0.6~dual-a3101_all.deb` first.
Extracting the package does not run package scripts:

```bash
release=https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/download/dual-a310-preview-2026.11.09.1
curl -fL "$release/arc-rebar_1.0.6.dual-a3101_all.deb" -o 'arc-rebar_1.0.6~dual-a3101_all.deb'
curl -fL "$release/SHA256SUMS" -o SHA256SUMS
sha256sum -c --ignore-missing SHA256SUMS
dpkg-deb -x arc-rebar_1.0.6~dual-a3101_all.deb ./preview
sudo env ARC_REBAR_DRYRUN=1 ARC_REBAR_EXPERIMENTAL_DUAL=1 \
  sh ./preview/usr/share/arc-rebar/scripts/init-premount/arc-rebar
```

Expected: two `DUAL-CHECK` records and `PLAN: act experimental-dual` (or `none`
if both are already at 4 GiB). Each record contains GPU, root port, upstream
switch, host bus, current/target size fields, and memory-window start/length.
Field 12 means 4 GiB; field 8 means 256 MiB. A `skip` is a refusal: stop and
share the reason, rather than bypassing it. Actual writes also require the
kernel token; the environment-only opt-in cannot enable them.

The original report mentions four cards while its diagnostics show two A310
endpoints. Please confirm the current host count before testing. The preview
deliberately refuses if more than two eligible Intel GPUs are visible.

## 2. Prepare a boot-only test

This procedure assumes an existing working initramfs-tools/GRUB installation.
Other bootloader arrangements need separate review. Have local or remote console
access, current VM/host backups, a maintenance window and a known-working boot
entry. Shut down the affected guests and disable their automatic start for the
test so both host BARs can be inspected before passing the cards to a guest.
Read the project's [disclaimer](../DISCLAIMER.md) and [licence](../LICENSE).

Keep a copy of the stable
[v1.0.5 package](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/download/v1.0.5/arc-rebar_1.0.5_all.deb).
Save the current boot files in a private directory before refreshing the hook:

```bash
backupdir=$(sudo mktemp -d /root/arc-rebar-before-dual.XXXXXX)
sudo cp -a /etc/initramfs-tools /etc/default/grub /boot/grub/grub.cfg \
  "/boot/initrd.img-$(uname -r)" "$backupdir/"
printf 'Private boot backup: %s\n' "$backupdir"
sudo apt install ./arc-rebar_1.0.6~dual-a3101_all.deb
sudo arc-rebar install --reinstall
```

Stop if installation, backup, rebuild or inspection fails. The installer retains
its own transactional recovery as well. At this point the refreshed hook still
uses default single-card behavior.

On the next boot, edit the GRUB entry **for that boot only**: retain `pci=realloc`
and append **`rebar.dual=1`** to the kernel's Linux line. Do not make this token
persistent yet. `norebar` disables the entire hook if recovery is needed.

## 3. Verify both cards before starting the guest

On the reported topology, run these read-only checks (adjust PCI addresses only
if enumeration changed):

```bash
cat /proc/cmdline
sudo dmesg | grep 'arc-rebar:'
sudo lspci -Dvv -s 0000:84:00.0
sudo lspci -Dvv -s 0000:88:00.0
sudo arc-rebar verify
```

Require the final `PLAN: done experimental-dual ... bar2_each=4096M`, and **both**
GPU `Region 2` and ReBAR current sizes at 4 GiB. A single per-card `done`, the
diagnostic summary alone, or full VRAM reported by a guest driver is insufficient.
The verifier checks all qualifying GPUs; WARN means inconclusive PCIe health,
not confirmation that a warning is harmless. Preserve the full relevant results.

Then confirm VFIO bindings, start the guest, check both guest BAR2 windows and
test an ordinary workload on each card, then both together. Record any resets,
hangs or new AER/PCIe errors on host and guest. Do not claim a performance gain
without a controlled comparison. Once the first test succeeds, repeat a reboot
with the one-time token before considering persistence.

Please share the exact package version, current GPU count, kernel/bootloader,
both host BAR records, final boot verdict, guest BAR results and workload/reboot
observations in issue #3. Redact hostnames, addresses, serials and other private
details from logs before posting. Do not submit guest or host secrets.

## Recovery and acceptance

If boot or GPU use fails, reboot with `norebar` and use console access or the
known-working boot entry as needed. Removing the one-time `rebar.dual=1` token
returns this preview to default first-card behavior on the next boot. To restore
the stable package **and its installed boot hook**:

```bash
sudo apt install --allow-downgrades ./arc-rebar_1.0.5_all.deb
sudo arc-rebar install --reinstall
```

Do not reboot following a failed installer recovery; restore from the saved
boot files/known-working entry first. Keep backups until stable boot and GPU use
are confirmed. Software tests use only fake PCI trees; they do not establish
hardware safety, VFIO guest behavior or success on other systems. Issue #3 stays
open pending confirmation, and broader model/count support needs separate work.
