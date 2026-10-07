import ast
import json
from pathlib import Path
import runpy
import socket
import struct
import threading
from types import SimpleNamespace
import unittest
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'live/usr/local/bin/hafthios-greeter'
Client = runpy.run_path(str(SOURCE))['Client']


class GreeterTests(unittest.TestCase):
    def test_ocr_prompt_tolerates_one_glyph_error_but_rejects_other_states(self):
        tree = ast.parse((ROOT / 'scripts/test-boot.py').read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('normalize_screen_text', 'screen_label_present')]
        namespace = {'re': re, 'unicodedata': unicodedata}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<screen labels>', 'exec'), namespace)
        match = namespace['screen_label_present']
        for text in ('Lösenord', 'lésenord', 'Loésenord', 'Losenor'):
            self.assertTrue(match(text, 'Lösenord'), text)
        self.assertTrue(match('Inloggning\nmisslyckades. Försök igen.', 'Inloggning misslyckades'))
        for text in ('Pausa vågorna', 'Användarnamn', 'Logga in', 'lösen', 'xxsenord', 'xxlosenordxx'):
            self.assertFalse(match(text, 'Lösenord'), text)
        self.assertFalse(match('Inloggning lyckades', 'Inloggning misslyckades'))

    def test_swedish_ocr_labels_match_without_accents_and_with_line_breaks(self):
        tree = ast.parse((ROOT / 'scripts/test-boot.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'normalize_screen_text')
        namespace = {'re': re, 'unicodedata': unicodedata}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<screen text>', 'exec'), namespace)
        normalize = namespace['normalize_screen_text']
        for label, ocr in [('Användarnamn', 'Anvandarnamn'), ('Lösenord', 'Losenord'),
                           ('Inloggning misslyckades', 'Inloggning\n\nmisslyckades')]:
            self.assertIn(normalize(label), normalize(ocr))
        self.assertNotIn(normalize('Användarnamn'), normalize('Pausa vågorna'))

    def test_fragmented_utf8_socket_response_and_native_length(self):
        left, right = socket.socketpair()
        client = Client.__new__(Client)
        client.sock = left
        received = []
        def daemon():
            header = right.recv(4)
            size = struct.unpack('=I', header)[0]
            data = bytearray()
            while len(data) < size:
                data.extend(right.recv(size - len(data)))
            received.append(json.loads(data))
            payload = json.dumps({'type': 'auth_message', 'auth_message_type': 'secret',
                                  'auth_message': 'Lösenord:'}, ensure_ascii=False).encode()
            for byte in struct.pack('=I', len(payload)) + payload:
                right.sendall(bytes([byte]))
        thread = threading.Thread(target=daemon)
        thread.start()
        try:
            reply = client.request({'type': 'create_session', 'username': 'hafthi'})
            thread.join(timeout=2)
            self.assertEqual(reply['auth_message'], 'Lösenord:')
            self.assertEqual(received, [{'type': 'create_session', 'username': 'hafthi'}])
        finally:
            left.close()
            right.close()

    def test_closed_socket_fails_without_accepting_authentication(self):
        left, right = socket.socketpair()
        client = Client.__new__(Client)
        client.sock = left
        right.close()
        try:
            with self.assertRaises(ConnectionError):
                client.read(4)
        finally:
            left.close()

    def response(self, reply, starting=False):
        tree = ast.parse(SOURCE.read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        cls = next(n for n in main.body if isinstance(n, ast.ClassDef))
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'response')
        namespace = {'tr': lambda en, sv: en, 'Gtk': SimpleNamespace(InputPurpose=SimpleNamespace(PASSWORD=1, FREE_FORM=0))}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<greeter>', 'exec'), namespace)
        calls = []
        widget = SimpleNamespace(set_sensitive=lambda v: None, set_text=lambda v: calls.append(('text', v)),
                                 set_visibility=lambda v: calls.append(('visible', v)), set_input_purpose=lambda v: None,
                                 set_label=lambda v: None, grab_focus=lambda: None)
        view = SimpleNamespace(entry=widget, button=widget, prompt=widget, message=widget,
                               reset=lambda: calls.append(('reset',)), destroy=lambda: calls.append(('destroy',)),
                               send=lambda request, **kw: calls.append(('send', request, kw)))
        namespace['response'](view, reply, False, starting)
        return calls

    def test_failed_auth_never_starts_session_and_secret_prompts_are_masked(self):
        calls = self.response({'type': 'error', 'error_type': 'auth_error'})
        self.assertIn(('reset',), calls)
        self.assertFalse(any(c[0] in ('send', 'destroy') for c in calls))
        calls = self.response({'type': 'auth_message', 'auth_message_type': 'secret', 'auth_message': 'Password:'})
        self.assertIn(('visible', False), calls)
        self.assertFalse(any(c[0] == 'send' for c in calls))

    def test_success_uses_only_fixed_session_and_waits_for_start_ack(self):
        calls = self.response({'type': 'success'})
        request = next(c[1] for c in calls if c[0] == 'send')
        self.assertEqual(request['cmd'], ['/usr/local/bin/hafthios-installed-session'])
        self.assertNotIn(('destroy',), calls)
        self.assertIn(('destroy',), self.response({'type': 'success'}, starting=True))

    def test_informational_and_unknown_prompts_do_not_bypass_pam(self):
        calls = self.response({'type': 'auth_message', 'auth_message_type': 'info', 'auth_message': 'Account notice'})
        self.assertIn(('send', {'type': 'post_auth_message_response'}, {}), calls)
        calls = self.response({'type': 'auth_message', 'auth_message_type': 'unknown'})
        self.assertIn(('send', {'type': 'cancel_session'}, {'cancel': True}), calls)


if __name__ == '__main__':
    unittest.main()
