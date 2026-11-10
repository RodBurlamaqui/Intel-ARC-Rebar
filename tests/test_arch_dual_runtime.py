"""Run the mkinitcpio hook with the real dual payload and entirely fake PCI."""
from pathlib import Path
import shutil
import subprocess
import unittest

import test_dual_a310


REPO = Path(__file__).resolve().parents[1]


class ArchDualRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fake = test_dual_a310.DualA310Tests(
            'test_both_small_plan_includes_both_without_mutation')
        self.fake.setUp()
        self.addCleanup(self.fake.doCleanups)
        self.image = self.fake.root / 'image'
        self.image.mkdir()
        shutil.copyfile(self.fake.script, self.image / 'arc-rebar-boot')
        self.runtime = self.image / 'runtime-hook'
        # Only path redirection is changed in the real mkinitcpio runtime hook.
        self.runtime.write_text((REPO / 'mkinitcpio/hooks/arc-rebar').read_text().replace(
            '/arc-rebar-boot', str(self.image / 'arc-rebar-boot')))
        (self.fake.tools / 'sh').symlink_to(shutil.which('busybox'))

    def run_hook(self, *, real=False, cmdline='pci=realloc rebar.dual=1'):
        env = self.fake.env_for(cmdline=cmdline)
        env['MOCK_SLEEP'] = str(self.fake.tools / 'sleep')
        env.pop('ARC_REBAR_EXPERIMENTAL_DUAL', None)
        if real:
            env.pop('ARC_REBAR_DRYRUN', None)
        p = subprocess.run(['busybox', 'ash', '-c', '. "$1"; run_hook',
                            'mock-init', str(self.runtime)], env=env,
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout + p.stderr

    def test_runtime_hook_preflights_both_without_mutation(self):
        before = self.fake.mutation_snapshot()
        out = self.run_hook()
        self.assertIn('PLAN: act experimental-dual', out)
        self.assertIn('DUAL-CHECK 0000:03:00.0', out)
        self.assertIn('DUAL-CHECK 0000:07:00.0', out)
        self.fake.assert_no_mutations(before)

    def test_runtime_hook_processes_second_after_full_first(self):
        self.fake.set_bar(self.fake.first, 12)
        self.fake.enable_mock_writes()
        out = self.run_hook(real=True)
        self.assertIn('PLAN: done experimental-dual', out)
        self.assertEqual(self.fake.write_log.read_text().splitlines(),
                         ['0000:07:00.0 ECAP_REBAR+8.l=00000c22'])

    def test_runtime_hook_preserves_shared_mmio_refusal(self):
        self.fake.iomem.write_text('200000000-403ffffff : PCI Bus 0000:00\n')
        before = self.fake.mutation_snapshot()
        out = self.run_hook()
        self.assertIn('dual-insufficient-contiguous-mmio', out)
        self.assertNotIn('PLAN: act', out)
        self.fake.assert_no_mutations(before)

    def test_runtime_hook_respects_norebar(self):
        before = self.fake.mutation_snapshot()
        self.assertIn('reason=norebar', self.run_hook(
            cmdline='pci=realloc rebar.dual=1 norebar'))
        self.fake.assert_no_mutations(before)

    def test_runtime_hook_missing_payload_is_noop(self):
        (self.image / 'arc-rebar-boot').unlink()
        before = self.fake.mutation_snapshot()
        self.assertEqual(self.run_hook(), '')
        self.fake.assert_no_mutations(before)
