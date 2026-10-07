#!/usr/bin/env python3
"""CI-only installation test, carried on a separate temporary read-only CD."""
import os
import sys
import traceback


def main():
    if sys.argv[1:] != ['--disposable-vm'] or os.geteuid() != 0:
        raise SystemExit('Run only in the CI-created disposable live VM as root.')
    sys.stdout = open('/dev/ttyS0', 'w', buffering=1)
    sys.stderr = sys.stdout
    os.dup2(sys.stdout.fileno(), 1)
    os.dup2(sys.stdout.fileno(), 2)
    try:
        print('HAFTHIOS_INSTALL_STARTED', flush=True)
        import runpy, subprocess
        for repository in ('core', 'extra'):
            servers = subprocess.check_output(['pacman-conf', '--repo', repository, 'Server'], text=True).strip()
            if not servers.startswith('https://'):
                raise RuntimeError('Missing HTTPS package servers for ' + repository)
        subprocess.run(['systemctl', 'start', 'hafthios-package-keys.service'], check=True, timeout=180)
        subprocess.run(['df', '-h', '/', '/run/archiso/cowspace'], check=True, timeout=30)
        subprocess.run(['pacman', '-Syu', '--noconfirm', '--needed', 'git', 'base-devel'], check=True, timeout=600)
        subprocess.run(['pacman', '-Scc', '--noconfirm'], check=True, timeout=60)
        subprocess.run(['git', '--version'], check=True, timeout=30)
        subprocess.run(['make', '--version'], check=True, timeout=30)
        print('HAFTHIOS_PACKAGE_REPOSITORIES_OK', flush=True)
        backend=runpy.run_path('/usr/local/bin/hafthios-install')
        plan=backend['make_plan']('/dev/vda')
        backend['install']({'token':plan['token'],'confirmation':plan['confirmation'],'password':'testpassword123','settings':{'language':'sv','keyboard':'se'}})
        print('HAFTHIOS_INSTALL_OK', flush=True)
    except Exception:
        traceback.print_exc()
        print('HAFTHIOS_INSTALL_ERROR', flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
