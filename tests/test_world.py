import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
world = runpy.run_path(str(ROOT / 'live/usr/local/bin/hafthios-world'))


class VillageTests(unittest.TestCase):
    def test_fort_travellers_shrink_to_dots_and_keep_continuous_dry_routes(self):
        self.assertLessEqual(22*world['distant_scale'](717),2)
        self.assertEqual(world['distant_scale'](935),1)
        for y in range(718,936):
            self.assertGreater(world['distant_scale'](y),world['distant_scale'](y-1))
        for tick in range(2401):
            for a in world['fort_travellers'](tick):
                x,y=a['position']
                self.assertLess(y+15*a['scale'],world['shoreline_y'](x)-12)
                for left,top,right,bottom in world['HOUSE_OBSTACLES']:
                    self.assertFalse(left<x<right and top<y<bottom)
            old={a['kind']:a for a in world['fort_travellers'](tick)}
            for a in world['fort_travellers'](tick+1):
                if a['kind'] in old:
                    self.assertLess(world['math'].dist(a['position'],old[a['kind']]['position']),3)

    def test_woodland_animals_remain_in_dry_western_glades(self):
        for tick in range(3601):
            a=world['woodland_animals'](tick*.5)
            b=world['woodland_animals']((tick+1)*.5)
            for animal,next_animal in zip(a,b):
                x,y=animal['position']
                self.assertLess(y+8,world['shoreline_y'](x)-12)
                self.assertLess(x,350)
                self.assertLess(world['math'].dist(animal['position'],next_animal['position']),1)
                for left,top,right,bottom in world['HOUSE_OBSTACLES']:
                    self.assertFalse(left<x<right and top<y<bottom)

    def test_fisher_rows_lands_cleans_and_returns_without_teleporting(self):
        state=world['fishing_state']
        self.assertEqual([state(t)['action'] for t in (140,200,300,340,370,420,500)],
                         ['row','fish','row','unload-fish','fish-carry','clean-fish','walk'])
        for tick in range(1300,9300):
            a,b=state(tick/10),state((tick+1)/10)
            self.assertLess(world['math'].dist(a['position'],b['position']),2)
            if a['aboard']:
                self.assertEqual(a['position'],a['boat'])
            if a['action']=='clean-fish':
                self.assertFalse(a['aboard'])
                self.assertLess(a['position'][1],world['shoreline_y'](a['position'][0])-12)
        self.assertEqual(state(530)['boat'],state(130)['boat'])

    def test_supper_seats_fire_benches_and_approaches_stay_on_dry_land(self):
        shore=world['shoreline_y']
        x,y=world['SUPPER_X'],world['SUPPER_Y']
        # Includes the lowest bench and the rightmost edge of the hearth.
        for dx,dy in [(-8,28),(70,28),(102,-2)]:
            self.assertLess(y+dy,shore(x+dx)-12)
        for tick in range(0,18001):
            for index,actor in enumerate(world['daily_actors'](tick/10)):
                if actor['visible'] and not actor.get('aboard'):
                    px,py=actor['position']
                    if not (index==1 and abs(px-1397)<.01 and 1020<=py<=1145):
                        self.assertLess(py,shore(px)-12)

    def test_visible_villagers_do_not_cross_house_footprints(self):
        for tick in range(0,3601):
            for actor in world['daily_actors'](tick*.5)+world['connected_actors'](tick*.5):
                if not actor['visible'] or actor.get('aboard'):
                    continue
                x,y=actor['position']
                for left,top,right,bottom in world['HOUSE_OBSTACLES']:
                    self.assertFalse(left<x<right and top<y<bottom,
                                     (tick,actor,(left,top,right,bottom)))
        for a,b in [((775,810),(2040,875)),((1614,840),(960,1015))]:
            route=world['walking_route'](a,b)
            self.assertTrue(all(world['clear_house_segment'](p,q)
                                for p,q in zip(route,route[1:])))

    def test_hunter_keeps_distance_and_catches_one_of_twenty_shots(self):
        import math
        hunt=world['hunting_state']
        shots=[hunt(40+i*12+.5) for i in range(20)]
        self.assertEqual(sum(s['hit'] for s in shots),1)
        self.assertTrue(all(math.dist(s['position'],s['prey'])>150 for s in shots))
        self.assertTrue(hunt(275)['caught'])
        self.assertFalse(hunt(325)['caught'])
        previous=hunt(0)
        for i in range(1,7201):
            current=hunt(i*.1)
            self.assertLess(math.dist(previous['position'],current['position']),3)
            previous=current

    def test_food_delivery_supper_and_night_have_continuous_routes(self):
        actors=world['daily_actors']
        self.assertEqual(actors(370)[1]['action'],'fish-carry')
        self.assertEqual(actors(400)[1]['action'],'clean-fish')
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
                self.assertEqual(current['position'], world['door_position'](home))
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
