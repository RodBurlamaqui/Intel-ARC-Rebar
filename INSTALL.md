# INSTALL — arc-rebar, step by step

**Applies to:** Debian 12/13, Ubuntu 22.04 or newer, or any distro using
`initramfs-tools`. Kernel 6.12 or newer recommended. You need `sudo`.

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
You should see a kernel version. If it is below `6.12`, the fix may still work
but the `xe` driver's ReBAR support is younger than that; proceed with Path B.

## 1. Get the tool (both paths)

**From the .deb** (download from https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases):
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
If any line says `[FAIL]`, the installer restores the backup and removes itself.
Nothing is enabled. Report the output.

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

Both leave `pci=realloc` in GRUB; it is harmless. To remove it:
```
sudo cp /etc/default/grub.arc-rebar.bak /etc/default/grub
sudo update-grub
```
