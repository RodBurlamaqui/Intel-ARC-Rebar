#!/bin/bash
# Vulkan memory heaps for the Intel GPU, with interpretation. A small-BAR card shows a
# separate DEVICE_LOCAL|HOST_VISIBLE heap of 256 MiB; a full-aperture card shows one merged heap.
command -v vulkaninfo >/dev/null || { echo "vulkaninfo missing (apt install vulkan-tools)"; exit 1; }
out=$(vulkaninfo 2>/dev/null | sed -n '/memoryHeaps: count = /,/memoryTypes/p' | sed '/memoryTypes/q')   # first device = GPU0
vulkaninfo --summary 2>/dev/null | grep -m1 deviceName | sed 's/^\s*/  /'
echo "$out" | grep -E 'memoryHeaps: count|memoryHeaps\[|size *=|budget|MEMORY_HEAP' | sed 's/^\s*/  /'
n=$(echo "$out" | grep -oP 'memoryHeaps: count = \K[0-9]+')
small=$(echo "$out" | grep -oP 'size\s+= \K[0-9]+' | awk '$1==268435456{c++} END{print c+0}')
echo; if [ "${small:-0}" -gt 0 ]; then echo "  => a 256 MiB device-local heap exists: SMALL BAR. CPU-visible VRAM is capped at 256 MiB."
elif [ -n "$n" ]; then echo "  => no 256 MiB heap ($n heaps): full aperture. VRAM is fully CPU-visible."
else echo "  => could not parse vulkaninfo output"; fi
