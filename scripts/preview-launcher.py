#!/usr/bin/env python3
"""Exercise real GTK searching, desktop-entry launching and Escape under Xvfb."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from PIL import ImageGrab

out = Path('out')
out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    apps = root / 'data/applications'
    apps.mkdir(parents=True)
    opened = root / 'opened'
    (apps / 'launcher-smoke.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=Hafthi Test\n'
        f'Exec=/usr/bin/touch {opened}\nIcon=utilities-terminal\nTerminal=false\n')
    environment = dict(os.environ, LANG='sv_SE.UTF-8', LC_ALL='C.UTF-8', GDK_BACKEND='x11',
                       GSK_RENDERER='cairo', XDG_DATA_HOME=str(root / 'data'),
                       XDG_DATA_DIRS=str(root / 'empty'), HOME=str(root),
                       XDG_RUNTIME_DIR=str(root), NO_AT_BRIDGE='1')
    def start(log):
        process = subprocess.Popen([sys.executable, 'live/usr/local/bin/hafthios-launcher', '--preview'],
                                   env=environment, stdout=log, stderr=log)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Launcher exited before drawing')
            windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(process.pid)],
                                     capture_output=True, text=True)
            if windows.returncode == 0:
                subprocess.run(['xdotool', 'windowfocus', windows.stdout.splitlines()[0]], check=True)
                time.sleep(1)
                return process
            time.sleep(.25)
        process.terminate()
        raise RuntimeError('Launcher window did not draw')
    with (out / 'launcher.log').open('w') as log:
        process = start(log)
        try:
            ImageGrab.grab(xdisplay=os.environ['DISPLAY']).save(out / 'launcher.png')
            subprocess.run(['xdotool', 'type', '--clearmodifiers', 'hafthi'], check=True)
            time.sleep(.5)
            subprocess.run(['xdotool', 'key', 'Return'], check=True)
            process.wait(timeout=10)
            assert opened.exists(), 'Selected desktop entry did not launch'
            process = start(log)
            subprocess.run(['xdotool', 'key', 'Escape'], check=True)
            process.wait(timeout=10)
            assert process.returncode == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    diagnostics = (out / 'launcher.log').read_text()
    if 'Traceback' in diagnostics or 'CRITICAL' in diagnostics:
        raise RuntimeError(diagnostics)
    print('HAFTHIOS_LAUNCHER_PREVIEW_OK: GTK drawing, search, desktop launch and Escape')
