import importlib.machinery
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

path = pathlib.Path(__file__).parents[1] / 'live/usr/local/bin/hafthios-welcome'
loader = importlib.machinery.SourceFileLoader('welcome', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
welcome = importlib.util.module_from_spec(spec)
loader.exec_module(welcome)


class DiskPreviewTests(unittest.TestCase):
    def test_excludes_partitions_readonly_and_loop_devices(self):
        disks = [{'path': '/dev/vda', 'type': 'disk', 'ro': False},
                 {'path': '/dev/vda1', 'type': 'part', 'ro': False},
                 {'path': '/dev/sr0', 'type': 'rom', 'ro': True},
                 {'path': '/dev/loop0', 'type': 'loop', 'ro': False},
                 {'path': '/dev/sdb', 'type': 'disk', 'ro': True}]
        self.assertEqual(welcome.eligible_disks({'blockdevices': disks}), [disks[0]])

    def test_disk_query_is_read_only(self):
        with patch.object(welcome.subprocess, 'run') as run:
            run.return_value.stdout = '{"blockdevices":[{"path":"/dev/vda","type":"disk","ro":false,"size":16000000000,"model":"Virtual disk"}]}'
            disks = welcome.read_disks()
            self.assertEqual(disks[0]['size'], '16.0 GB')
            args = run.call_args.args[0]
            self.assertEqual(args[0], 'lsblk')
            self.assertEqual(run.call_count, 1)

    def test_empty_machine(self):
        self.assertEqual(welcome.eligible_disks({'blockdevices': []}), [])


if __name__ == '__main__':
    unittest.main()
