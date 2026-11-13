# INSTALL — arc-rebar, step by step

**Applies to:** Debian 12/13, Ubuntu 22.04 or newer and other `initramfs-tools` systems
(Mint, Proxmox); Arch, CachyOS and Manjaro (`mkinitcpio`); Fedora,
RHEL, Rocky, AlmaLinux and openSUSE (`dracut`). Kernel 6.12 or newer recommended. You need
`sudo`. The steps below show Debian/Ubuntu; [Arch](#arch-linux--cachyos-mkinitcpio) and
[Fedora/RHEL/openSUSE](#fedora--rhel--opensuse-dracut) have their own short sections, and
every `arc-rebar` command works the same on all of them.

**Do this over SSH if you can.** The optional live test turns the local display
off for about 10 seconds; if the machine were to hang, you want a second way in.

There are two paths. **Path A** is one reboot. **Path B** proves the fix live
before enabling it at boot, at the cost of a second reboot — use it on a board
nobody has tried this on.

---

## 0. Prerequisites (both paths)

```
sudo apt update
sudo apt install pciutils initramfs-tools
uname -r
```
Review the package manager's proposed changes first. **Ubuntu releases that use dracut**
(newer releases may by default): the `.deb` needs `initramfs-tools`, so apt will offer to
replace dracut with it. Installing `initramfs-tools` replaces the dracut frontend and rebuilds
boot images; do not switch a working
production system's backend merely to bypass an installer refusal. The installer
checks the selected updater and refuses incompatible or unidentifiable backends
before hardware probing or boot-file changes. It does not convert backends.

You should see a kernel version. If it is below `6.12`, the fix may still work
but the `xe` driver's ReBAR support is younger than that; proceed with Path B.

## 1. Get the tool (both paths)

**From the package.** Download the package for your system and the checksum files from the
[latest release](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/latest):
```
wget https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/latest/download/arc-rebar_1.0.8_all.deb
wget https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/latest/download/SHA256SUMS
wget https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/latest/download/SHA256SUMS.asc
```
```
sha256sum -c --ignore-missing SHA256SUMS         # must print: arc-rebar_1.0.8_all.deb: OK
```
**Check that it really came from us.** A checksum only proves the file wasn't damaged; these
prove it was built and signed by this project, not by an imitation:
```
wget https://raw.githubusercontent.com/RodBurlamaqui/Intel-ARC-Rebar/v1.0.8/docs/signing-key.asc
gpg --import signing-key.asc                      # once
gpg --verify SHA256SUMS.asc SHA256SUMS            # must say "Good signature"; fingerprint in SECURITY.md
gh attestation verify arc-rebar_1.0.8_all.deb -R RodBurlamaqui/Intel-ARC-Rebar   # needs the GitHub CLI
```
If any check fails, **don't install the file**; download it again from the Releases page.

Then install it:
```
sudo apt install ./arc-rebar_1.0.8_all.deb
```
You should see, at the end:
```
arc-rebar installed. Nothing is enabled yet.
  1. sudo arc-rebar diagnose    # do you have the problem; is the fix safe here
  2. sudo arc-rebar live-test   # optional: prove it without rebooting
  3. sudo arc-rebar install     # enable at boot (checks + licence/disclaimer acceptance)
```
Installing the package changes nothing on your system yet. Every `arc-rebar install` first
checks that its files are the official, unmodified release; a modified copy is refused.
`sudo arc-rebar integrity` checks an installed copy at any time.

**From source instead** (the signed release tag; every install checks the files against your
copy's signed file list):
```
git clone --branch v1.0.8 https://github.com/RodBurlamaqui/Intel-ARC-Rebar.git
cd Intel-ARC-Rebar
```
Then everywhere below, replace `sudo arc-rebar <command>` with `sudo ./<command>.sh`.

## 2. PRE-CHECK: diagnose (both paths)

(For a deeper read-only look first — which link is real, which BAR pins the
window, the real allocation ceiling — see [diag/INSTALL.md](diag/INSTALL.md).)

```
sudo arc-rebar diagnose
```
Read the **last line**. It is one of these:

| Last line starts with | Meaning | Do |
|---|---|---|
| `YES: pinned window, all safety checks pass` | you have the problem and the fix is safe here | continue |
| `BAR already at full size` | you do not have the problem | stop — nothing to do |
| `NOT SAFE / NOT APPLICABLE here: skip reason=...` | a safety check refused | stop — read the reason in the README table. Do not force it |
| `none found. arc-rebar does not apply.` | no supported GPU | stop |

---

## Path A — one reboot

### A3. Install and enable
```
sudo arc-rebar install
```
It prints PRE-CHECKS, then a PLAN line, then the licence and disclaimer. Type
`ACCEPT` and press Enter. You should then see:
```
== INSTALL ==
GRUB updated
initramfs rebuilt

== POST-CHECKS ==
  [ok] /etc/initramfs-tools/hooks/arc-rebar
  [ok] /etc/initramfs-tools/scripts/init-premount/arc-rebar
  [ok] pci=realloc in /etc/default/grub
  [ok] pci=realloc in grub.cfg
  [ok] boot script inside /boot/initrd.img-<kernel>
  [ok] setpci inside initramfs
  [ok] libpci inside initramfs
  all post-checks passed

Installed. Next:   sudo reboot   then   sudo arc-rebar verify
```
If any line says `[FAIL]`, the installer attempts to restore the state from before
this installation attempt, including an existing working installation during
`--reinstall`. Check the recovery result before rebooting; if restoration fails,
follow [failure recovery](#debianubuntu-installer-failure-recovery) below.

### A4. Reboot
```
sudo reboot
```

### A5. POST-CHECK: verify
```
sudo arc-rebar verify
```
A clean check ends with `RESULT: PASS`. `RESULT: WARN` (exit 2) means PCIe
health remains inconclusive; it is not a clean pass. The important
lines:
```
  [ok]   boot verdict: done gpu=0000:XX:00.0 bar2=16384M
  [ok]   0000:XX:00.0 BAR2 = 16384 MiB (size field 14 = card maximum)
  [ok]   xe last probe VISIBLE VRAM: 0x..., 0x0000000400000000
```
(`16384M` is for a 12 GB or 16 GB card. An 8 GB card shows `8192M`, a 6 GB card `8192M`.)

To inspect the boot script's messages directly:

```bash
sudo dmesg | grep -F 'arc-rebar:'
```

`journalctl -k -b` can omit userspace messages written to `/dev/kmsg`, including
the boot script's verdict. A missing journal match alone does not mean the script
did not run. Use `dmesg` and the verifier; if the ring buffer has wrapped, gather
the evidence after another controlled boot.

**Done.** Go to "If something is wrong" only if you did not get `PASS`.

---

## Path B — prove it live first (two reboots)

### B3. Add pci=realloc only
```
sudo arc-rebar prepare
```
Then, as a separate step:
```
sudo reboot
```
After the reboot, confirm:
```
grep -o pci=realloc /proc/cmdline
```
You must see `pci=realloc`. If you see nothing, `prepare` could not edit your boot
loader. Add `pci=realloc` by hand: Fedora/RHEL `sudo grubby --update-kernel=ALL --args=pci=realloc`;
otherwise add it to `GRUB_CMDLINE_LINUX_DEFAULT` in `/etc/default/grub` and regenerate the menu
(`sudo update-grub` on Debian/Ubuntu, `sudo grub-mkconfig -o /boot/grub/grub.cfg` on Arch,
`sudo grub2-mkconfig -o /boot/grub2/grub.cfg` on openSUSE). Reboot.

### B4. Live test (over SSH, work saved)
```
sudo arc-rebar live-test
```
It shows the dry run, then asks `Run for real now? [y/N]`. Type `y`. The local
display goes dark. About 10 seconds later you should see:
```
arc-rebar: PLAN: done gpu=0000:XX:00.0 bar2=16384M
	Region 2: Memory at ... (64-bit, prefetchable) [size=16G]
		BAR 2: current size: 16GB, supported: ...
```
and your display comes back.

- If you see `PLAN: rolled-back ...`: the BAR could not be placed and the tool
  restored the old size. The machine is fine. Do not install. See "If something is wrong".
- If the machine hangs: power-cycle it. Nothing persistent changed. Do not install.

### B5. Install, reboot, verify
Now do **A3**, **A4**, **A5** above.

---

## Arch Linux / CachyOS (mkinitcpio)

The same arc-rebar, packaged for Arch, CachyOS and Manjaro. Check the download
as in [step 1](#1-get-the-tool-both-paths), then:

```
sudo pacman -U ./arc-rebar-1.0.8-1-any.pkg.tar.zst
sudo arc-rebar diagnose
sudo arc-rebar install
sudo reboot
sudo arc-rebar verify
```
If pacman asks about the signing key (when the `.sig` file sits next to the package), add it
once: `sudo pacman-key --add signing-key.asc && sudo pacman-key --lsign-key C3CFCBF8EE592C27BCBE1E498D8ED73D0C2DE44B`.

`arc-rebar install` hands over to the mkinitcpio installer, which does the same integrity
check, safety checks and licence/disclaimer acceptance, then:

- installs the boot script to `/usr/lib/arc-rebar/arc-rebar-boot`
- installs `/etc/initcpio/install/arc-rebar` (build hook) and
  `/etc/initcpio/hooks/arc-rebar` (runtime hook)
- adds `arc-rebar` to `HOOKS` in `/etc/mkinitcpio.conf`, immediately **before
  `kms`**, and leaves the rest of the array alone
- adds `pci=realloc` to `/etc/default/grub` and runs `grub-mkconfig` if it is not
  there yet (any other bootloader: add it by hand)
- backs up managed configuration/hooks, runs `mkinitcpio -P`, and post-checks the image for
  the boot script, the hook, `setpci` and `tr`

Two mkinitcpio details: `arc-rebar` stays after `udev` and before `kms`; and mkinitcpio's
busybox has no `tr`, so the build hook also copies coreutils' `tr` into the image.

Uninstall with `sudo arc-rebar uninstall` (removes both hooks, drops `arc-rebar` from
`HOOKS`, rebuilds the initramfs), then `sudo pacman -R arc-rebar`.
Reinstall with `sudo arc-rebar install --reinstall`.
See [installer safeguards](#arch-installer-safeguards) for rollback behaviour.

---

## Fedora / RHEL / openSUSE (dracut)

The same arc-rebar, packaged for Fedora, RHEL, Rocky, AlmaLinux and openSUSE. Check the
download as in [step 1](#1-get-the-tool-both-paths), then:

```
sudo dnf install ./arc-rebar-1.0.8-1.noarch.rpm      # openSUSE: sudo zypper install ./arc-rebar-1.0.8-1.noarch.rpm
sudo arc-rebar diagnose
sudo arc-rebar install
sudo reboot
sudo arc-rebar verify
```
On openSUSE, zypper may report the package as unsigned: our signature is the separate `.sig`
and `SHA256SUMS.asc` files you checked in step 1. After checking them, install with
`sudo zypper install --allow-unsigned-rpm ./arc-rebar-1.0.8-1.noarch.rpm`.
`arc-rebar install` hands over to the dracut installer, which does the same integrity check,
safety checks and licence/disclaimer acceptance, then:

- checks the boot images are at `/boot/initramfs-<kernel>.img` (Fedora/RHEL) or
  `/boot/initrd-<kernel>` (openSUSE); other layouts, including unified kernel images, are
  refused before anything changes
- backs up the dracut configuration, boot entries, GRUB configuration and **every boot image**
- installs the dracut module to `/usr/lib/dracut/modules.d/90arc-rebar` and enables it in
  `/etc/dracut.conf.d/90-arc-rebar.conf`; it runs before udev loads the graphics driver
- adds `pci=realloc` with `grubby` (Fedora/RHEL) or `/etc/default/grub` + `grub2-mkconfig`
  (openSUSE), then rebuilds all boot images with `dracut --regenerate-all`
- post-checks the running kernel's image for the boot script, the hook and `setpci`

If anything fails, including a dropped SSH session, it restores the settings, rebuilds the
images without arc-rebar and puts the exact previous images back.

Uninstall with `sudo arc-rebar uninstall`, then `sudo dnf remove arc-rebar` (or `zypper remove`).
Removing the RPM also removes an enabled boot hook. To drop `pci=realloc`:
`sudo grubby --update-kernel=ALL --remove-args=pci=realloc`.

---

## If something is wrong

**The machine does not boot, or boots with no display, after install.**
At the GRUB menu press `e`, find the line starting with `linux`, add a space and
`norebar` at its end, press `Ctrl-X` (or `F10`) to boot. You are now on the old
small BAR with the tool disabled for this boot. Then either uninstall (below) or
report the output of `sudo arc-rebar diagnose`.

**`verify` says `boot verdict: rolled-back`.**
Your MMIO window is too small for the full BAR. Try a smaller one: add
`rebar.size=13` (8 GB) or `rebar.size=12` (4 GB) to the kernel command line (the same
way as `pci=realloc` above), reboot, verify again.

**`verify` says `boot verdict: skip reason=...`.**
A safety check refused at boot. The reason maps to the table in README.md.

**`verify` shows `RESULT: FAIL` on DevSta or AER.**
PCIe error evidence remains; its cause is not established by verification.
Preserve diagnostics and investigate before adopting the workaround.

**`verify` shows `RESULT: WARN` for latched DevSta bits.**
BAR allocation can succeed while previously latched correctable/Unsupported
Request bits remain. They are not automatically harmless or caused by ReBAR.
Verification never clears them or writes PCI registers. Exit 2 means unresolved
PCIe status, not successful workload validation. See the evidence limits in
[README.md](README.md#pcie-status).

**`dmesg` still shows `Small BAR device`.**
Normal. That is the driver's *first* probe, before the fix runs at boot. Judge by
`verify`, not by that line.

**`install` says `already installed`.**
Use `sudo arc-rebar install --reinstall` to refresh the boot script.

## Uninstall

**Any system:** `sudo arc-rebar uninstall` removes the boot hook and rebuilds the boot images.
Then, if you like, remove the package: `sudo pacman -R arc-rebar` (Arch) or
`sudo dnf remove arc-rebar` / `sudo zypper remove arc-rebar` (Fedora/RHEL/openSUSE).

**.deb:**
```
sudo apt purge arc-rebar      # removes the tool AND the boot hook (only if the .deb installed it), rebuilds the initramfs
```
(`apt remove` removes only the tool and deliberately leaves the boot hook active.)

Before removing the hook, purge saves copies of the package-installed hooks, their
origin marker, the GRUB files and the existing initramfs images. Purge rebuilds all kernel images and checks that the runtime script is gone.
A missing tool, failed rebuild, failed archive inspection or stale image returns
failure and attempts to restore the saved boot files. Source-owned/unknown hooks
are preserved. Partial package-owned hook installations are also cleaned up.

On purge failure, diagnostics/snapshots remain under
`/var/lib/arc-rebar/purge-transaction`. Fix the reported storage or tool problem,
then retry `sudo dpkg --purge arc-rebar`; the retained package maintainer script
first recovers an interrupted transaction. Use this retry even though the
package's ordinary commands may already have been removed. If recovery fails,
**do not reboot** until the boot files have been repaired. A retained purge
transaction blocks the source installer to prevent it overwriting recovery state.

This is file-level recovery, not an atomic power-loss guarantee. Keep enough space
for copies of all `/boot/initrd.img-*` files, including existing backups. Managed
file symlinks/whitespace paths are refused, and concurrent manual boot updates or
third-party hook side effects outside the snapshot are not covered. A shared lock
file and original escape-hatch backups remain. See the
[package lifecycle test record](docs/DEBIAN-PACKAGE-TESTS.md).

These package-purge safeguards are included since v1.0.4.

**From source** (any system; it picks the right uninstaller):
```
sudo ./uninstall.sh
```

All of them leave `pci=realloc` on the kernel command line; it is harmless. To remove it:
```
sudo cp /etc/default/grub.arc-rebar.bak /etc/default/grub && sudo update-grub   # Debian/Ubuntu
sudo grubby --update-kernel=ALL --remove-args=pci=realloc                       # Fedora/RHEL
```
On Arch and openSUSE, delete `pci=realloc` from `/etc/default/grub`, then regenerate the menu
(`sudo grub-mkconfig -o /boot/grub/grub.cfg`, or `sudo grub2-mkconfig -o /boot/grub2/grub.cfg`).

### Debian/Ubuntu installer failure recovery

The source installer snapshots the previous hooks, origin marker, GRUB defaults,
GRUB menu, running kernel's initramfs, and corresponding backup files before
mutation. A failed command or caught INT/TERM/HUP restores those files (including
an existing installation during `--reinstall`) and returns failure. Rebuild errors
are fatal even if an old image passes content checks. Only the running kernel is
rebuilt, explicitly with `update-initramfs -u -k`.

Diagnostics and snapshots remain in `/var/lib/arc-rebar/install-transaction` on
failure. A new installation refuses to overwrite that journal. After checking the
error and resolving any storage problem, run:

```bash
sudo arc-rebar install --recover     # package install; from a source checkout: sudo ./install.sh --recover
```

Recovery needs no GPU probe and can be retried if restoration fails. Do not reboot
if recovery reports failure. Successful recovery removes the journal; copy its
logs first if needed. Original `.arc-rebar.bak` escape-hatch backups are preserved.
A lock serializes this installer, but does not lock package managers or other boot
configuration tools: do not run them concurrently. Required boot files and hook
directories must already exist; symlink file destinations and nonliteral or
ambiguous GRUB default assignments are refused before installation.

This is file-level recovery, not an atomic boot transaction or a guarantee against
power loss, disk failure, or arbitrary third-party update hooks. SIGKILL/power loss
cannot trigger immediate rollback: recover before rebooting, using rescue media if
necessary. Custom update hooks may modify files outside the snapshot; UKIs and
nonstandard boot layouts are not covered. `--live-test` hardware effects and the
separate uninstaller are outside this transaction's scope.

Validation before release: run the mocked suite (`python3 -m unittest discover -s
 tests -v`, on one line), then validate normal installation, warm/cold boot,
reinstallation, `norebar` recovery, and removal on disposable Debian/Ubuntu systems
with the affected Intel Arc hardware, checking BAR allocation, driver binding and
a real workload. Test real GRUB/initramfs-tools integration in a snapshot VM first.
Mocked tests do not establish bootability or hardware correctness. This section covers the
Debian/Ubuntu installer; the Arch and dracut installers have their own sections.

See [VM installer validation](docs/INSTALLER-VM-TESTS.md) for the completed
software checks, their limits, and the remaining release gates.

### Arch installer safeguards

The source-tree Arch installer and uninstaller retain root-only backups of the
managed configuration and hook files under `/var/lib/arc-rebar/backups/change.*`.
Keep `arch-transaction.sh` alongside the scripts when running from a checkout.
A failed file installation, GRUB generation, initramfs build, or post-check
returns failure and restores the previous managed files, including an existing
installation during `--reinstall`. It then attempts to rebuild the restored
configuration. Build/recovery output is kept in that backup directory.

If recovery also fails, the scripts explicitly say **do not reboot**: inspect
the saved logs and repair the boot images first. These are configuration/hook
backups, not copies of the boot images or a guarantee of recovery after power
loss, disk failure, or forced termination. Do not run concurrent installers or
package/kernel updates while changing these hooks.

Automatic editing requires one simple single-line `HOOKS=(...)` assignment,
with `udev` before `kms`; quoted hook names and trailing whitespace are accepted.
Reinstallation moves `arc-rebar` before `kms` if needed. Config drop-ins and
systemd-based initramfs configurations are refused rather than silently editing
an ineffective setting. Managed symlinks are also refused.

Preset-specific config or output paths, UKIs and non-GRUB boot paths are not edited
automatically; the image post-check scans the conventional paths.

Hardware-free regression checks from the repository root:

```bash
python3 -m unittest discover -s tests -v
bash -n install-arch.sh uninstall-arch.sh arch-transaction.sh
```

Real moduleless mkinitcpio builds, inert-hook execution and rebuild/recovery tests
also passed in an isolated userspace filesystem. See the
[Arch userspace test record](docs/ARCH-USERSPACE-TESTS.md) for exact scope and
remaining boot/hardware validation; those tests do not replace a real Arch boot.

Configuration/preset reference:
https://man.archlinux.org/man/mkinitcpio.conf.5.en and
https://man.archlinux.org/man/mkinitcpio.8.en
