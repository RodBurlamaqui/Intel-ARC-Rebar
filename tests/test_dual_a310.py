"""Experimental dual-A310 tests: fake PCI tree only, never access host PCI."""
import os
from pathlib import Path
import subprocess
import unittest

import test_boot_dryrun as boot_fixture


class DualA310Tests(unittest.TestCase):
    add_gpu = boot_fixture.BootDryrunTests.add_gpu
    env_for = boot_fixture.BootDryrunTests.env_for
    mutation_snapshot = boot_fixture.BootDryrunTests.mutation_snapshot
    assert_no_mutations = boot_fixture.BootDryrunTests.assert_no_mutations

    def setUp(self):
        boot_fixture.BootDryrunTests.setUp(self)
        # Some initramfs BusyBox builds prefer their internal sleep applet over
        # PATH. Force the fake script to call our simulator explicitly.
        self.script.write_text(self.script.read_text().replace(
            'PREREQ=""', 'sleep() { "$MOCK_SLEEP" "$@"; }\nPREREQ=""', 1))
        (self.devices / self.default_gpu['gpu'] / 'driver').unlink()
        self.first = self.add_gpu(cap='0001f000', driver='vfio-pci')
        self.second = self.add_gpu(bus='00', rp='0000:00:02.0',
                                   us='0000:05:00.0', ds='0000:06:01.0',
                                   gpu='0000:07:00.0', cap='0001f000', driver='vfio-pci')
        for info in (self.first, self.second):
            (self.devices / info['gpu'] / 'device').write_text('0x56a6\n')
            (self.devices / info['gpu'] / 'boot_vga').write_text('0\n')
            self.set_bar(info, 8)
        self.iomem = self.root / 'proc/iomem'
        self.iomem.write_text('200000000-fffffffff : PCI Bus 0000:00\n'
                              '  200000000-3007fffff : PCI Bus 0000:03\n')

    def set_bar(self, info, field, start=None):
        node = self.devices / info['gpu']
        node.joinpath('rebar-ctl').write_text(f'{(field << 8) | 0x22:08x}')
        start = start if start is not None else (0x200000000 if info == self.first else 0xc0000000)
        node.joinpath('resource').write_text(
            f'0 0 0\n0 0 0\n0x{start:016x} 0x{start + (1 << (field + 20)) - 1:016x} 0\n')

    def run_dual(self, cmdline='pci=realloc rebar.dual=1', *, real=False, extra_env=None):
        env = self.env_for(cmdline=cmdline)
        # Do not inherit any experimental opt-in from the developer's shell.
        env.pop('ARC_REBAR_EXPERIMENTAL_DUAL', None)
        if real:
            env.pop('ARC_REBAR_DRYRUN', None)
        env['MOCK_SLEEP'] = str(self.tools / 'sleep')
        env.update(extra_env or {})
        p = subprocess.run(os.environ.get('ARC_REBAR_TEST_SHELL', 'dash').split() + [str(self.script)], env=env,
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout + p.stderr

    def rejected(self, expected, **kwargs):
        before = self.mutation_snapshot()
        out = self.run_dual(**kwargs)
        self.assertIn(expected, out)
        self.assertNotIn('PLAN: act', out)
        after = self.mutation_snapshot()
        if kwargs.get('real'):
            # Logging a refusal to the fake kernel log is permitted.
            before.pop('dev/kmsg'); after.pop('dev/kmsg')
        self.assertEqual(before, after)
        self.assertEqual(self.write_log.read_text(), '')

    def enable_mock_writes(self):
        # All redirections in self.script have already been rewritten into
        # TemporaryDirectory. setpci writes update only the fake card state.
        (self.tools / 'setpci').write_text('''#!/bin/sh
case "$1:$2:$3" in
  -s:*:ECAP_REBAR+8.l=*)
    printf '%s %s\\n' "$2" "$3" >> "$WRITE_LOG"
    [ "$2" != "$FAIL_GPU" ] || exit 97
    echo "${3#*=}" > "$DEVICE_ROOT/$2/rebar-ctl";;
  -s:*:ECAP_REBAR+4.l) cat "$DEVICE_ROOT/$2/rebar-cap";;
  -s:*:ECAP_REBAR+8.l) cat "$DEVICE_ROOT/$2/rebar-ctl";;
  *) exit 98;;
esac
''')
        (self.tools / 'sleep').write_text('''#!/usr/bin/env python3
import os, pathlib, sys
if sys.argv[1] != '3':
    raise SystemExit(0)
d = pathlib.Path(os.environ['DEVICE_ROOT'])
for gpu, address in [('0000:03:00.0', 0x400000000), ('0000:07:00.0', 0x600000000)]:
    node = d / gpu
    field = (int((node / 'rebar-ctl').read_text(), 16) >> 8) & 63
    size = 1 << (field + 20)
    if os.environ.get('OVERLAP_AFTER_SECOND') and gpu == '0000:07:00.0' and field == 12:
        address = 0x400000000
    if os.environ.get('WRONG_BAR') == gpu and field == 12:
        size = 1 << 28
    (node / 'resource').write_text(f'0 0 0\\n0 0 0\\n0x{address:016x} 0x{address+size-1:016x} 0\\n')
if os.environ.get('CHANGE_TOPOLOGY'):
    second = d / '0000:07:00.0'
    if second.is_symlink():
        second.unlink()
''')

    def test_reported_fujitsu_layout_first_full_second_small(self):
        for gpu in (self.first['gpu'], self.second['gpu']):
            (self.devices / gpu).unlink()
        first = self.add_gpu(bus='80', rp='0000:80:02.0', us='0000:82:00.0',
                             ds='0000:83:01.0', gpu='0000:84:00.0', cap='0001f000', driver='vfio-pci',
                             iomem_start='3c000000000', iomem_end='3ffffffffff')
        second = self.add_gpu(bus='80', rp='0000:80:03.0', us='0000:86:00.0',
                              ds='0000:87:01.0', gpu='0000:88:00.0', cap='0001f000', driver='vfio-pci',
                              iomem_start='3c000000000', iomem_end='3ffffffffff')
        for info in (first, second):
            (self.devices / info['gpu'] / 'device').write_text('0x56a6')
            (self.devices / info['gpu'] / 'boot_vga').write_text('0')
        self.set_bar(first, 12, 0x3c000000000)
        self.set_bar(second, 8, 0xc0000000)
        self.iomem.write_text('3c000000000-3ffffffffff : PCI Bus 0000:80\n'
                              '  3c000000000-3c1007fffff : PCI Bus 0000:82\n'
                              '    3c000000000-3c0ffffffff : GPU BAR2\n'
                              '    3c100000000-3c1007fffff : switch BAR0\n')
        before = self.mutation_snapshot()
        out = self.run_dual()
        self.assertIn('DUAL-CHECK 0000:84:00.0 0000:80:02.0 0000:82:00.0 0000:80 12 12', out)
        self.assertIn('DUAL-CHECK 0000:88:00.0 0000:80:03.0 0000:86:00.0 0000:80 8 12', out)
        self.assertIn('PLAN: act experimental-dual', out)
        self.assert_no_mutations(before)

    def test_both_small_plan_includes_both_without_mutation(self):
        before = self.mutation_snapshot()
        out = self.run_dual()
        self.assertIn('PLAN: act experimental-dual', out)
        self.assertIn('DUAL-CHECK 0000:03:00.0', out)
        self.assertIn('DUAL-CHECK 0000:07:00.0', out)
        self.assert_no_mutations(before)

    def test_first_full_still_plans_second(self):
        self.set_bar(self.first, 12)
        before = self.mutation_snapshot()
        self.assertIn('PLAN: act experimental-dual', self.run_dual())
        self.assert_no_mutations(before)

    def test_both_full_report_none(self):
        self.set_bar(self.first, 12)
        self.set_bar(self.second, 12, 0x400000000)
        self.assertIn('PLAN: none experimental-dual reason=both-already-at-target', self.run_dual())

    def test_missing_third_and_mixed_cards_refuse(self):
        third = self.add_gpu(bus='40', cap='0001f000')
        (self.devices / third['gpu'] / 'device').write_text('0x56a6')
        self.rejected('count=3')
        (self.devices / third['gpu']).unlink()
        (self.devices / self.second['gpu'] / 'device').write_text('0x56a0')
        self.rejected('dual-requires-a310')
        (self.devices / self.second['gpu']).unlink()
        self.rejected('count=1')

    def test_unreadable_third_a310_still_refuses(self):
        third = self.add_gpu(bus='40', cap='0001f000')
        node = self.devices / third['gpu']
        (node / 'device').write_text('0x56a6')
        (node / 'rebar-cap').unlink()
        self.rejected('count=3')

    def test_second_card_external_topology_refuses_before_first_write(self):
        second = self.add_gpu(bus='00', rp='0000:00:02.0', us='0000:05:00.0',
                              ds='0000:06:01.0', gpu='0000:07:00.0', cap='0001f000', driver='vfio-pci', extra_depth=1)
        (self.devices / second['gpu'] / 'device').write_text('0x56a6')
        (self.devices / second['gpu'] / 'boot_vga').write_text('0')
        self.rejected('unexpected-topology')

    def test_shared_root_refuses_before_writes(self):
        shared = self.add_gpu(bus='00', rp=self.first['rp'], us=self.first['us'],
                              ds='0000:02:02.0', gpu=self.second['gpu'], cap='0001f000', driver='vfio-pci')
        (self.devices / shared['gpu'] / 'device').write_text('0x56a6')
        (self.devices / shared['gpu'] / 'boot_vga').write_text('0')
        self.rejected('unexpected-device-on-card')

    def test_conflicting_options_and_norebar(self):
        for suffix, reason in [('rebar.dev=0000:07:00.0', 'dual-conflicting-override'),
                               ('rebar.size=12', 'dual-conflicting-override'),
                               ('norebar', 'reason=norebar')]:
            with self.subTest(suffix=suffix):
                self.rejected(reason, cmdline='pci=realloc rebar.dual=1 ' + suffix)

    def test_console_gpu_and_host_graphics_driver_refuse(self):
        node = self.devices / self.second['gpu']
        (node / 'boot_vga').write_text('1')
        self.rejected('dual-requires-non-console-gpu')
        (node / 'boot_vga').write_text('0')
        (node / 'driver').unlink()
        host_driver = self.sys / 'bus/pci/drivers' / 'xe'
        (node / 'driver').symlink_to(host_driver)
        self.rejected('dual-requires-vfio-or-unbound-gpu')

    def test_environment_only_opt_in_cannot_write(self):
        self.rejected('dual-requires-boot-opt-in', cmdline='pci=realloc', real=True,
                      extra_env={'ARC_REBAR_EXPERIMENTAL_DUAL': '1'})

    def test_environment_preflight_is_read_only(self):
        before = self.mutation_snapshot()
        out = self.run_dual(cmdline='pci=realloc', extra_env={'ARC_REBAR_EXPERIMENTAL_DUAL': '1'})
        self.assertIn('PLAN: act experimental-dual', out)
        self.assert_no_mutations(before)

    def test_default_stays_first_gpu_only(self):
        before = self.mutation_snapshot()
        out = self.run_dual(cmdline='pci=realloc')
        self.assertIn('PLAN: act gpu=0000:03:00.0', out)
        self.assertNotIn('gpu=0000:07:00.0', out)
        self.assert_no_mutations(before)

    def test_separate_host_windows_are_budgeted_independently(self):
        (self.devices / self.second['gpu']).unlink()
        self.second = self.add_gpu(bus='40', cap='0001f000', driver='vfio-pci',
                                   iomem_start='400000000', iomem_end='503ffffff')
        (self.devices / self.second['gpu'] / 'device').write_text('0x56a6')
        (self.devices / self.second['gpu'] / 'boot_vga').write_text('0')
        self.set_bar(self.first, 8, 0xc0000000)
        self.set_bar(self.second, 8, 0xd0000000)
        self.iomem.write_text('200000000-303ffffff : PCI Bus 0000:00\n'
                              '400000000-503ffffff : PCI Bus 0000:40\n')
        before = self.mutation_snapshot()
        self.assertIn('PLAN: act experimental-dual', self.run_dual())
        self.assert_no_mutations(before)

    def test_unbound_gpus_are_accepted(self):
        for info in (self.first, self.second):
            (self.devices / info['gpu'] / 'driver').unlink()
        before = self.mutation_snapshot()
        self.assertIn('PLAN: act experimental-dual', self.run_dual())
        self.assert_no_mutations(before)

    def test_shared_window_capacity_is_not_counted_twice(self):
        self.iomem.write_text('200000000-403ffffff : PCI Bus 0000:00\n')
        self.rejected('dual-insufficient-contiguous-mmio')

    def test_unrelated_occupied_memory_is_not_treated_as_free(self):
        self.iomem.write_text('200000000-7ffffffff : PCI Bus 0000:00\n'
                              '  200000000-7f0000000 : unrelated device\n')
        self.rejected('dual-insufficient-contiguous-mmio')

    def test_occupied_end_of_window_refuses(self):
        self.iomem.write_text('200000000-7ffffffff : PCI Bus 0000:00\n'
                              '  7f0000000-7ffffffff : unrelated device\n')
        self.rejected('dual-no-contiguous-mmio-tail')

    def test_missing_malformed_and_undersized_capabilities_refuse(self):
        node = self.devices / self.second['gpu']
        for cap, ctl in [('garbage', '00000822'), ('0000f000', '00000822'),
                         ('0001f000', '00000922'), ('0001f000', '00000821')]:
            with self.subTest(cap=cap, ctl=ctl):
                (node / 'rebar-cap').write_text(cap)
                (node / 'rebar-ctl').write_text(ctl)
                self.rejected('dual-second-preflight-failed')

    def test_overlapping_assigned_bars_refuse_before_any_write(self):
        self.set_bar(self.second, 8, 0x200000000)
        self.rejected('dual-overlapping-bars')

    def test_malformed_resource_refuses_cleanly(self):
        node = self.devices / self.second['gpu']
        for resource in ('', '0xgarbage 0x1234 0',
                         '0xffffffffffffffff 0xffffffffffffffff 0'):
            with self.subTest(resource=resource):
                (node / 'resource').write_text('0 0 0\n0 0 0\n' + resource + '\n')
                self.rejected('dual-invalid-resource')

    def test_full_control_with_wrong_resource_refuses(self):
        (self.devices / self.first['gpu'] / 'rebar-ctl').write_text('00000c22')
        self.rejected('dual-current-bar2-unassigned-or-wrong-size')

    def test_mocked_boot_resizes_both_and_checks_final_state(self):
        self.enable_mock_writes()
        out = self.run_dual(real=True)
        self.assertIn('PLAN: done experimental-dual', out)
        writes = self.write_log.read_text().splitlines()
        self.assertEqual(writes, ['0000:03:00.0 ECAP_REBAR+8.l=00000c22',
                                  '0000:07:00.0 ECAP_REBAR+8.l=00000c22'])

    def test_mocked_boot_skips_full_first_and_resizes_second(self):
        self.set_bar(self.first, 12)
        self.enable_mock_writes()
        out = self.run_dual(real=True)
        self.assertIn('PLAN: done experimental-dual', out)
        self.assertEqual(self.write_log.read_text().splitlines(),
                         ['0000:07:00.0 ECAP_REBAR+8.l=00000c22'])

    def test_unbind_failure_stops_before_register_writes(self):
        unbind = self.sys / 'bus/pci/drivers/vfio-pci/unbind'
        unbind.unlink(); unbind.mkdir()
        self.enable_mock_writes()
        out = self.run_dual(real=True)
        self.assertIn('dual-unbind-failed', out)
        self.assertIn('FAILED reason=dual-stopped', out)
        self.assertEqual(self.write_log.read_text(), '')

    def test_remove_and_rescan_failures_stop_before_second(self):
        self.enable_mock_writes()
        for path, reason in [(self.devices / self.first['rp'] / 'remove', 'root-port-remove-failed'),
                             (self.sys / 'bus/pci/rescan', 'pci-rescan-failed')]:
            with self.subTest(reason=reason):
                path.unlink(); path.mkdir()
                self.write_log.write_text('')
                self.set_bar(self.first, 8)
                out = self.run_dual(real=True)
                self.assertIn(reason, out)
                self.assertNotIn('PLAN: done experimental-dual', out)
                self.assertNotIn(self.second['gpu'], self.write_log.read_text())
                path.rmdir(); path.write_text('sentinel')

    def test_final_overlap_is_failure_even_after_per_card_success(self):
        self.enable_mock_writes()
        out = self.run_dual(real=True, extra_env={'OVERLAP_AFTER_SECOND': '1'})
        self.assertIn('PLAN: done gpu=0000:07:00.0', out)
        self.assertIn('FAILED reason=dual-overlapping-bars', out)
        self.assertNotIn('PLAN: done experimental-dual', out)

    def test_first_write_failure_stops_before_second(self):
        self.enable_mock_writes()
        out = self.run_dual(real=True, extra_env={'FAIL_GPU': self.first['gpu']})
        self.assertIn('FAILED reason=dual-stopped', out)
        self.assertEqual(len(self.write_log.read_text().splitlines()), 1)

    def test_second_write_failure_is_partial_failure_not_success(self):
        self.enable_mock_writes()
        out = self.run_dual(real=True, extra_env={'FAIL_GPU': self.second['gpu']})
        self.assertIn('FAILED reason=dual-stopped', out)
        self.assertNotIn('PLAN: done experimental-dual', out)

    def test_wrong_assigned_size_rolls_back_and_stops(self):
        self.enable_mock_writes()
        out = self.run_dual(real=True, extra_env={'WRONG_BAR': self.first['gpu']})
        self.assertIn('PLAN: rolled-back', out)
        self.assertIn('FAILED reason=dual-stopped', out)
        self.assertNotIn(self.second['gpu'], self.write_log.read_text())

    def test_topology_change_after_rescan_stops_before_second(self):
        self.enable_mock_writes()
        out = self.run_dual(real=True, extra_env={'CHANGE_TOPOLOGY': '1'})
        self.assertNotIn('PLAN: done experimental-dual', out)
        self.assertNotIn(self.second['gpu'], self.write_log.read_text())

    def test_live_test_rejects_dual_before_root_check_or_hardware(self):
        source = (Path(__file__).resolve().parents[1] / 'live-test.sh').read_text()
        source = source.replace('/proc/cmdline', str(self.root / 'proc/cmdline'))
        live = self.root / 'live-test'
        live.write_text(source)
        env = self.env_for(cmdline='pci=realloc rebar.dual=1')
        p = subprocess.run(['bash', str(live)], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn('boot-only', p.stdout)
        self.assertEqual(self.write_log.read_text(), '')


if __name__ == '__main__':
    unittest.main()
