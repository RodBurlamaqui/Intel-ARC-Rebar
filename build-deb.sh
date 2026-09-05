#!/bin/bash
# Build the arc-rebar .deb from this tree. Output: dist/arc-rebar_<version>_all.deb + SHA256SUMS.
# Edit debian/control (Version, Maintainer) first. Needs dpkg-deb (package: dpkg).
set -e
S=$(dirname "$(readlink -f "$0")"); cd "$S"
V=$(grep -m1 '^Version:' debian/control | awk '{print $2}'); [ -n "$V" ] || { echo "no Version: in debian/control"; exit 1; }
B=build/arc-rebar_${V}_all; rm -rf build; mkdir -p $B/DEBIAN $B/usr/share/arc-rebar $B/usr/bin $B/usr/share/doc/arc-rebar dist
for f in diagnose.sh prepare.sh live-test.sh install.sh verify.sh uninstall.sh README.md INSTALL.md DISCLAIMER.md LICENSE CHANGELOG.md; do cp "$f" $B/usr/share/arc-rebar/; done
cp -a hooks scripts $B/usr/share/arc-rebar/; cp bin/arc-rebar $B/usr/bin/arc-rebar
mkdir -p $B/usr/share/arc-rebar/diag; cp -a diag/bin diag/src diag/Makefile diag/README.md diag/INSTALL.md $B/usr/share/arc-rebar/diag/; rm -f $B/usr/share/arc-rebar/diag/bin/ocl_test
cp debian/control debian/postinst debian/prerm debian/postrm $B/DEBIAN/; chmod 0755 $B/DEBIAN/postinst $B/DEBIAN/prerm $B/DEBIAN/postrm
{ echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"; echo "Upstream-Name: arc-rebar"; echo
  echo "Files: *"; echo "Copyright: 2026 Rod Burlamaqui"; echo "License: arc-rebar-proprietary"; sed 's/^/ /; s/^ $/ ./' LICENSE; } > $B/usr/share/doc/arc-rebar/copyright
cp README.md INSTALL.md $B/usr/share/doc/arc-rebar/
find $B -type d -exec chmod 0755 {} \; ; find $B/usr -type f -exec chmod 0644 {} \;
chmod 0755 $B/usr/bin/arc-rebar $B/usr/share/arc-rebar/*.sh $B/usr/share/arc-rebar/diag/bin/*.sh $B/usr/share/arc-rebar/hooks/arc-rebar $B/usr/share/arc-rebar/scripts/init-premount/arc-rebar
dpkg-deb --build --root-owner-group $B dist/ >/dev/null
echo "built: dist/arc-rebar_${V}_all.deb"; dpkg-deb -I dist/arc-rebar_${V}_all.deb | grep -E '^ (Package|Version|Depends|Maintainer):'
echo; echo "to also refresh the tarball and checksums:"
echo "  (cd .. && tar czf $(basename $S)/dist/arc-rebar-${V}.tar.gz --exclude=.git --exclude=dist --exclude=build $(basename $S))"
echo "  (cd dist && sha256sum arc-rebar_${V}_all.deb arc-rebar-${V}.tar.gz > SHA256SUMS)"
