import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / 'live/usr/local/bin/hafthios-chrome'
loader = importlib.machinery.SourceFileLoader('chrome_setup', str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
chrome = importlib.util.module_from_spec(spec)
loader.exec_module(chrome)


class ChromeTests(unittest.TestCase):
    def test_root_is_rejected_and_normal_user_keeps_sandbox(self):
        with patch.object(chrome.os, 'geteuid', return_value=0), patch.object(chrome.subprocess, 'Popen') as spawn:
            with self.assertRaises(RuntimeError):
                chrome.launch()
            spawn.assert_not_called()
        with patch.object(chrome.os, 'geteuid', return_value=1000), patch.object(chrome.subprocess, 'Popen') as spawn:
            chrome.launch()
            command = spawn.call_args.args[0]
            self.assertNotIn('--no-sandbox', command)
            self.assertNotIn('--disable-setuid-sandbox', command)
            self.assertIn('--ozone-platform=wayland', command)

    def test_failed_download_preserves_existing_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'chrome'
            root.mkdir()
            marker = root / 'existing'
            marker.write_text('keep')
            with patch.object(chrome, 'ROOT', root), patch.object(chrome.urllib.request, 'urlopen', side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    chrome.install()
            self.assertEqual(marker.read_text(), 'keep')
            self.assertEqual(sorted(Path(temporary).iterdir()), [root])
