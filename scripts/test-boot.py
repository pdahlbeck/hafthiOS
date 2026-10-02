#!/usr/bin/env python3
"""Boot the ISO with TCG and a disposable disk; check GTK's ready marker."""
import json
import pathlib
import socket
import subprocess
import tempfile
import time
from PIL import Image, ImageChops, ImageFilter

def qmp_request(sock_path, name, arguments):
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
        return command(name, arguments)

def capture_screen(sock_path, filename):
    return qmp_request(sock_path, 'screendump', {'filename': str(filename)})

def ship_visible(frame):
    original = Image.open('live/usr/share/plymouth/themes/hafthios/ship.png').convert('RGB')
    width = int(min(frame.width * 0.90, frame.height * 1.15, original.width))
    artwork = original.resize((width, int(width * original.height / original.width)))
    samples = [(x, y) for y in range(artwork.height) for x in range(artwork.width)
               if min(artwork.getpixel((x, y))) > 210][::30]
    # Match the actual line artwork, with tolerance for scaling and its motion.
    expanded = frame.convert('L').filter(ImageFilter.MaxFilter(15))
    left = (frame.width - artwork.width) // 2
    top = (frame.height - artwork.height) // 2
    for dx in (-24, -12, 0, 12, 24):
        for dy in (-6, 0, 6):
            matches = sum(expanded.getpixel((left + x + dx, top + y + dy)) > 180
                          for x, y in samples)
            if samples and matches / len(samples) > 0.75:
                return True
    return False

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
        '-cpu', 'max', '-cdrom', str(iso), '-boot', 'd',
        '-drive', f'file={disk},format=raw,if=virtio',
        '-vga', 'none', '-device', 'virtio-vga', '-display', 'none',
        '-serial', f'file:{serial_path}', '-monitor', 'none',
        '-qmp', f'unix:{sock_path},server=on,wait=off', '-no-reboot',
    ], stdout=subprocess.DEVNULL, stderr=open(out / 'qemu.log', 'w'))
    try:
        deadline = time.monotonic() + 360
        splash_seen = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('VM exited before the splash appeared')
            if serial_path.exists() and 'HAFTHIOS_GUI_READY' in serial_path.read_text(errors='replace'):
                raise RuntimeError('GTK appeared without the ship splash being detected')
            if sock_path.exists():
                capture_screen(sock_path, out / 'splash-probe.ppm')
                frame = Image.open(out / 'splash-probe.ppm').convert('RGB')
                if ship_visible(frame):
                    frame.save(out / 'splash-screen.png')
                    splash_seen = True
                    break
            time.sleep(2)
        if not splash_seen:
            raise RuntimeError('The ship splash was not detected')
        time.sleep(1)
        capture_screen(sock_path, out / 'splash-motion.ppm')
        moved = Image.open(out / 'splash-motion.ppm').convert('RGB')
        if ImageChops.difference(frame, moved).getbbox() is None:
            raise RuntimeError('The ship splash did not animate')
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'esc'}], 'hold-time': 300})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            time.sleep(1)
            capture_screen(sock_path, out / 'boot-details.ppm')
            details = Image.open(out / 'boot-details.ppm').convert('RGB')
            if not ship_visible(details):
                break
        else:
            raise RuntimeError('Esc did not replace the ship with boot details')
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'esc'}], 'hold-time': 300})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            time.sleep(1)
            capture_screen(sock_path, out / 'splash-return.ppm')
            if ship_visible(Image.open(out / 'splash-return.ppm').convert('RGB')):
                break
        else:
            raise RuntimeError('The second Esc did not restore the ship')
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
        capture_screen(sock_path, out / 'boot-screen.ppm')
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'f1'}]})
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if 'HAFTHIOS_GUIDE_READY' in serial_path.read_text(errors='replace'):
                break
            time.sleep(2)
        else:
            raise RuntimeError('The offline guide did not open after F1')
        if 'HAFTHIOS_INVENTORY_READY ' not in serial_path.read_text(errors='replace'):
            raise RuntimeError('The complete ISO register did not load')
        marker = serial_path.read_text(errors='replace').split('HAFTHIOS_INVENTORY_READY ')[-1].splitlines()[0]
        if int(marker) < 1000:
            raise RuntimeError('ISO register is unexpectedly small')
        time.sleep(3)
        capture_screen(sock_path, out / 'guide-screen.ppm')
        print('BIOS VM boot passed: animated ship, Esc details, welcome screen and offline guide reached.')
    finally:
        if process.poll() is None and not (out / 'boot-screen.ppm').exists():
            try:
                capture_screen(sock_path, out / 'boot-screen.ppm')
            except (OSError, RuntimeError, ValueError):
                pass
        if serial_path.exists():
            print(serial_path.read_text(errors='replace')[-12000:])
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
