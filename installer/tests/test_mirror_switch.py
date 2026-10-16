"""网络首次连接、后续变化与失败回退；不访问网络或宿主 /etc。"""
import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mipl_installer import configure
from tests.support import FakeRunner

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'profile/airootfs/usr/local/bin/mipl-mirror-switch'
loader = importlib.machinery.SourceFileLoader('mirror_switch', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
mirror = importlib.util.module_from_spec(spec)
loader.exec_module(mirror)


class TestNetworkMirrors(unittest.TestCase):
    def run_event(self, run_dir, event='up', connectivity='full', result=False):
        with patch.object(mirror, 'Logger', return_value=lambda msg: None), \
             patch.object(mirror, 'nm_connectivity', return_value=connectivity), \
             patch.object(mirror, 'switch_official', return_value=result) as official, \
             patch.object(mirror, 'switch_archlinuxcn', return_value=result) as cn:
            rc = mirror.main(['--run-dir', str(run_dir), '--trigger', event, '--quiet'])
            return rc, official.call_count, cn.call_count

    def test_first_connection_without_live_markers_probes_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_event(tmp), (0, 1, 1))
            self.assertTrue((Path(tmp) / 'mipl-mirror-switch.event').is_file())

    def test_new_network_event_ignores_recent_success_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_event(tmp)
            self.assertEqual(self.run_event(tmp, 'vpn-up'), (0, 1, 1))
            self.assertEqual(self.run_event(tmp, 'connectivity-change'), (0, 1, 1))

    def test_offline_waits_for_next_connectivity_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_event(tmp, connectivity='limited'), (0, 0, 0))
            self.assertFalse((Path(tmp) / 'mipl-mirror-switch.event').exists())
            self.assertEqual(self.run_event(tmp, 'connectivity-change'), (0, 1, 1))

    def test_failed_probe_does_not_mark_event_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_event(tmp, result=None), (0, 1, 1))
            self.assertFalse((Path(tmp) / 'mipl-mirror-switch.event').exists())
            self.assertFalse((Path(tmp) / 'mipl-mirror-switch.stamp').exists())

    def test_waiting_event_already_covered_is_coalesced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'mipl-mirror-switch.event').write_text(str(10**30))
            with patch.object(mirror, 'acquire_lock', wraps=mirror.acquire_lock) as lock:
                self.assertEqual(self.run_event(tmp), (0, 0, 0))
                lock.assert_called_once_with(root, wait=True)

    def test_proxy_event_ignores_recent_stamp_and_reports_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_event(tmp)
            self.assertEqual(self.run_event(tmp, 'proxy-route-change'), (0, 1, 1))
            self.assertEqual(self.run_event(tmp, 'proxy-route-change', connectivity='limited'),
                             (75, 0, 0))
            self.assertEqual(self.run_event(tmp, 'proxy-route-change', result=None), (1, 1, 1))

    def test_official_failure_preserves_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            listing = root / 'mirrorlist'
            listing.write_text('Server = https://baseline.invalid/$repo/$arch\n')
            original = listing.read_bytes()
            with patch.object(mirror.subprocess, 'run', side_effect=FileNotFoundError):
                self.assertIsNone(mirror.switch_official(listing, root, False, lambda msg: None))
            self.assertEqual(listing.read_bytes(), original)

    def test_installs_executable_hook_and_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data/network'
            data.mkdir(parents=True)
            hook = ROOT / 'profile/airootfs/etc/NetworkManager/dispatcher.d/90-mipl-mirror-switch'
            watcher = ROOT / 'profile/airootfs/usr/local/bin/mipl-mirror-watch'
            service = ROOT / 'profile/airootfs/etc/systemd/system/mipl-mirror-watch.service'
            for source in (SCRIPT, hook, watcher, service):
                (data / source.name).write_bytes(source.read_bytes())
            target = root / 'target'
            with patch.object(configure, '__file__', str(root / 'configure.py')):
                configure.copy_mirror_switch(FakeRunner(), configure.TargetConfig(target=str(target)))
            for source, dest in ((SCRIPT, 'usr/local/bin/mipl-mirror-switch'),
                                 (hook, 'etc/NetworkManager/dispatcher.d/90-mipl-mirror-switch'),
                                 (watcher, 'usr/local/bin/mipl-mirror-watch'),
                                 (service, 'etc/systemd/system/mipl-mirror-watch.service')):
                installed = target / dest
                self.assertEqual(installed.read_bytes(), source.read_bytes())
                self.assertEqual(installed.stat().st_mode & 0o777,
                                 0o644 if dest.endswith(".service") else 0o755)
