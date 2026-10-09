import copy
import ast
from types import SimpleNamespace
import json
from pathlib import Path
import runpy
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
backend = runpy.run_path(str(ROOT / 'live/usr/local/bin/hafthios-install'))


def disk(path='/dev/vda', **updates):
    value = {'path': path, 'type': 'disk', 'ro': False, 'size': 16 * 1024**3,
             'model': 'Virtual disk', 'serial': 'disk-a', 'wwn': None, 'maj:min': '252:0', 'mountpoints': [None]}
    value.update(updates)
    return value


class InstallationSafetyTests(unittest.TestCase):
    def test_live_root_accepts_ram_and_usb_but_rejects_installed_or_unrelated_roots(self):
        globals_ = backend['live_root'].__globals__
        mounts = {'/': 'overlay rw,lowerdir=/run/archiso/airootfs,upperdir=/run/archiso/cowspace/upper',
                  '/run/archiso/airootfs': 'squashfs ro,relatime'}
        with patch.dict(globals_, mount_info=lambda path: mounts.get(path, '')):
            with patch.object(Path, 'exists', return_value=False):
                self.assertTrue(backend['live_root']())  # bootmnt absent: copy-to-RAM
                mounts['/run/archiso/bootmnt'] = 'iso9660 ro'
                self.assertTrue(backend['live_root']())
                mounts['/'] = 'ext4 rw'
                self.assertFalse(backend['live_root']())
                mounts['/'] = 'overlay rw,lowerdir=/run/other'
                self.assertFalse(backend['live_root']())
                mounts['/'] = 'overlay rw,lowerdir=/run/archiso/airootfs'
                mounts['/run/archiso/airootfs'] = 'squashfs rw'
                self.assertFalse(backend['live_root']())
                mounts['/run/archiso/airootfs'] = 'squashfs ro'
            with patch.object(Path, 'exists', return_value=True):
                self.assertFalse(backend['live_root']())

    def test_unmounted_live_usb_resolved_by_boot_uuid_is_excluded_and_unknown_media_fails_closed(self):
        payload = {'blockdevices': [disk('/dev/nvme0n1'),
                   disk('/dev/sda', children=[{'path': '/dev/sda1', 'type': 'part', 'mountpoints': [None]}])]}
        def command(args, **kwargs):
            if args[0] == 'findmnt': return ''
            if args[0] == 'blkid': return '/dev/sda1\n'
            if args[0] == 'lsblk': return json.dumps(payload)
            self.fail(str(args))
        globals_ = backend['read_disks'].__globals__
        with patch.dict(globals_, command=command, live_root=lambda: True):
            with patch.object(Path, 'read_text', return_value='archisobasedir=arch archisosearchuuid=live-uuid'):
                self.assertEqual([d['path'] for d in backend['read_disks']()], ['/dev/nvme0n1'])
            with patch.object(Path, 'read_text', return_value='quiet splash'):
                with self.assertRaisesRegex(RuntimeError, 'Could not identify the live USB'):
                    backend['read_disks']()

    def test_mounted_live_media_source_is_excluded_without_boot_uuid(self):
        def command(args, **kwargs):
            return '/dev/sda1\n' if args[0] == 'findmnt' else ''
        with patch.dict(backend['live_media_paths'].__globals__, command=command):
            with patch.object(Path, 'read_text', return_value='quiet splash'):
                self.assertEqual(backend['live_media_paths'](), {'/dev/sda1'})

    def test_live_media_mounted_root_swap_readonly_small_and_stacked_devices_are_excluded(self):
        safe = disk()
        values = [safe, disk('/dev/sda', children=[{'type':'part','mountpoints':['/run/archiso/bootmnt']}]),
                  disk('/dev/sdb', children=[{'type':'part','mountpoints':['/']}]),
                  disk('/dev/sdc', children=[{'type':'part','mountpoints':['[SWAP]']}]),
                  disk('/dev/sdd', ro=True), disk('/dev/sde', size=1024**3),
                  disk('/dev/sdf', children=[{'type':'crypt','mountpoints':[None]}])]
        self.assertEqual(backend['eligible_disks']({'blockdevices': values}), [safe])

    def test_disk_identity_exact_confirmation_password_and_expiry_are_required(self):
        current = disk()
        plan = {'disk': backend['identity'](current), 'confirmation':'ERASE /dev/vda', 'created':time.time()}
        request = {'confirmation':'ERASE /dev/vda', 'password':'test-password-123', 'settings':{'language':'sv','keyboard':'se'}}
        backend['validate_request'](plan, request, current)
        cases = [(dict(request, confirmation='yes'), current, plan),
                 (dict(request, password='short'), current, plan),
                 (dict(request, password='secret\nroot:bad'), current, plan),
                 (request, disk(serial='replacement'), plan),
                 (request, current, dict(plan, created=time.time()-1801))]
        for req, dev, saved in cases:
            with self.assertRaises(ValueError):
                backend['validate_request'](saved, req, dev)

    def test_vm_console_handles_the_complete_install_command_before_sending_keys(self):
        tree = ast.parse((ROOT / 'scripts/test-boot.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'type_text')
        sleeps = []
        namespace = {'time': SimpleNamespace(sleep=sleeps.append)}
        calls = []
        namespace['qmp_request'] = lambda _socket, name, args: calls.append((name, args))
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<console test>', 'exec'), namespace)
        command = 'echo Q+/== | base64 -d | sudo python3 > /dev/ttyS0 2>&1' + ' findmnt --output TARGET,SOURCE,FSTYPE,OPTIONS'
        namespace['type_text']('mock-socket', command)
        typed = []
        shifted = {'7':'&', 'equal':'+', 'backslash':'|', 'dot':'>', 'minus':'_'}
        plain = {'comma':',', 'spc':' ', 'equal':'=', 'backslash':'\\', 'dot':'.', 'minus':'-', 'slash':'/'}
        self.assertTrue(all(not e['data']['down'] for e in calls[0][1]['events']))
        for name, args in calls[1:]:
            self.assertEqual(name, 'send-key')
            self.assertLess(args['hold-time'] / 1000, min(sleeps))
            keys = [key['data'] for key in args['keys']]
            key = keys[-1]
            if key != 'ret':
                typed.append(shifted.get(key, key.upper()) if 'shift' in keys else plain.get(key, key))
        self.assertEqual(''.join(typed), command)
        self.assertEqual(calls[-1][1]['keys'], [{'type':'qcode','data':'ret'}])
        calls.clear()
        namespace['type_text']('mock-socket', 'hafthi', submit=False)
        self.assertFalse(any(key['data'] == 'ret' for name,args in calls if name == 'send-key' for key in args['keys']))
        self.assertEqual(len(calls) - 1, len('hafthi'))
        calls.clear()
        with self.assertRaises(ValueError):
            namespace['type_text']('mock-socket', 'echo unsupported!')
        self.assertEqual(calls, [])

    def test_partition_names_include_digit_separator_only_when_required(self):
        self.assertEqual(backend['partition_path']('/dev/vda',3), '/dev/vda3')
        self.assertEqual(backend['partition_path']('/dev/nvme0n1',3), '/dev/nvme0n1p3')
        self.assertEqual(backend['partition_path']('/dev/mmcblk0',2), '/dev/mmcblk0p2')

    def test_invalid_confirmation_cannot_reach_partition_or_format_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            token='a'*32
            plan={'disk':backend['identity'](disk()),'created':time.time(),'confirmation':'ERASE /dev/vda'}
            (state/(token+'.json')).write_text(json.dumps(plan))
            globals_ = backend['install'].__globals__
            with patch.dict(globals_, STATE=state, live_only=lambda:None, selected_disk=lambda _:disk(), command=lambda *_args,**_kw: self.fail('A disk command ran before confirmation')):
                with self.assertRaises(ValueError):
                    backend['install']({'token':token,'confirmation':'yes','password':'test-password-123','settings':{'language':'sv','keyboard':'se'}})
            self.assertTrue((state/(token+'.json')).exists())

    def test_installed_config_removes_live_autologin_and_passwordless_sudo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for path in ('etc/systemd/system/getty@tty1.service.d/autologin.conf','etc/sudoers.d/hafthios-live','etc/mkinitcpio.conf.d/archiso.conf','home/hafthi/.config/hafthios/chrome/SingletonLock'):
                target=root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_text('live-only')
            kernel=root/'usr/lib/modules/test/vmlinuz';kernel.parent.mkdir(parents=True);kernel.write_bytes(b'kernel')
            mirror=root/'etc/pacman.d/mirrorlist'
            mirror.parent.mkdir(parents=True, exist_ok=True)
            mirror_content=(ROOT/'live/etc/pacman.d/mirrorlist').read_text()
            mirror.write_text(mirror_content)
            (root/'boot').mkdir()
            commands=[]
            def command(args, **kwargs):
                commands.append((args,kwargs));return ''
            with patch.dict(backend['configure'].__globals__, command=command, phase=lambda _:None):
                backend['configure'](root, {'password':'test-password-123','settings':{'language':'sv','keyboard':'se'}})
            self.assertFalse((root/'etc/sudoers.d/hafthios-live').exists())
            self.assertFalse((root/'home/hafthi/.config/hafthios/chrome/SingletonLock').exists())
            self.assertFalse((root/'etc/systemd/system/getty@tty1.service.d/autologin.conf').exists())
            self.assertNotIn('NOPASSWD', (root/'etc/sudoers.d/hafthios-wheel').read_text())
            self.assertNotIn('archiso', (root/'etc/mkinitcpio.conf').read_text())
            self.assertEqual((root/'etc/locale.conf').read_text(), 'LANG=sv_SE.UTF-8\n')
            self.assertEqual((root/'etc/vconsole.conf').read_text(), 'KEYMAP=sv-latin1\n')
            self.assertEqual(mirror.read_text(), mirror_content)
            self.assertNotIn('niri-session', (root/'home/hafthi/.bash_profile').read_text())
            greeter = (root/'etc/greetd/config.toml').read_text()
            self.assertIn('LANG=sv_SE.UTF-8 XKB_DEFAULT_LAYOUT=se', greeter)
            self.assertIn('/usr/local/bin/hafthios-greeter', greeter)
            self.assertIn('WLR_NO_HARDWARE_CURSORS=1', greeter)
            self.assertNotIn('initial_session', greeter)
            self.assertIn('user = "greeter"', greeter)
            self.assertTrue(any('enable' in args and 'greetd.service' in args for args,kw in commands))
            self.assertTrue(any(args[-1:] == ['graphical.target'] for args,kw in commands))
            self.assertTrue(any(args[-1:] == ['chpasswd'] and kw['input'].startswith('hafthi:') for args,kw in commands))
            self.assertTrue(any('runuser' in args and 'sv' in args and 'se' in args for args,kw in commands))


if __name__ == '__main__':
    unittest.main()
