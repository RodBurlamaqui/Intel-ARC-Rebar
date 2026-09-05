# Tests used, with before/after results

Every command run on the Supermicro X9DRH-7TF + Arc B580 during the
2026-09-05 investigation, exactly as run, so anyone can reproduce the numbers in
ROOT-CAUSE.md. "Before" = 256 MiB BAR. "After" = arc-rebar active.

## 1. Is the problem present, and why (read-only)

```
# the failure
journalctl -k -b | grep -E 'resize bar|Small BAR|BAR 2|VISIBLE VRAM'
# THE line that names the cause (was missed by grepping for "releasing|can't assign")
journalctl -k -b | grep 'was not released'
# what occupies the root port window
cat /proc/iomem | grep -A6 '381fe0000000-381ff07fffff'
# host bridge window above 4G, per root bus
journalctl -k -b | grep 'root bus resource'
# bridge decode capability: low nibble 1 = 64-bit prefetchable decode
sudo setpci -s 80:03.0 0x24.l 0x28.l 0x2c.l        # 0xf071e001 / 0x381f / 0x381f
sudo setpci -s 84:00.0 0x24.l
# the card's ReBAR capability and current size field
sudo setpci -s 86:00.0 ECAP_REBAR+4.l              # 0x0007f000 = 256MB..16GB supported
sudo setpci -s 86:00.0 ECAP_REBAR+8.l              # 0x00000822 = size field 8 = 256MB
# which link is real (the GPU function lies: 2.5 GT/s x1 is a virtual port)
for d in 80:03.0 84:00.0 85:01.0 86:00.0; do sudo lspci -vv -s $d | grep -E 'LnkCap:|LnkCap2:|LnkSta:|EqualizationComplete|DLActive'; done
journalctl -k -b | grep 'available PCIe bandwidth'   # kernel names the limiting link itself
```

## 2. Media engine (unaffected by Small BAR — do NOT use this to judge health)

```
ffmpeg -hide_banner -loglevel error -stats -vaapi_device /dev/dri/renderD128 \
  -f lavfi -i testsrc=size=1920x1080:rate=60:duration=15 \
  -vf 'format=nv12,hwupload' -c:v h264_vaapi -b:v 10M -f null -
```
Before: 149 fps (2.48x). After: same. VAAPI H.264/HEVC/VP9/AV1 encode+decode all present (vainfo).

## 3. Host-to-device bandwidth (disproves the "Gen1 x1" reading)

```
for i in 1 2 3 4; do ffmpeg -hide_banner -loglevel error -stats -vaapi_device /dev/dri/renderD128 \
  -f lavfi -i color=c=blue:size=3840x2160:rate=2000:duration=20 \
  -vf 'format=nv12,hwupload' -f null - 2>/tmp/p$i.txt & done; wait
# sum the fps, x 12.44 MB per 4K nv12 frame
```
Result: 177 fps aggregate = 2,201 MB/s, 8.8x the 250 MB/s theoretical maximum of a Gen1 x1 link.
Real link is Gen3 x8 (7.88 GB/s), the platform maximum.

## 4. Vulkan compute (the one that fails on Small BAR)

```
# heaps: 3 heaps with a 256 MiB DEVICE_LOCAL|HOST_VISIBLE heap = small BAR; 2 heaps = full aperture
vulkaninfo | sed -n '/memoryHeaps: count = /,/memoryTypes/p' | head -22
# 4K gaussian blur, 500 frames (duration=1 at rate=500). Use a generous timeout: at 4K it is ~40-50 fps.
timeout 150 ffmpeg -hide_banner -loglevel error -stats -init_hw_device vulkan=vk:0 -filter_hw_device vk \
  -f lavfi -i testsrc=size=3840x2160:rate=500:duration=1 \
  -vf 'format=nv12,hwupload,gblur_vulkan=sigma=8,hwdownload,format=nv12' -f null -
```
Before: stalls, 0 frames (heap[2] 256 MiB, budget 3 MiB). After: 39-50 fps.
Note: an early run used duration=10 (5,000 frames) with a 90 s timeout, which kills even a working run; that
produced a false "still fails" reading once. Use duration=1.

```
# nlmeans is memory-hungry; at 4K it exceeds the 10.7 GiB budget even with the full aperture
... -vf 'format=nv12,hwupload,nlmeans_vulkan=s=3,hwdownload,format=nv12' ...   # 1080p: 17 fps, 1440p: 7.6 fps, 4K: ENOMEM (filter limit, not BAR)
```

## 5. OpenCL: the real allocation ceiling (clinfo lies)

```
RUSTICL_ENABLE=iris clinfo | grep -E 'Global memory size|Max memory allocation'   # says 11.93 GiB / 1024 MiB — wrong on small BAR
# real test: diag/bin/ocl_test [nbuf] [MiB], or diag/bin/ocl-alloc-ceiling.sh
for m in 16 64 128 192 224 256 320 384 512; do RUSTICL_ENABLE=iris ./ocl_test 1 $m; done
RUSTICL_ENABLE=iris ./ocl_test 40 224     # chunked total
RUSTICL_ENABLE=iris ./ocl_test 10 1024
```
Before: 256 MiB ok, 320 FAIL (CL_OUT_OF_RESOURCES -5); 40 x 224 MiB = 8.8 GiB ok; saxpy 15.4 GB/s.
After: 1024 MiB ok (1536+ fails on the runtime's own 1 GiB max-alloc limit); 10 x 1 GiB ok; saxpy 388-392 GB/s.

## 6. Thermals / throttling under load

```
D=/sys/class/drm/card0/device; H=$(echo $D/hwmon/hwmon*)
cat $H/temp2_input $H/temp3_input $H/fan1_input $D/tile0/gt0/freq0/act_freq $D/tile0/gt0/freq0/throttle/reasons
```
51 C package / 58 C VRAM under sustained 4K60 HEVC encode, throttle reasons: none, DevSta clean, AER none.

## 7. The boot script's safety paths (no hardware needed)

```
S=scripts/init-premount/arc-rebar
sudo env ARC_REBAR_DRYRUN=1 sh $S                                   # real box: full fact line + PLAN
printf '100000000-13fffffff : PCI Bus 0000:80\n' > /tmp/iomem-1g    # 1 GB window -> expect step-down note
sudo env ARC_REBAR_DRYRUN=1 ARC_REBAR_IOMEM=/tmp/iomem-1g sh $S
printf 'e0000000-fbffffff : PCI Bus 0000:80\n'   > /tmp/iomem-0     # nothing above 4G -> skip no-mmio-window-above-4g
sudo env ARC_REBAR_DRYRUN=1 ARC_REBAR_IOMEM=/tmp/iomem-0 sh $S
printf '100000000-10fffffff : PCI Bus 0000:80\n' > /tmp/iomem-256m  # 256 MB window -> skip mmio-window-too-small
sudo env ARC_REBAR_DRYRUN=1 ARC_REBAR_IOMEM=/tmp/iomem-256m sh $S
```
Replace `0000:80` with your GPU's root bus. Dry runs never write to the kernel log.
The shared-root-port, unexpected-topology and rolled-back paths were reviewed, not hardware-tested.

## 8. After a reboot with the hook installed

```
dmesg | grep arc-rebar                 # want: PLAN: done gpu=... bar2=16384M
dmesg | grep 'VISIBLE VRAM' | tail -1  # want: ..., 0x0000000400000000
sudo ./verify.sh                        # PASS
```
The first xe probe at ~3 s still logs "Small BAR device" every boot; that is before the hook runs.
