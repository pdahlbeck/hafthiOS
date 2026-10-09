import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
world = runpy.run_path(str(ROOT / 'live/usr/local/bin/hafthios-world'))


class VillageTests(unittest.TestCase):
    def test_food_delivery_supper_and_night_have_continuous_routes(self):
        actors=world['daily_actors']
        self.assertEqual(actors(400)[1]['action'],'fish-carry')
        self.assertEqual(actors(500)[1]['action'],'clean-fish')
        self.assertEqual(actors(500)[2]['action'],'cook')
        self.assertEqual(actors(800)[2]['action'],'bake')
        self.assertTrue(all(a['action']=='eat' for a in actors(1100)))
        self.assertTrue(all(not a['visible'] for a in actors(1500)))
        actions=set()
        import math
        previous=actors(0)
        for tick in range(1,7201):
            current=actors(tick*.5)
            for before,after in zip(previous,current):
                self.assertLess(math.dist(before['position'],after['position']),8)
                actions.add(after['action'])
            previous=current
        self.assertTrue({'sow','harvest','sack','net','weave','roof','herd','sit','talk','eat'}<=actions)
        self.assertEqual(world['evening_light'](0),0)
        self.assertGreater(world['evening_light'](1400),.9)
        self.assertAlmostEqual(world['evening_light'](1799.999),world['evening_light'](1800.001),places=4)

    def test_connected_deliveries_precede_smithing_shipwork_and_trade_departure(self):
        actors=world['connected_actors']
        self.assertEqual(actors(139)[0]['action'],'handoff')
        self.assertEqual(actors(155)[1]['action'],'smith')
        self.assertEqual(actors(240)[2]['action'],'tools')
        self.assertEqual(actors(272)[2]['action'],'handoff')
        self.assertEqual(actors(290)[3]['action'],'ship')
        self.assertEqual(actors(415)[3]['action'],'talk')
        # Trade crew unloads, visits the market and boards before the ship leaves.
        self.assertEqual(actors(315)[4]['action'],'carry')
        self.assertEqual(actors(340)[4]['action'],'trade')
        self.assertEqual(actors(400)[4]['action'],'aboard')
        self.assertFalse(world['voyage_state'](425)[1])
        self.assertTrue(all(not a['visible'] for a in actors(425)[4:]))
        import math
        previous=actors(0)
        for i in range(1,9601):
            current=actors(i*.1)
            for before,after in zip(previous,current):
                self.assertLess(math.dist(before['position'],after['position']),2)
            previous=current

    def test_ship_docks_for_loading_and_voyages_are_continuous(self):
        voyage = world['voyage_state']
        for t in (0, 30, 59, 300, 359, 360):
            self.assertEqual(voyage(t), (0., True))
        for t in (90, 180, 250):
            distance, docked = voyage(t)
            self.assertFalse(docked)
            self.assertTrue(0 < distance <= 1)
        for boundary in (60,150,210,300,360):
            self.assertAlmostEqual(voyage(boundary-.001)[0], voyage(boundary+.001)[0], places=5)

    def test_occupations_reach_workplace_and_return_indoors_without_teleporting(self):
        state = world['worker_state']
        home, destination = (800,800), (1100,1000)
        previous = None
        actions = set()
        for i in range(2200):
            current = state(i*.1,0,home,destination,'smith')
            actions.add(current['action'])
            if current['action'] == 'smith':
                self.assertEqual(current['position'], destination)
            if not current['visible']:
                self.assertEqual(current['position'], home)
            if previous:
                import math
                self.assertLessEqual(math.dist(previous['position'],current['position']),1.31)
            previous=current
        self.assertTrue({'indoors','walk','smith'} <= actions)

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
