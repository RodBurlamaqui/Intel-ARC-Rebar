# DISCLAIMER — READ BEFORE USE

Copyright (c) 2026 Rod Burlamaqui. Licensed under the terms in LICENSE.

**USE AT YOUR OWN RISK.**

This software is provided "AS IS", without warranty of any kind, express or
implied, including but not limited to the warranties of merchantability,
fitness for a particular purpose and non-infringement.

In no event shall the author(s) or contributor(s) be liable for any claim,
damages or other liability — including without limitation data loss, hardware
damage, downtime, lost work, or any direct, indirect, incidental or
consequential loss — arising from or in connection with this software or its
use, whether in contract, tort or otherwise.

You are solely responsible for deciding whether this is appropriate for your
hardware, for backing up your data before running it, and for every consequence
of running it. No support is promised.

## What it actually does, so you can judge the risk yourself

- Writes one PCI configuration register on the GPU: the Resizable BAR control
  register. This is a standard, specification-defined register that the Linux
  kernel itself writes when it resizes a BAR. It does not touch firmware,
  flash, voltages or clocks. It resets on power cycle.
- Removes and rescans one PCIe root port through the kernel's sysfs interface.
  This is software re-enumeration, the same thing hot-plug does.
- Installs two small files into the initramfs (Debian/Ubuntu) and adds
  `pci=realloc` to the kernel command line. Backups are taken; `uninstall.sh`
  removes everything.

It is **designed to fail safe** — to have no effect rather than a harmful one.
Every safety check refuses rather than guesses; every step at boot is
non-fatal; if the new BAR cannot be placed it rolls back to the old size. But
no such design can be guaranteed on hardware and firmware the authors have never
seen. Known realistic failure modes:

- **The machine hangs during the rescan.** Some chipsets do not tolerate root
  port re-enumeration. Recovery is a power cycle. Nothing persistent has
  changed on the first (live) run; after install, boot with `norebar`.
- **The GPU is unusable for one boot** if both the resize and the rollback fail.
  Recovery: reboot with `norebar` on the kernel command line.
- **Running live-test.sh at a local console** stops the display manager. Do it
  over SSH, and save your work first.
- Anything on the same root port as the GPU would be removed with it. The
  script refuses to run in that situation, but if you override it, that is on you.

If you are not comfortable with any of the above, do not use this.
