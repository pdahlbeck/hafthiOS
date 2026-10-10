#!/usr/bin/env python3
"""CI-only installation test, carried on a separate temporary read-only CD."""
import os
import sys
import traceback


def test_update():
    """Exercise the shipped command on the newly installed disposable disk."""
    from pathlib import Path
    import shutil, subprocess, tempfile, json
    archive=Path(__file__).resolve().with_name('update.tar.gz')
    if not archive.exists():
        return  # A reused older ISO has no newly built update package.
    with tempfile.TemporaryDirectory(prefix='update-vm-') as temporary:
        root=Path(temporary)
        subprocess.run(['mount','/dev/vda3',str(root)],check=True,timeout=30)
        try:
            shutil.copyfile(archive,root/'var/tmp/hafthios-test-update.tar.gz')
            launcher=root/'usr/local/bin/hafthios-launcher'
            old=b'#!/bin/sh\n# previous desktop fixture\nexit 0\n'
            launcher.write_bytes(old)
            launcher.chmod(0o755)
            home=root/'home/hafthi'
            personal=home/'Documents/update-preservation-test.txt'
            personal.parent.mkdir(exist_ok=True)
            personal.write_text('keep my personal file\n')
            prefs=home/'.config/hafthios/settings.json'
            saved=prefs.read_bytes()
            village=home/'.config/hafthios/world.json'
            age=village.read_bytes() if village.exists() else None
            def command(*args):
                subprocess.run(['arch-chroot',str(root),'env','SUDO_USER=hafthi',
                                '/usr/local/bin/hafthios-update',*args],check=True,timeout=120)
            def preserved():
                assert personal.read_text()=='keep my personal file\n'
                assert json.loads(prefs.read_bytes())==json.loads(saved)
                assert (village.read_bytes() if village.exists() else None)==age
            command('--package','/var/tmp/hafthios-test-update.tar.gz')
            assert launcher.read_bytes()!=old
            assert 'hafthios-launcher' in (home/'.config/niri/config.kdl').read_text()
            preserved()
            command('--rollback')
            assert launcher.read_bytes()==old
            preserved()
            command('--package','/var/tmp/hafthios-test-update.tar.gz')
            assert launcher.read_bytes()!=old
            preserved()
            personal.unlink()
            (root/'var/tmp/hafthios-test-update.tar.gz').unlink()
            print('HAFTHIOS_UPDATE_TEST_OK: installed update, settings, personal files, village age and rollback',flush=True)
        finally:
            subprocess.run(['umount','-R',str(root)],check=True,timeout=30)


def test_display():
    import runpy, time
    backend = runpy.run_path('/usr/local/bin/hafthios-settings')
    outputs = backend['read_outputs']()
    name, output = next((n, o) for n, o in outputs.items() if o.get('logical') and o.get('current_mode') is not None)
    mode = backend['mode_string'](output['modes'][output['current_mode']])
    scale = output['logical']['scale']
    # A moderate advertised mode exercises resolution changes without selecting
    # the first (5K ultrawide) EDID mode on a small CI virtual graphics device.
    alternatives = [m for m in output['modes'] if backend['mode_string'](m) != mode
                    and 1024 <= m['width'] <= 1920 and 720 <= m['height'] <= 1200]
    trial_mode = backend['mode_string'](min(alternatives, key=lambda m: abs(m['width'] - 1920) + abs(m['height'] - 1080))) if alternatives else mode
    trial_scale = '1.25' if scale != 1.25 else '1'
    previous, watchdog = backend['trial_display'](name, trial_mode, trial_scale)
    time.sleep(2)
    active = backend['read_outputs']()[name]
    assert backend['mode_string'](active['modes'][active['current_mode']]) == trial_mode, (trial_mode, active)
    assert active['logical']['scale'] == float(trial_scale), (trial_scale, active)
    # Do not confirm: the independent process must restore real output state.
    watchdog.wait(timeout=30)
    time.sleep(2)
    active = backend['read_outputs']()[name]
    assert backend['mode_string'](active['modes'][active['current_mode']]) == mode
    assert active['logical']['scale'] == scale
    backend['set_output'](name, mode, trial_scale)
    backend['save_display'](name, mode, trial_scale)
    current = backend['read_settings']()
    backend['apply_settings'](current['language'], current['keyboard'])
    time.sleep(2)
    assert backend['read_displays']()[name]['scale'] == trial_scale
    assert backend['read_outputs']()[name]['logical']['scale'] == float(trial_scale)
    backend['save_display'](name, mode, str(int(scale)) if scale == int(scale) else str(scale))
    print('HAFTHIOS_DISPLAY_TEST_OK: advertised mode, scaling, independent rollback and confirmed persistence', flush=True)
    # Exercise the running GTK/Wayland wallpaper, not just its settings writer.
    import json
    from pathlib import Path
    world = runpy.run_path('/usr/local/bin/hafthios-world')
    original = world['preferences']()
    status = Path(os.environ['XDG_RUNTIME_DIR']) / 'hafthios-world.json'
    def wait_for(predicate):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                value = json.loads(status.read_text())
                if predicate(value):
                    return value
            except (OSError, ValueError):
                pass
            time.sleep(.25)
        raise RuntimeError('Village did not apply its settings')
    try:
        world['save_preferences']({**original, 'enabled': True, 'paused': True})
        paused = wait_for(lambda v: v['paused'] and v['enabled'])
        time.sleep(4)
        still = json.loads(status.read_text())
        assert still['elapsed'] == paused['elapsed'], (paused, still)
        world['save_preferences']({**original, 'enabled': True, 'paused': False, 'economy': True})
        moving = wait_for(lambda v: not v['paused'] and v['economy'] and v['elapsed'] > paused['elapsed'])
        assert moving['draws'] > paused['draws']
        world['save_preferences']({**original, 'enabled': False})
        wait_for(lambda v: not v['enabled'])
        world['save_preferences']({**original, 'enabled': True})
        wait_for(lambda v: v['enabled'])
    finally:
        world['save_preferences'](original)
    print('HAFTHIOS_WORLD_TEST_OK: real GTK drawing, pause, resume, economy and disable/re-enable', flush=True)


def main():
    if sys.argv[1:] == ['--display-test'] and os.geteuid() != 0:
        test_display()
        return
    if sys.argv[1:] != ['--disposable-vm'] or os.geteuid() != 0:
        raise SystemExit('Run only in the CI-created disposable live VM as root.')
    sys.stdout = open('/dev/ttyS0', 'w', buffering=1)
    sys.stderr = sys.stdout
    os.dup2(sys.stdout.fileno(), 1)
    os.dup2(sys.stdout.fileno(), 2)
    try:
        print('HAFTHIOS_INSTALL_STARTED', flush=True)
        import runpy, subprocess
        from pathlib import Path
        import pwd
        runtime = Path('/run/user') / str(pwd.getpwnam('hafthi').pw_uid)
        socket = next(runtime.glob('niri*.sock'))
        # The root runner is entered through tty2. Niri relinquishes its DRM
        # device on an inactive VT, so modesets must be tested back on tty1.
        subprocess.run(['chvt', '1'], check=True, timeout=10)
        import time
        time.sleep(2)
        subprocess.run(['runuser', '-u', 'hafthi', '--', 'env', f'NIRI_SOCKET={socket}',
                        f'XDG_RUNTIME_DIR={runtime}', 'python3', str(Path(__file__).resolve()), '--display-test'],
                       check=True, timeout=90)
        for repository in ('core', 'extra'):
            servers = subprocess.check_output(['pacman-conf', '--repo', repository, 'Server'], text=True).strip()
            if not servers.startswith('https://'):
                raise RuntimeError('Missing HTTPS package servers for ' + repository)
        subprocess.run(['systemctl', 'start', 'hafthios-package-keys.service'], check=True, timeout=180)
        # A live kernel cannot reboot into the upgrade before installing. Keep
        # the EFI filesystem and its codepages loaded before pacman replaces
        # /usr/lib/modules; ext4 and virtio are already used by the live boot.
        subprocess.run(['modprobe', '-a', 'vfat', 'nls_cp437', 'nls_iso8859_1'], check=True, timeout=30)
        subprocess.run(['df', '-h', '/', '/run/archiso/cowspace'], check=True, timeout=30)
        subprocess.run(['pacman', '-Syu', '--noconfirm', '--needed', 'git', 'base-devel'], check=True, timeout=600)
        subprocess.run(['pacman', '-Scc'], input='y\ny\n', text=True, check=True, timeout=60)
        subprocess.run(['git', '--version'], check=True, timeout=30)
        subprocess.run(['make', '--version'], check=True, timeout=30)
        print('HAFTHIOS_PACKAGE_REPOSITORIES_OK', flush=True)
        backend=runpy.run_path('/usr/local/bin/hafthios-install')
        # Reproduce physical USB boot: Archiso unmounts bootmnt after copying
        # the image to RAM. The detached USB must still never be an install target.
        assert Path('/run/archiso/copytoram').is_mount(), 'USB live root was not copied to RAM'
        assert not Path('/run/archiso/bootmnt').is_mount(), 'Live media should be unmounted after copy-to-RAM'
        disks = backend['read_disks']()
        assert [d['path'] for d in disks] == ['/dev/vda'], disks
        print('HAFTHIOS_RAM_USB_INSTALL_TEST_OK: live RAM root accepted; original USB excluded', flush=True)
        plan=backend['make_plan']('/dev/vda')
        backend['install']({'token':plan['token'],'confirmation':plan['confirmation'],'password':'testpassword123','settings':{'language':'sv','keyboard':'se'}})
        test_update()
        print('HAFTHIOS_INSTALL_OK', flush=True)
    except Exception:
        traceback.print_exc()
        print('HAFTHIOS_INSTALL_ERROR', flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
