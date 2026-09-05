# INSTALL — the diagnostics, step by step

**Applies to:** any Linux with an Intel Arc discrete GPU. Debian/Ubuntu package
names are given; other distros need the equivalents. Nothing here changes your
system: these tools only read state and, in one case, allocate GPU memory.

## 0. Prerequisites

```
sudo apt update
sudo apt install pciutils vulkan-tools mesa-opencl-icd ocl-icd-libopencl1 gcc make
```
You should see the packages install (or "already the newest version").

## 1. Get and extract

```
cd arc-rebar/diag        # or /usr/share/arc-rebar/diag after apt install
```

## 2. Build (one small C program)

```
make
```
You should see one compiler line ending in `libOpenCL.so.1` and then your
prompt. If you see `libOpenCL.so.1 not found`, step 0 did not install
`ocl-icd-libopencl1`; install it and run `make` again.

## 3. Run the tools, in this order

### 3a. Is the BAR pinned?
```
sudo bin/bar-pin-check.sh
```
Read the `VERDICT:` line:

| VERDICT | Meaning |
|---|---|
| `PINNED. A bridge BAR0 holds the root port window. Fix: arc-rebar.` | you have the problem arc-rebar fixes |
| `BAR is at the card maximum. No problem here.` | full aperture already |
| `small BAR and a bridge BAR0 is present in the path; likely the pin` | probably the same problem; the kernel log line was not on this boot |
| `small BAR, but no pin detected. Different cause` | not this problem — check Above 4G Decoding and MMIO space |

### 3b. Which link is real?
```
sudo bin/pcie-link-truth.sh
```
You should see a table with one row per hop. The **root-port** row shows `EQ +`
and `DLACTIVE +` — that is your real link. The **GPU** row shows `2.5GT/s, Width
x1` with `EQ -` — that is a virtual port; ignore it. The last line quotes the
kernel's own bandwidth statement.

### 3c. Vulkan's view
```
bin/vulkan-heaps.sh
```
Last line is either
`=> a 256 MiB device-local heap exists: SMALL BAR` or
`=> no 256 MiB heap (2 heaps): full aperture`.

### 3d. The real allocation ceiling (allocates GPU memory; about one minute)
```
bin/ocl-alloc-ceiling.sh
```
You should see a sweep like
```
  256 MiB : ok
  320 MiB : FAIL        <-- small BAR: this is where it stops
  => largest single allocation that worked: 256 MiB
```
or, with a full aperture, every size `ok` up to 2048 MiB. Then a chunked run
ending in `RESULT: N GiB allocated and computed on` and a `saxpy: ... GB/s` line.
If you see `no OpenCL platform`, `mesa-opencl-icd` is missing (step 0).

### 3e. Health
```
sudo bin/gpu-health.sh
```
You want `DevSta: CorrErr- NonFatalErr- FatalErr- UnsupReq-`, `AER error
reports in log: 0`, and temperatures that look sane.

## 4. Save a baseline (recommended before applying any fix)

```
mkdir -p ~/arc-baseline
for t in bar-pin-check pcie-link-truth gpu-health; do sudo bin/$t.sh > ~/arc-baseline/$t.txt 2>&1; done
for t in vulkan-heaps ocl-alloc-ceiling;          do      bin/$t.sh > ~/arc-baseline/$t.txt 2>&1; done
ls ~/arc-baseline
```
Re-run the same loop into a second folder after the fix and `diff` them.

## 5. Uninstall

Nothing was installed by these tools. They live inside arc-rebar.

## Troubleshooting

- `run as root` — use `sudo` for `bar-pin-check`, `pcie-link-truth`, `gpu-health`.
- `vulkaninfo missing` — `sudo apt install vulkan-tools`.
- `no OpenCL platform` / `no OpenCL GPU device` — `sudo apt install mesa-opencl-icd`;
  the wrapper sets `RUSTICL_ENABLE=iris` for you. Intel's own OpenCL runtime is not in
  Debian; Mesa's works for this measurement.
- Desktop stutters during 3d — expected; it is writing gigabytes of VRAM. It stops on its own.
