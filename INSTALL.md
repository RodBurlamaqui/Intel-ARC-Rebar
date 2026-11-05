# INSTALL — arc-rebar, step by step

**Applies to:** Debian 12/13, Ubuntu 22.04 or newer, or any distro using
an active `initramfs-tools` backend. Kernel 6.12 or newer recommended. You need
`sudo`. A distribution version or the presence of `/etc/initramfs-tools` alone
does not establish compatibility: some systems provide a dracut-backed
`update-initramfs` command instead.
Draft Arch Linux / CachyOS (mkinitcpio) support is described under
[Arch Linux / CachyOS](#arch-linux--cachyos-mkinitcpio) below.

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
Review the package manager's proposed changes first. Installing `initramfs-tools`
can replace a dracut frontend and rebuild boot images; do not switch a working
production system's backend merely to bypass an installer refusal. The installer
checks the selected updater and refuses incompatible or unidentifiable backends
before hardware probing or boot-file changes. It does not convert backends.

You should see a kernel version. If it is below `6.12`, the fix may still work
but the `xe` driver's ReBAR support is younger than that; proceed with Path B.

## 1. Get the tool (both paths)

**From the .deb.** Download it and its checksum file:
```
wget https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/latest/download/arc-rebar_1.0.3_all.deb
wget https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases/latest/download/SHA256SUMS
```
```
sha256sum -c --ignore-missing SHA256SUMS         # must print: arc-rebar_1.0.3_all.deb: OK
```
Then install it:
```
sudo apt install ./arc-rebar_1.0.3_all.deb
```
You should see, at the end:
```
arc-rebar installed. Nothing is enabled yet.
  1. sudo arc-rebar diagnose    # do you have the problem; is the fix safe here
  2. sudo arc-rebar live-test   # optional: prove it without rebooting
  3. sudo arc-rebar install     # enable at boot (checks + licence/disclaimer acceptance)
```
Installing the package changes nothing on your system yet.

**From the tarball instead:**
```
tar xzf arc-rebar-1.0.3.tar.gz
cd arc-rebar
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
backup: /boot/initrd.img-<kernel>.arc-rebar.bak
GRUB: added pci=realloc (backup: /etc/default/grub.arc-rebar.bak)
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
You should see every line `[ok]` and, at the end, `RESULT: PASS`. The important
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
You must see `pci=realloc`. If you see nothing, `prepare` could not edit GRUB;
add `pci=realloc` to `GRUB_CMDLINE_LINUX_DEFAULT` in `/etc/default/grub` by hand,
run `sudo update-grub`, reboot.

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

The boot script is the same file; only the initramfs plumbing differs.
`install.sh` detects `mkinitcpio` and hands over to `install-arch.sh`, so the
flow is still diagnose → (optional) live-test → install → reboot → verify:

```
sudo pacman -S --needed pciutils mkinitcpio
sudo ./diagnose.sh
sudo ./install.sh          # on Arch this runs install-arch.sh
sudo reboot
sudo ./verify.sh
```

`install-arch.sh` does the same safety checks and the same licence/disclaimer
acceptance, then:

- installs the boot script to `/usr/lib/arc-rebar/arc-rebar-boot`
- installs `/etc/initcpio/install/arc-rebar` (build hook) and
  `/etc/initcpio/hooks/arc-rebar` (runtime hook)
- adds `arc-rebar` to `HOOKS` in `/etc/mkinitcpio.conf`, immediately **before
  `kms`**, and leaves the rest of the array alone
- adds `pci=realloc` to `/etc/default/grub` and runs `grub-mkconfig` if it is not
  there yet (any other bootloader: add it by hand)
- backs up managed configuration/hooks, runs `mkinitcpio -P`, and post-checks the image for the boot script, the hook,
  `setpci` and `tr`

Two things that are mkinitcpio-specific:

- **`arc-rebar` must stay before `kms`.** That hook is what loads `i915`/`xe`;
  running after it means the driver has already claimed the card.
- **mkinitcpio's bundled busybox has no `tr` applet**, which the boot script uses
  to split the device path. The build hook therefore also copies coreutils' `tr`
  into the image. Without it the script would log
  `skip reason=unexpected-topology` and silently do nothing.

GRUB on Arch has no `update-grub`; regenerate with
`sudo grub-mkconfig -o /boot/grub/grub.cfg`. Uninstall with
`sudo ./uninstall-arch.sh` (removes both hooks, drops `arc-rebar` from `HOOKS`,
rebuilds the initramfs). See [installer safeguards](#arch-installer-safeguards-pending-hardware-validation) for rollback behavior and validation limits.

---

## If something is wrong

**The machine does not boot, or boots with no display, after install.**
At the GRUB menu press `e`, find the line starting with `linux`, add a space and
`norebar` at its end, press `Ctrl-X` (or `F10`) to boot. You are now on the old
small BAR with the tool disabled for this boot. Then either uninstall (below) or
report the output of `sudo arc-rebar diagnose`.

**`verify` says `boot verdict: rolled-back`.**
Your MMIO window is too small for the full BAR. Try a smaller one: add
`rebar.size=13` (8 GB) or `rebar.size=12` (4 GB) to the kernel command line in
`/etc/default/grub`, `sudo update-grub`, reboot, verify again.

**`verify` says `boot verdict: skip reason=...`.**
A safety check refused at boot. The reason maps to the table in README.md.

**`verify` shows `RESULT: FAIL` on DevSta or AER.**
Your GPU is reporting PCIe errors. That is not caused by this tool but you
should not ignore it. Uninstall and investigate the errors first.

**`dmesg` still shows `Small BAR device`.**
Normal. That is the driver's *first* probe, before the fix runs at boot. Judge by
`verify`, not by that line.

**`install` says `already installed`.**
Use `sudo arc-rebar install --reinstall` to refresh the boot script.

## Uninstall

**.deb:**
```
sudo apt purge arc-rebar      # removes the tool AND the boot hook (only if the .deb installed it), rebuilds the initramfs
```
(`apt remove` removes only the tool and deliberately leaves the boot hook active.)

**Tarball:**
```
sudo ./uninstall.sh
```

**Arch / CachyOS:**
```
sudo ./uninstall-arch.sh
```

All leave `pci=realloc` in GRUB; it is harmless. To remove it:
```
sudo cp /etc/default/grub.arc-rebar.bak /etc/default/grub
sudo update-grub          # Arch: sudo grub-mkconfig -o /boot/grub/grub.cfg
```

### Debian/Ubuntu installer failure recovery

The source installer snapshots the previous hooks, origin marker, GRUB defaults,
GRUB menu, running kernel's initramfs, and corresponding backup files before
mutation. A failed command or caught INT/TERM/HUP restores those files (including
an existing installation during `--reinstall`) and returns failure. Rebuild errors
are fatal even if an old image passes content checks. Only the running kernel is
rebuilt, explicitly with `update-initramfs -u -k`.

Diagnostics and snapshots remain in `/var/lib/arc-rebar/install-transaction` on
failure. A new installation refuses to overwrite that journal. After checking the
error and resolving any storage problem, run from the same source checkout:

```bash
sudo ./install.sh --recover
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
Mocked tests do not establish bootability or hardware correctness. This change is
independent of the pending Arch/mkinitcpio work.

See [VM installer validation](docs/INSTALLER-VM-TESTS.md) for the completed
software checks, their limits, and the remaining release gates.

### Arch installer safeguards (pending hardware validation)

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

Before merging this Arch port, validate installation, an actual reboot with
BAR allocation and driver binding, reinstallation, and removal on the
contributor's CachyOS/A380 setup. Confirm the hook runs at the intended time;
image membership alone does not prove runtime ordering. Preset-specific config
or output paths, UKIs, early graphics modules and non-GRUB boot paths still
need dedicated review/testing. The existing image post-check scans conventional
paths; this draft is not a claim of support for every mkinitcpio layout.

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
