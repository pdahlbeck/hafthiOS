import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
settings = runpy.run_path(str(ROOT / 'live/usr/local/bin/hafthios-settings'))


class LiveSettingsTests(unittest.TestCase):
    def test_confirmed_display_survives_language_change_and_invalid_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/hafthios/displays.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'Virtual-1': {'mode': '1920x1080@60.000', 'scale': '1.5'},
                                        'bad': {'mode': '"; spawn "sh"', 'scale': '1'}}))
            with patch('subprocess.run'):
                settings['apply_settings']('sv', 'se', home, ROOT / 'live/etc/niri/config.kdl')
            config = (home / '.config/niri/config.kdl').read_text()
            self.assertIn('output "Virtual-1"', config)
            self.assertIn('mode "1920x1080@60.000"', config)
            self.assertIn('scale 1.5', config)
            self.assertNotIn('spawn "sh"', config)

    def test_trial_rejects_unadvertised_modes_and_starts_restore_before_change(self):
        output = {'Virtual-1': {'modes': [{'width': 1280, 'height': 800, 'refresh_rate': 60000}],
                                 'current_mode': 0, 'logical': {'scale': 1.0}}}
        events = []
        watchdog = SimpleNamespace(terminate=lambda: events.append('cancel'), wait=lambda **kw: None)
        with patch.dict(settings['trial_display'].__globals__,
                        read_outputs=lambda: output,
                        restore_watchdog=lambda previous: events.append(('watchdog', previous)) or watchdog,
                        set_output=lambda *args: events.append(('change', args))):
            with self.assertRaises(ValueError):
                settings['trial_display']('Virtual-1', '3840x2160@60.000', '1')
            self.assertEqual(events, [])
            previous, process = settings['trial_display']('Virtual-1', '1280x800@60.000', '1.5')
            self.assertEqual(events[0], ('watchdog', previous))
            self.assertEqual(events[1], ('change', ('Virtual-1', '1280x800@60.000', '1.5')))
            self.assertIs(process, watchdog)
            self.assertEqual(previous['scale'], '1.0')

    def test_failed_display_change_restores_original_mode(self):
        output = {'Virtual-1': {'modes': [{'width': 1280, 'height': 800, 'refresh_rate': 60000}],
                                 'current_mode': 0, 'logical': {'scale': 1.0}}}
        calls = []
        watchdog = SimpleNamespace(terminate=lambda: calls.append('cancel'), wait=lambda **kw: None)
        def change(*args):
            calls.append(args)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, 'niri')
        with patch.dict(settings['trial_display'].__globals__, read_outputs=lambda: output,
                        restore_watchdog=lambda previous: watchdog, set_output=change):
            with self.assertRaises(subprocess.CalledProcessError):
                settings['trial_display']('Virtual-1', '1280x800@60.000', '1.5')
        self.assertEqual(calls[-2:], [('Virtual-1', '1280x800@60.000', '1.0'), 'cancel'])

    def test_language_and_keyboard_are_independent_and_written_without_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            base = ROOT / 'live/etc/niri/config.kdl'
            with patch('subprocess.run') as validate:
                settings['apply_settings']('en', 'se', home, base)
                validate.assert_called_once()
                self.assertEqual(validate.call_args.args[0][:3], ['niri', 'validate', '--config'])
            self.assertEqual(settings['read_settings'](home), {'language': 'en', 'keyboard': 'se'})
            self.assertIn('layout "se"', (home / '.config/niri/config.kdl').read_text())
            env = dict(os.environ, HOME=str(home))
            result = subprocess.run(['bash', '-c', 'source "$HOME/.config/hafthios/environment"; printf "%s %s %s" "$LANG" "$LANGUAGE" "$XKB_DEFAULT_LAYOUT"'],
                                    check=True, capture_output=True, text=True, env=env)
            self.assertEqual(result.stdout, 'en_US.UTF-8 en se')

    def test_failed_validation_preserves_previous_settings_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            base = ROOT / 'live/etc/niri/config.kdl'
            with patch('subprocess.run'):
                settings['apply_settings']('en', 'us', home, base)
            before = {p: p.read_bytes() for p in home.rglob('*') if p.is_file()}
            with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'niri')):
                with self.assertRaises(subprocess.CalledProcessError):
                    settings['apply_settings']('sv', 'se', home, base)
            self.assertEqual(before, {p: p.read_bytes() for p in home.rglob('*') if p.is_file()})

    def test_invalid_or_malformed_settings_fall_back_and_injection_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.config/hafthios/settings.json'
            path.parent.mkdir(parents=True)
            for text in ('invalid', '[]', json.dumps({'language': 'invalid', 'keyboard': '"; spawn "sh"'})):
                path.write_text(text)
                self.assertEqual(settings['read_settings'](home), {'language': 'en', 'keyboard': 'us'})
            with self.assertRaises(ValueError):
                settings['apply_settings']('sv;touch /tmp/bad', 'se', home)


class SessionRecoveryTests(unittest.TestCase):
    def test_failed_desktop_restores_welcome_with_diagnostics(self):
        for code in (0, 1):
            with self.subTest(exit_code=code), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                binary = home / 'bin'
                runtime = home / 'runtime'
                binary.mkdir()
                runtime.mkdir()
                scripts = {
                    'cage': '''#!/bin/bash
printf '%s\\n' "$*" >> "$HOME/cage-calls"
if [[ ! -f "$HOME/first-cage" ]]; then
    touch "$HOME/first-cage" "$XDG_RUNTIME_DIR/hafthios-try-desktop"
fi
''',
                    'niri-session': f'#!/bin/bash\necho renderer-failure\nexit {code}\n',
                    'systemctl': '#!/bin/bash\nif [[ "$2" == show ]]; then echo exit-code; fi\n',
                    'journalctl': '#!/bin/bash\necho no-render-device\n',
                }
                for name, text in scripts.items():
                    p = binary / name
                    p.write_text(text)
                    p.chmod(0o755)
                env = dict(os.environ, HOME=str(home), XDG_RUNTIME_DIR=str(runtime), PATH=str(binary) + ':' + os.environ['PATH'])
                subprocess.run(['bash', str(ROOT / 'live/usr/local/bin/hafthios-session')], env=env, check=True, timeout=5)
                calls = (home / 'cage-calls').read_text().splitlines()
                self.assertEqual(len(calls), 2)
                self.assertIn('--session-error', calls[1])
                self.assertIn('no-render-device', (home / '.local/state/hafthios/desktop-error.log').read_text())
                self.assertFalse((runtime / 'hafthios-try-desktop').exists())


if __name__ == '__main__':
    unittest.main()
