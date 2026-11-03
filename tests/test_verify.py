"""Hardware-free regression tests; every PCI access is intercepted."""
import pathlib
import subprocess
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'verify.sh'


class VerifyTests(unittest.TestCase):
    def run_case(self, statuses=('0000',), seconds=0, counters='0',
                 later=None, write_fails=False, initial_fail=0, log='', full=False,
                 bar='0x0000000200000000', driver=True, log_fails=False, parent=False):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            dev = root / '0000:83:00.0'
            dev.mkdir()
            (dev / 'vendor').write_text('0x8086\n')
            (dev / 'class').write_text('0x030000\n')
            (dev / 'resource').write_text('0 0 0\n0 0 0\n' + bar + ' 0x00000003ffffffff 0\n')
            if driver:
                (root / 'i915').mkdir()
                (dev / 'driver').symlink_to(root / 'i915')
            if parent:
                bridge = root / '0000:81:00.0'
                bridge.mkdir()
                dev.rename(bridge / dev.name)
                dev.symlink_to(bridge / dev.name)
                counter = bridge / 'aer_rootport_total_err_cor'
            else:
                counter = dev / 'aer_dev_correctable'
            if counters is not None:
                counter.write_text(('' if parent else 'TOTAL_ERR_COR ') + counters + '\n')
            (root / 'statuses').write_text('\n'.join(statuses) + '\n')
            (root / 'reads').write_text('0')
            (root / 'writes').write_text('')
            (root / 'log').write_text(log)
            (root / 'cmdline').write_text('pci=realloc\n')
            # Test-only path substitution: no runtime environment can redirect sysfs.
            source = SOURCE.read_text().replace('/sys/bus/pci/devices/*', str(root / '0000:*'))
            source = source.replace('/proc/cmdline', str(root / 'cmdline'))
            (root / 'verify.sh').write_text(source)
            code = r'''
source "$T/verify.sh"
setpci(){
  [[ $1 == -s && $2 == 0000:83:00.0 ]] || return 90
  case "$3" in
    ECAP_REBAR+4.l) echo 0003f000;;
    ECAP_REBAR+8.l) echo 00000d22;;
    CAP_EXP+0xa.w)
      n=$(cat "$T/reads"); n=$((n+1)); echo "$n" > "$T/reads"
      v=$(sed -n "${n}p" "$T/statuses")
      [[ -n $v ]] || v=$(tail -1 "$T/statuses")
      [[ $v != ERROR ]] || return 1
      echo "$v";;
    CAP_EXP+0xa.w=*) echo "$3" >> "$T/writes"; return "$WRITE_FAILS";;
    *) return 91;;
  esac
}
sleep(){
  if [[ -n $LATER ]]; then
    printf '%s%s\n' "$COUNTER_PREFIX" "$LATER" > "$COUNTER_PATH"
  fi
}
dmesg(){ cat "$T/log"; return "$LOG_FAILS"; }
vulkaninfo(){ :; }
fail=$INITIAL_FAIL; inconclusive=0
if [[ $FULL == 1 ]]; then
  if (( SECONDS_TEST )); then main --recheck-pcie "$SECONDS_TEST"; else main; fi
else
  check_pcie "$T/0000:83:00.0" "$SECONDS_TEST"
  check_kernel_log "$(cat "$T/log")"
  result
fi
'''
            import os
            env = dict(os.environ, T=td, SECONDS_TEST=str(seconds),
                       LATER='' if later is None else later,
                       WRITE_FAILS=str(int(write_fails)), INITIAL_FAIL=str(initial_fail),
                       FULL=str(int(full)), LOG_FAILS=str(int(log_fails)), COUNTER_PATH=str(counter),
                       COUNTER_PREFIX='' if parent else 'TOTAL_ERR_COR ')
            p = subprocess.run(['bash', '-c', code], env=env, text=True, capture_output=True)
            return p.returncode, p.stdout + p.stderr, (root / 'writes').read_text()

    def test_clean(self):
        rc, out, writes = self.run_case(full=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual(writes, '')

    def test_aux_power_is_not_error(self):
        self.assertEqual(self.run_case(('0010',))[0], 0)

    def test_latched_is_inconclusive_and_read_only(self):
        for status in ('0001', '0008', '0019'):
            rc, out, writes = self.run_case((status,), full=True)
            self.assertEqual(rc, 2, out)
            self.assertIn('age and cause unknown', out)
            self.assertEqual(writes, '')

    def test_one_shot_mask_excludes_aux_power(self):
        rc, out, writes = self.run_case(('0019', '0010'), seconds=2, full=True)
        self.assertEqual(rc, 2, out)  # history never silently upgraded to PASS
        self.assertIn('no new PCIe evidence', out)
        self.assertEqual(writes, 'CAP_EXP+0xa.w=0009\n')

    def test_unsupported_request_only_mask(self):
        self.assertEqual(self.run_case(('0008', '0000'), seconds=1)[2], 'CAP_EXP+0xa.w=0008\n')

    def test_persistent_or_immediate_recurrence(self):
        rc, out, writes = self.run_case(('0008',), seconds=2)
        self.assertEqual(rc, 1, out)
        self.assertEqual(writes.count('\n'), 1)

    def test_delayed_recurrence(self):
        for recurring in ('0001', '0008', '0002', '0004'):
            rc, out, writes = self.run_case(('0008', '0000', '0000', recurring), seconds=2)
            self.assertEqual(rc, 1, out)
            self.assertIn('persists/recurs', out)
            self.assertEqual(writes.count('\n'), 1)

    def test_new_error_from_clean_baseline(self):
        rc, out, writes = self.run_case(('0000', '0000', '0008'), seconds=1)
        self.assertEqual(rc, 1, out)
        self.assertEqual(writes, '')

    def test_severe_never_cleared(self):
        for status in ('0002', '0004', '000f'):
            rc, out, writes = self.run_case((status,), seconds=1)
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_unreadable_and_malformed(self):
        for status in ('ERROR', 'ffff', 'FFFF', 'garbage', '0', '00000', '0008 0000'):
            rc, out, writes = self.run_case((status,), seconds=1)
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_read_failure_after_clear(self):
        self.assertEqual(self.run_case(('0008', 'ERROR'), seconds=1)[0], 1)

    def test_clear_failure(self):
        rc, out, writes = self.run_case(('0008', '0000'), seconds=1, write_fails=True)
        self.assertEqual(rc, 1, out)
        self.assertIn('clear failed', out)
        self.assertEqual(writes.count('\n'), 1)

    def test_counters_detect_kernel_cleared_errors_and_reset(self):
        for before, after in [('0', '1'), ('4', '0')]:
            rc, out, _ = self.run_case(seconds=2, counters=before, later=after)
            self.assertEqual(rc, 1, out)
            self.assertIn('counters changed', out)

    def test_parent_counter_recurrence(self):
        rc, out, writes = self.run_case(seconds=2, parent=True, later='1')
        self.assertEqual(rc, 1, out)
        self.assertIn('0000:81:00.0/aer_rootport_total_err_cor', out)
        self.assertEqual(writes, '')

    def test_missing_counters_inconclusive(self):
        rc, out, _ = self.run_case(seconds=1, counters=None)
        self.assertEqual(rc, 2, out)

    def test_bad_counters(self):
        rc, out, writes = self.run_case(('0008',), seconds=1, counters='bad')
        self.assertEqual(rc, 1, out)
        self.assertEqual(writes, '')

    def test_clean_recheck(self):
        rc, out, writes = self.run_case(seconds=2)
        self.assertEqual(rc, 0, out)
        self.assertEqual(writes, '')

    def test_existing_failure_prevents_clear(self):
        rc, out, writes = self.run_case(('0008',), seconds=1, initial_fail=1)
        self.assertEqual(rc, 1, out)
        self.assertEqual(writes, '')

    def test_allocation_or_driver_failure_prevents_clear(self):
        for kwargs in [dict(bar='0x0000000000000000'), dict(driver=False), dict(bar='0x0000000300000000')]:
            rc, out, writes = self.run_case(('0008',), seconds=1, full=True, **kwargs)
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_kernel_log_failure_prevents_clear(self):
        rc, out, writes = self.run_case(('0008',), seconds=1, full=True, log_fails=True)
        self.assertEqual(rc, 1, out)
        self.assertEqual(writes, '')

    def test_logged_errors_not_downgraded(self):
        for log in ('AER: Corrected error received\n', 'PCIe Bus Error: severity=Uncorrectable (Fatal)\n', 'DPC: containment event\n'):
            rc, out, writes = self.run_case(('0008',), seconds=1, log=log, full=True)
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_arguments(self):
        for args in [[], ['--help'], ['--recheck-pcie', '0'], ['--recheck-pcie', '-1'],
                     ['--recheck-pcie', '3601'], ['--recheck-pcie', '09'],
                     ['--recheck-pcie', '1;echo bad'], ['--bogus']]:
            if not args:
                continue  # main without fixtures must never access the test host
            p = subprocess.run(['bash', str(SOURCE), *args], capture_output=True)
            self.assertEqual(p.returncode, 0 if args == ['--help'] else 64)


if __name__ == '__main__':
    unittest.main()
