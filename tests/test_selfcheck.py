"""Integrity self-check: genuine copies pass; modified, unsigned or wrongly signed copies are refused.

Uses a throwaway OpenPGP key in a temporary GNUPGHOME, never the maintainer's key.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
HAVE_GPG = all(shutil.which(t) for t in ('gpg', 'gpgv', 'sha256sum'))


@unittest.skipUnless(HAVE_GPG, 'gpg/gpgv not installed')
class SelfCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.gnupg = self.tmp / 'gnupg'
        self.gnupg.mkdir(mode=0o700)
        self.env = dict(os.environ, GNUPGHOME=str(self.gnupg))
        self.key = self.make_key('Test Maintainer <maintainer@example.invalid>')
        self.copy = self.tmp / 'arc-rebar'
        (self.copy / 'scripts/init-premount').mkdir(parents=True)
        (self.copy / 'docs').mkdir()
        shutil.copyfile(REPO / 'selfcheck.sh', self.copy / 'selfcheck.sh')
        shutil.copyfile(REPO / 'scripts/init-premount/arc-rebar', self.copy / 'scripts/init-premount/arc-rebar')
        shutil.copyfile(REPO / 'LICENSE', self.copy / 'LICENSE')
        self.sign_release(self.key)

    def make_key(self, uid):
        subprocess.run(['gpg', '--batch', '--passphrase', '', '--quick-generate-key', uid, 'ed25519', 'sign', '1d'],
                       env=self.env, check=True, capture_output=True)
        out = subprocess.run(['gpg', '--with-colons', '--list-keys', uid], env=self.env,
                             check=True, capture_output=True, text=True).stdout
        return next(l.split(':')[9] for l in out.splitlines() if l.startswith('fpr'))

    def sign_release(self, key, keyring_key=None):
        files = ['LICENSE', 'scripts/init-premount/arc-rebar', 'selfcheck.sh']
        sums = subprocess.run(['sha256sum', *files], cwd=self.copy, check=True,
                              capture_output=True, text=True).stdout
        (self.copy / 'MANIFEST.sha256').write_text(sums)
        subprocess.run(['gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--passphrase', '',
                        '--local-user', key, '--armor', '--detach-sign', '--output',
                        str(self.copy / 'MANIFEST.sha256.asc'), str(self.copy / 'MANIFEST.sha256')],
                       env=self.env, check=True, capture_output=True)
        with open(self.copy / 'docs/signing-key.gpg', 'wb') as out:
            subprocess.run(['gpg', '--export', keyring_key or key], env=self.env, check=True, stdout=out)

    def check(self):
        p = subprocess.run(['sh', '-c', '. ./selfcheck.sh; arc_selfcheck "$PWD"'], cwd=self.copy,
                           env=self.env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_genuine_copy_passes(self):
        rc, out = self.check()
        self.assertEqual(rc, 0, out)
        self.assertIn('signed by the arc-rebar maintainer', out)
        self.assertIn('all files match the official release', out)

    def test_removed_notice_is_refused(self):
        boot = self.copy / 'scripts/init-premount/arc-rebar'
        boot.write_text(''.join(l for l in boot.read_text().splitlines(True) if 'Copyright' not in l))
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('files differ from the official release', out)
        self.assertIn('scripts/init-premount/arc-rebar', out)

    def test_changed_licence_is_refused(self):
        lic = self.copy / 'LICENSE'
        lic.write_text(lic.read_text().replace('Rod Burlamaqui', 'Someone Else'))
        rc, out = self.check()
        self.assertEqual(rc, 1, out)

    def test_rewritten_manifest_without_maintainer_key_is_refused(self):
        # An imitator edits a file and regenerates the manifest, signing with their own key,
        # but the shipped keyring still holds the maintainer key: the signature check fails.
        (self.copy / 'LICENSE').write_text('rebranded\n')
        other = self.make_key('Imitator <imitator@example.invalid>')
        self.sign_release(other, keyring_key=self.key)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('not signed by the arc-rebar maintainer', out)

    def test_missing_signature_is_refused(self):
        (self.copy / 'MANIFEST.sha256.asc').unlink()
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('no maintainer signature', out)

    def test_missing_manifest_is_refused_outside_a_checkout(self):
        (self.copy / 'MANIFEST.sha256').unlink()
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('integrity manifest missing', out)

    def test_installer_refuses_a_modified_copy_before_any_change(self):
        (self.copy / 'LICENSE').write_text('rebranded\n')
        p = subprocess.run(['sh', '-c', '. ./selfcheck.sh; arc_selfcheck_or_refuse "$PWD"; echo SHOULD-NOT-RUN'],
                           cwd=self.copy, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 4, p.stdout)
        self.assertIn('REFUSING: this copy of arc-rebar has been modified', p.stdout)
        self.assertNotIn('SHOULD-NOT-RUN', p.stdout)


if __name__ == '__main__':
    unittest.main()
