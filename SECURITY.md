# Security

## The only official source

arc-rebar is published **only** at https://github.com/RodBurlamaqui/Intel-ARC-Rebar.
Official downloads are the `.deb` packages on its
[Releases](https://github.com/RodBurlamaqui/Intel-ARC-Rebar/releases) page, with a
`SHA256SUMS` file. We never distribute `.zip`, `.rar`, `.exe`, "setup" or "installer"
files, and never through other accounts, websites or file-sharing services.

arc-rebar runs with full system (root) privileges at boot, so only install a genuine copy.

## Check that your copy is genuine

From v1.0.7:
```
sha256sum -c SHA256SUMS
gh attestation verify arc-rebar_<version>_all.deb -R RodBurlamaqui/Intel-ARC-Rebar
sudo arc-rebar integrity        # after installing: are the installed files unmodified?
arc-rebar version               # shows the version and the official source
```
If any check fails, don't use that copy. Download it again from the Releases page.

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue:
- use GitHub's **Report a vulnerability** button under this repository's **Security** tab, or
- email **burlam1nx@outlook.com** with "arc-rebar security" in the subject.

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
