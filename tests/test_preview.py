import importlib.machinery
import importlib.util
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

path = pathlib.Path(__file__).parents[1] / 'live/usr/local/bin/hafthios-welcome'
loader = importlib.machinery.SourceFileLoader('welcome', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
welcome = importlib.util.module_from_spec(spec)
loader.exec_module(welcome)


class DiskPreviewTests(unittest.TestCase):
    def test_installation_ui_queries_disks_through_privileged_readonly_helper(self):
        with patch.object(welcome.subprocess, 'run') as run:
            run.return_value = SimpleNamespace(stdout='{"disks":[{"path":"/dev/nvme0n1"}]}', stderr='', returncode=0)
            self.assertEqual(welcome.installer_request('list')['disks'][0]['path'], '/dev/nvme0n1')
            self.assertEqual(run.call_args.args[0], ['sudo', '-n', '/usr/local/bin/hafthios-install', 'list'])
            run.return_value = SimpleNamespace(stdout='{"error":"Could not identify the live USB"}', stderr='', returncode=1)
            with self.assertRaisesRegex(RuntimeError, 'Could not identify the live USB'):
                welcome.installer_request('list')
            run.return_value = SimpleNamespace(stdout='', stderr='sudo: a password is required', returncode=1)
            with self.assertRaisesRegex(RuntimeError, 'sudo: a password is required'):
                welcome.installer_request('list')
        source = path.read_text()
        self.assertIn("self.settings_task(lambda: installer_request('list')['disks'], finished)", source)

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
