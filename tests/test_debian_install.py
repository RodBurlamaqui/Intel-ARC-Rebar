"""Execute a path-rewritten installer exclusively in a temporary filesystem."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('etc/initramfs-tools/hooks', 'etc/initramfs-tools/scripts/init-premount',
                          'etc/default', 'boot/grub', 'var/lib/arc-rebar', 'repo/hooks',
                          'repo/scripts/init-premount', 'mock'):
            (self.root / directory).mkdir(parents=True)
        self.put('etc/default/grub', 'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n# user config\n')
        self.put('boot/grub/grub.cfg', 'previous menu\n')
        self.put('boot/initrd.img-6.12-test', 'previous image\n')
        self.put('repo/hooks/arc-rebar', '# hook\n')
        self.put('repo/scripts/init-premount/arc-rebar',
                 f'echo probed >> "{self.root}/probe-called"\necho "PLAN: act test"\n')
        source = (SOURCE / 'install.sh').read_text()
        for prefix in ('/etc/', '/boot/', '/var/lib/', '/proc/'):
            source = source.replace(prefix, str(self.root) + prefix)
        self.put('repo/install.sh', source)
        # A developer checkout: the integrity self-check allows it without a release manifest.
        self.put('repo/selfcheck.sh', (SOURCE / 'selfcheck.sh').read_text())
        (self.root / 'repo/.git').mkdir()
        mocks = {
            'id': 'echo 0', 'uname': 'echo 6.12-test', 'setpci': 'exit 99',
            'sync': 'exit 0',
            'update-grub': f'''echo called >> "{self.root}/update-grub-called"
echo "new pci=realloc" > "{self.root}/boot/grub/grub.cfg"
[ "$FAIL" != grub ] && [ "$FAIL" != restore ]''',
            'update-initramfs': f'''[ "$1 $2 $3" = "-u -k 6.12-test" ] || exit 98
echo called >> "{self.root}/update-initramfs-called"
[ "$FAIL" != stale ] || exit 1
echo new > "{self.root}/boot/initrd.img-6.12-test"
[ "$FAIL" != term ] || kill -TERM "$PPID"
[ "$FAIL" != kill ] || kill -KILL "$PPID"
[ "$FAIL" != initramfs ]''',
            'lsinitramfs': '''echo scripts/init-premount/arc-rebar
echo bin/setpci
[ "$FAIL" != post ] && echo libpci.so
[ "$FAIL" != inspect ]''',
            'install': '''case "$FAIL:$2" in
copy:*) exit 1;;
partial:*) case "$4" in */scripts/*) exit 1;; esac;;
esac
/usr/bin/install "$@"''',
            'cp': '''[ "$FAIL" != backup ] || exit 1
if [ "$FAIL" = restore ]; then case "$3" in *install-transaction/files*) exit 1;; esac; fi
/bin/cp "$@"''',
            'dpkg-query': f'''[ "$1" = -S ] || exit 99
echo "$2" >> "{self.root}/queried-frontend"
case "$BACKEND_OWNER" in
  initramfs-tools) echo "initramfs-tools: $2" ;;
  initramfs-tools-core) echo "initramfs-tools-core: $2" ;;
  other) echo "other-package: $2" ;;
  unowned) exit 1 ;;
  wrong-path) echo "initramfs-tools: /different/path" ;;
  *) exit 1 ;;
esac''',
        }
        # Model current updater behavior by default, with opt-in legacy and
        # incompatible probes for backend-preflight regression cases.
        updater = mocks['update-initramfs']
        mocks['update-initramfs'] = f'''if [ "$1" = --version ]; then
  case "$BACKEND" in
    initramfs-tools) echo "initramfs-tools 0.151ubuntu1"; exit 0 ;;
    dracut) echo "dracut 110-11"; exit 0 ;;
    unknown) echo "some-other-builder 1.0"; exit 0 ;;
    legacy) exit 1 ;;
    legacy-misleading) echo "initramfs-tools 0.151ubuntu1"; exit 1 ;;
  esac
fi
{updater}'''
        for name, body in mocks.items():
            path = self.put('mock/' + name, '#!/bin/bash\n' + body + '\n')
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root / 'mock') + ':' + os.environ['PATH'],
                        BACKEND='initramfs-tools', BACKEND_OWNER='initramfs-tools')

    def put(self, name, text):
        path = self.root / name
        path.write_text(text)
        return path

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode & 0o777)
                for base in ('etc', 'boot') for p in (self.root / base).rglob('*') if p.is_file()} | {
                    'origin': ((self.root / 'var/lib/arc-rebar/hook-origin').read_bytes()
                               if (self.root / 'var/lib/arc-rebar/hook-origin').exists() else None)}

    def run_install(self, failure='', *args, backend='initramfs-tools', owner='initramfs-tools', path=None):
        env = dict(self.env, FAIL=failure, BACKEND=backend, BACKEND_OWNER=owner)
        if path:
            env['PATH'] = path + ':' + env['PATH']
        return subprocess.run(['bash', str(self.root / 'repo/install.sh'), '--yes', *args],
                              env=env, capture_output=True, text=True, timeout=10)

    def check_backend_rejected(self, backend, owner='initramfs-tools', path=None):
        for marker in ('probe-called', 'update-grub-called', 'update-initramfs-called'):
            marker_path = self.root / marker
            if marker_path.exists():
                marker_path.unlink()
        before = self.snapshot()
        result = self.run_install('', backend=backend, owner=owner, path=path)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertRegex(result.stdout, 'unsupported initramfs backend|legacy update-initramfs frontend')
        self.assertEqual(before, self.snapshot(), result.stdout + result.stderr)
        self.assertFalse((self.root / 'var/lib/arc-rebar/install-transaction').exists())
        self.assertFalse((self.root / 'probe-called').exists(), 'hardware dry run must not run')
        self.assertFalse((self.root / 'update-grub-called').exists())
        self.assertFalse((self.root / 'update-initramfs-called').exists())

    def check_failure(self, failure, reinstall=False):
        if reinstall:
            self.put('etc/initramfs-tools/hooks/arc-rebar', 'old working hook')
            self.put('etc/initramfs-tools/scripts/init-premount/arc-rebar', 'old working script')
            self.put('var/lib/arc-rebar/hook-origin', 'deb\n')
        before = self.snapshot()
        result = self.run_install(failure, '--reinstall')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(before, self.snapshot(), result.stdout + result.stderr)

    def test_success(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / 'var/lib/arc-rebar/install-transaction').exists())
        self.assertEqual((self.root / 'boot/initrd.img-6.12-test').read_text(), 'new\n')

    def test_retained_purge_journal_blocks_install_and_install_recovery(self):
        (self.root / 'var/lib/arc-rebar/purge-transaction').mkdir()
        before = self.snapshot()
        for args in ((), ('--recover',)):
            result = self.run_install('', *args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('purge transaction retained', result.stdout)
            self.assertEqual(before, self.snapshot())
            self.assertFalse((self.root / 'var/lib/arc-rebar/install-transaction').exists())

    def test_failures(self):
        for failure in ('grub', 'initramfs', 'stale', 'copy', 'partial', 'post', 'inspect', 'backup', 'term'):
            with self.subTest(failure=failure):
                self.check_failure(failure)
                self.run_install('', '--recover')

    def test_reinstall_failures(self):
        for failure in ('grub', 'initramfs', 'stale', 'partial', 'post', 'term'):
            with self.subTest(failure=failure):
                self.check_failure(failure, True)
                self.run_install('', '--recover')

    def test_killed_install_recovery(self):
        before = self.snapshot()
        self.assertNotEqual(self.run_install('kill').returncode, 0)
        self.assertNotEqual(self.run_install().returncode, 0)
        result = self.run_install('', '--recover', backend='dracut')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_failed_restore_retains_recoverable_journal(self):
        before = self.snapshot()
        result = self.run_install('restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RECOVERY FAILED', result.stdout)
        self.assertTrue((self.root / 'var/lib/arc-rebar/install-transaction/active').exists())
        self.assertEqual(self.run_install('', '--recover').returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_existing_backups_preserved(self):
        self.put('boot/initrd.img-6.12-test.arc-rebar.bak', 'original backup')
        self.put('etc/default/grub.arc-rebar.bak', 'original config backup')
        self.assertEqual(self.run_install().returncode, 0)
        self.assertEqual((self.root / 'boot/initrd.img-6.12-test.arc-rebar.bak').read_text(), 'original backup')

    def test_unsupported_grub(self):
        self.put('etc/default/grub', "GRUB_CMDLINE_LINUX_DEFAULT='quiet'\n")
        self.check_failure('')

    def test_symlink_refused(self):
        target = self.root / 'etc/initramfs-tools/hooks/arc-rebar'
        target.symlink_to(self.root / 'repo/hooks/arc-rebar')
        self.check_failure('')
        self.assertTrue(target.is_symlink())

    def test_dracut_backend_refused_before_hardware_probe(self):
        self.check_backend_rejected('dracut')

    def test_unknown_backend_refused_before_hardware_probe(self):
        self.check_backend_rejected('unknown')

    def test_legacy_backend_requires_exact_package_owner(self):
        result = self.run_install('', backend='legacy')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for owner in ('initramfs-tools-core', 'other', 'unowned', 'wrong-path'):
            with self.subTest(owner=owner):
                self.check_backend_rejected('legacy', owner)

    def test_failed_version_probe_uses_ownership_not_output(self):
        accepted = self.run_install('', backend='legacy-misleading', owner='initramfs-tools')
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        for owner in ('initramfs-tools-core', 'unowned'):
            with self.subTest(owner=owner):
                self.check_backend_rejected('legacy-misleading', owner)

    def test_legacy_frontend_symlink_resolves_to_owned_target(self):
        alias_dir = self.root / 'mock-alias'
        alias_dir.mkdir()
        (alias_dir / 'update-initramfs').symlink_to(self.root / 'mock/update-initramfs')
        result = self.run_install('', backend='legacy', path=str(alias_dir))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        queried = (self.root / 'queried-frontend').read_text().splitlines()
        self.assertEqual(queried, [str(self.root / 'mock/update-initramfs')])

    def test_legacy_frontend_symlink_with_wrong_owner_is_refused(self):
        alias_dir = self.root / 'mock-alias'
        alias_dir.mkdir()
        (alias_dir / 'update-initramfs').symlink_to(self.root / 'mock/update-initramfs')
        self.check_backend_rejected('legacy', 'other', path=str(alias_dir))

if __name__ == '__main__':
    unittest.main()
