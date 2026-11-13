---
name: Hardware compatibility report
about: Share success, partial success, a refusal or a failure on an Intel Arc setup
title: "[Hardware report] GPU model / motherboard"
---

Thanks for helping test more Intel Arc models. Report your existing observations;
you do not need to reinstall or perform PCIe writes just to submit this form.
Read INSTALL.md before choosing any installation tests. Redact private details
and share relevant excerpts rather than full machine logs.

## Hardware and software

- GPU model and VRAM:
- Motherboard and BIOS version:
- OS and kernel:
- Driver (i915/xe):
- arc-rebar version or commit:
- Initramfs backend (initramfs-tools / mkinitcpio / dracut / other):
- Physical hardware, VM or passthrough:
- GPU count and relevant PCIe topology (shared root port/switch, if known):

## Observed result

- What were you trying to resolve?
- Diagnosis verdict (relevant, redacted excerpt):
- BAR2 before / after, if measured:
- What worked, refused or failed? Include the exact stage and relevant error.

Mark each as **passed**, **failed** or **not tested**:

| Stage | Result / relevant observation |
|---|---|
| Read-only diagnosis | |
| Initramfs image inspection | |
| Live operation, if already tested | |
| Installation and warm reboot | |
| Cold boot | |
| Driver binding and usual GPU workload | |
| Reinstallation and reboot | |
| Removal and reboot | |

## Verification and limits

- Verifier output and exit status, if run:
- Relevant `dmesg` lines (`journalctl -k` may omit boot-script messages):
- Any GPU hangs/resets, PCIe errors or other limitations:
- Local modifications, custom kernel parameters or other ReBAR tools involved:

Do not include IP addresses, hostnames, local usernames, serial numbers,
credentials or private paths. Please leave untested stages marked as such.
