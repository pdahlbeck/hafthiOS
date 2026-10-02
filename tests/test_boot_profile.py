import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_boot', ROOT / 'scripts/prepare-boot.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)

class BootProfileTests(unittest.TestCase):
    def test_quiet_bios_uefi_and_loopback_preserve_mount_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'syslinux').mkdir()
            (root / 'grub').mkdir()
            bios = root / 'syslinux/syslinux-linux.cfg'
            bios.write_text('APPEND archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID%\n')
            uefi = root / 'grub/grub.cfg'
            uefi.write_text('    linux /%INSTALL_DIR%/boot/%ARCH%/vmlinuz-linux archisosearchuuid=%ARCHISO_UUID%\n')
            loop = root / 'grub/loopback.cfg'
            loop.write_text('    linux /%INSTALL_DIR%/boot/%ARCH%/vmlinuz-linux img_dev=UUID=${archiso_img_dev_uuid} img_loop="${iso_path}"\n')
            originals = {p: p.read_text().strip() for p in (bios, uefi, loop)}
            boot.prepare(root)
            boot.prepare(root)
            for path, original in originals.items():
                text = path.read_text().strip()
                self.assertTrue(text.startswith(original))
                self.assertEqual(text.count(' splash '), 1)
                self.assertIn('quiet', text)
                self.assertIn('systemd.show_status=false', text)

    def test_missing_boot_entries_fail_instead_of_building_a_noisy_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                boot.prepare(tmp)
