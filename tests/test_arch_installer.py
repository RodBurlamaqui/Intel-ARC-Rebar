"""Execute installers against a temporary filesystem with mocked build commands."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
MANAGED = ('etc/mkinitcpio.conf', 'etc/default/grub', 'boot/grub/grub.cfg',
           'usr/lib/arc-rebar/arc-rebar-boot', 'etc/initcpio/install/arc-rebar',
           'etc/initcpio/hooks/arc-rebar', 'var/lib/arc-rebar/hook-origin')


class ArchInstallerTests(unittest.TestCase):
    def run_entrypoint(self, args, arch=True, debian=False, helper=True, untouched=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            (root / 'etc').mkdir()
            if arch:
                (root / 'etc/mkinitcpio.conf').write_text('HOOKS=(base udev kms)\n')
            if debian:
                (root / 'etc/initramfs-tools').mkdir()
            text = (REPO / 'install.sh').read_text()
            for prefix in ('/etc/', '/boot/', '/var/lib/', '/proc/'):
                text = text.replace(prefix, str(root) + prefix)
            (source / 'install.sh').write_text(text)
            # A developer checkout: the integrity self-check allows it without a release manifest.
            shutil.copyfile(REPO / 'selfcheck.sh', source / 'selfcheck.sh')
            (source / '.git').mkdir()
            if helper:
                handoff = source / 'install-arch.sh'
                handoff.write_text('#!/bin/sh\nprintf "arch: %s\\n" "$*"\nexit 23\n')
                handoff.chmod(0o755)
            mock = root / 'mock'
            mock.mkdir()
            for name, body in {
                'id': 'echo 0',
                'update-initramfs': f'touch "{root}/backend-probed"; exit 99',
            }.items():
                command = mock / name
                command.write_text('#!/bin/sh\n' + body + '\n')
                command.chmod(0o755)
            result = subprocess.run(
                ['bash', str(source / 'install.sh'), *args],
                env=dict(os.environ, PATH=str(mock) + ':' + os.environ['PATH']),
                capture_output=True, text=True, timeout=10)
            if untouched:
                self.assertFalse((root / 'backend-probed').exists())
                self.assertFalse((root / 'var').exists())
            return result.returncode, result.stdout + result.stderr

    def test_entrypoint_hands_off_before_debian_backend_checks(self):
        rc, out = self.run_entrypoint(['--experimental-arch', '--yes', '--reinstall'])
        self.assertEqual(rc, 23, out)
        # The integrity self-check runs first, then the hand-off is the only other output.
        self.assertIn('== INTEGRITY: is this the official, unmodified arc-rebar? ==', out)
        self.assertTrue(out.endswith('arch: --experimental-arch --yes --reinstall\n'), out)

    def test_entrypoint_hands_off_to_arch_without_any_flag(self):
        # Arch is a normal install: no opt-in flag is needed.
        for args in ([], ['--yes'], ['--yes', '--reinstall']):
            with self.subTest(args=args):
                rc, out = self.run_entrypoint(args)
                self.assertEqual(rc, 23, out)
                self.assertTrue(out.endswith('arch: ' + ' '.join(args) + '\n'), out)
                self.assertNotIn('experimental', out)

    def test_initramfs_tools_takes_precedence_and_old_flag_is_harmless(self):
        # initramfs-tools takes precedence even if mkinitcpio is also present; the old
        # --experimental-arch flag is accepted and ignored.
        for arch in (False, True):
            # The Debian installer proceeds normally (its own backend checks run).
            rc, out = self.run_entrypoint(['--experimental-arch', '--yes'],
                                          arch=arch, debian=True, untouched=False)
            self.assertNotIn('arch: ', out)
            self.assertNotIn('usage:', out)

    def test_entrypoint_reports_missing_arch_source(self):
        rc, out = self.run_entrypoint([], helper=False)
        self.assertEqual(rc, 2, out)
        self.assertIn('install the Arch package', out)

    def run_fixture(self, mode='ok', reinstall=False, uninstall=False,
                    missing=False, cmdline=True, grubfail=False, hookfail=False,
                    hooks=None, override=False, experimental=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            for name in ('install-arch.sh', 'uninstall-arch.sh', 'arch-transaction.sh'):
                text = (REPO / name).read_text()
                for prefix in ('/etc/', '/boot/', '/efi/', '/var/lib/arc-rebar',
                               '/usr/lib/arc-rebar', '/proc/cmdline'):
                    text = text.replace(prefix, str(root) + prefix)
                (source / name).write_text(text)
            shutil.copyfile(REPO / 'selfcheck.sh', source / 'selfcheck.sh')
            (source / '.git').mkdir()
            for name in ('mkinitcpio/install/arc-rebar', 'mkinitcpio/hooks/arc-rebar'):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / name, path)
            boot = source / 'scripts/init-premount/arc-rebar'
            boot.parent.mkdir(parents=True)
            boot.write_text('#!/bin/sh\nprintf dryrun >> "$FIXTURE/probes"\necho "arc-rebar: PLAN: act gpu=mock"\n')
            for name, content in {
                'etc/mkinitcpio.conf': 'MODULES=()\nHOOKS=(base udev kms filesystems)   \n',
                'etc/default/grub': "GRUB_CMDLINE_LINUX_DEFAULT='quiet'\n",
                'boot/grub/grub.cfg': 'original grub menu\n',
                'boot/initramfs-linux.img': 'original image\n',
                'proc/cmdline': 'pci=realloc\n' if cmdline else 'quiet\n',
            }.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            if cmdline:
                (root / 'etc/default/grub').write_text("GRUB_CMDLINE_LINUX_DEFAULT='quiet pci=realloc'\n")
            if reinstall or uninstall:
                (root / 'etc/mkinitcpio.conf').write_text('HOOKS=(base udev arc-rebar kms filesystems)   \n')
                for name in MANAGED[3:]:
                    p = root / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text('previous ' + name + '\n')
                    p.chmod(0o750)
            if hooks is not None:
                (root / 'etc/mkinitcpio.conf').write_text(hooks)
            if override:
                (root / 'etc/mkinitcpio.conf.d').mkdir()
                (root / 'etc/mkinitcpio.conf.d/custom.conf').write_text('HOOKS=(systemd)\n')
            before = {name: ((root / name).read_bytes(), (root / name).stat().st_mode)
                      if (root / name).exists() else None for name in MANAGED}
            binpath = root / 'bin'
            binpath.mkdir()
            stubs = {
                'id': 'echo 0',
                'setpci': 'printf setpci >> "$FIXTURE/probes"; exit 0',
                'dmesg': 'echo "arc-rebar: PLAN: done gpu=mock"',
                'mkinitcpio': '''n=0
[ ! -f "$FIXTURE/count" ] || n=$(cat "$FIXTURE/count")
n=$((n+1)); echo "$n" > "$FIXTURE/count"
echo "build $n" > "$FIXTURE/boot/initramfs-linux.img"
echo "build attempt $n"
case "$MODE:$n" in fail-all:*|fail-first:1) exit 7;; esac
exit 0''',
                'grub-mkconfig': '''echo changed > "$FIXTURE/boot/grub/grub.cfg"
echo "grub generation output"
exit "$GRUBFAIL"''',
                'lsinitcpio': '''echo arc-rebar-boot
echo usr/bin/setpci
echo hooks/arc-rebar
[ "$MISSING" = 1 ] || echo usr/bin/tr
exit 0''',
            }
            if hookfail:
                stubs['install'] = 'echo "simulated file copy failure" >&2; exit 8'
            for name, body in stubs.items():
                p = binpath / name
                p.write_text('#!/bin/bash\n' + body + '\n')
                p.chmod(0o755)
            env = dict(os.environ, PATH=str(binpath) + ':' + os.environ['PATH'],
                       FIXTURE=str(root), MODE=mode, MISSING=str(int(missing)), GRUBFAIL=str(int(grubfail)))
            args = ['bash', str(source / ('uninstall-arch.sh' if uninstall else 'install-arch.sh'))]
            if not uninstall:
                args += (['--experimental-arch'] if experimental else [])
                args += ['--yes'] + (['--reinstall'] if reinstall else [])
            p = subprocess.run(args, env=env, text=True, capture_output=True, timeout=10)
            after = {name: ((root / name).read_bytes(), (root / name).stat().st_mode)
                     if (root / name).exists() else None for name in MANAGED}
            backups = list((root / 'var/lib/arc-rebar/backups').glob('change.*'))
            logs = {f.name: f.read_text() for b in backups for f in b.glob('*.log')}
            logs['probes'] = (root / 'probes').read_text() if (root / 'probes').exists() else ''
            calls = int((root / 'count').read_text()) if (root / 'count').exists() else 0
            return p.returncode, p.stdout + p.stderr, before, after, logs, calls, bool(backups)

    def assert_restored(self, result):
        rc, out, before, after, logs, calls, backup = result
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn('Installed. Next:', out)
        self.assertEqual(before, after, out)
        self.assertTrue(backup)
        return out, logs, calls

    def test_arch_install_needs_no_opt_in_flag(self):
        # Without the old --experimental-arch flag the install runs normally.
        rc, out, before, after, logs, calls, backup = self.run_fixture(experimental=False)
        self.assertEqual(rc, 0, out)
        self.assertNotIn('experimental', out)
        self.assertNotEqual(logs['probes'], '')

    def test_success_retains_backup_and_correct_order(self):
        rc, out, before, after, logs, calls, backup = self.run_fixture()
        self.assertEqual(rc, 0, out)
        self.assertIn('Installed. Next:', out)
        self.assertIn(b'udev arc-rebar kms', after['etc/mkinitcpio.conf'][0])
        self.assertEqual(calls, 1)
        self.assertTrue(backup)
        self.assertIn('build attempt 1', logs['build.log'])

    def test_failed_build_cannot_pass_using_old_image(self):
        out, logs, calls = self.assert_restored(self.run_fixture(mode='fail-first'))
        self.assertIn('mkinitcpio failed', out)
        self.assertEqual(calls, 2)
        self.assertIn('build attempt 1', logs['build.log'])

    def test_recovery_failure_explicit_and_nonzero(self):
        out, logs, calls = self.assert_restored(self.run_fixture(mode='fail-all'))
        self.assertIn('Do not reboot', out)
        self.assertIn('build attempt 2', logs['recovery-build.log'])

    def test_failed_reinstall_preserves_previous_installation(self):
        self.assert_restored(self.run_fixture(mode='fail-first', reinstall=True))

    def test_failed_postcheck_restores_previous_installation(self):
        result = self.run_fixture(missing=True, reinstall=True)
        self.assertEqual(result[0], 3, result[1])
        self.assert_restored(result)

    def test_grub_failure_restores_config_and_menu(self):
        out, logs, calls = self.assert_restored(self.run_fixture(cmdline=False, grubfail=True))
        self.assertIn('grub-mkconfig failed', out)
        self.assertIn('grub generation output', logs['grub-build.log'])

    def test_copy_failure_aborts_before_success(self):
        self.assert_restored(self.run_fixture(hookfail=True))

    def test_uninstall_failure_restores_hooks(self):
        self.assert_restored(self.run_fixture(mode='fail-first', uninstall=True))

    def test_reinstall_moves_existing_hook_before_kms(self):
        rc, out, before, after, logs, calls, backup = self.run_fixture(
            reinstall=True, hooks='HOOKS=(base udev kms arc-rebar filesystems)\n')
        self.assertEqual(rc, 0, out)
        self.assertIn(b'udev arc-rebar kms', after['etc/mkinitcpio.conf'][0])

    def test_unsupported_config_refused_without_mutation(self):
        for hooks in ('HOOKS=(base systemd kms)\n', 'HOOKS=(base kms udev)\n',
                      'HOOKS=(base udev)\n', 'HOOKS=(\nbase udev kms\n)\n',
                      'HOOKS=(base udev kms)\nHOOKS=(base systemd kms)\n'):
            rc, out, before, after, logs, calls, backup = self.run_fixture(hooks=hooks)
            self.assertNotEqual(rc, 0, out)
            self.assertEqual(before, after)
            self.assertEqual(calls, 0)
            self.assertFalse(backup)

    def test_dropin_refused_without_mutation(self):
        rc, out, before, after, logs, calls, backup = self.run_fixture(override=True)
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(before, after)
        self.assertEqual(calls, 0)

    def test_quoted_hooks_supported(self):
        rc, out, before, after, logs, calls, backup = self.run_fixture(
            hooks='HOOKS=("base" "udev" "kms" "filesystems")\n')
        self.assertEqual(rc, 0, out)
        self.assertIn(b'udev arc-rebar kms', after['etc/mkinitcpio.conf'][0])

    def test_uninstall_success(self):
        rc, out, before, after, logs, calls, backup = self.run_fixture(uninstall=True)
        self.assertEqual(rc, 0, out)
        self.assertNotIn(b'arc-rebar', after['etc/mkinitcpio.conf'][0])
        for name in MANAGED[3:]:
            self.assertIsNone(after[name])
        self.assertTrue(backup)


if __name__ == '__main__':
    unittest.main()
