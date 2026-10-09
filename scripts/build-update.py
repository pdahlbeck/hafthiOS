#!/usr/bin/env python3
"""Package only Hafthi-owned desktop files, including the compiled terminal."""
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tarfile

project = Path(__file__).resolve().parents[1]
allowed = runpy.run_path(str(project / 'live/usr/local/bin/hafthios-update'))['allowed_path']
root, out = map(Path, sys.argv[1:3])
manifest = {'format': 1, 'architecture': 'x86_64', 'revision': os.environ['GITHUB_SHA'],
            'run_id': int(os.environ['GITHUB_RUN_ID']), 'files': []}
paths = sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and allowed(p.relative_to(root).as_posix()))
for path in paths:
    relative = path.relative_to(root).as_posix()
    manifest['files'].append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                              'mode': 0o755 if relative.startswith(('usr/local/bin/', 'usr/local/libexec/')) else 0o644})
out.mkdir(exist_ok=True)
archive = out / 'hafthios-update.tar.gz'
with tarfile.open(archive, 'w:gz') as tar:
    raw = json.dumps(manifest).encode()
    header = tarfile.TarInfo('manifest.json')
    header.size = len(raw)
    tar.addfile(header, io.BytesIO(raw))
    for item in manifest['files']:
        tar.add(root / item['path'], arcname='payload/' + item['path'], recursive=False)
(out / 'hafthios-update.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n')
(out / 'hafthios-update.json').write_text(json.dumps({key: manifest[key] for key in ('revision', 'run_id', 'format', 'architecture')}) + '\n')
print('Desktop update packaged:', len(paths), 'files,', archive.stat().st_size, 'bytes')
