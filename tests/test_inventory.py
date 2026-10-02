import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inventory', ROOT / 'scripts/build-inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

class InventoryTests(unittest.TestCase):
    def test_every_entry_hidden_files_dangling_links_and_package_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root'
            root.mkdir()
            (root / '.hidden').write_text('hello')
            (root / 'dangling').symlink_to('/missing')
            (root / 'directory-link').symlink_to('.')
            package = root / 'var/lib/pacman/local/example-1'
            package.mkdir(parents=True)
            (package / 'desc').write_text('%NAME%\nexample\n\n%VERSION%\n1-1\n\n%DESC%\nExample package\n')
            (package / 'files').write_text('%FILES%\n.hidden\n')
            database = root / 'usr/share/doc/hafthios/file-register.sqlite'
            inventory.make(database,[('Live system',root)],root,{'files':[]})
            with sqlite3.connect(database) as db:
                rows = {r[0]:r[1:] for r in db.execute('SELECT path,kind,bytes,package,target FROM files')}
                self.assertEqual(rows['/.hidden'],('file',5,'example',''))
                self.assertEqual(rows['/dangling'][0],'symlink')
                self.assertEqual(rows['/dangling'][3],'/missing')
                self.assertEqual(rows['/directory-link'][0],'symlink')
                self.assertIn('/',rows)
                self.assertEqual(rows['/usr/share/doc/hafthios/file-register.sqlite'][1],database.stat().st_size)
                self.assertFalse(any('-journal' in p for p in rows))
                self.assertEqual(set(rows),{'/' if p == root else '/' + p.relative_to(root).as_posix() for p in inventory.entries(root)})

    def test_other_layers_do_not_claim_live_package_ownership_and_verify_missing_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root';root.mkdir()
            (root / 'command').write_text('a')
            first = Path(tmp) / 'first.sqlite'
            second = Path(tmp) / 'second.sqlite'
            inventory.make(first,[('Initramfs',root)],root,{'files':[]})
            (root / 'new').write_text('b')
            inventory.make(second,[('Initramfs',root)],root,{'files':[]})
            with self.assertRaises(RuntimeError):inventory.verify(first,second)
            inventory.verify(second,second)
