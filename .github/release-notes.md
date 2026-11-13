**Recommended upgrade for everyone.** It includes many bug fixes and safety improvements: a fix for a kernel issue on some systems with Secure Boot, safer installs that automatically restore everything if anything fails, and built-in authenticity checks that confirm every file is the genuine, signed release before anything is installed, so you are protected from tampered or fake copies. After installing the new package, run `sudo arc-rebar install --reinstall`.

| Linux | Package |
|---|---|
| Debian, Ubuntu, Linux Mint, Proxmox | `.deb` |
| Arch, CachyOS, Manjaro | `.pkg.tar.zst` |
| Fedora, RHEL, Rocky, AlmaLinux, openSUSE | `.rpm` |

Installing a package enables nothing by itself: run `sudo arc-rebar diagnose`, then `sudo arc-rebar install`. Full list of changes: [CHANGELOG.md](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/blob/main/CHANGELOG.md).

**Check your download** before installing it ([SECURITY.md](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/blob/main/SECURITY.md#check-that-your-copy-is-genuine)):
```
sha256sum -c --ignore-missing SHA256SUMS
gpg --verify SHA256SUMS.asc SHA256SUMS
gh attestation verify <package file> -R RodBurlamaqui/Intel-ARC-Rebar
```
Official downloads are only on this page. We never distribute `.zip`, `.rar`, `.exe`, "setup" or "installer" files.
