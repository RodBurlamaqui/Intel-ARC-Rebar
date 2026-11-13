"""Integrity self-check: genuine copies pass; modified, unsigned or wrongly signed copies are refused.

Uses a throwaway OpenPGP key in a temporary GNUPGHOME, never the maintainer's key: the
copies under test have the pinned maintainer fingerprint replaced by the test key's.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
HAVE_GPG = all(shutil.which(t) for t in ('gpg', 'gpgv', 'sha256sum'))
MAINTAINER_FPR = 'C3CFCBF8EE592C27BCBE1E498D8ED73D0C2DE44B'
FILES = ['DISCLAIMER.md', 'LICENSE', 'dracut-transaction.sh', 'dracut/90arc-rebar/arc-rebar-hook.sh',
         'dracut/90arc-rebar/module-setup.sh', 'install-dracut.sh', 'scripts/init-premount/arc-rebar', 'selfcheck.sh']


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
        (self.copy / 'dracut/90arc-rebar').mkdir(parents=True)
        for f in FILES:   # pin the test key in place of the maintainer's
            (self.copy / f).write_text((REPO / f).read_text().replace(MAINTAINER_FPR, self.key))
        self.sign_release(self.key)

    def make_key(self, uid, *faked_time):
        subprocess.run(['gpg', '--batch', *faked_time, '--passphrase', '', '--quick-generate-key', uid, 'ed25519', 'sign', '2y'],
                       env=self.env, check=True, capture_output=True)
        out = subprocess.run(['gpg', '--with-colons', '--list-keys', uid], env=self.env,
                             check=True, capture_output=True, text=True).stdout
        return next(l.split(':')[9] for l in out.splitlines() if l.startswith('fpr'))

    def sign_release(self, key, keyring_key=None, faked_time=()):
        sums = subprocess.run(['sha256sum', *FILES], cwd=self.copy, check=True,
                              capture_output=True, text=True).stdout
        (self.copy / 'MANIFEST.sha256').write_text(sums)
        subprocess.run(['gpg', '--batch', *faked_time, '--yes', '--pinentry-mode', 'loopback', '--passphrase', '',
                        '--local-user', key, '--armor', '--detach-sign', '--output',
                        str(self.copy / 'MANIFEST.sha256.asc'), str(self.copy / 'MANIFEST.sha256')],
                       env=self.env, check=True, capture_output=True)
        with open(self.copy / 'docs/signing-key.gpg', 'wb') as out:
            subprocess.run(['gpg', '--export', keyring_key or key], env=self.env, check=True, stdout=out)

    def check(self, env=None):
        p = subprocess.run(['sh', '-c', '. ./selfcheck.sh; arc_selfcheck "$PWD"'], cwd=self.copy,
                           env=env or self.env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def run_installer(self, **extra_env):
        """install-dracut.sh up to its integrity checks (id is mocked to root)."""
        mock = self.tmp / 'mock'; mock.mkdir(exist_ok=True)
        (mock / 'id').write_text('#!/bin/sh\necho 0\n'); (mock / 'id').chmod(0o755)
        env = dict(self.env, PATH=f'{mock}:{os.environ["PATH"]}', **extra_env)
        p = subprocess.run(['bash', str(self.copy / 'install-dracut.sh'), '--yes'], env=env,
                           capture_output=True, text=True, timeout=30)
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

    # --- bypass attempts (medium 1) ---
    def test_substituted_keyring_is_refused(self):
        # An imitator re-signs with their own key AND ships their own key as the keyring:
        # only the pinned maintainer fingerprint is accepted.
        (self.copy / 'LICENSE').write_text('rebranded\n')
        other = self.make_key('Imitator <imitator@example.invalid>')
        self.sign_release(other)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('not signed by the arc-rebar maintainer', out)

    def test_deleted_keyring_is_refused(self):
        (self.copy / 'docs/signing-key.gpg').unlink()
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('maintainer key (docs/signing-key.gpg) is missing', out)

    def test_missing_gpgv_is_refused(self):
        bindir = self.tmp / 'bin'; bindir.mkdir()
        for tool in ('sh', 'sha256sum', 'grep', 'sed', 'cat', 'date'):
            os.symlink(shutil.which(tool), bindir / tool)
        rc, out = self.check(env=dict(self.env, PATH=str(bindir)))
        self.assertEqual(rc, 1, out)
        self.assertIn('gpgv is needed', out)

    def test_fake_git_checkout_without_manifest_is_refused(self):
        for f in ('MANIFEST.sha256', 'MANIFEST.sha256.asc'):
            (self.copy / f).unlink()
        (self.copy / '.git').mkdir()
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('integrity manifest missing', out)
        rc, out = self.check(env=dict(self.env, ARC_REBAR_DEV='1'))
        self.assertEqual(rc, 0, out)
        self.assertIn('developer mode', out)

    def test_deleted_required_file_is_refused(self):
        (self.copy / 'DISCLAIMER.md').unlink()
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn('required file missing: DISCLAIMER.md', out)

    def test_installer_refuses_an_edited_checker(self):
        # Neutralising selfcheck.sh alone is caught by the installer's independent check.
        sc = self.copy / 'selfcheck.sh'
        sc.write_text(sc.read_text().replace('arc_selfcheck() {', 'arc_selfcheck() { return 0\n'))
        rc, out = self.run_installer()
        self.assertEqual(rc, 4, out)
        self.assertIn('REFUSING: this copy of arc-rebar has been modified', out)

    def test_installer_requires_its_own_files(self):
        (self.copy / 'install-dracut.sh').write_text(
            (self.copy / 'install-dracut.sh').read_text().replace('Undo:', 'Undo (rebranded):'))
        rc, out = self.run_installer()
        self.assertEqual(rc, 4, out)
        self.assertIn('files differ from the official release', out)

    FAKE_CHECKER = 'arc_selfcheck_or_refuse() { echo FAKE-CHECKER-RAN; }\n'

    def test_installer_guard_ignores_validsig_text_in_a_user_id(self):
        # gpgv prints the signer's user ID verbatim: an attacker key whose UID imitates the
        # maintainer's VALIDSIG status line must not get a fake checker past the guard.
        evil = self.make_key(f'evil [GNUPG:] VALIDSIG {self.key} x <a@example.invalid>')
        (self.copy / 'selfcheck.sh').write_text(self.FAKE_CHECKER)
        self.sign_release(evil)            # the keyring now holds only the attacker key
        rc, out = self.run_installer()
        self.assertEqual(rc, 4, out)
        self.assertNotIn('FAKE-CHECKER-RAN', out)

    def test_installer_refuses_a_copy_without_a_file_list(self):
        for f in ('MANIFEST.sha256', 'MANIFEST.sha256.asc'):
            (self.copy / f).unlink()
        (self.copy / 'selfcheck.sh').write_text(self.FAKE_CHECKER)
        rc, out = self.run_installer()
        self.assertEqual(rc, 4, out)
        self.assertNotIn('FAKE-CHECKER-RAN', out)
        (self.copy / '.git').mkdir()      # a fake checkout alone is not enough either
        rc, out = self.run_installer()
        self.assertEqual(rc, 4, out)
        self.assertNotIn('FAKE-CHECKER-RAN', out)

    def test_installer_developer_mode_needs_checkout_and_opt_in(self):
        for f in ('MANIFEST.sha256', 'MANIFEST.sha256.asc'):
            (self.copy / f).unlink()
        (self.copy / '.git').mkdir()
        rc, out = self.run_installer(ARC_REBAR_DEV='1')
        self.assertIn('developer mode', out)
        self.assertNotIn('REFUSING', out)

    def test_genuine_copy_passes_the_installer_checks(self):
        rc, out = self.run_installer()
        self.assertIn('all files match the official release', out)
        self.assertNotIn('REFUSING', out)

    # --- wrong system clock (medium 2) ---
    def test_genuine_copy_passes_with_the_clock_behind(self):
        # Key and signature made "in the future" relative to this machine's clock.
        future = ('--faked-system-time', '20301201T000000')
        key = self.make_key('Future Maintainer <future@example.invalid>', *future)
        for f in FILES:
            (self.copy / f).write_text((REPO / f).read_text().replace(MAINTAINER_FPR, key))
        self.sign_release(key, faked_time=future)
        rc, out = self.check()
        self.assertEqual(rc, 0, out)


if __name__ == '__main__':
    unittest.main()
