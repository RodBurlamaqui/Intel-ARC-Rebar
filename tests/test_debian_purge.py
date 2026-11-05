"""Purge maintainer-script regressions; all managed paths/builds are simulated."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class PurgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'var/lib/arc-rebar'
        self.tx = self.state / 'purge-transaction'
        for d in ('etc/initramfs-tools/hooks', 'etc/initramfs-tools/scripts/init-premount',
                  'etc/default', 'boot/grub', 'var/lib/arc-rebar', 'tools'):
            (self.root / d).mkdir(parents=True)
        self.put('etc/initramfs-tools/hooks/arc-rebar', 'previous hook\n').chmod(0o750)
        self.put('etc/initramfs-tools/scripts/init-premount/arc-rebar', 'previous boot script\n').chmod(0o750)
        self.put('var/lib/arc-rebar/hook-origin', 'deb\n')
        self.put('etc/default/grub', 'unchanged user GRUB config\n')
        self.put('boot/grub/grub.cfg', 'original GRUB menu\n')
        self.put('boot/initrd.img-first', 'first original image\n')
        self.put('boot/initrd.img-second', 'second original image\n')
        self.put('boot/initrd.img-first.bak', 'pre-existing image backup\n')
        source = (REPO / 'debian/postrm').read_text()
        for prefix in ('/etc/', '/boot/', '/var/lib/'):
            source = source.replace(prefix, str(self.root) + prefix)
        self.put('postrm', source)
        self.tools = self.root / 'tools'
        for cmd in ('flock', 'cat', 'rm', 'cp', 'mv', 'mkdir', 'touch', 'grep'):
            (self.tools / cmd).symlink_to(shutil.which(cmd))
        self.tool('sync', 'exit 0')
        self.tool('grep', '''if [ "$FAIL" = grep-inspect ]; then
    case "$3" in */purge-transaction/contents) exit 2;; esac
fi
if [ "$FAIL" = grep-restore ]; then
    case "$4" in */purge-transaction/images) exit 2;; esac
fi
exec /bin/grep "$@"''')
        self.tool('cp', '''[ "$FAIL" != snapshot ] || exit 96
if [ "$FAIL" = restore ]; then
    case "$3" in *purge-transaction/files/*) exit 95;; esac
fi
/bin/cp "$@"''')
        self.tool('update-initramfs', f'''printf '%s\\n' "$*" >> "{self.root}/calls"
[ "$*" = '-u -k all' ] || exit 98
[ "$FAIL" != stale ] || exit 0
printf rebuilt > "{self.root}/boot/initrd.img-first"
printf rebuilt > "{self.root}/boot/initrd.img-second"
printf generated > "{self.root}/boot/initrd.img-second.bak"
if [ -n "$FAIL" ]; then
    printf changed > "{self.root}/boot/grub/grub.cfg"
fi
[ "$FAIL" != kill ] || kill -KILL "$PPID"
[ "$FAIL" != term ] || kill -TERM "$PPID"
[ "$FAIL" != rebuild ] && [ "$FAIL" != restore ] && [ "$FAIL" != grep-restore ]''')
        self.tool('lsinitramfs', '''[ "$FAIL" != inspect ] || exit 94
contents=$(cat "$1") || exit 93
case "$contents" in *original*) echo scripts/init-premount/arc-rebar;; *) echo init;; esac''')
        self.env = dict(os.environ, PATH=str(self.tools), FAIL='')

    def put(self, relative, text):
        p = self.root / relative
        p.write_text(text)
        return p

    def tool(self, name, body):
        p = self.tools / name
        if p.exists() or p.is_symlink():
            p.unlink()
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)

    def run_purge(self, failure='', action='purge'):
        return subprocess.run(['/bin/sh', str(self.root / 'postrm'), action],
                              env=dict(self.env, FAIL=failure), text=True,
                              capture_output=True, timeout=10)

    def snapshot(self):
        result = {}
        for directory in ('etc', 'boot'):
            for p in (self.root / directory).rglob('*'):
                if p.is_file():
                    result[str(p.relative_to(self.root))] = (p.read_bytes(), p.stat().st_mode & 0o777)
        origin = self.state / 'hook-origin'
        result['origin'] = (origin.read_bytes(), origin.stat().st_mode & 0o777) if origin.exists() else None
        return result

    def test_success_updates_all_kernels_and_keeps_grub(self):
        result = self.run_purge()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / 'etc/initramfs-tools/hooks/arc-rebar').exists())
        self.assertFalse((self.root / 'etc/initramfs-tools/scripts/init-premount/arc-rebar').exists())
        self.assertFalse((self.state / 'hook-origin').exists())
        self.assertEqual((self.root / 'calls').read_text(), '-u -k all\n')
        self.assertEqual((self.root / 'etc/default/grub').read_text(), 'unchanged user GRUB config\n')
        self.assertFalse(self.tx.exists())

    def test_rebuild_failures_restore_files_images_modes_and_new_backups(self):
        for failure in ('rebuild', 'term', 'stale', 'inspect', 'grep-inspect'):
            with self.subTest(failure=failure):
                before = self.snapshot()
                result = self.run_purge(failure)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, self.snapshot(), result.stdout + result.stderr)
                self.assertFalse((self.tx / 'active').exists())
                self.assertIn('previous hooks/images restored', result.stderr)

    def test_missing_updater_refuses_before_mutation(self):
        (self.tools / 'update-initramfs').unlink()
        before = self.snapshot()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tx.exists())
        self.assertIn('no hooks removed', result.stderr)

    def test_partial_hook_installations_are_cleaned(self):
        for name in ('hooks/arc-rebar', 'scripts/init-premount/arc-rebar'):
            with self.subTest(missing=name):
                self.put('var/lib/arc-rebar/hook-origin', 'deb\n')
                for relative in ('hooks/arc-rebar', 'scripts/init-premount/arc-rebar'):
                    self.put('etc/initramfs-tools/' + relative, 'old\n')
                (self.root / 'etc/initramfs-tools' / name).unlink()
                result = self.run_purge()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((self.root / 'etc/initramfs-tools/hooks/arc-rebar').exists())
                self.assertFalse((self.root / 'etc/initramfs-tools/scripts/init-premount/arc-rebar').exists())
                self.assertFalse((self.state / 'hook-origin').exists())

    def test_missing_archive_inspector_refuses_before_mutation(self):
        (self.tools / 'lsinitramfs').unlink()
        before = self.snapshot()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tx.exists())
        self.assertFalse((self.root / 'calls').exists())

    def test_missing_grep_refuses_before_mutation(self):
        (self.tools / 'grep').unlink()
        before = self.snapshot()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tx.exists())
        self.assertFalse((self.root / 'calls').exists())

    def test_unknown_and_source_ownership_preserved(self):
        for origin in ('source:separate-checkout\n', '', 'unknown\n'):
            with self.subTest(origin=origin):
                self.put('var/lib/arc-rebar/hook-origin', origin)
                before = self.snapshot()
                result = self.run_purge()
                self.assertEqual(result.returncode, 0)
                self.assertEqual(before, self.snapshot())
                self.assertFalse((self.root / 'calls').exists())

    def test_non_purge_actions_do_not_change_state(self):
        before = self.snapshot()
        for action in ('remove', 'upgrade', 'abort-install', 'failed-upgrade'):
            result = self.run_purge(action=action)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(before, self.snapshot())
            self.assertFalse((self.root / 'calls').exists())

    def test_snapshot_failure_does_not_remove_hooks(self):
        before = self.snapshot()
        result = self.run_purge('snapshot')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.tx / 'active').exists())
        self.assertFalse((self.root / 'calls').exists())

    def test_failed_restoration_can_be_retried(self):
        before = self.snapshot()
        result = self.run_purge('restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RECOVERY FAILED', result.stderr)
        self.assertTrue((self.tx / 'active').exists())
        # Restore is retried before tool preflight; removing the tool prevents
        # starting another purge and lets us inspect the recovered old state.
        (self.tools / 'update-initramfs').unlink()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot(), result.stderr)
        self.assertFalse(self.tx.exists())

    def test_sigkill_retry_restores_before_any_new_purge(self):
        before = self.snapshot()
        result = self.run_purge('kill')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.tx / 'active').exists())
        (self.tools / 'update-initramfs').unlink()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot(), result.stderr)
        self.assertFalse(self.tx.exists())

    def test_restore_matcher_error_retains_journal_without_deleting_unknown_images(self):
        before = self.snapshot()
        result = self.run_purge('grep-restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RECOVERY FAILED', result.stderr)
        self.assertTrue((self.tx / 'active').exists())
        # Failure to read the old image list must not authorize deleting files.
        self.assertTrue((self.root / 'boot/initrd.img-second.bak').exists())
        for key, value in before.items():
            self.assertEqual(value, self.snapshot()[key])
        (self.tools / 'update-initramfs').unlink()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot(), result.stderr)
        self.assertFalse(self.tx.exists())

    def test_active_installation_transaction_blocks_purge(self):
        (self.state / 'install-transaction').mkdir()
        before = self.snapshot()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tx.exists())
        self.assertFalse((self.root / 'calls').exists())

    def test_lock_contention_refuses_without_mutation(self):
        before = self.snapshot()
        with (self.state / 'install.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tx.exists())

    def test_symlink_destination_is_refused(self):
        p = self.root / 'boot/initrd.img-second'
        p.unlink()
        p.symlink_to(self.root / 'boot/initrd.img-first')
        before = self.snapshot()
        result = self.run_purge()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(p.is_symlink())
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.tx.exists())


if __name__ == '__main__':
    unittest.main()
