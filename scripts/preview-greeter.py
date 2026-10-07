#!/usr/bin/env python3
"""Render the real GTK greeter under Xvfb; preview never authenticates."""
import os
from pathlib import Path
import subprocess
import sys
import time
from PIL import ImageChops, ImageGrab

out = Path('out')
out.mkdir(exist_ok=True)
environment = dict(os.environ, LANG='sv_SE.UTF-8', LC_ALL='C.UTF-8', NO_AT_BRIDGE='1')
with (out / 'coastal-greeter.log').open('w') as log:
    process = subprocess.Popen([sys.executable, 'live/usr/local/bin/hafthios-greeter', '--preview'],
                               env=environment, stdout=log, stderr=log)
    try:
        time.sleep(6)
        if process.poll() is not None:
            raise RuntimeError('GTK greeter exited: ' + (out / 'coastal-greeter.log').read_text())
        windows = subprocess.check_output(['xdotool', 'search', '--onlyvisible', '--pid', str(process.pid)], text=True)
        subprocess.run(['xdotool', 'windowfocus', windows.splitlines()[0]], check=True)
        first = ImageGrab.grab(xdisplay=os.environ['DISPLAY'])
        first.save(out / 'coastal-greeter.png')
        time.sleep(2)
        second = ImageGrab.grab(xdisplay=os.environ['DISPLAY'])
        region = (900, 650, 1400, 880)
        if ImageChops.difference(first.crop(region), second.crop(region)).getbbox() is None:
            raise RuntimeError('Coastal waves did not animate')
        subprocess.run(['xdotool', 'key', 'F10'], check=True)
        time.sleep(1)
        paused = ImageGrab.grab(xdisplay=os.environ['DISPLAY'])
        time.sleep(1)
        still = ImageGrab.grab(xdisplay=os.environ['DISPLAY'])
        if ImageChops.difference(paused.crop(region), still.crop(region)).getbbox() is not None:
            raise RuntimeError('Pause did not stop the waves')
        if (out / 'coastal-greeter.log').read_text().strip():
            raise RuntimeError('GTK preview emitted diagnostics: ' + (out / 'coastal-greeter.log').read_text())
        print('Coastal GTK greeter rendered; waves animate and pause correctly.')
    finally:
        process.terminate()
        process.wait(timeout=10)
