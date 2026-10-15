"""Offline checks for package inspection and the local installer workflow.

All watch operations are mocked. These checks do not validate a watch firmware,
package signature trust, or Facer's current syncing service.
"""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import installer


TARGET = '192.168.1.37:26101'
CONNECTED = [{'serial': TARGET, 'state': 'device', 'model': 'SM-R800'}]
SUCCESS = '__return_cb req_id[1] pkg_type[wgt] pkgid[example123] key[end] val[ok]'
MANIFEST = '''<?xml version="1.0" encoding="UTF-8"?>
<widget xmlns="http://www.w3.org/ns/widgets"
        xmlns:tizen="http://tizen.org/ns/widgets"
        id="https://example.test/watch" version="2.4.1">
  <tizen:application id="example123.Main" package="example123" required_version="5.5"/>
  <name>Example &amp; Clock</name>
  <tizen:category name="http://tizen.org/category/wearable_clock"/>
</widget>'''


def package_bytes(manifest=MANIFEST, signed=True):
    stream = BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('config.xml', manifest)
        archive.writestr('index.html', '<p>A test watch face</p>')
        if signed:
            # Deliberately invalid cryptographic signature: presence is only metadata.
            archive.writestr('signature1.xml', '<not-a-valid-signature/>')
    return stream.getvalue()


class PackageInspectionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'face.wgt'

    def inspect(self, data, filename='face.wgt'):
        self.path.write_bytes(data)
        return installer.inspect_package(self.path, filename)

    def test_namespaced_widget_metadata_and_digest(self):
        data = package_bytes()
        package = self.inspect(data, 'My Face.WGT')
        self.assertEqual(package['id'], 'example123')
        self.assertEqual(package['name'], 'Example & Clock')
        self.assertEqual(package['version'], '2.4.1')
        self.assertEqual(package['type'], 'wgt')
        self.assertTrue(package['is_watchface'])
        self.assertEqual(package['size'], len(data))
        self.assertEqual(package['sha256'], hashlib.sha256(data).hexdigest())

    def test_signature_presence_does_not_claim_signature_is_valid(self):
        package = self.inspect(package_bytes())
        self.assertTrue(package['signed'])
        self.assertIn('present', package['signature_note'])
        self.assertIn('trust and validity are checked by the watch', package['signature_note'])
        unsigned = self.inspect(package_bytes(signed=False))
        self.assertFalse(unsigned['signed'])
        self.assertIn('may be rejected', unsigned['signature_note'])

    def test_broken_zip_is_rejected(self):
        with self.assertRaises(installer.InstallerError):
            self.inspect(b'this is not a ZIP file')

    def test_missing_manifest_and_invalid_xml_are_rejected(self):
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('index.html', 'missing config.xml')
        for data in (stream.getvalue(), package_bytes('<widget>')):
            with self.subTest(data=data[:20]):
                with self.assertRaises(installer.InstallerError):
                    self.inspect(data)

    def test_xml_entities_and_unsupported_extension_are_rejected(self):
        malicious = '<!DOCTYPE widget [<!ENTITY a "content">]><widget><name>&a;</name></widget>'
        with self.assertRaises(installer.InstallerError):
            self.inspect(package_bytes(malicious))
        with self.assertRaises(installer.InstallerError):
            self.inspect(package_bytes(), 'legacy.face')


class InstallResultTests(unittest.TestCase):
    def test_explicit_terminal_success_is_required(self):
        for output in ('', 'key[install_percent] val[100]',
                       'spend time for pkgcmd is [971]ms', 'OK'):
            with self.subTest(output=output):
                self.assertFalse(installer.install_result(0, output))
        self.assertTrue(installer.install_result(0, SUCCESS))
        self.assertTrue(installer.install_result(0, SUCCESS + '\nkey[error] val[0]'))

    def test_transport_and_terminal_failures_override_earlier_success(self):
        for rc, output in ((1, SUCCESS), (-1, SUCCESS),
                           (0, SUCCESS + '\nkey[error] val[-27]'),
                           (0, SUCCESS + '\nkey[error] val[22]'),
                           (0, SUCCESS + '\nkey[end] val[fail]')):
            with self.subTest(rc=rc, output=output):
                self.assertFalse(installer.install_result(rc, output))


class InstallationPipelineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'face.wgt'
        self.path.write_bytes(package_bytes())
        self.package = installer.inspect_package(self.path, self.path.name)

    def test_single_install_attempt_and_cleanup_on_success_or_rejection(self):
        for installation_output, expected_success in ((SUCCESS, True),
                ('key[error] val[-27]\nkey[end] val[fail]', False)):
            with self.subTest(success=expected_success), \
                    patch.object(installer, 'devices', return_value=CONNECTED), \
                    patch.object(installer, 'run_sdb', return_value=(0, 'Pushed')) as run, \
                    patch.object(installer, 'shell', side_effect=[
                        (0, ''), (0, installation_output), (0, '')]) as shell:
                result = installer.install_package(TARGET, self.path, self.package)
                self.assertEqual(result['success'], expected_success)
                calls = shell.call_args_list
                self.assertEqual(len(calls), 3)
                self.assertEqual(calls[0].args, (TARGET, 'mkdir -p /opt/usr/apps/tmp'))
                self.assertIn('pkgcmd -i -t wgt -p ', calls[1].args[1])
                self.assertTrue(calls[1].args[1].endswith(' -w'))
                self.assertTrue(calls[2].args[1].startswith('rm -f /opt/usr/apps/tmp/mac_install_'))
                self.assertFalse(any('pkgcmd -u' in call.args[1] for call in calls))
                self.assertFalse(any('launch_app' in call.args[1] for call in calls))
                remote = run.call_args.args[0][-1]
                self.assertIn(remote, calls[1].args[1])
                self.assertEqual(calls[2].args[1], 'rm -f ' + remote)

    def test_failed_push_still_cleans_up_and_never_installs(self):
        with patch.object(installer, 'devices', return_value=CONNECTED), \
                patch.object(installer, 'run_sdb', return_value=(1, 'No space left')), \
                patch.object(installer, 'shell', return_value=(0, '')) as shell:
            with self.assertRaisesRegex(installer.InstallerError, 'File transfer failed'):
                installer.install_package(TARGET, self.path, self.package)
            commands = [call.args[1] for call in shell.call_args_list]
            self.assertEqual(len(commands), 2)
            self.assertTrue(commands[-1].startswith('rm -f '))
            self.assertFalse(any('pkgcmd' in command for command in commands))

    def test_install_timeout_still_cleans_up(self):
        with patch.object(installer, 'devices', return_value=CONNECTED), \
                patch.object(installer, 'run_sdb', return_value=(0, 'Pushed')), \
                patch.object(installer, 'shell', side_effect=[
                    (0, ''), installer.InstallerError('SDB timed out'), (0, '')]) as shell:
            with self.assertRaisesRegex(installer.InstallerError, 'timed out'):
                installer.install_package(TARGET, self.path, self.package)
            self.assertTrue(shell.call_args.args[1].startswith('rm -f '))

    def test_offline_or_unlisted_target_never_receives_a_command(self):
        for listed in ([], [{'serial': TARGET, 'state': 'offline', 'model': 'SM-R800'}]):
            with self.subTest(devices=listed), \
                    patch.object(installer, 'devices', return_value=listed), \
                    patch.object(installer, 'run_sdb') as run, \
                    patch.object(installer, 'shell') as shell:
                with self.assertRaises(installer.InstallerError):
                    installer.install_package(TARGET, self.path, self.package)
                run.assert_not_called()
                shell.assert_not_called()


class LocalAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise HTTP parsing/routing without opening any network sockets.
        cls.storage = tempfile.TemporaryDirectory()
        cls.server = SimpleNamespace(token='a-test-session-token', storage=cls.storage,
                                    uploads={}, allowed_hosts={'127.0.0.1', 'localhost'})

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def tearDown(self):
        for path, _ in self.server.uploads.values():
            path.unlink(missing_ok=True)
        self.server.uploads.clear()

    def request(self, method, path, body=None, headers=None, token=True):
        request_headers = {'Host': '127.0.0.1:8765'}
        if token:
            request_headers['X-Tizen-Token'] = self.server.token
        body = body or b''
        request_headers['Content-Length'] = str(len(body))
        request_headers.update(headers or {})
        head = '%s %s HTTP/1.0\r\n%s\r\n\r\n' % (method, path, '\r\n'.join(
            '%s: %s' % (key, value) for key, value in request_headers.items()))
        connection = MemorySocket(head.encode('latin-1') + body)
        installer.Handler(connection, ('127.0.0.1', 42000), self.server)
        response_head, response_body = bytes(connection.response).split(b'\r\n\r\n', 1)
        status = int(response_head.split(b'\r\n', 1)[0].split()[1])
        return status, json.loads(response_body)

    def test_api_rejects_missing_and_wrong_token_before_watch_access(self):
        with patch.object(installer, 'run_sdb') as run:
            for headers in ({}, {'X-Tizen-Token': 'incorrect'}):
                with self.subTest(headers=headers):
                    status, result = self.request('POST', '/api/install', b'{}', headers, token=False)
                    self.assertEqual(status, 401)
                    self.assertIn('error', result)
            run.assert_not_called()

    def test_api_rejects_foreign_host_and_origin(self):
        for headers in ({'Host': 'untrusted.example'}, {'Origin': 'https://untrusted.example'}):
            with self.subTest(headers=headers):
                status, result = self.request('GET', '/api/status', headers=headers)
                self.assertEqual(status, 403)
                self.assertIn('error', result)

    def test_upload_then_install_uses_the_stored_package(self):
        data = package_bytes()
        status, upload = self.request('POST', '/api/package?' + urlencode({'filename': 'Facer.wgt'}), data)
        self.assertEqual(status, 200)
        self.assertEqual(upload['package']['id'], 'example123')
        upload_id = upload['upload_id']
        saved_path, saved_package = self.server.uploads[upload_id]
        self.assertEqual(saved_path.read_bytes(), data)
        with patch.object(installer, 'install_package', return_value={'success': True, 'output': 'confirmed'}) as install:
            status, result = self.request('POST', '/api/install', json.dumps({
                'target': TARGET, 'upload_id': upload_id}).encode())
            self.assertEqual(status, 200)
            self.assertTrue(result['success'])
            install.assert_called_once_with(TARGET, saved_path, saved_package)

    def test_bad_upload_is_removed_and_expired_upload_cannot_install(self):
        before = set(Path(self.server.storage.name).iterdir())
        status, result = self.request('POST', '/api/package?filename=broken.wgt', b'not a zip')
        self.assertEqual(status, 400)
        self.assertIn('Invalid WGT package', result['error'])
        self.assertEqual(set(Path(self.server.storage.name).iterdir()), before)
        with patch.object(installer, 'install_package') as install:
            status, result = self.request('POST', '/api/install', json.dumps({
                'target': TARGET, 'upload_id': 'expired'}).encode())
            self.assertEqual(status, 400)
            self.assertIn('expired', result['error'])
            install.assert_not_called()


class MemorySocket:
    def __init__(self, request):
        self.request = BytesIO(request)
        self.response = bytearray()

    def makefile(self, *_args):
        return self.request

    def sendall(self, data):
        self.response.extend(data)

    def settimeout(self, _timeout):
        pass


if __name__ == '__main__':
    unittest.main()
