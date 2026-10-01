#!/usr/bin/env python3
"""Boot the ISO with TCG and a disposable disk; check GTK's ready marker."""
import json
import pathlib
import socket
import subprocess
import tempfile
import time

out = pathlib.Path('out').resolve()
iso = max(out.glob('*.iso'), key=lambda p: p.stat().st_mtime)
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    disk = tmp / 'disk.raw'
    with disk.open('wb') as stream:
        stream.truncate(16 * 1024**3)
    sock_path = tmp / 'qmp.sock'
    serial_path = out / 'boot-serial.log'
    process = subprocess.Popen([
        'qemu-system-x86_64', '-accel', 'tcg', '-m', '2048', '-smp', '2',
        '-cdrom', str(iso), '-boot', 'd',
        '-drive', f'file={disk},format=raw,if=virtio',
        '-vga', 'none', '-device', 'virtio-vga', '-display', 'none',
        '-serial', f'file:{serial_path}', '-monitor', 'none',
        '-qmp', f'unix:{sock_path},server=on,wait=off', '-no-reboot',
    ], stdout=subprocess.DEVNULL, stderr=open(out / 'qemu.log', 'w'))
    try:
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('VM exited before GTK appeared')
            if serial_path.exists() and 'HAFTHIOS_GUI_READY' in serial_path.read_text(errors='replace'):
                break
            time.sleep(2)
        else:
            raise RuntimeError('GTK ready marker not received within 6 minutes')
        time.sleep(3)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(20)
            sock.connect(str(sock_path))
            file = sock.makefile('rwb')
            file.readline()
            def command(name, arguments=None):
                request = {'execute': name}
                if arguments:
                    request['arguments'] = arguments
                file.write((json.dumps(request) + '\n').encode())
                file.flush()
                while True:
                    response = json.loads(file.readline())
                    if 'error' in response:
                        raise RuntimeError(response)
                    if 'return' in response:
                        return response['return']
            command('qmp_capabilities')
            command('screendump', {'filename': str(out / 'boot-screen.ppm')})
        print('BIOS VM boot passed: graphical welcome screen reached.')
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
