"""Hardware-free dry-run tests for the initramfs boot script."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'scripts/init-premount/arc-rebar'


class BootDryrunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sys = self.root / 'sys'
        self.devices = self.sys / 'bus/pci/devices'
        self.devices.mkdir(parents=True)
        (self.sys / 'bus/pci/drivers').mkdir(parents=True)
        (self.sys / 'bus/pci/rescan').write_text('rescan-sentinel\n')
        (self.root / 'proc').mkdir()
        (self.root / 'dev').mkdir()
        (self.root / 'dev/kmsg').write_text('kmsg-sentinel\n')
        (self.root / 'proc/cmdline').write_text('pci=realloc\n')
        # Eight GiB BAR plus 64 MiB alignment allowance, aligned at 8 GiB.
        (self.root / 'proc/iomem').write_text(
            '200000000-403ffffff : PCI Bus 0000:00\n')
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        self.write_log = self.root / 'setpci-writes.log'
        self.write_log.write_text('')
        mock = self.tools / 'setpci'
        mock.write_text('''#!/bin/sh
case "$1:$2:$3" in
  -s:*:*=*) printf '%s %s\\n' "$2" "$3" >> "$WRITE_LOG"; echo "write rejected" >&2; exit 97;;
  -s:*:ECAP_REBAR+4.l) cat "$DEVICE_ROOT/$2/rebar-cap";;
  -s:*:ECAP_REBAR+8.l) cat "$DEVICE_ROOT/$2/rebar-ctl";;
  *) echo "unexpected setpci read: $*" >&2; exit 98;;
esac
''')
        mock.chmod(0o755)
        sleep = self.tools / 'sleep'
        sleep.write_text('#!/bin/sh\nexit 0\n')
        sleep.chmod(0o755)
        source = SOURCE.read_text()
        source = source.replace('/sys/', str(self.root) + '/sys/')
        source = source.replace('/proc/', str(self.root) + '/proc/')
        source = source.replace('/dev/kmsg', str(self.root / 'dev/kmsg'))
        self.script = self.root / 'arc-rebar-test'
        self.script.write_text(source)
        self.default_gpu = self.add_gpu()

    def add_gpu(self, *, bus='00', rp=None, us=None, ds=None, gpu=None,
                cap='0003f000', ctl='00000822', vendor='0x8086',
                gpu_class='0x030000', driver='xe', extra_depth=0,
                iomem_start='200000000', iomem_end='403ffffff'):
        rp = rp or f'0000:{bus}:01.0'
        us = us or f'0000:{int(bus, 16) + 1:02x}:00.0'
        ds = ds or f'0000:{int(bus, 16) + 2:02x}:01.0'
        gpu = gpu or f'0000:{int(bus, 16) + 3:02x}:00.0'
        pci_root = self.sys / 'devices' / f'pci0000:{bus}'
        rp_path = pci_root / rp
        us_path = rp_path / us
        ds_path = us_path / ds
        gpu_parent = ds_path
        for n in range(extra_depth):
            extra = f'0000:{int(bus, 16) + 3 + n:02x}:01.0'
            gpu_parent = gpu_parent / extra
        gpu_path = gpu_parent / gpu
        gpu_path.mkdir(parents=True, exist_ok=True)

        # Parent bridge nodes plus the GPU; device links mimic sysfs PCI links.
        nodes = [
            (rp, rp_path, '0x8086', '0x060400', 'pcieport'),
            (us, us_path, '0x8086', '0x060400', 'pcieport'),
            (ds, ds_path, '0x8086', '0x060400', 'pcieport'),
        ]
        prior = ds_path
        for n in range(extra_depth):
            bdf = f'0000:{int(bus, 16) + 3 + n:02x}:01.0'
            path = prior / bdf
            path.mkdir(parents=True, exist_ok=True)
            nodes.append((bdf, path, '0x8086', '0x060400', 'pcieport'))
            prior = path
        nodes.append((gpu, gpu_path, vendor, gpu_class, driver))
        for bdf, path, dev_vendor, dev_class, dev_driver in nodes:
            (path / 'vendor').write_text(dev_vendor + '\n')
            (path / 'class').write_text(dev_class + '\n')
            if bdf == gpu:
                (path / 'config').write_text('')
                (path / 'resource').write_text('0 0 0\n0 0 0\n0x0000000200000000 0x00000003ffffffff 0\n')
                (path / 'rebar-cap').write_text(cap)
                (path / 'rebar-ctl').write_text(ctl)
            driver_path = self.sys / 'bus/pci/drivers' / dev_driver
            driver_path.mkdir(parents=True, exist_ok=True)
            for filename in ('bind', 'unbind'):
                sentinel = driver_path / filename
                if not sentinel.exists():
                    sentinel.write_text(f'{dev_driver}-{filename}-sentinel\n')
            if not (path / 'driver').exists():
                (path / 'driver').symlink_to(driver_path)
            link = self.devices / bdf
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(path)
            (path / 'remove').write_text(f'{bdf}-remove-sentinel\n')

        # The firmware window belongs to the root bus, not the GPU bus.
        iomem = self.root / 'proc/iomem'
        old = iomem.read_text()
        bus_id = rp.rsplit(':', 1)[0]
        line = f'{iomem_start}-{iomem_end} : PCI Bus {bus_id}\n'
        if line not in old:
            iomem.write_text(old + line)
        return {'rp': rp, 'us': us, 'ds': ds, 'gpu': gpu, 'bus_id': bus_id}

    def env_for(self, *, cmdline=None):
        if cmdline is not None:
            (self.root / 'proc/cmdline').write_text(cmdline + '\n')
        env = dict(os.environ)
        env.pop('ARC_REBAR_ASSUME_REALLOC', None)
        env.update({
            'PATH': str(self.tools) + ':' + env.get('PATH', ''),
            'ARC_REBAR_DRYRUN': '1',
            'DEVICE_ROOT': str(self.devices),
            'WRITE_LOG': str(self.write_log),
        })
        return env

    def run_case(self, *, cmdline=None):
        p = subprocess.run(['sh', str(self.script)], env=self.env_for(cmdline=cmdline),
                           capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout + p.stderr

    def mutation_snapshot(self):
        paths = [self.sys / 'bus/pci/rescan', self.root / 'dev/kmsg']
        paths.extend(self.devices.glob('*/config'))
        paths.extend(self.devices.glob('*/remove'))
        paths.extend((self.sys / 'bus/pci/drivers').glob('*/bind'))
        paths.extend((self.sys / 'bus/pci/drivers').glob('*/unbind'))
        return {str(path.relative_to(self.root)): path.read_bytes() for path in paths}

    def assert_no_mutations(self, before):
        self.assertEqual(before, self.mutation_snapshot())
        self.assertEqual(self.write_log.read_text(), '')

    def test_a380_and_a750_max_13_small_bar_plan_act_without_writes(self):
        before = self.mutation_snapshot()
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('PLAN: act gpu=0000:03:00.0', out)
        self.assertIn('from=8 to=13', out)
        self.assert_no_mutations(before)

    def test_b580_max_14_small_bar_plan_act_without_writes(self):
        # A 16 GiB + 64 MiB window aligned at 16 GiB fits the BAR plus margin.
        info = self.add_gpu(cap='0007f000', ctl='00000822',
                            iomem_start='400000000', iomem_end='803ffffff')
        before = self.mutation_snapshot()
        rc, out = self.run_case(cmdline=f'pci=realloc rebar.dev={info["gpu"]}')
        self.assertEqual(rc, 0, out)
        self.assertIn(f'PLAN: act gpu={info["gpu"]}', out)
        self.assertIn('from=8 to=14', out)
        self.assert_no_mutations(before)

    def test_already_at_card_maximum_is_none(self):
        (self.devices / self.default_gpu['gpu'] / 'rebar-ctl').write_text('00000d22')
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('PLAN: none reason=already-at-target current=13', out)
        self.assertEqual(self.write_log.read_text(), '')

    def test_norebar_and_missing_pci_realloc_skip(self):
        for cmdline, expected in [
            ('pci=realloc norebar', 'skip reason=norebar'),
            ('quiet', 'skip reason=no-pci-realloc'),
        ]:
            with self.subTest(cmdline=cmdline):
                self.write_log.write_text('')
                rc, out = self.run_case(cmdline=cmdline)
                self.assertEqual(rc, 0, out)
                self.assertIn(expected, out)
                self.assertEqual(self.write_log.read_text(), '')

    def test_unsafe_topologies_skip(self):
        # An extra downstream bridge makes this an unsupported external depth.
        self.add_gpu(extra_depth=1)
        before = self.mutation_snapshot()
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('skip reason=unexpected-topology depth=5', out)
        self.assert_no_mutations(before)

    def test_shared_root_port_skips(self):
        info = self.add_gpu()
        sibling = self.sys / 'devices/pci0000:00' / info['rp'] / '0000:00:02.0'
        sibling.mkdir(parents=True)
        (sibling / 'vendor').write_text('0x8086\n')
        (sibling / 'class').write_text('0x060400\n')
        (self.devices / '0000:00:02.0').symlink_to(sibling)
        before = self.mutation_snapshot()
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('skip reason=shared-root-port other-device=0000:00:02.0', out)
        self.assert_no_mutations(before)

    def test_nonintel_descendant_skips(self):
        info = self.add_gpu()
        sibling = self.sys / 'devices/pci0000:00' / info['rp'] / info['us'] / '0000:01:00.1'
        sibling.mkdir(parents=True)
        (sibling / 'vendor').write_text('0x10de\n')
        (sibling / 'class').write_text('0x030000\n')
        (self.devices / '0000:01:00.1').symlink_to(sibling)
        before = self.mutation_snapshot()
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('skip reason=non-intel-device-on-card device=0000:01:00.1', out)
        self.assert_no_mutations(before)

    def test_missing_and_too_small_mmio_skip(self):
        for iomem in ('', '100000000-10fffffff : PCI Bus 0000:00\n'):
            with self.subTest(iomem=iomem):
                (self.root / 'proc/iomem').write_text(iomem)
                before = self.mutation_snapshot()
                rc, out = self.run_case()
                self.assertEqual(rc, 0, out)
                expected = 'no-mmio-window-above-4g' if not iomem else 'mmio-window-too-small'
                self.assertIn(expected, out)
                self.assert_no_mutations(before)

    def test_pci_nocrs_style_iomem_refuses(self):
        # With pci=nocrs the kernel ignores the ACPI host-bridge windows and never
        # inserts "PCI Bus DDDD:BB" entries; device BARs sit at the top level.
        # Realistic layout: RAM, reserved ranges and a large BAR above 4G.
        (self.root / 'proc/iomem').write_text(
            '00000000-00000fff : Reserved\n'
            '00001000-0009ffff : System RAM\n'
            '00100000-7fffffff : System RAM\n'
            '  01000000-01ffffff : Kernel code\n'
            'c0000000-cfffffff : PCI ECAM 0000 [bus 00-ff]\n'
            'fed00000-fed003ff : HPET 0\n'
            '100000000-87fffffff : System RAM\n'
            '381000000000-3813ffffffff : 0000:03:00.0\n'
            '381400000000-3814007fffff : 0000:01:00.0\n')
        before = self.mutation_snapshot()
        rc, out = self.run_case(cmdline='pci=realloc pci=nocrs')
        self.assertEqual(rc, 0, out)
        self.assertIn('skip reason=no-mmio-window-above-4g', out)
        self.assertNotIn('PLAN: act', out)
        self.assert_no_mutations(before)

    def test_b580_steps_down_to_fit_window(self):
        (self.root / 'proc/iomem').write_text(
            '200000000-403ffffff : PCI Bus 0000:00\n')
        (self.devices / self.default_gpu['gpu'] / 'rebar-cap').write_text('0007f000')
        before = self.mutation_snapshot()
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('stepping target down from 14 to 13', out)
        self.assertIn('PLAN: act gpu=0000:03:00.0', out)
        self.assert_no_mutations(before)

    def test_malformed_rebar_registers_skip_without_writes(self):
        for cap, ctl in [('garbage', '00000822'), ('0003f000', '0000'), ('', '')]:
            with self.subTest(cap=cap, ctl=ctl):
                self.write_log.write_text('')
                before = self.mutation_snapshot()
                (self.devices / self.default_gpu['gpu'] / 'rebar-cap').write_text(cap)
                (self.devices / self.default_gpu['gpu'] / 'rebar-ctl').write_text(ctl)
                rc, out = self.run_case()
                self.assertEqual(rc, 0, out)
                self.assertIn('skip reason=rebar-registers-unreadable', out)
                self.assert_no_mutations(before)

    def test_two_gpu_selection_default_first_explicit_second_and_first_only(self):
        (self.devices / self.default_gpu['gpu'] / 'rebar-ctl').write_text('00000d22')
        second = self.add_gpu(bus='40', cap='0007f000', ctl='00000822',
                              iomem_start='400000000', iomem_end='803ffffff')
        before = self.mutation_snapshot()
        rc, out = self.run_case()
        self.assertEqual(rc, 0, out)
        self.assertIn('PLAN: none reason=already-at-target current=13', out)
        self.assertNotIn(f'PLAN: act gpu={second["gpu"]}', out)
        self.assert_no_mutations(before)

        self.write_log.write_text('')
        rc, out = self.run_case(cmdline=f'pci=realloc rebar.dev={second["gpu"]}')
        self.assertEqual(rc, 0, out)
        self.assertIn(f'PLAN: act gpu={second["gpu"]}', out)
        self.assertEqual(out.count('PLAN: act'), 1, out)
        self.assert_no_mutations(before)


if __name__ == '__main__':
    unittest.main()
