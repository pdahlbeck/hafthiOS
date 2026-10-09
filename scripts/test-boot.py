#!/usr/bin/env python3
"""Boot the ISO with TCG and a disposable disk; check GTK's ready marker."""
import json
import re
import shutil
import os
import sys
import pathlib
import socket
import subprocess
import tempfile
import time
import unicodedata

def normalize_screen_text(value):
    # OCR engines may omit Swedish accents and split a label across lines.
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', value).strip()

def screen_label_present(text, label):
    # Thin GTK glyphs can produce one wrong or extra character (e.g. lésenord).
    # Match whole words, allowing at most one edit only in long label words.
    # This detects prompts only; authentication still requires the guest's
    # desktop marker, actual Hafthi window and rejection of a wrong password.
    actual = re.findall(r'[a-z]+', normalize_screen_text(text))
    expected = re.findall(r'[a-z]+', normalize_screen_text(label))
    def matches(a, b):
        if a == b:
            return True
        if len(b) < 7 or abs(len(a) - len(b)) > 1:
            return False
        if len(a) == len(b):
            return sum(x != y for x, y in zip(a, b)) <= 1
        longer, shorter = (a, b) if len(a) > len(b) else (b, a)
        return any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))
    return bool(expected) and any(
        all(matches(a, b) for a, b in zip(actual[i:i + len(expected)], expected))
        for i in range(len(actual) - len(expected) + 1))

def window_present(text, app_id, focused=False):
    for line in reversed(text.splitlines()):
        if line.startswith('HAFTHIOS_DESKTOP_READY '):
            try:
                return any(w.get('app_id', '').lower() == app_id and
                           (not focused or w.get('is_focused') is True)
                           for w in json.loads(line.split(' ', 1)[1]))
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

def type_text(sock_path, text, submit=True):
    special = {' ': ('spc', False), '-': ('minus', False), '=': ('equal', False),
               '+': ('equal', True), '/': ('slash', False), '|': ('backslash', True),
               '>': ('dot', True), '.': ('dot', False), '_': ('minus', True), '&': ('7', True)}
    unknown = set(text) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') - set(special)
    if unknown:
        raise ValueError('Unsupported VM console characters: ' + repr(sorted(unknown)))

    def event(key, down):
        return {'type': 'key', 'data': {'down': down, 'key': {'type': 'qcode', 'data': key}}}

    # Release any earlier shortcut, then send complete key chords one at a time.
    # The pause exceeds send-key's hold-time so timers never overlap.
    modifiers = ('shift', 'shift_r', 'ctrl', 'ctrl_r', 'alt', 'alt_r', 'meta_l', 'meta_r')
    qmp_request(sock_path, 'input-send-event', {'events': [event(key, False) for key in modifiers]})
    time.sleep(0.25)

    def press(keys):
        qmp_request(sock_path, 'send-key', {
            'keys': [{'type': 'qcode', 'data': key} for key in keys],
            'hold-time': 80,
        })
        time.sleep(0.20)

    for character in text:
        if character.isalnum():
            key, shift = character.lower(), character.isupper()
        else:
            key, shift = special[character]
        press((['shift'] if shift else []) + [key])
    if submit:
        press(['ret'])


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

reuse_iso = bool(os.environ.get('HAFTHIOS_RETEST_ISO'))
acceleration = 'kvm' if reuse_iso and os.access('/dev/kvm', os.R_OK | os.W_OK) else 'tcg'
cpu_model = 'host' if acceleration == 'kvm' else 'max'
print('VM acceleration: ' + acceleration, flush=True)
out = pathlib.Path('out').resolve()
iso = max(out.glob('*.iso'), key=lambda p: p.stat().st_mtime)
with tempfile.TemporaryDirectory() as tmp:
    tmp = pathlib.Path(tmp)
    # Test code is carried on separate read-only media, never inside the OS ISO.
    payload = tmp / 'test-input'
    payload.mkdir()
    shutil.copyfile('scripts/vm-install.py', payload / 'install.py')
    payload_iso = tmp / 'test-input.iso'
    subprocess.run(['xorriso', '-as', 'mkisofs', '-quiet', '-V', 'hafthios-test',
                    '-o', str(payload_iso), str(payload)], check=True, timeout=60)
    disk = tmp / 'disk.raw'
    with disk.open('wb') as stream:
        stream.truncate(16 * 1024**3)
    # A writable, full-size USB exposes the original regression: after RAM
    # boot it has no mounts and would otherwise look like an eligible target.
    live_usb = tmp / 'live-usb.raw'
    shutil.copyfile(iso, live_usb)
    with live_usb.open('r+b') as stream:
        stream.truncate(32 * 1024**3)
    sock_path = tmp / 'qmp.sock'
    serial_path = out / 'boot-serial.log'
    process = subprocess.Popen([
        # The live overlay uses half of RAM; signed full upgrades need headroom.
        'qemu-system-x86_64', '-accel', acceleration, '-m', '8192', '-smp', '2',
        '-nic', 'user,model=virtio-net-pci',
        '-cpu', cpu_model,
        '-device', 'qemu-xhci',
        '-drive', f'file={live_usb},format=raw,if=none,id=liveusb',
        '-device', 'usb-storage,drive=liveusb,bootindex=1',
        '-drive', f'file={payload_iso},format=raw,media=cdrom,readonly=on',
        '-drive', f'file={disk},format=raw,if=virtio',
        '-vga', 'none', '-device', 'virtio-vga-gl', '-display', 'sdl,gl=on',
        '-serial', f'file:{serial_path}', '-monitor', 'none',
        '-qmp', f'unix:{sock_path},server=on,wait=off', '-no-reboot',
    ], stdout=subprocess.DEVNULL, stderr=open(out / 'qemu.log', 'w'))
    try:
        if acceleration == 'tcg':
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
        else:
            print('KVM retest checks installation and disk boot; ship animation is checked by the full TCG build.', flush=True)
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
        # The terminal can be ready before the background finishes loading the
        # original raster ship, especially under x86 software emulation. Wait
        # for evidence of an actual GTK draw rather than a fixed startup delay.
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if 'HAFTHIOS_WORLD_READY' in serial_path.read_text(errors='replace'):
                break
            if process.poll() is not None:
                raise RuntimeError('VM exited before the village background drew')
            time.sleep(1)
        else:
            raise RuntimeError('Living village background did not draw in Niri within 90 seconds')
        capture_screen(sock_path, out / 'desktop-screen.ppm')
        def wait_panel(hidden):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                text = serial_path.read_text(errors='replace')
                lines = [line for line in text.splitlines() if line.startswith('HAFTHIOS_PANEL_STATE ')]
                if lines and json.loads(lines[-1].split(' ', 1)[1])['hidden'] == hidden:
                    return
                time.sleep(1)
            raise RuntimeError('Right panel did not toggle to hidden=' + str(hidden))
        wait_panel(False)
        for hidden in (True, False):
            qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'meta_l'}, {'type': 'qcode', 'data': 'spc'}]})
            wait_panel(hidden)
            capture_screen(sock_path, out / ('panel-hidden.ppm' if hidden else 'panel-open.ppm'))
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'meta_l'}, {'type': 'qcode', 'data': 'd'}]})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            text = serial_path.read_text(errors='replace')
            if 'HAFTHIOS_DISPLAY_READY ' in text:
                displays = json.loads(text.split('HAFTHIOS_DISPLAY_READY ')[-1].splitlines()[0])
                if not displays or not all(o['modes'] for o in displays.values()):
                    raise RuntimeError('Display page has no advertised modes')
                break
            time.sleep(1)
        else:
            raise RuntimeError('Display page did not open')
        capture_screen(sock_path, out / 'display-settings.ppm')
        # A layer-shell panel can retain keyboard focus even when Niri opens
        # a new window. Unmap it before pressing Chrome's download button.
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'meta_l'}, {'type': 'qcode', 'data': 'spc'}]})
        wait_panel(True)
        qmp_request(sock_path, 'send-key', {'keys': [{'type': 'qcode', 'data': 'meta_l'}, {'type': 'qcode', 'data': 'b'}]})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if window_present(serial_path.read_text(errors='replace'), 'org.hafthios.chromesetup', focused=True):
                break
            time.sleep(1)
        else:
            raise RuntimeError('Chrome download dialog did not receive keyboard focus')
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
        print('BIOS live VM boot passed: ' + ('ship, ' if acceleration == 'tcg' else '') + 'settings, guide, Hafthi, right panel toggle, display modes and Chrome.', flush=True)
        # The sole target is a newly created disposable 16 GiB VM disk.
        # Run a script from separate temporary read-only media through the real
        # VM console. No test service or test payload is shipped in the OS ISO.
        # A real text console is deterministic even if Chrome retains focus.
        # The live hafthi account has an empty password; installed PAM is separate.
        qmp_request(sock_path, 'send-key', {'keys':[
            {'type':'qcode','data':'ctrl'}, {'type':'qcode','data':'alt'},
            {'type':'qcode','data':'f2'}]})
        console_screen = out / 'installer-console.ppm'
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            capture_screen(sock_path, console_screen)
            console_text = subprocess.run(['tesseract', str(console_screen), 'stdout'],
                                          capture_output=True, text=True, timeout=20).stdout.lower()
            if 'login:' in console_text:
                break
            time.sleep(2)
        else:
            raise RuntimeError('The live tty2 login prompt did not appear: ' + console_text)
        # Wait for agetty to initialize instead of racing its first key event.
        # A blank submission wakes the console without submitting a username.
        type_text(sock_path, '')
        time.sleep(2)
        for attempt in range(3):
            qmp_request(sock_path, 'send-key', {'keys':[
                {'type':'qcode','data':'ctrl'}, {'type':'qcode','data':'u'}]})
            time.sleep(1)
            type_text(sock_path, 'hafthi', submit=False)
            time.sleep(1)
            capture_screen(sock_path, console_screen)
            console_text = subprocess.run(['tesseract', str(console_screen), 'stdout'],
                                          capture_output=True, text=True, timeout=20).stdout.lower()
            if re.search(r'(?:login:\s*|\n)\s*hafthi(?:\s|$)', console_text):
                type_text(sock_path, '')
                break
        else:
            raise RuntimeError('The live login username was not received intact: ' + console_text)
        time.sleep(5)
        type_text(sock_path, 'echo HAFTHIOS_INSTALL_CONSOLE_READY > /dev/ttyS0')
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if any(line.strip() == 'HAFTHIOS_INSTALL_CONSOLE_READY' for line in serial_path.read_text(errors='replace').splitlines()):
                break
            time.sleep(1)
        else:
            raise RuntimeError('The installation test console did not execute its readiness command')
        capture_screen(sock_path, out / 'installer-console.ppm')
        type_text(sock_path, 'sudo mount -o ro /dev/disk/by-label/hafthios-test /mnt')
        time.sleep(3)
        type_text(sock_path, 'sudo python3 /mnt/install.py --disposable-vm')
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            installation_log = serial_path.read_text(errors='replace')
            if 'HAFTHIOS_INSTALL_STARTED' in installation_log:
                break
            time.sleep(1)
        else:
            raise RuntimeError('The VM console did not execute the complete installation script')
        deadline = time.monotonic() + 1800
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
                'qemu-system-x86_64', '-accel', acceleration, '-m', '4096', '-smp', '2', '-cpu', cpu_model,
                '-nic', 'user,model=virtio-net-pci',
                '-boot', 'c', '-drive', f'file={disk},format=raw,if=virtio',
                '-vga', 'none', '-device', 'virtio-vga-gl', '-display', 'sdl,gl=on',
                '-serial', f'file:{serial_path}', '-monitor', 'none',
                '-qmp', f'unix:{sock_path},server=on,wait=off', '-no-reboot', *extra,
            ], stdout=subprocess.DEVNULL, stderr=open(out / ('installed-' + firmware + '-qemu.log'), 'w'))
            # Real firmware + GRUB boot from disk, with the ISO physically absent.
            login_screen = out / ('installed-' + firmware + '-login.ppm')
            def wait_greeter(words, timeout=240):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('Installed VM exited before graphical login')
                    capture_screen(sock_path, login_screen)
                    ocr = subprocess.run(['tesseract', str(login_screen), 'stdout', '--psm', '11'],
                                         capture_output=True, text=True, timeout=20).stdout.lower()
                    if any(screen_label_present(ocr, word) for word in words):
                        return ocr
                    time.sleep(3)
                raise RuntimeError('Graphical login prompt did not appear: ' + ocr)
            wait_greeter(('username', 'användarnamn'))
            if 'HAFTHIOS_INSTALLED_READY ' in serial_path.read_text(errors='replace'):
                raise RuntimeError('The desktop started before password authentication')
            type_text(sock_path, 'hafthi')
            wait_greeter(('password', 'lösenord'), timeout=45)
            type_text(sock_path, 'wrongpassword123')
            # gtkgreet returns to a fresh username entry after PAM rejects login.
            wait_greeter(('login failed', 'inloggning misslyckades'), timeout=60)
            capture_screen(sock_path, out / ('installed-' + firmware + '-wrong-password.ppm'))
            if 'HAFTHIOS_INSTALLED_READY ' in serial_path.read_text(errors='replace'):
                raise RuntimeError('A wrong password opened the desktop')
            type_text(sock_path, 'hafthi')
            wait_greeter(('password', 'lösenord'), timeout=45)
            type_text(sock_path, 'testpassword123')
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                text = serial_path.read_text(errors='replace') if serial_path.exists() else ''
                if 'HAFTHIOS_INSTALLED_READY ' in text and 'HAFTHIOS_WORLD_READY' in text and window_present(text, 'se.dahlbeck.hafthi'):
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
            # Niri's quit action asks for confirmation; Enter returns to greetd.
            qmp_request(sock_path, 'send-key', {'keys':[
                {'type':'qcode','data':'meta_l'}, {'type':'qcode','data':'shift'},
                {'type':'qcode','data':'e'}]})
            time.sleep(3)
            type_text(sock_path, '')
            wait_greeter(('username', 'användarnamn'), timeout=90)
            capture_screen(sock_path, out / ('installed-' + firmware + '-logout.ppm'))
            print('Installed ' + firmware.upper() + ' disk boot passed: wrong password rejected, graphical login, Hafthi, Chrome, persistent Swedish settings, ext4 root, live policy removal and logout to greeter.')
            process.terminate()
            process.wait(timeout=20)

    finally:
        if sys.exc_info()[0] is not None and process.poll() is None:
            try:
                failure = out / 'installer-failure.ppm'
                capture_screen(sock_path, failure)
                ocr = subprocess.run(['tesseract', str(failure), 'stdout'], capture_output=True, text=True, timeout=20)
                print('VM failure screen text: ' + ocr.stdout[-5000:], flush=True)
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
                pass
        if process.poll() is None and not (out / 'boot-screen.ppm').exists():
            try:
                capture_screen(sock_path, out / 'boot-screen.ppm')
            except (OSError, RuntimeError, ValueError):
                pass
        if serial_path.exists():
            log = serial_path.read_text(errors='replace')
            diagnostics = '\n'.join(line for line in log.splitlines() if not line.startswith('HAFTHIOS_DESKTOP_READY '))
            print(diagnostics[-16000:])
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
