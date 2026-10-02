#!/usr/bin/env python3
"""Quiet the official Archiso boot entries without changing their mount arguments."""
from pathlib import Path
import sys

PARAMETERS = 'quiet splash loglevel=3 systemd.show_status=true fbcon=nodefer rd.udev.log_level=3 vt.global_cursor_default=0'

def prepare(profile):
    profile = Path(profile)
    changed = 0
    for directory in ('syslinux', 'grub'):
        for path in (profile / directory).glob('*.cfg'):
            lines = []
            for line in path.read_text().splitlines():
                if ('vmlinuz-linux' in line and line.lstrip().startswith('linux ')) or line.startswith('APPEND '):
                    if ' splash ' not in f' {line} ':
                        line += ' ' + PARAMETERS
                    changed += 1
                line = line.replace('MENU TITLE Arch Linux', 'MENU TITLE Hafthi OS')
                line = line.replace('MENU LABEL Arch Linux', 'MENU LABEL Hafthi OS')
                line = line.replace('menuentry "Arch Linux', 'menuentry "Hafthi OS')
                line = line.replace('TIMEOUT 30', 'TIMEOUT 10')
                line = line.replace('timeout=15', 'timeout=1').replace('timeout_style=menu', 'timeout_style=hidden')
                lines.append(line)
            path.write_text('\n'.join(lines) + '\n')
    if changed < 2:
        raise RuntimeError('Expected BIOS and UEFI Linux boot entries in the Archiso baseline')

if __name__ == '__main__':
    prepare(sys.argv[1])
