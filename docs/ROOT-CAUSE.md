# [SOLVED] Arc B580 Small BAR on Supermicro X9DRH-7TF (Ivy Bridge-EP, no ReBAR in BIOS) — root cause + no-firmware fix that survives reboot

## TL;DR

Full 12 GB VRAM CPU-visible on a 2015 board with no ReBAR option, **no firmware
modification**. Root cause traced from the kernel log; fix runs from initramfs.
Package: https://github.com/RodBurlamaqui/Intel-ARC-Rebar (diagnose / live-test / install / verify / uninstall, .deb, README).
Licence: free for personal use; no modification or resale without my approval; see LICENSE.

```
before   BAR2 256M   Vulkan: 11.68 GiB device-only + 256 MiB host-visible (3 MiB free)
after    BAR2 16G    Vulkan: one 11.93 GiB heap           OpenCL 1 GiB single alloc ok
         VRAM bandwidth 15 GB/s -> 392 GB/s              4K vulkan filters: stalled -> 39-50 fps
```

## Hardware

```
Board    Supermicro X9DRH-7TF, AMI BIOS 3.2 (2015), no ReBAR option, Above 4G enabled
CPU      2x Xeon E5-2670 v2 (Ivy Bridge-EP), C602
GPU      Intel Arc B580 12GB (ASRock 1849:6021), xe driver, Mesa 26.1.2
Kernel   7.1.8 (Debian 13)
```

## Root cause — it's not "your BIOS is too old"

The kernel says exactly what's wrong if you grep for the right line:

```
pcieport 0000:80:03.0: bridge window [mem 0x381fe0000000-0x381ff07fffff 64bit pref]:
    was not released (still contains assigned resources)
```

The B580 carries an **integrated PCIe switch**. Its upstream port (84:00.0,
8086:e2ff) has its own 8 MB BAR0, which firmware placed inside the root port's
prefetchable window. The resize path releases bridge *windows* up the chain but
never a bridge's *own BAR*. So the root port window stays pinned at 264 MB and the
16 GB request fails with -ENOSPC — with 63 GB of address space sitting free.

```
80:03.0 root port      window 264M   <-- pinned
 └84:00.0 switch US    BAR0 8M       <-- the pin (owned by pcieport, unused)
   └85:01.0 switch DS
     └86:00.0 B580     BAR2 256M     <-- wants 16G
```

Intel wrote a quirk for exactly this ("PCI: Release BAR0 of an integrated
bridge to allow GPU BAR resize", Ilpo Järvinen / Lucas De Marchi, Sept–Oct 2025,
IDs 0x4fa0/0x4fa1/0xe2ff). It stalled in review and is not in mainline as of 7.1.
Its companion, "drm/xe: Move rebar to be done earlier" (which handles the GPU's
*own* BAR0), did merge to drm-xe-next in October 2025 — but the switch's BAR0 is
what pins the window here, and that half is the one still pending. Upstream
tracking: gitlab.freedesktop.org/drm/xe/kernel issue 6356.

## The fix

From initramfs, before xe binds: program ECAP_REBAR ctrl to the max supported
size, **remove the root port**, rescan. The remove drops BAR0 with everything
else; the rescan allocates BAR0 and the 16 GB BAR2 fresh into one window. The
pin never exists. Needs `pci=realloc`.

Real boot log with the hook installed:

```
[  3.241] xe 0000:86:00.0: [drm] Attempting to resize bar from 256MiB -> 16384MiB
[  3.242] xe 0000:86:00.0: [drm] Failed to resize BAR2 to 16384MiB (-ENOSPC)
[  3.244] xe 0000:86:00.0: [drm] Small BAR device                      <-- first probe
[  4.182] arc-rebar: gpu=0000:86:00.0 rootport=0000:80:03.0 cap=0x0007f000 ctl=0x00000822 size_field current=8 target=14
[  4.695] arc-rebar: unbound xe from 0000:86:00.0
[  5.753] arc-rebar: wrote ECAP_REBAR ctl=0x00000e22; removing 0000:80:03.0 and rescanning
[  7.861] xe 0000:86:00.0: [drm] VISIBLE VRAM: 0x0000381000000000, 0x0000000400000000
[ 11.209] arc-rebar: done: 0000:86:00.0 BAR2 is now 16384 MiB
```

Based on andersevenrud's H11SSL-i gist; generalised (finds the GPU and its root
port from sysfs, picks the largest size the card advertises, `norebar` cmdline
escape hatch, every step non-fatal). Should apply to Alchemist too (same switch
design, IDs 0x4fa0/0x4fa1) — untested.

## Things that did NOT work, so you can skip them

`pci=realloc` alone (release walk still hits the pin), `xe.vram_bar_size` (root
port window fully consumed), `pci=hpmemprefsize` (root port is `Slot-`), other
slots, Mesa 25→26, BIOS 3.3 (microcode-only), any Intel GPU firmware (the card
already advertises 256MB..16GB — the host is the problem).

On that last point, tested rather than assumed (Sept 2026): flashing FWCODE
21.1137 → **21.1182** and OptionROM code 23.1051.0.0 → **23.1066.0.0** from LVFS
changes nothing. The card still powers up at size field 8 (256 MB), the kernel
still fails the resize with `-ENOSPC`, and the hook still has to fire to reach
16 G. `cap` reads `0x0007f000` before and after. The OptionROM is the part that
would plausibly govern pre-boot BAR sizing, and it moved a full version without
changing the power-up size field. Do not spend a flash on this.

## Two traps for anyone debugging this

- `current_link_speed` on the GPU function reads **2.5 GT/s x1**. That's the
  switch's die-internal virtual port. The real link is on the switch upstream
  port (here Gen3 x8, the platform max).
- `clinfo` reports 11.93 GiB global / 1 GiB max alloc on a small-BAR card. Both
  wrong — real ceiling was 256 MiB per allocation. Measure, don't trust.

## Open question for Intel / linux-pci

Is the integrated-bridge BAR0 quirk going anywhere, or is the newer "Reserve
prefetchable window headroom for Resizable BARs" (Aug 2026) the intended path?
This box is available for testing patches. Data point: here the pinned window
is the **root port's**, and after remove/rescan BAR0 gets a fresh valid address
rather than a dangling one — maybe relevant to the "impossible address" thread.
