import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_guide', ROOT / 'scripts/build-guide.py')
guide = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guide)


class FileGuideTests(unittest.TestCase):
    def test_every_file_is_documented_and_sources_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'guide'
            catalog = guide.bundle(ROOT, destination)
            self.assertEqual(catalog['language'], 'en')
            self.assertEqual(len(catalog['files']), len(guide.project_files(ROOT)))
            for entry in catalog['files']:
                path = entry['path']
                self.assertEqual((ROOT / path).read_bytes(), (destination / 'sources' / path).read_bytes())
            self.assertEqual(json.loads((destination / 'file-guide.json').read_text()), catalog)

    def test_rejects_absolute_and_parent_paths(self):
        for path in ('/etc/shadow', '../outside', 'docs/../../outside', ''):
            with self.assertRaises(ValueError):
                guide.safe_path(path)


if __name__ == '__main__':
    unittest.main()
