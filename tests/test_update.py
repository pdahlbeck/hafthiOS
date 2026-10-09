import hashlib
import io
import json
from pathlib import Path
import runpy
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
updater = runpy.run_path(str(ROOT / 'live/usr/local/bin/hafthios-update'))


def archive(path, entries):
    with tarfile.open(path, 'w:gz') as tar:
        for name, data, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(data) if kind == tarfile.REGTYPE else 0
            member.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
            tar.addfile(member, io.BytesIO(data) if member.isfile() else None)


class UpdateTests(unittest.TestCase):
    def test_archive_rejects_traversal_links_unlisted_files_and_bad_hashes(self):
        data = b'new terminal'
        manifest = {'format': 1, 'files': [{'path': 'usr/local/bin/hafthi', 'mode': 0o755,
                                         'sha256': hashlib.sha256(data).hexdigest()}]}
        good = [('manifest.json', json.dumps(manifest).encode(), tarfile.REGTYPE),
                ('payload/usr/local/bin/hafthi', data, tarfile.REGTYPE)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'update.tar.gz'
            for entries in (good + [('payload/../../etc/passwd', b'bad', tarfile.REGTYPE)],
                            good + [('payload/usr/local/bin/hafthi', b'', tarfile.SYMTYPE)],
                            [good[0], ('payload/usr/local/bin/hafthi', b'tampered', tarfile.REGTYPE)],
                            good + [('payload/etc/shadow', b'bad', tarfile.REGTYPE)]):
                archive(path, entries)
                with self.assertRaises(RuntimeError):
                    updater['unpack_verified'](path, Path(tmp) / 'payload')
            archive(path, good)
            self.assertEqual(updater['unpack_verified'](path, Path(tmp) / 'good')['format'], 1)

    def test_update_and_rollback_preserve_user_data_and_remove_new_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'system'
            payload = Path(tmp) / 'payload'
            old = root / 'usr/local/bin/hafthi'
            old.parent.mkdir(parents=True)
            old.write_text('old')
            user = root / 'home/hafthi/Documents/test.txt'
            user.parent.mkdir(parents=True)
            user.write_text('personal file')
            files = [{'path': 'usr/local/bin/hafthi', 'mode': 0o755},
                     {'path': 'usr/local/bin/hafthios-launcher', 'mode': 0o755}]
            for item in files:
                source = payload / item['path']
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('new')
            backup = Path(tmp) / 'backup'
            with patch.object(updater['os'], 'chown'):
                updater['apply_payload'](payload, {'files': files}, root, backup)
                self.assertEqual(old.read_text(), 'new')
                self.assertEqual(user.read_text(), 'personal file')
                updater['restore'](backup)
                self.assertEqual(old.read_text(), 'old')
                self.assertFalse((root / 'usr/local/bin/hafthios-launcher').exists())
                self.assertEqual(user.read_text(), 'personal file')

    def test_download_rejects_unverified_release(self):
        values = [json.dumps({'assets': [{'name': name, 'browser_download_url': 'https://github.com/' + name}
                  for name in ('hafthios-update.tar.gz', 'hafthios-update.sha256', 'hafthios-update.json')]}).encode(),
                  json.dumps({'run_id': 123, 'revision': 'abc'}).encode(),
                  json.dumps({'status': 'completed', 'conclusion': 'failure', 'head_sha': 'abc', 'head_branch': 'main'}).encode()]
        with patch.dict(updater['verified_release'].__globals__, fetch=lambda *_: values.pop(0)):
            with self.assertRaisesRegex(RuntimeError, 'has not passed'):
                updater['verified_release']()


if __name__ == '__main__':
    unittest.main()
