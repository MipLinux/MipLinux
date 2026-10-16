"""桌面代理与路由监听：防抖、串行、失败重试与用户权限边界。"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'profile/airootfs/usr/local/bin/mipl-mirror-watch'
loader = importlib.machinery.SourceFileLoader('mirror_watch', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
watch = importlib.util.module_from_spec(spec)
loader.exec_module(watch)


class TestChanges(unittest.TestCase):
    def test_initial_observation_and_proxy_on_off_are_debounced(self):
        changes = watch.Changes()
        off, on = {'user:1000': 'off'}, {'user:1000': 'on'}
        self.assertFalse(changes.ready(off, 0, busy=False))
        self.assertTrue(changes.ready(off, 2, busy=False))
        changes.started()
        self.assertFalse(changes.ready(on, 3, busy=False))
        self.assertTrue(changes.ready(on, 5, busy=False))
        changes.started()
        self.assertFalse(changes.ready(off, 6, busy=False))
        self.assertTrue(changes.ready(off, 8, busy=False))

    def test_settings_burst_only_probes_final_state(self):
        changes = watch.Changes()
        for t, state in enumerate(('mode', 'host', 'port')):
            self.assertFalse(changes.ready({'proxy': state}, t, busy=False))
        self.assertTrue(changes.ready({'proxy': 'port'}, 4, busy=False))
        changes.started()
        self.assertFalse(changes.ready({'proxy': 'port'}, 100, busy=False))

    def test_change_during_probe_remains_pending(self):
        changes = watch.Changes()
        changes.ready({'route': 'direct'}, 0, busy=False)
        changes.ready({'route': 'direct'}, 2, busy=False)
        changes.started()
        self.assertFalse(changes.ready({'route': 'tun'}, 3, busy=True))
        self.assertFalse(changes.ready({'route': 'tun'}, 20, busy=True))
        self.assertTrue(changes.ready({'route': 'tun'}, 21, busy=False))

    def test_transient_read_failure_does_not_invent_change(self):
        changes = watch.Changes()
        self.assertFalse(changes.ready({}, 0, busy=False))
        changes.ready({'proxy': 'off'}, 1, busy=False)
        changes.ready({'proxy': 'off'}, 3, busy=False)
        changes.started()
        self.assertFalse(changes.ready({}, 5, busy=False))

    def test_failed_probe_retries_but_new_changes_do_not_wait(self):
        changes = watch.Changes()
        changes.ready({'proxy': 'on'}, 0, busy=False)
        changes.ready({'proxy': 'on'}, 2, busy=False)
        changes.started()
        changes.failed(3)
        self.assertFalse(changes.ready({'proxy': 'on'}, 32, busy=False))
        self.assertTrue(changes.ready({'proxy': 'on'}, 33, busy=False))
        self.assertFalse(changes.ready({'proxy': 'off'}, 34, busy=False))
        self.assertTrue(changes.ready({'proxy': 'off'}, 36, busy=False))


class TestSnapshot(unittest.TestCase):
    def test_route_lease_countdown_is_ignored_but_tun_route_is_detected(self):
        first = [{'dst': 'default', 'dev': 'eth0', 'expires': 99}]
        later = [{'dst': 'default', 'dev': 'eth0', 'expires': 98}]
        tun = [{'dst': 'default', 'dev': 'tun0', 'table': 2022}]
        self.assertEqual(watch.route_state(json.dumps(first)), watch.route_state(json.dumps(later)))
        self.assertNotEqual(watch.route_state(json.dumps(first)), watch.route_state(json.dumps(tun)))

    def test_tun_link_toggle_is_detected_even_before_routes_change(self):
        links = [{'ifname': 'eth0', 'operstate': 'UP', 'flags': ['UP'], 'stats64': {'tx': 1}}]
        base = watch.link_state(json.dumps(links))
        links[0]['stats64']['tx'] = 500
        self.assertEqual(base, watch.link_state(json.dumps(links)))
        links.append({'ifname': 'tun0', 'operstate': 'UNKNOWN', 'flags': ['UP'],
                      'linkinfo': {'info_kind': 'tun'}})
        self.assertNotEqual(base, watch.link_state(json.dumps(links)))

    def test_gsettings_and_kde_toggles_change_only_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'kioslaverc'
            with patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}), \
                 patch.object(watch, 'command', return_value="org.gnome.system.proxy mode 'none'\n"):
                off = watch.user_state()
                config.write_text('[Proxy Settings]\nProxyType=1\nhttpProxy=http://private.invalid:7890\n')
                on = watch.user_state()
                config.write_text('[Proxy Settings]\nProxyType=0\nhttpProxy=http://private.invalid:7890\n')
                disabled = watch.user_state()
            self.assertNotEqual(off, on)
            self.assertNotEqual(on, disabled)
            self.assertEqual(len(on), 64)
            self.assertNotIn('private.invalid', on)

    def test_password_and_unrelated_settings_do_not_trigger(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp}):
            base = "org.gnome.system.proxy mode 'none'\n"
            with patch.object(watch, 'command', return_value=base):
                first = watch.user_state()
            with patch.object(watch, 'command', return_value=base +
                              "org.gnome.system.proxy.http authentication-password 'secret'\n"):
                self.assertEqual(watch.user_state(), first)

    def test_user_settings_are_read_after_dropping_privileges(self):
        def output(argv, **kwargs):
            if 'loginctl' in argv[0]:
                return '1000 alice\n0 root\n'
            if 'runuser' in argv[0]:
                return 'a' * 64 + '\n'
            return '[]'
        with patch.object(watch, 'command', side_effect=output) as run, \
             patch.object(watch.pwd, 'getpwuid', return_value=SimpleNamespace(
                 pw_name='alice', pw_dir='/home/alice')), \
             patch.object(watch.Path, 'exists', return_value=True):
            state = watch.snapshot()
        calls = [call.args[0] for call in run.call_args_list if 'runuser' in call.args[0][0]]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:6], ['/usr/bin/runuser', '-u', 'alice', '--', '/usr/bin/env', '-i'])
        self.assertIn('DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus', calls[0])
        self.assertEqual(state['user:1000'], 'a' * 64)
