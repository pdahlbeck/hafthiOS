#!/usr/bin/env python3
"""Validate project-file coverage and package offline documentation + sources."""
import argparse
import json
from pathlib import Path
import shutil

EXCLUDED = {'.git', 'out', 'preview', '__pycache__'}


def project_files(root):
    return {p.relative_to(root).as_posix() for p in root.rglob('*')
            if p.is_file() and not any(part in EXCLUDED for part in p.relative_to(root).parts)
            and p.suffix != '.pyc'}


def safe_path(value):
    path = Path(value)
    if not value or path.is_absolute() or '..' in path.parts or str(path) == '.':
        raise ValueError(f'Invalid catalog path: {value}')
    return path


def bundle(root, destination):
    catalog = json.loads((root / 'docs/file-guide.json').read_text())
    entries = catalog['files']
    paths = [entry['path'] for entry in entries]
    for path in paths:
        safe_path(path)
    if len(paths) != len(set(paths)):
        raise ValueError('Duplicate catalog entries')
    actual = project_files(root)
    if set(paths) != actual:
        raise ValueError(f'Catalog mismatch: undocumented={sorted(actual - set(paths))}; missing={sorted(set(paths) - actual)}')
    for entry in entries:
        if not entry['purpose'] or not entry['when'] or not entry['details']:
            raise ValueError(f'Incomplete article: {entry["path"]}')
        if not set(entry['connections']) <= actual:
            raise ValueError(f'Unknown connected file: {entry["path"]}')
    # Destination must be outside the source inventory (typically a temporary image root).
    if destination.resolve().is_relative_to(root.resolve()):
        raise ValueError('Guide bundle destination must be outside the repository')
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'docs/file-guide.json', destination / 'file-guide.json')
    shutil.copyfile(root / 'docs/index.md', destination / 'index.md')
    for path in paths:
        source = root / safe_path(path)
        if source.is_symlink():
            raise ValueError(f'Source snapshots must be regular files: {path}')
        target = destination / 'sources' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return catalog


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    catalog = bundle(root, args.destination)
    print(f'Bundled English guide for {len(catalog["files"])} project files.')
