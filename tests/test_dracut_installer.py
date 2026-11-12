"""dracut installer/uninstaller (Fedora, RHEL, Rocky, Alma, openSUSE) in a path-rewritten fake root.

Never touches the host: every system path in the scripts is rewritten into a temporary
directory, and dracut, lsinitrd, uname and id are mocks.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
KV = '6.12.0-test'
PREFIXES = ['/usr/lib/dracut', '/usr/lib/modules', '/lib/modules', '/var/lib/arc-rebar',
            '/proc/cmdline', '/boot', '/efi', '/etc']


def rewrite(text, root):
    for prefix in PREFIXES:
        text = re.sub(r'(?<![A-Za-z0-9_./-])' + re.escape(prefix) + r'(?=[/ "\'*]|$)', str(root) + prefix, text,
                      flags=re.M)
    return text


class DracutInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / 'root'
        self.src = self.tmp / 'src'
        self.mock = self.tmp / 'mock'
        for d in ('etc/dracut.conf.d', 'boot', 'var/lib', 'usr/lib/dracut/modules.d', 'proc'):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        (self.root / 'proc/cmdline').write_text('quiet pci=realloc\n')
        self.image = self.root / f'boot/initramfs-{KV}.img'
        self.image.write_text('original image\n')
        self.src.mkdir(); (self.src / '.git').mkdir()   # developer checkout for the self-check
        for name in ('install-dracut.sh', 'uninstall-dracut.sh', 'dracut-transaction.sh'):
            text = rewrite((REPO / name).read_text(), self.root)
            code = [l for l in text.splitlines() if not l.lstrip().startswith('#')]
            for prefix in PREFIXES:
                stray = [l for l in code if re.search(r'(?<![A-Za-z0-9_./-])' + re.escape(prefix) + r'(?=[/ "\'*]|$)', l)]
                self.assertEqual(stray, [], f'{name}: unrewritten {prefix}')
            (self.src / name).write_text(text)
        shutil.copyfile(REPO / 'selfcheck.sh', self.src / 'selfcheck.sh')
        shutil.copyfile(REPO / 'DISCLAIMER.md', self.src / 'DISCLAIMER.md')
        shutil.copyfile(REPO / 'LICENSE', self.src / 'LICENSE')
        mod = self.src / 'dracut/90arc-rebar'; mod.mkdir(parents=True)
        for f in ('module-setup.sh', 'arc-rebar-hook.sh'):
            shutil.copyfile(REPO / 'dracut/90arc-rebar' / f, mod / f)
        boot = self.src / 'scripts/init-premount/arc-rebar'; boot.parent.mkdir(parents=True)
        boot.write_text('#!/bin/sh\necho "arc-rebar: PLAN: act gpu=mock"\n')
        self.mock.mkdir()
        conf = self.root / 'etc/dracut.conf.d/90-arc-rebar.conf'
        mocks = {
            'id': 'echo 0',
            'uname': f'echo {KV}',
            'setpci': 'exit 0',
            'grubby': 'exit 0',
            'dmesg': 'exit 0',
            # dracut: rebuild the image; include arc-rebar only when the conf enables it.
            'dracut': f'''echo call >> "{self.tmp}/dracut-calls"
if [ "$FAIL" = hup ] && [ ! -e "{self.tmp}/hup-sent" ]; then touch "{self.tmp}/hup-sent"; kill -HUP $PPID; sleep 1; fi
[ "$FAIL" != dracut ] || exit 1
if [ -e "{conf}" ] && [ "$FAIL" != post ]; then
  printf 'usr/lib/arc-rebar/arc-rebar-boot\\nusr/bin/setpci\\nvar/lib/dracut/hooks/pre-udev/30-arc-rebar-hook.sh\\n' > "{self.image}"
else
  echo 'rebuilt without arc-rebar' > "{self.image}"
fi''',
            'lsinitrd': 'cat "$1"',
        }
        for name, body in mocks.items():
            p = self.mock / name
            p.write_text('#!/bin/sh\n' + body + '\n'); p.chmod(0o755)
        self.conf = conf
        self.module = self.root / 'usr/lib/dracut/modules.d/90arc-rebar'

    def run_script(self, name, *args, fail=''):
        env = dict(os.environ, PATH=f'{self.mock}:{os.environ["PATH"]}', FAIL=fail)
        p = subprocess.run(['bash', str(self.src / name), *args], env=env,
                           capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout + p.stderr

    def backups(self):
        d = self.root / 'var/lib/arc-rebar/backups'
        return sorted(d.iterdir()) if d.exists() else []

    def test_install_succeeds_and_post_checks_pass(self):
        rc, out = self.run_script('install-dracut.sh', '--yes')
        self.assertEqual(rc, 0, out)
        self.assertIn('all post-checks passed', out)
        self.assertTrue(self.conf.exists())
        self.assertTrue((self.module / 'arc-rebar-boot').exists())
        self.assertIn('arc-rebar-boot', self.image.read_text())
        self.assertNotIn('experimental', out.lower())

    def test_unsupported_layout_is_refused_before_any_change(self):
        # H1: Debian-style naming (and other layouts) cannot be backed up and restored.
        self.image.unlink()
        (self.root / f'boot/initrd.img-{KV}').write_text('debian-style image\n')
        rc, out = self.run_script('install-dracut.sh', '--yes')
        self.assertNotEqual(rc, 0, out)
        self.assertIn('unsupported boot image layout', out)
        self.assertFalse(self.conf.exists())
        self.assertFalse((self.tmp / 'dracut-calls').exists())
        self.assertEqual(self.backups(), [])

    def test_unified_kernel_image_is_refused(self):
        uki = self.root / 'boot/efi/EFI/Linux/linux.efi'
        uki.parent.mkdir(parents=True); uki.write_text('uki\n')
        rc, out = self.run_script('install-dracut.sh', '--yes')
        self.assertNotEqual(rc, 0, out)
        self.assertIn('unsupported boot image layout', out)
        self.assertFalse(self.conf.exists())

    def test_failed_post_check_restores_everything(self):
        rc, out = self.run_script('install-dracut.sh', '--yes', fail='post')
        self.assertEqual(rc, 3, out)
        self.assertIn('Previous settings and boot images restored', out)
        self.assertFalse(self.conf.exists())
        self.assertFalse(self.module.exists())
        self.assertEqual(self.image.read_text(), 'original image\n')

    def test_dracut_failure_restores_everything(self):
        rc, out = self.run_script('install-dracut.sh', '--yes', fail='dracut')
        self.assertNotEqual(rc, 0, out)
        self.assertFalse(self.conf.exists())
        self.assertEqual(self.image.read_text(), 'original image\n')

    def test_ssh_drop_during_rebuild_rolls_back(self):
        # H7: SIGHUP (closed SSH session) must roll back like INT/TERM.
        rc, out = self.run_script('install-dracut.sh', '--yes', fail='hup')
        self.assertEqual(rc, 129, out)
        self.assertIn('restoring the previous state', out)
        self.assertFalse(self.conf.exists())
        self.assertFalse(self.module.exists())
        self.assertEqual(self.image.read_text(), 'original image\n')

    def test_uninstall_removes_hook_and_rebuilds(self):
        rc, out = self.run_script('install-dracut.sh', '--yes')
        self.assertEqual(rc, 0, out)
        rc, out = self.run_script('uninstall-dracut.sh')
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.conf.exists())
        self.assertFalse(self.module.exists())
        self.assertEqual(self.image.read_text(), 'rebuilt without arc-rebar\n')

    def test_failed_uninstall_keeps_previous_installation(self):
        self.run_script('install-dracut.sh', '--yes')
        installed = self.image.read_text()
        rc, out = self.run_script('uninstall-dracut.sh', fail='dracut')
        self.assertNotEqual(rc, 0, out)
        self.assertTrue(self.conf.exists())
        self.assertEqual(self.image.read_text(), installed)


if __name__ == '__main__':
    unittest.main()
