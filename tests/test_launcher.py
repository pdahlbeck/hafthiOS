import runpy
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
launcher = runpy.run_path(str(ROOT / 'live/usr/local/bin/hafthios-launcher'))


class LauncherTests(unittest.TestCase):
    def test_search_ranks_names_before_descriptions_and_folds_accents(self):
        apps = [{'id': 'a', 'name': 'Google Chrome', 'search': 'Google Chrome browser'},
                {'id': 'b', 'name': 'Notes', 'search': 'Notes import Chrome bookmarks'},
                {'id': 'c', 'name': 'Hafþi', 'search': 'Hafþi terminal'},
                {'id': 'd', 'name': 'Översikt', 'search': 'Översikt skärmar'}]
        rank = launcher['ranked_apps']
        self.assertEqual([a['id'] for a in rank(apps, 'chrome', ['b'])], ['a', 'b'])
        self.assertEqual([a['id'] for a in rank(apps, 'oversikt', [])], ['d'])
        self.assertEqual([a['id'] for a in rank(apps, 'haf terminal', [])], ['c'])
        self.assertEqual(rank(apps, 'unknown', []), [])

    def test_recency_is_bounded_deduplicated_and_handles_bad_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state/recent.json'
            self.assertEqual(launcher['read_recent'](path), [])
            recent = launcher['save_recent'](path, ['a', 'b'], 'b')
            self.assertEqual(recent, ['b', 'a'])
            self.assertEqual(launcher['read_recent'](path), recent)
            path.write_text('{broken')
            self.assertEqual(launcher['read_recent'](path), [])
        apps = [{'id': str(i), 'name': str(i), 'search': str(i)} for i in range(10)]
        self.assertEqual([a['id'] for a in launcher['ranked_apps'](apps, '', ['7', '3'])][:2], ['7', '3'])
        self.assertEqual(len(launcher['ranked_apps'](apps, '', [])), 5)


if __name__ == '__main__':
    unittest.main()
