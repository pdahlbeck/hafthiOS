#!/usr/bin/env python3
"""Embed the full register, repack once, then verify against the finished ISO."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('inventory', ROOT / 'scripts/build-inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, **kwargs)

def extract_iso(iso, destination):
    destination.mkdir()
    run('xorriso', '-osirrox', 'on', '-indev', iso, '-extract', '/', destination)

def package(workspace, root):
    import json
    work = workspace / 'work'
    live = work / 'x86_64/airootfs'
    out = root / 'out'
    iso = max(out.glob('*.iso'), key=lambda p: p.stat().st_mtime)
    first = workspace / 'iso-first'
    extract_iso(iso, first)
    initramfs = first / 'arch/boot/x86_64/initramfs-linux.img'
    main = workspace / 'initramfs'
    early = workspace / 'early-initramfs'
    efi = workspace / 'efi-files'
    for directory in (main, early, efi):
        directory.mkdir()
    run('lsinitcpio', '--cpio', '-x', initramfs, cwd=main)
    run('lsinitcpio', '--early', '-x', initramfs, cwd=early)
    run('mcopy', '-s', '-i', work / 'efiboot.img', '::*', efi)
    catalog = json.loads((root / 'docs/file-guide.json').read_text())
    database = live / 'usr/share/doc/hafthios/file-register.sqlite'
    layers = [('Live system',live), ('ISO filesystem',first), ('Initramfs',main),
              ('Early initramfs',early), ('EFI partition',efi)]
    inventory.make(database,layers,live,catalog)
    shutil.copyfile(database, work / 'iso/hafthios-file-register.sqlite')
    # The register changes only the compressed root and the enclosing ISO.
    # Leave package installation, boot images and initramfs intact.
    markers = ('base._prepare_airootfs_image', 'base._mkairootfs_squashfs',
               'iso._build_iso_image', 'build._build_buildmode_iso')
    for name in markers:
        marker = work / name
        if not marker.exists():
            raise RuntimeError(f'Archiso build checkpoint changed: {name}')
        marker.unlink()
    run('mkarchiso', '-v', '-w', work, '-o', out, workspace / 'profile')
    shutil.rmtree(first)
    final = workspace / 'iso-final'
    extract_iso(iso,final)
    final_root = workspace / 'root-final'
    run('unsquashfs', '-no-progress', '-d', final_root, final / 'arch/x86_64/airootfs.sfs')
    exported = out / 'hafthios-file-register.sqlite'
    inventory.make(exported,[('Live system',final_root),('ISO filesystem',final),
                             ('Initramfs',main),('Early initramfs',early),('EFI partition',efi)],
                   final_root,catalog,final=True)
    embedded = final_root / 'usr/share/doc/hafthios/file-register.sqlite'
    inventory.verify(embedded,exported)
    inventory.export(exported,out / 'hafthios-file-register.csv')
    with __import__('sqlite3').connect(exported) as db:
        counts = db.execute('SELECT layer,count(*) FROM files GROUP BY layer').fetchall()
    (out / 'file-register-summary.txt').write_text('\n'.join(f'{layer}: {count}' for layer,count in counts)
        + '\nFinal ISO path/type coverage verified against the embedded register.\n')

if __name__ == '__main__':
    package(Path(sys.argv[1]),Path(sys.argv[2]))
