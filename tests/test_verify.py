"""Hardware-free regression tests; every PCI access is intercepted."""
import pathlib
import subprocess
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'verify.sh'


class VerifyTests(unittest.TestCase):
    def run_case(self, statuses=('0000',), initial_fail=0, log='', full=False,
                 bar='0x0000000200000000', bar_end='0x00000003ffffffff',
                 driver=True, driver_name='i915', log_fails=False, broken_driver=False,
                 cap='0003f000', ctl='00000d22', bdf='0000:83:00.0', device=True):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            dev = root / bdf
            if device:
                dev.mkdir()
                (dev / 'vendor').write_text('0x8086\n')
                (dev / 'class').write_text('0x030000\n')
                (dev / 'resource').write_text('0 0 0\n0 0 0\n' + bar + ' ' + bar_end + ' 0\n')
                if driver:
                    if not broken_driver:
                        (root / driver_name).mkdir()
                    (dev / 'driver').symlink_to(root / driver_name)
            (root / 'statuses').write_text('\n'.join(statuses) + '\n')
            (root / 'reads').write_text('0')
            (root / 'writes').write_text('')
            (root / 'log').write_text(log)
            (root / 'cmdline').write_text('pci=realloc\n')
            # Test-only path substitution: no runtime environment can redirect sysfs.
            source = SOURCE.read_text().replace('/sys/bus/pci/devices/*', str(root / '????:??:??.?'))
            source = source.replace('/proc/cmdline', str(root / 'cmdline'))
            (root / 'verify.sh').write_text(source)
            code = r'''
source "$T/verify.sh"
setpci(){
  [[ ${3-} == *=* ]] && echo "$3" >> "$T/writes"
  [[ $1 == -s && $2 == "$BDF" ]] || return 90
  case "$3" in
    ECAP_REBAR+4.l) echo "$CAP";;
    ECAP_REBAR+8.l) echo "$CTL";;
    CAP_EXP+0xa.w)
      n=$(cat "$T/reads"); n=$((n+1)); echo "$n" > "$T/reads"
      v=$(sed -n "${n}p" "$T/statuses")
      [[ -n $v ]] || v=$(tail -1 "$T/statuses")
      [[ $v != ERROR ]] || return 1
      echo "$v";;
    *) return 91;;
  esac
}
dmesg(){ cat "$T/log"; return "$LOG_FAILS"; }
vulkaninfo(){ :; }
fail=$INITIAL_FAIL; inconclusive=0
if [[ $FULL == 1 ]]; then
  main
else
  check_pcie "$T/$BDF"
  check_kernel_log "$(cat "$T/log")"
  result
fi
'''
            import os
            env = dict(os.environ, T=td, INITIAL_FAIL=str(initial_fail),
                       FULL=str(int(full)), LOG_FAILS=str(int(log_fails)),
                       CAP=cap, CTL=ctl, BDF=bdf)
            p = subprocess.run(['bash', '-c', code], env=env, text=True, capture_output=True,
                               timeout=10)
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

    def test_issue10_reported_a380_8gib_i915_latch_is_warn_only(self):
        rc, out, writes = self.run_case(
            statuses=('0008',), full=True, cap='0003f000', ctl='00000d22',
            bar='0x0000000200000000', bar_end='0x00000003ffffffff', driver_name='i915')
        self.assertEqual(rc, 2, out)
        self.assertIn('BAR2 = 8192 MiB (size field 13 = card maximum)', out)
        self.assertIn('driver: i915', out)
        self.assertIn('latched correctable/Unsupported Request status; age and cause unknown', out)
        self.assertEqual(writes, '')

    def test_issue11_reported_b580_16gib_vfio_resources_do_not_claim_workload_health(self):
        rc, out, writes = self.run_case(
            statuses=('0000',), full=True, cap='0007f000', ctl='00000e22',
            bar='0x0000000200000000', bar_end='0x00000005ffffffff',
            driver_name='vfio-pci', log='')
        self.assertEqual(rc, 0, out)
        self.assertIn('BAR2 = 16384 MiB (size field 14 = card maximum)', out)
        self.assertIn('driver: vfio-pci', out)
        self.assertIn('no arc-rebar verdict in the kernel log this boot', out)
        self.assertIn('Driver binding/BAR allocation do not establish GPU workload health.', out)
        self.assertEqual(writes, '')

    def test_no_intel_gpu_fails_without_pci_writes(self):
        rc, out, writes = self.run_case(full=True, device=False)
        self.assertEqual(rc, 1, out)
        self.assertIn('no Intel GPU with a ReBAR capability found', out)
        self.assertEqual(writes, '')

    def test_severe_never_cleared(self):
        for status in ('0002', '0004', '000f'):
            rc, out, writes = self.run_case((status,))
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_unreadable_and_malformed(self):
        for status in ('ERROR', 'ffff', 'FFFF', 'garbage', '0', '00000', '0008 0000'):
            rc, out, writes = self.run_case((status,))
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_existing_failure_overrides_latched_warning(self):
        rc, out, writes = self.run_case(('0008',), initial_fail=1)
        self.assertEqual(rc, 1, out)
        self.assertEqual(writes, '')

    def test_allocation_or_driver_failure_overrides_latched_warning(self):
        for kwargs in [dict(bar='0x0000000000000000'), dict(driver=False), dict(broken_driver=True), dict(bar='0x0000000300000000')]:
            rc, out, writes = self.run_case(('0008',), full=True, **kwargs)
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_kernel_log_failure_overrides_latched_warning(self):
        rc, out, writes = self.run_case(('0008',), full=True, log_fails=True)
        self.assertEqual(rc, 1, out)
        self.assertEqual(writes, '')

    def test_logged_errors_not_downgraded(self):
        for log in ('AER: Corrected error received\n', 'PCIe Bus Error: severity=Uncorrectable (Fatal)\n', 'DPC: containment event\n'):
            rc, out, writes = self.run_case(('0008',), log=log, full=True)
            self.assertEqual(rc, 1, out)
            self.assertEqual(writes, '')

    def test_malformed_capability_control_and_resource_fail_read_only(self):
        for kwargs in [dict(cap='garbage!'), dict(cap='ffffffff'), dict(cap='00000000'),
                       dict(ctl='garbage!'), dict(ctl='ffffffff'), dict(ctl=''),
                       dict(bar='invalid'), dict(bar_end='0x0000000000000001'),
                       dict(bar_end='0x0000000400000000')]:
            with self.subTest(**kwargs):
                rc, out, writes = self.run_case(full=True, **kwargs)
                self.assertEqual(rc, 1, out)
                self.assertIn('RESULT: FAIL', out)
                self.assertEqual(writes, '')

    def test_arguments(self):
        import os
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            marker = root / 'accessed'
            for command in ('setpci', 'dmesg', 'uptime'):
                stub = root / command
                stub.write_text('#!/bin/sh\nprintf accessed >> "$ACCESS_MARKER"\nexit 99\n')
                stub.chmod(0o755)
            env = dict(os.environ, ACCESS_MARKER=str(marker),
                       PATH=td + os.pathsep + os.environ['PATH'])
            for args in [['--help'], ['--recheck-pcie', '0'], ['--recheck-pcie', '-1'],
                         ['--recheck-pcie', '1'], ['--recheck-pcie', '3601'],
                         ['--recheck-pcie', '09'], ['--recheck-pcie', '1;echo bad'],
                         ['--bogus']]:
                p = subprocess.run(['bash', str(SOURCE), *args], capture_output=True,
                                   env=env, timeout=10)
                self.assertEqual(p.returncode, 0 if args == ['--help'] else 64)
                self.assertFalse(marker.exists(), args)


if __name__ == '__main__':
    unittest.main()
