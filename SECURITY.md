# Security

## The only official source

arc-rebar is published **only** at https://github.com/RodBurlamaqui/Intel-ARC-Rebar.
Official downloads are the packages on its
[Releases](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases) page (`.deb` for
Debian/Ubuntu, `.pkg.tar.zst` for Arch, `.rpm` for Fedora/RHEL/openSUSE), with `SHA256SUMS`,
`SHA256SUMS.asc` and a `.sig` for each package. We never distribute `.zip`, `.rar`, `.exe`, "setup" or "installer"
files, and never through other accounts, websites or file-sharing services. (The only `.zip` you
will see from us is GitHub's automatic "Source code" archive on our own Releases page.)

arc-rebar runs with full system (root) privileges at boot, so only install a genuine copy.

## Check that your copy is genuine

From v1.0.8:
```
sha256sum -c --ignore-missing SHA256SUMS
gpg --verify SHA256SUMS.asc SHA256SUMS     # see the signing key below
gh attestation verify <package file> -R RodBurlamaqui/Intel-ARC-Rebar
sudo arc-rebar integrity        # after installing: are the installed files unmodified?
arc-rebar version               # shows the version and the official source
```
If any check fails, don't use that copy. Download it again from the Releases page.

### Release signing key

Releases from v1.0.8 include `SHA256SUMS.asc` and a `.sig` per package, signed with this key:

- Owner: Rod Burlamaqui
- Fingerprint: `C3CF CBF8 EE59 2C27 BCBE  1E49 8D8E D73D 0C2D E44B`
- Public key: [docs/signing-key.asc](docs/signing-key.asc)

```
wget https://raw.githubusercontent.com/RodBurlamaqui/Intel-ARC-Rebar/v1.0.8/docs/signing-key.asc
gpg --import signing-key.asc               # once
gpg --verify SHA256SUMS.asc SHA256SUMS     # must say "Good signature" and show the fingerprint above
```
A good signature from any other key means the file is not from us.

Every `arc-rebar install` also checks, before changing anything, that its files match a file
list signed with this key, and refuses a modified copy. The key's fingerprint is built into
the installers, so a file list re-signed with another key, a replaced or deleted key file, a
missing file or a modified checker is refused, and a wrong system clock does not make a genuine
copy fail. `gpgv` is required for this check. It runs on your machine, so someone who
rewrites the installers themselves can still remove it. For a download, the signature and
attestation checks above are the proof.

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue: email
**burlam1nx@outlook.com** with "arc-rebar security" in the subject.

Include the arc-rebar version, your distribution and kernel, and the steps to reproduce.
We aim to acknowledge reports within a few days. Please give us reasonable time to fix
the problem before disclosing it publicly.

## Reporting imitations or tampered copies

If you find a copy of arc-rebar elsewhere, especially one offering a download from another
account or website, don't download or run it. Send the link to **burlam1nx@outlook.com**.
Unauthorized copies and modified versions violate the [LICENSE](LICENSE) and are reported
and taken down.

## Supported versions

Only the latest release receives fixes.
