# arc-rebar diagnostics — is it Small BAR, is it the pin, did the fix work

Copyright (c) 2026 Rod Burlamaqui. Free for personal use; see [../LICENSE](../LICENSE).

> **USE AT YOUR OWN RISK. NO WARRANTY.** See [../DISCLAIMER.md](../DISCLAIMER.md).

Read-only tools that tell you *what is actually going on* with an Intel Arc
discrete GPU whose kernel log says `Small BAR device`, and that measure the real
effect. They produced every number in [../docs/ROOT-CAUSE.md](../docs/ROOT-CAUSE.md).
The fix is the parent project, arc-rebar; this directory is how you know whether
you need it, and how you prove it worked.

Two traps these tools exist to catch:

- `lspci`/sysfs report the GPU's link as **2.5 GT/s x1**. That is the card's
  die-internal virtual switch port, not your slot. `pcie-link-truth.sh` shows
  the real link.
- `clinfo` claims 11.9 GiB global / 1 GiB max allocation on a small-BAR card.
  Both are wrong; the real ceiling is 256 MiB per allocation.
  `ocl-alloc-ceiling.sh` measures it by allocating for real.

## Tools

| Tool | What it tells you | Needs |
|---|---|---|
| `bin/bar-pin-check.sh` | BAR2 size vs card max, the root port window, **which bridge BAR0 pins it**, MMIO room, the kernel's "was not released" line, a verdict | root, pciutils |
| `bin/pcie-link-truth.sh` | Every hop from root port to GPU with LnkCap2, LnkSta, equalization and DLActive — which link is physical | root, pciutils |
| `bin/vulkan-heaps.sh` | Vulkan heaps with interpretation: a 256 MiB device-local heap = small BAR; one merged heap = full aperture | vulkan-tools |
| `bin/ocl-alloc-ceiling.sh` | Real single-allocation ceiling by sweeping sizes, then total usable VRAM in chunks, with measured bandwidth | OpenCL ICD (e.g. `mesa-opencl-icd`), gcc |
| `bin/gpu-health.sh` | PCIe DevSta error bits, AER reports, hangs/resets, temperatures, clocks, throttle reasons, firmware | root |
| `src/ocl_test.c` | The allocator/bandwidth test behind `ocl-alloc-ceiling.sh`. Links against the ICD loader directly — no OpenCL dev headers | gcc, `ocl-icd-libopencl1` |

## Install and run

**Step-by-step with expected output: [INSTALL.md](INSTALL.md).** Short version:

```
sudo apt install pciutils vulkan-tools mesa-opencl-icd ocl-icd-libopencl1 gcc make
cd diag && make
sudo bin/bar-pin-check.sh        # read the VERDICT line
sudo bin/pcie-link-truth.sh
bin/vulkan-heaps.sh
bin/ocl-alloc-ceiling.sh         # allocates real GPU memory, ~1 min
sudo bin/gpu-health.sh
```

Run them **before** applying arc-rebar to capture a baseline, and **after** to
prove the change. On a Supermicro X9DRH-7TF with a B580 that looked like: 256 MiB
ceiling and 15 GB/s before, 1 GiB+ single allocations and 392 GB/s after. The
exact commands and numbers are in [../docs/TESTS.md](../docs/TESTS.md).

## What "Small BAR" really costs

It is a **per-allocation** cap, not a total-VRAM cap. Measured on a B580:
a single 320 MiB buffer fails, but 40 × 224 MiB = 8.8 GiB allocates and
computes fine. Workloads that chunk their data mostly work; anything wanting one
large contiguous buffer, and anything streaming through the CPU-visible aperture
(ffmpeg's Vulkan/OpenCL filters at 4K), fails or crawls. Media encode/decode is
unaffected — it runs on the media tile.

## Docs

- [../docs/ROOT-CAUSE.md](../docs/ROOT-CAUSE.md) — the full investigation: the
  integrated-switch BAR0 pin, the kernel log proof, what was ruled out, upstream status.

## Layout

```
diag/bin/       the five tools (bash) + ocl_test once built
diag/src/       ocl_test.c
diag/Makefile   builds ocl_test against libOpenCL.so.1 directly
../docs/        root cause, tests
```

## Contributing

Bug reports welcome via issues. Modifications require the copyright holder's
prior written approval (LICENSE §3.2) — open an issue first.

## Licence

Copyright (c) 2026 Rod Burlamaqui. Personal, non-commercial use free of charge.
Commercial licences are for sale (LICENSE §9); Modification and resale require
prior written approval. See [../LICENSE](../LICENSE). Not an open-source licence.
