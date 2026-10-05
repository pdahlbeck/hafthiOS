#!/usr/bin/env python3
"""Boot the ISO with TCG and a disposable disk; check GTK's ready marker."""
import json
import base64
import shutil
import os
import pathlib
import socket
import subprocess
import tempfile
import time

def window_present(text, app_id):
    for line in reversed(text.splitlines()):
        if line.startswith('HAFTHIOS_DESKTOP_READY '):
            try:
                return any(w.get('app_id', '').lower() == app_id for w in json.loads(line.split(' ', 1)[1]))
            except (ValueError, AttributeError):
                continue
    return False
from PIL import Image, ImageChops, ImageFilter, ImageGrab

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

def type_text(sock_path, text):
    special = {' ': ('spc', False), '-': ('minus', False), '=': ('equal', False),
               '+': ('equal', True), '/': ('slash', False), '|': ('backslash', True),
               '>': ('dot', True), '.': ('dot', False), '_': ('minus', True), '&': ('7', True)}
    unknown = set(text) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') - set(special)
    if unknown:
        raise ValueError('Unsupported VM console characters: ' + repr(sorted(unknown)))
    for character in text:
        if character.isalnum():
            key, shift = character.lower(), character.isupper()
        else:
            key, shift = special[character]
        keys = ([{'type':'qcode', 'data':'shift'}] if shift else []) + [{'type':'qcode', 'data':key}]
        qmp_request(sock_path, 'send-key', {'keys':keys, 'hold-time':20})
        time.sleep(0.04)
    qmp_request(sock_path, 'send-key', {'keys':[{'type':'qcode', 'data':'ret'}]})


def capture_screen(sock_path, filename):
    # GL scanouts may have no CPU surface for QMP screendump. Capture the actual
    # SDL window from Xvfb instead, including frames rendered by VirGL.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(process.pid)], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            window = result.stdout.splitlines()[0]
            geometry = subprocess.check_output(['xdotool', 'getwindowgeometry', '--shell', window], text=True)
            values = dict(line.split('=', 1) for line in geometry.splitlines() if '=' in line)
            x, y, width, height = [int(values[k]) for k in ('X', 'Y', 'WIDTH', 'HEIGHT')]
            frame = ImageGrab.grab(bbox=(x, y, x + width, y + height), xdisplay=os.environ['DISPLAY'])
            frame.save(filename)
            return
        if process.poll() is not None:
            raise RuntimeError('QEMU exited before a display window appeared')
        time.sleep(0.5)
    raise RuntimeError('QEMU SDL display window did not appear')

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
        'qemu-system-x86_64', '-accel', 'tcg', '-m', '4096', '-smp', '2',
        '-cpu', 'max', '-cdrom', str(iso), '-boot', 'd',
        '-drive', f'file={disk},format=raw,if=virtio',
        '-vga', 'none', '-device', 'virtio-vga-gl', '-display', 'sdl,gl=on',
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
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'f3'}]})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if 'HAFTHIOS_SETTINGS_READY' in serial_path.read_text(errors='replace'):
                break
            time.sleep(1)
        else:
            raise RuntimeError('The language and keyboard settings did not open after F3')
        time.sleep(2)
        capture_screen(sock_path, out / 'settings-screen.ppm')
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'esc'}]})
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
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'f4'}]})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            text = serial_path.read_text(errors='replace')
            if 'HAFTHIOS_DISKS_READY ' in text:
                available = json.loads(text.split('HAFTHIOS_DISKS_READY ')[-1].splitlines()[0])
                if available != ['/dev/vda']:
                    raise RuntimeError('Installer offered unexpected target disks: ' + repr(available))
                break
            time.sleep(1)
        else:
            raise RuntimeError('Installer disk selection did not load')
        capture_screen(sock_path, out / 'installer-disks.ppm')
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}]})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if 'HAFTHIOS_REVIEW_READY ERASE /dev/vda' in serial_path.read_text(errors='replace'):
                break
            time.sleep(1)
        else:
            raise RuntimeError('Installer review did not open')
        capture_screen(sock_path, out / 'installer-review.ppm')
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'f2'}]})
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            text = serial_path.read_text(errors='replace')
            if window_present(text, 'se.dahlbeck.hafthi'):
                break
            time.sleep(3)
        else:
            raise RuntimeError('Niri desktop and Hafthi window did not become ready')
        time.sleep(5)
        capture_screen(sock_path, out / 'desktop-screen.ppm')
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'meta_l'}, {'type': 'qcode', 'data': 'b'}]})
        time.sleep(10)
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}]})
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            text = serial_path.read_text(errors='replace')
            if window_present(text, 'google-chrome'):
                break
            time.sleep(3)
        else:
            raise RuntimeError('Google Chrome window did not open after download')
        time.sleep(10)
        capture_screen(sock_path, out / 'chrome-screen.ppm')
        print('BIOS live VM boot passed: ship, settings, guide, Hafthi and Chrome.')
        # The sole target is a newly created disposable 16 GiB VM disk.
        # Feed a test script through the actual VM console; no auto-erasing service
        # or test backdoor is shipped in the ISO.
        qmp_request(sock_path, 'send-key', {'keys':[{'type':'qcode','data':'ctrl'}, {'type':'qcode','data':'alt'}, {'type':'qcode','data':'f2'}]})
        time.sleep(5)
        type_text(sock_path, 'hafthi')
        time.sleep(5)
        type_text(sock_path, '')
        time.sleep(2)
        script = """import runpy
from pathlib import Path
backend=runpy.run_path('/usr/local/bin/hafthios-install')
plan=backend['make_plan']('/dev/vda')
backend['install']({'token':plan['token'],'confirmation':plan['confirmation'],'password':'testpassword123','settings':{'language':'sv','keyboard':'se'}})
with open('/dev/ttyS0','w') as serial: serial.write('HAFTHIOS_INSTALL_OK\\n')
"""
        script = 'import traceback\ntry:\n' + '\n'.join('    ' + line for line in script.splitlines()) + '\nexcept Exception:\n    traceback.print_exc()\n    print("HAFTHIOS_INSTALL_ERROR", flush=True)\n'
        encoded = base64.b64encode(script.encode()).decode()
        type_text(sock_path, 'echo ' + encoded + ' | base64 -d | sudo python3 > /dev/ttyS0 2>&1')
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            installation_log = serial_path.read_text(errors='replace')
            if 'HAFTHIOS_INSTALL_ERROR' in installation_log:
                capture_screen(sock_path, out / 'installer-failure.ppm')
                raise RuntimeError('Disk installation failed: ' + installation_log[-5000:])
            if 'HAFTHIOS_INSTALL_OK' in installation_log:
                break
            if process.poll() is not None:
                raise RuntimeError('Live VM exited during installation')
            time.sleep(3)
        else:
            raise RuntimeError('Disk installation did not finish: ' + serial_path.read_text(errors='replace')[-4000:])
        process.terminate()
        process.wait(timeout=20)
        for firmware in ('bios', 'uefi'):
            sock_path.unlink(missing_ok=True)
            serial_path = out / ('installed-' + firmware + '-serial.log')
            extra = []
            if firmware == 'uefi':
                variables = tmp / 'OVMF_VARS.fd'
                shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
                extra = ['-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
                         '-drive', 'if=pflash,format=raw,file=' + str(variables)]
            process = subprocess.Popen([
                'qemu-system-x86_64', '-accel', 'tcg', '-m', '4096', '-smp', '2', '-cpu', 'max',
                '-boot', 'c', '-drive', f'file={disk},format=raw,if=virtio',
                '-vga', 'none', '-device', 'virtio-vga-gl', '-display', 'sdl,gl=on',
                '-serial', f'file:{serial_path}', '-monitor', 'none',
                '-qmp', f'unix:{sock_path},server=on,wait=off', '-no-reboot', *extra,
            ], stdout=subprocess.DEVNULL, stderr=open(out / ('installed-' + firmware + '-qemu.log'), 'w'))
            # Real firmware + GRUB boot from disk, with the ISO physically absent.
            time.sleep(90)
            capture_screen(sock_path, out / ('installed-' + firmware + '-login.ppm'))
            type_text(sock_path, 'hafthi')
            time.sleep(3)
            type_text(sock_path, 'testpassword123')
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                text = serial_path.read_text(errors='replace') if serial_path.exists() else ''
                if 'HAFTHIOS_INSTALLED_READY ' in text and window_present(text, 'se.dahlbeck.hafthi'):
                    break
                if process.poll() is not None:
                    raise RuntimeError('Installed VM exited before the desktop')
                time.sleep(3)
            else:
                capture_screen(sock_path, out / ('installed-' + firmware + '-failure.ppm'))
                raise RuntimeError('Installed ' + firmware + ' desktop did not start: ' + text[-4000:])
            marker = text.split('HAFTHIOS_INSTALLED_READY ')[-1].splitlines()[0]
            state = json.loads(marker)
            if state['settings'] != {'language':'sv','keyboard':'se'}:
                raise RuntimeError('Language and keyboard were not preserved')
            if state['root']['filesystems'][0]['fstype'] != 'ext4':
                raise RuntimeError('The installed VM is not running from its ext4 disk')
            if not state['live_sudo_removed'] or not state['autologin_removed']:
                raise RuntimeError('Live account privileges were left enabled')
            time.sleep(3)
            capture_screen(sock_path, out / ('installed-' + firmware + '-desktop.ppm'))
            qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'meta_l'}, {'type': 'qcode', 'data': 'b'}]})
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if window_present(serial_path.read_text(errors='replace'), 'google-chrome'):
                    break
                time.sleep(3)
            else:
                raise RuntimeError('Copied Chrome profile did not open on installed ' + firmware)
            capture_screen(sock_path, out / ('installed-' + firmware + '-chrome.ppm'))
            print('Installed ' + firmware.upper() + ' disk boot passed: password login, Hafthi, copied Chrome profile, persistent Swedish settings, ext4 root and live policy removal.')
            process.terminate()
            process.wait(timeout=20)

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
