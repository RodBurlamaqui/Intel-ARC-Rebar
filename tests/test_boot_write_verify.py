"""Boot hook: lockdown refusal and post-write verification.

`setpci` exits 0 even when the kernel refuses a config write (for example
under lockdown with Secure Boot), so the hook must not report `done` unless the
ReBAR control register holds the written value and BAR2 has the target size.
All runs use a fake sysfs/proc tree; nothing touches real PCI devices.
"""
import subprocess
import unittest

import test_boot_dryrun as base  # module import: keeps discovery from running the base tests twice

SIZE_256M = '0x0000000200000000 0x000000020fffffff 0'
SIZE_8G = '0x0000000200000000 0x00000003ffffffff 0'

# setpci mock for the write path. MODE selects how a write behaves:
#   applied      - store the value and resize BAR2 the way a rescan would
#   refused      - change nothing, warn on stderr, exit 0 (real setpci on EPERM)
#   ctl-only     - store the value but leave BAR2 at its old size
SETPCI_WRITE_MOCK = r'''#!/bin/sh
case "$1:$2:$3" in
  -s:*:ECAP_REBAR+8.l=*)
    printf '%s %s\n' "$2" "$3" >> "$WRITE_LOG"
    val=${3#ECAP_REBAR+8.l=}
    case "$MODE" in
      refused)
        echo "pcilib: sysfs_write: write failed: Operation not permitted" >&2; exit 0;;
      applied|ctl-only)
        printf '%s' "$val" > "$DEVICE_ROOT/$2/rebar-ctl"
        size=$(( (0x$val >> 8) & 0x3f ))
        if [ "$MODE" = applied ]; then
          end=$(printf '0x%016x' $(( 0x200000000 + (1 << (size + 20)) - 1 )))
          printf '0 0 0\n0 0 0\n0x0000000200000000 %s 0\n' "$end" > "$DEVICE_ROOT/$2/resource"
        fi
        exit 0;;
    esac;;
  -s:*:ECAP_REBAR+4.l) cat "$DEVICE_ROOT/$2/rebar-cap";;
  -s:*:ECAP_REBAR+8.l) cat "$DEVICE_ROOT/$2/rebar-ctl";;
  *) echo "unexpected setpci call: $*" >&2; exit 98;;
esac
'''


class BootWriteVerifyTests(base.BootDryrunTests):
    """Reuses the dry-run fixture; inherited tests are disabled below."""

    def setUp(self):
        super().setUp()
        self.gpu = self.default_gpu['gpu']
        (self.devices / self.gpu / 'resource').write_text(
            f'0 0 0\n0 0 0\n{SIZE_256M}\n')
        (self.tools / 'setpci').write_text(SETPCI_WRITE_MOCK)

    def set_lockdown(self, text):
        path = self.sys / 'kernel/security/lockdown'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + '\n')

    def run_write_path(self, mode):
        env = self.env_for()
        env.pop('ARC_REBAR_DRYRUN')
        env['MODE'] = mode
        p = subprocess.run(['sh', str(self.script)], env=env,
                           capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout + p.stderr

    def plan_lines(self, out):
        return [line for line in out.splitlines() if 'PLAN:' in line]

    # --- lockdown check (also visible in dry runs, so diagnose reports it)

    def test_lockdown_integrity_skips_without_writes(self):
        for mode in ('[integrity]', 'none [integrity] confidentiality',
                     'none integrity [confidentiality]'):
            with self.subTest(lockdown=mode):
                self.set_lockdown(mode)
                before = self.mutation_snapshot()
                rc, out = self.run_case()
                self.assertEqual(rc, 0, out)
                self.assertIn('PLAN: skip reason=kernel-lockdown', out)
                self.assert_no_mutations(before)

    def test_lockdown_none_still_acts(self):
        self.set_lockdown('[none] integrity confidentiality')
        before = self.mutation_snapshot()
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('PLAN: act gpu=0000:03:00.0', out)
        self.assert_no_mutations(before)

    def test_lockdown_skip_happens_before_any_write(self):
        self.set_lockdown('none [integrity] confidentiality')
        rc, out = self.run_write_path('applied')
        self.assertEqual(rc, 0, out)
        self.assertIn('PLAN: skip reason=kernel-lockdown', out)
        self.assertEqual(self.write_log.read_text(), '')
        self.assertNotIn('unbound', out)

    # --- post-write verification on the real (non-dry) path

    def test_applied_write_reports_done_with_new_size(self):
        rc, out = self.run_write_path('applied')
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.plan_lines(out),
                         ['arc-rebar: PLAN: done gpu=0000:03:00.0 bar2=8192M'])

    def test_refused_write_is_not_reported_as_done(self):
        rc, out = self.run_write_path('refused')
        self.assertEqual(rc, 0, out)
        plans = self.plan_lines(out)
        self.assertEqual(len(plans), 1, out)
        self.assertIn('PLAN: skip reason=rebar-write-not-applied gpu=0000:03:00.0 bar2=256M', plans[0])
        self.assertNotIn('PLAN: done', out)

    def test_register_written_but_size_unchanged_rolls_back(self):
        rc, out = self.run_write_path('ctl-only')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('PLAN: done', out)
        self.assertIn('WARNING: BAR2 is 256M after rescan, expected 8192M', out)
        self.assertIn('PLAN: rolled-back gpu=0000:03:00.0 bar2=256M', out)
        # The rollback restored the original control value.
        self.assertEqual((self.devices / self.gpu / 'rebar-ctl').read_text(), '00000822')


for _name in [n for n in dir(base.BootDryrunTests) if n.startswith('test_')]:
    setattr(BootWriteVerifyTests, _name, None)


if __name__ == '__main__':
    unittest.main()
