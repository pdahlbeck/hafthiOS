#!/usr/bin/env python3
"""Inventory every filesystem entry in the live root, ISO, initramfs and EFI image."""
import argparse
import csv
import json
import os
from pathlib import Path
import sqlite3
import stat

COLUMNS = ('layer', 'path', 'kind', 'bytes', 'mode', 'uid', 'gid', 'target',
           'package', 'version', 'package_description', 'purpose', 'evidence')
KINDS = ((stat.S_ISREG, 'file'), (stat.S_ISDIR, 'directory'), (stat.S_ISLNK, 'symlink'),
         (stat.S_ISCHR, 'character device'), (stat.S_ISBLK, 'block device'),
         (stat.S_ISFIFO, 'FIFO'), (stat.S_ISSOCK, 'socket'))

def entries(root):
    """Walk without following symlinks, including dotfiles and special nodes."""
    yield root
    def visit(directory):
        for child in sorted(directory.iterdir()):
            yield child
            if child.is_dir() and not child.is_symlink():
                yield from visit(child)
    yield from visit(root)

def sections(path):
    values = {}
    key = None
    for line in path.read_text().splitlines():
        if line.startswith('%') and line.endswith('%'):
            key = line.strip('%')
            values[key] = []
        elif line and key:
            values[key].append(line)
    return values

def owners(root):
    result = {}
    for desc in sorted((root / 'var/lib/pacman/local').glob('*/desc')):
        data = sections(desc)
        package = (data['NAME'][0], data['VERSION'][0], ' '.join(data.get('DESC', [])))
        manifest = desc.with_name('files')
        for path in sections(manifest).get('FILES', []):
            result.setdefault('/' + path.rstrip('/'), []).append(package)
    return result

def role(path, kind):
    if kind == 'symlink':
        return 'Symbolic link: redirects this path to the recorded target.'
    if kind == 'directory':
        return 'Directory: groups entries beneath this path.'
    if kind != 'file':
        return f'{kind.capitalize()}: special filesystem node; not a regular document.'
    rules = (
        ('/usr/lib/modules/', 'Kernel module or its metadata; supports kernel hardware and features.'),
        ('/usr/lib/firmware/', 'Hardware firmware data or supporting metadata.'),
        ('/usr/share/licenses/', 'License material supplied by its package.'),
        ('/usr/share/man/', 'Manual page or manual-page index.'),
        ('/usr/share/locale/', 'Translation or locale data.'),
        ('/usr/share/fonts/', 'Font resource or font metadata.'),
        ('/var/lib/pacman/local/', 'Installed-package database metadata used by pacman.'),
        ('/usr/bin/', 'Executable or command helper.'),
        ('/etc/', 'System configuration or supporting data.'),
        ('/boot/', 'Bootloader, kernel or early-startup resource.'),
        ('/usr/lib/', 'Library, service component or supporting runtime data.'),
        ('/usr/share/', 'Shared application data or documentation.'),
    )
    for prefix, explanation in rules:
        if path.startswith(prefix):
            return 'Inferred from its location: ' + explanation
    return 'No file-specific purpose has been verified. Consult its owner and path.'

def make(database, layers, root, catalog, final=False):
    package_owners = owners(root)
    curated = {'/' + e['path'][5:]: e['purpose'] for e in catalog['files'] if e['path'].startswith('live/')}
    # Create before walking so that the register indexes itself, too.
    database.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(database)
    db.execute('PRAGMA journal_mode=MEMORY')
    db.execute('DROP TABLE IF EXISTS files')
    db.execute('DROP TABLE IF EXISTS metadata')
    db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('''CREATE TABLE files (layer TEXT, path TEXT, kind TEXT, bytes INTEGER,
                mode TEXT, uid INTEGER, gid INTEGER, target TEXT, package TEXT, version TEXT,
                package_description TEXT, purpose TEXT, evidence TEXT, PRIMARY KEY(layer,path))''')
    counts = {}
    for layer, directory in layers:
        count = 0
        for file in entries(directory):
            info = file.lstat()
            relative = file.relative_to(directory).as_posix()
            path = '/' if relative == '.' else '/' + relative
            kind = next((name for test, name in KINDS if test(info.st_mode)), 'unknown')
            target = os.readlink(file) if kind == 'symlink' else ''
            # initramfs relocates or decompresses some binaries; do not assert ownership
            # based only on a matching path in a different filesystem.
            owned = package_owners.get(path, []) if layer == 'Live system' else []
            package = '; '.join(p[0] for p in owned)
            version = '; '.join(p[1] for p in owned)
            description = '; '.join(p[2] for p in owned)
            purpose = curated.get(path) if layer == 'Live system' else None
            evidence = 'Project documentation' if purpose else 'Location-based inference; not a verified file-specific explanation'
            purpose = purpose or role(path, kind)
            size = info.st_size if kind in ('file', 'symlink') else None
            if path.endswith('/airootfs.sfs') and layer == 'ISO filesystem' and not final:
                size = None
                purpose = 'Compressed live filesystem. Its final compressed size is recorded in the exported register after the embedded register is added.'
                evidence = 'Build pipeline'
            if path.endswith('file-register.sqlite'):
                purpose = 'Complete offline file register for this ISO build.'
                evidence = 'Build pipeline'
            # FAT does not store Unix ownership/permissions. Do not present the
            # host extraction defaults as metadata from the EFI filesystem.
            mode = stat.filemode(info.st_mode) if layer != 'EFI partition' else ''
            uid = info.st_uid if layer != 'EFI partition' else None
            gid = info.st_gid if layer != 'EFI partition' else None
            row = (layer,path,kind,size,mode,uid,gid,target,
                   package,version,description,purpose,evidence)
            db.execute('INSERT INTO files VALUES (' + ','.join('?' for _ in COLUMNS) + ')', row)
            count += 1
        counts[layer] = count
    db.execute('CREATE INDEX files_package ON files(package)')
    db.execute('INSERT INTO metadata VALUES (?,?)', ('layers', json.dumps(counts)))
    db.execute('INSERT INTO metadata VALUES (?,?)', ('scope', 'Every filesystem entry, including directories, symlinks and device nodes. Includes the ISO filesystem, live SquashFS, early and main initramfs, and EFI FAT image. Archives that are ordinary data files are listed as files. Runtime mounts such as procfs are not ISO contents.'))
    db.execute('INSERT INTO metadata VALUES (?,?)', ('ownership', 'Package name/version/description come from the live system pacman manifests. Ownership in other layers is left unassigned unless independently verified. Purpose inference is explicitly labelled.'))
    db.commit()
    if not final:
        # Updating a field normally preserves SQLite page count; check rather than assume.
        for _ in range(10):
            size = database.stat().st_size
            db.execute("UPDATE files SET bytes=? WHERE path IN ('/usr/share/doc/hafthios/file-register.sqlite','/hafthios-file-register.sqlite')", (size,))
            db.commit()
            if database.stat().st_size == size:
                break
        else:
            raise RuntimeError('Register size did not stabilize')
    db.close()
    print('File register:', json.dumps(counts), 'total:', sum(counts.values()))
    return counts

def export(database, destination):
    with sqlite3.connect(database) as db, destination.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(COLUMNS)
        writer.writerows(db.execute('SELECT ' + ','.join('"' + c + '"' for c in COLUMNS) + ' FROM files ORDER BY layer,path'))

def verify(embedded, final):
    with sqlite3.connect(embedded) as left, sqlite3.connect(final) as right:
        before = set(left.execute('SELECT layer,path,kind FROM files'))
        after = set(right.execute('SELECT layer,path,kind FROM files'))
    if before != after:
        raise RuntimeError(f'Embedded register coverage differs from final ISO: missing={sorted(after-before)}, extra={sorted(before-after)}')
    print(f'Final ISO coverage verified: {len(after)} filesystem entries.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--iso', type=Path, required=True)
    parser.add_argument('--initramfs', type=Path, required=True)
    parser.add_argument('--early', type=Path, required=True)
    parser.add_argument('--efi', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--final', action='store_true')
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    make(args.database, [('Live system',args.root), ('ISO filesystem',args.iso),
                        ('Initramfs',args.initramfs), ('Early initramfs',args.early), ('EFI partition',args.efi)],
         args.root, json.loads(args.catalog.read_text()), args.final)
    if args.csv:
        export(args.database,args.csv)
    if args.verify:
        verify(args.verify,args.database)
