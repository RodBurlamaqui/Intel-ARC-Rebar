# Debian package lifecycle and purge recovery

Recorded 2026-11-05. No GPU or hardware boot behavior was tested.

## Findings before the fix

Real `dpkg --root` operations in disposable filesystem roots reproduced three
failure cases in the previous maintainer script:

- A failing initramfs updater was ignored after hook removal; purge returned
  success with the prior image still containing the runtime payload.
- A missing updater also returned success after hook removal.
- When the runtime-script file was already missing, a package-owned build hook
  and origin marker were left behind by purge.

Six normal lifecycle cases passed: fresh installation, upgrade of an existing
installation, removal with package/source-owned hooks, source-owned purge
preservation, and successful package-owned purge.

## Corrected behavior

The self-contained `postrm` script keeps recovery available after the package
payload has already been removed. Under the same lock as the source installer,
it checks ownership, required tools and supported destinations before mutation.
It saves package-owned hook files, origin metadata, optional GRUB files and all
existing conventional initramfs files in a root-only journal. Original backup
images are included in the snapshot and preserved as recovery data.

Rebuilding explicitly targets all kernels. Archive inspection rejects an updater
that returns success while leaving the script embedded. Recognized backup and
temporary suffixes (`.bak`, `.dpkg-bak`, `.new`, `.old`) are snapshotted but are
not treated as active images that must have the script removed. Failed attempts
restore previous files/modes and remove newly created initramfs artifacts. The
purge exits nonzero even when restoration succeeds. Unknown/source-owned hooks
are preserved rather than inferred to be package-owned.

A retry first restores an active interrupted transaction, then may attempt purge
again. If the original error remains, repair it before retrying. Failed
restoration retains the active journal and says not to reboot. The source
installer refuses a retained purge journal; source `--recover` is not the purge
recovery entrypoint. Use `sudo dpkg --purge arc-rebar` after fixing the error.

Snapshots and a shared lock do not make a multi-file boot update atomic. Restore
before reboot after forced termination; storage failures and arbitrary custom
boot hooks can require manual repair. Do not run manual boot updates concurrently.
The shared lock file and existing escape-hatch backups remain after purge.

## Validation

The ordinary CI suite uses path-rewritten maintainer scripts in temporary
filesystems, with simulated updater/archive commands. Its 30 methods include
the existing installer tests plus purge success, missing tools, changed/stale
images, partial hooks, source/unknown ownership, non-purge actions, snapshot
failure, content-matcher errors, failed restoration/retry, SIGKILL recovery, lock contention, unsupported
symlinks and coordination with installation recovery. Two kernel images and an
existing backup are modeled; failure also creates a new backup and changes the
GRUB menu to exercise restoration.

```bash
python3 -m unittest discover -s tests -v
dash -n debian/postinst debian/prerm debian/postrm
bash -n install.sh
bash build-deb.sh
```

Real dpkg lifecycle validation used private minimal roots with real shell/core
utilities and fixture dependency packages. The candidate was built from current
source; a private higher-version fixture allowed an actual upgrade from the
published v1.0.3 package. These fixture packages were not installed on the VM
host, published or tagged as releases.

The updater and archive inspector were test doubles. Rebuild failures occurred
after changing the fake image and creating a backup; a successful no-op updater
left the old embedded payload detectable. Successful retries were tested after
restoring tools or enabling rebuilding. All 13 corrected lifecycle cases passed:
the six normal cases, three original failure cases, failed/missing-tool purge
retries, stale-success rejection and its retry.

The VM host dpkg database and every host initramfs checksum matched before and
after. Raw evidence, package fixtures and complete source/history backups remain
private. This is package orchestration coverage on one VM, not a Debian/Ubuntu
release matrix, a real multi-kernel rebuild/boot test or physical GPU validation.
No published `.deb` or release asset was changed.
