# v1.0.6 Experimental — Dual GPU Support for Arch/CachyOS

This is a separate **source preview**, using the same guarded dual-GPU boot
payload as the Debian/Ubuntu preview. It requires mkinitcpio and
`--experimental-arch`. The published v1.0.5 Debian package/source release does
not contain the Arch installer. This is not an Arch binary package or an AUR
release. Physical Arch/CachyOS dual-GPU validation is **pending**.

## Eligible test setup

Exactly two non-console Intel A310s (`8086:56a6`), each with a maximum 4 GiB BAR2,
on distinct root ports. Each root must contain only that card's expected Intel
switch/GPU/audio hierarchy. GPUs must be unbound or using `vfio-pci`; host-bound
`xe`/`i915` devices, other GPU models/counts, shared roots and external switches
are refused. The generic release label does not widen this hardware scope.
`rebar.dev` and `rebar.size` conflict with dual mode.

The installer requires the existing supported mkinitcpio busybox/udev/kms layout
and conventional presets/images. Systemd initramfs, UKIs, configuration drop-ins,
custom image layouts and non-GRUB procedures are outside this preview. The
installer's checks remain in force. Do not bypass a refusal.

## Download and read-only preflight

Use a fresh directory. Download the source and its checksum file from the
[Arch dual-GPU preview](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/tag/dual-gpu-arch-preview-2026.11.09.1):

```bash
release=https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/download/dual-gpu-arch-preview-2026.11.09.1
curl -fL "$release/arc-rebar-dual-gpu-arch-preview-2026.11.09.1.tar.gz" -O
curl -fL "$release/SHA256SUMS" -O
sha256sum -c SHA256SUMS
tar -xzf arc-rebar-dual-gpu-arch-preview-2026.11.09.1.tar.gz
cd arc-rebar-dual-gpu-arch-preview-2026.11.09.1
sudo env ARC_REBAR_DRYRUN=1 ARC_REBAR_EXPERIMENTAL_DUAL=1 \
  ARC_REBAR_ASSUME_REALLOC=1 sh ./scripts/init-premount/arc-rebar
```

Require two `DUAL-CHECK` records and `PLAN: act experimental-dual`, or `none` if
both BARs are already at 4 GiB. Size field 8 means 256 MiB; field 12 means 4 GiB.
The assumption flag only permits this read-only check before `pci=realloc` is
active. Runtime still requires that kernel option. No PCI configuration writes,
driver unbinding or removal/rescan occur during this preflight.

## Back up and install

Have console/recovery access, current host/VM backups, a known-working boot entry
and a maintenance window. Stop affected guests and disable their automatic start
for the test. Read [INSTALL.md](../INSTALL.md), [DISCLAIMER.md](../DISCLAIMER.md)
and [LICENSE](../LICENSE). Keep the prior working source tree for restoration.

Back up the actual boot images as well as configuration; the Arch installer's
transaction restores managed configuration/hooks and rebuilds images, rather
than saving every original boot image. For a conventional GRUB setup:

```bash
backupdir=$(sudo mktemp -d /root/arc-rebar-before-dual-arch.XXXXXX)
sudo tar -czf "$backupdir/boot-config.tar.gz" -C / \
  boot etc/mkinitcpio.conf etc/mkinitcpio.d etc/default/grub
sudo gzip -t "$backupdir/boot-config.tar.gz"
if [ -d /etc/initcpio ]; then sudo cp -a /etc/initcpio "$backupdir/"; fi
if [ -d /usr/lib/arc-rebar ]; then sudo cp -a /usr/lib/arc-rebar "$backupdir/"; fi
printf 'Private boot backup: %s\n' "$backupdir"
sudo env ARC_REBAR_EXPERIMENTAL_DUAL=1 ./install.sh --experimental-arch
```

For an existing installation, use the same command with `--reinstall` appended
to refresh the boot payload and image. The environment opt-in makes the
installer's read-only preflight check both GPUs. Installation accepts the project
licence/disclaimer through the normal prompt; `--experimental-arch` is required
even for reinstall. Neither opting in nor installing enables live PCI operations.
Do not use `--live-test`: the Arch installer refuses it in dual mode.

Stop on any backup, installation, rebuild or post-check failure. If recovery
rebuilding fails, **do not reboot**; repair or restore a known-working image first.

## One-boot test and verification

Edit the next GRUB entry for **that boot only**: retain `pci=realloc` and append
`rebar.dual=1` to the kernel's Linux line. Do not make dual mode persistent yet.
The payload checks both cards and shared MMIO allocations before changing either,
rechecks after each rescan, and stops on failures or changed topology. A failure
on the second card can leave the first resized; this is not an atomic operation.

Before starting the guests, collect:

```bash
cat /proc/cmdline
sudo dmesg | grep 'arc-rebar:'
sudo lspci -Dnn
sudo bash ./verify.sh
```

Run `sudo lspci -Dvv -s ADDRESS` for each GPU using its address from the listing.
Require **both** `Region 2` and current ReBAR sizes at 4 GiB, plus the final
`PLAN: done experimental-dual ... bar2_each=4096M`. A single per-card success or
a guest VRAM total alone is insufficient. Preserve any verifier WARN/FAIL;
WARN means inconclusive PCIe health, with age/cause unresolved.

Then verify VFIO bindings, start the guests, check both guest BAR windows, and
test a normal workload on each card and together. Repeat a boot with the one-time
token after the first success. Record resets, hangs and new PCIe/AER errors on
host and guest. Share the source tag, card count/models, board/BIOS, kernel,
mkinitcpio/HOOKS setup, both host/guest BAR results and workload/reboot observations
in [#3](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/3) and
[#15](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/issues/15). Redact private
details before posting. Do not run the boot payload manually on live VFIO guests.

## Recovery and evidence limits

At GRUB, `norebar` disables all runtime PCI actions. Boot without `rebar.dual=1`
to return this preview to default first-GPU behavior. This cannot repair an
invalid boot image; use the saved image/known-working entry when needed.
Restore the prior source with `sudo ./install.sh --experimental-arch --reinstall`,
or remove the hook with `sudo ./uninstall-arch.sh`; require successful image
rebuild and inspection before rebooting. Keep backups until stable operation
is confirmed.

Software tests use fake PCI devices. The real mkinitcpio image experiment uses
`-k none`, isolated boot files, an inert installation preflight, and the exact
real dual-GPU payload with read-only fake-PCI runtime checks. It validates image
contents, dependencies and hook execution, installation/reinstallation/removal
plumbing. It does **not** validate a physical Arch kernel boot, real GRUB
generation, VFIO guest operation or GPU stability. Hardware acceptance remains
pending; broader counts/models require separate work.
