import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
world = runpy.run_path(str(ROOT / 'live/usr/local/bin/hafthios-world'))


class VillageTests(unittest.TestCase):
    def test_missing_sensors_are_unknown_and_pause_saves_energy(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics = world['Telemetry'](Path(tmp), Path(tmp))
            metrics.sample(1)
            self.assertIsNone(metrics.temperature)
            prefs = world['DEFAULT'].copy()
            self.assertEqual(world['frame_interval'](prefs, metrics), 83)
            metrics.load = .9
            self.assertEqual(world['frame_interval'](prefs, metrics), 125)
            prefs['economy'] = True
            self.assertEqual(world['frame_interval'](prefs, metrics), 200)
            prefs['paused'] = True
            self.assertEqual(world['frame_interval'](prefs, metrics), 1000)

    def test_counters_are_smoothed_loopback_excluded_and_disk_heat_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'net').mkdir()
            (root / 'stat').write_text('cpu 100 0 0 100 0 0 0 0 999 999\n')
            (root / 'net/dev').write_text('header\nheader\nlo: 99000000 0\neth0: 100 0\n')
            for chip, heat in [('coretemp', '75000'), ('nvme', '110000')]:
                monitor = root / 'class/hwmon' / ('hwmon0' if chip == 'coretemp' else 'hwmon1')
                monitor.mkdir(parents=True)
                (monitor / 'name').write_text(chip)
                (monitor / 'temp1_input').write_text(heat)
            metrics = world['Telemetry'](root, root)
            metrics.sample(1)
            (root / 'stat').write_text('cpu 200 0 0 100 0 0 0 0 9999 9999\n')
            (root / 'net/dev').write_text('header\nheader\nlo: 990000000 0\neth0: 2000100 0\n')
            metrics.sample(2)
            self.assertAlmostEqual(metrics.load, .08 + .92 * .18)
            self.assertAlmostEqual(metrics.network, .2)
            self.assertEqual(metrics.temperature, 75)
            (root / 'stat').write_text('cpu 0 0 0 0 0 0 0 0\n')
            (root / 'net/dev').write_text('header\nheader\neth0: 0 0\n')
            metrics.sample(3)
            self.assertGreaterEqual(metrics.load, 0)
            self.assertGreaterEqual(metrics.network, 0)

    def test_battery_and_strict_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            battery = root / 'class/power_supply/BAT0'
            battery.mkdir(parents=True)
            for name, value in [('type', 'Battery'), ('status', 'Discharging'), ('capacity', '19')]:
                (battery / name).write_text(value)
            metrics = world['Telemetry'](root, root)
            metrics.sample(1)
            self.assertTrue(metrics.battery_low)
            self.assertEqual(world['frame_interval'](world['DEFAULT'], metrics), 200)
            prefs = {**world['DEFAULT'], 'paused': True}
            world['save_preferences'](prefs, root)
            self.assertEqual(world['preferences'](root), prefs)
            for bad in ('[]', 'invalid', json.dumps({'paused': 'false'})):
                (root / '.config/hafthios/world.json').write_text(bad)
                self.assertEqual(world['preferences'](root), world['DEFAULT'])
            with self.assertRaises(ValueError):
                world['save_preferences']({**prefs, 'enabled': 1}, root)
