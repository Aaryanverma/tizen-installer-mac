#!/usr/bin/env python3
"""Local macOS UI for the TizenInstaller package-manager workflow. Python 3.9+."""
import argparse
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
import webbrowser
import xml.etree.ElementTree as ET
import zipfile

BASE = Path(__file__).resolve().parent
SDB_URL = 'https://download.tizen.org/sdk/tizenstudio/official/binary/sdb_4.2.36_macos-64.zip'
SDB_SHA256 = '0bd307ac8382c857be5c2106dd5b8587b10c1c91ac1e504de8432c8276bc28c5'
MAX_UPLOAD = 128 * 1024 * 1024
LOCK = threading.Lock()


class InstallerError(Exception):
    pass


def resolve_sdb():
    candidates = [os.environ.get('SDB_BIN'), str(BASE / 'bin/sdb'),
                  shutil.which('sdb'), str(Path.home() / 'tizen-studio/tools/sdb'),
                  '/Applications/GalaxyWatchStudio.app/Contents/tizen/tools/sdb']
    return next((str(Path(p).resolve()) for p in candidates
                 if p and Path(p).is_file() and os.access(p, os.X_OK) and not p.endswith('.exe')), None)


def setup_sdb():
    """Fetch only the official executable; never run the SDK's install.sh."""
    dest = BASE / 'bin/sdb'
    dest.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tizen-sdb-') as folder:
        archive = Path(folder) / 'sdb.zip'
        subprocess.run(['/usr/bin/curl', '--fail', '--location', '--proto', '=https',
                        '--tlsv1.2', '--max-time', '120', SDB_URL, '-o', str(archive)], check=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != SDB_SHA256:
            raise InstallerError('Official SDB download checksum did not match; nothing installed.')
        with zipfile.ZipFile(archive) as z:
            data = z.read('data/tools/sdb')
        staging = dest.with_suffix('.new')
        staging.write_bytes(data)
        staging.chmod(0o755)
        staging.replace(dest)
    print('Downloaded official Mac SDB 4.2.36. No SDK installation scripts were run.')


def run_sdb(args, timeout=30):
    binary = resolve_sdb()
    if not binary:
        raise InstallerError('SDB is missing. Run: python3 installer.py --setup')
    try:
        p = subprocess.run([binary] + args, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise InstallerError('SDB timed out. Check the watch and Wi-Fi. An installation may still be running; check the watch before retrying.') from e
    except OSError as e:
        raise InstallerError('Cannot run Mac SDB: %s' % e) from e
    return p.returncode, '\n'.join(s.strip() for s in (p.stdout, p.stderr) if s.strip())


def devices():
    rc, out = run_sdb(['devices'])
    if rc:
        raise InstallerError(out or 'SDB could not list devices.')
    found = []
    for line in out.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] in ('device', 'offline', 'unauthorized', 'locked'):
            found.append({'serial': fields[0], 'state': fields[1],
                          'model': ' '.join(fields[2:])})
    return found


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def inspect_package(path, filename):
    ext = Path(filename).suffix.lower()[1:]
    if ext not in ('wgt', 'tpk'):
        raise InstallerError('Choose a .wgt or .tpk Tizen package.')
    try:
        with zipfile.ZipFile(path) as z:
            manifest = 'config.xml' if ext == 'wgt' else 'tizen-manifest.xml'
            info = z.getinfo(manifest)
            if info.file_size > 1024 * 1024:
                raise InstallerError('Package manifest is too large.')
            xml = z.read(info)
            if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():
                raise InstallerError('Package manifest contains unsupported XML declarations.')
            root = ET.fromstring(xml)
            nodes = list(root.iter())
            application = next((n for n in nodes if local_name(n.tag) in
                                ('application', 'watch-application', 'ui-application')), None)
            pkgid = root.get('package', '')
            if not pkgid and application is not None:
                pkgid = application.get('package', '')
            name = next((''.join(n.itertext()).strip() for n in nodes
                         if local_name(n.tag) in ('name', 'label')), Path(filename).stem)
            signatures = [n for n in z.namelist() if re.fullmatch(r'signature[0-9]+\.xml', n)]
            watchface = any(local_name(n.tag) == 'watch-application' or
                            (local_name(n.tag) == 'category' and 'clock' in n.get('name', ''))
                            for n in nodes)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError) as e:
        raise InstallerError('Invalid %s package: %s' % (ext.upper(), e)) from e
    return {'id': pkgid or 'Unknown', 'name': name[:256], 'version': root.get('version', 'Unknown'),
            'type': ext, 'is_watchface': watchface, 'size': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'signed': bool(signatures),
            'signature_note': 'Distributor signature file present; trust and validity are checked by the watch.'
                              if signatures else 'No distributor signature file found; installation may be rejected.'}


def install_result(rc, output):
    # Failures take priority even when an earlier stage emitted an OK callback.
    errors = re.findall(r'key\[error\]\s+val\[(-?\d+)\]', output, re.I)
    if rc or any(int(x) != 0 for x in errors) or re.search(r'key\[end\]\s+val\[fail\]', output, re.I):
        return False
    return bool(re.search(r'key\[end\]\s+val\[ok\]', output, re.I))


def shell(target, command, timeout=30):
    return run_sdb(['-s', target, 'shell', command], timeout)


def install_package(target, path, package):
    if not any(d['serial'] == target and d['state'] == 'device' for d in devices()):
        raise InstallerError('The selected watch is not connected and authorized. Connect again.')
    remote = '/opt/usr/apps/tmp/mac_install_%s.%s' % (secrets.token_hex(8), package['type'])
    qremote = shlex.quote(remote)
    log = []
    rc, out = shell(target, 'mkdir -p /opt/usr/apps/tmp')
    if rc:
        raise InstallerError(out or 'Could not prepare watch temporary directory.')
    try:
        rc, out = run_sdb(['-s', target, 'push', str(path), remote], timeout=180)
        log.append(out)
        if rc:
            raise InstallerError('File transfer failed:\n' + out)
        command = 'pkgcmd -i -t %s -p %s -w' % (package['type'], qremote)
        rc, out = shell(target, command, timeout=180)
        log.append(out)
        success = install_result(rc, out)
        log.append('Installation confirmed. Select the face on your watch.' if success else
                   'Installation was not confirmed. Check the output and watch before retrying.')
        return {'success': success, 'output': '\n\n'.join(log)}
    finally:
        # Delete only this attempt's uploaded file; never uninstall an existing app.
        try:
            shell(target, 'rm -f ' + qremote)
        except InstallerError:
            pass


class InstallerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.token = secrets.token_urlsafe(32)
        self.storage = tempfile.TemporaryDirectory(prefix='tizen-packages-')
        self.uploads = {}
        self.allowed_hosts = {'127.0.0.1', 'localhost'}

    def server_close(self):
        super().server_close()
        storage = getattr(self, 'storage', None)
        if storage is not None:
            storage.cleanup()


class Handler(BaseHTTPRequestHandler):
    server_version = 'TizenInstallerMac'

    def log_message(self, fmt, *args):
        pass  # Never log URLs, tokens, or upload names.

    def reply(self, status, payload, content_type='application/json'):
        body = json.dumps(payload).encode() if content_type == 'application/json' else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        host = urlsplit('http://' + self.headers.get('Host', '')).hostname
        if host not in self.server.allowed_hosts:
            self.reply(403, {'error': 'Unrecognized host.'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            self.reply(403, {'error': 'Cross-origin requests are not allowed.'})
            return False
        if not hmac.compare_digest(self.headers.get('X-Tizen-Token', ''), self.server.token):
            self.reply(401, {'error': 'Open the complete link shown in Terminal, or enter its pairing token.'})
            return False
        return True

    def do_GET(self):
        try:
            if self.path == '/':
                self.reply(200, (BASE / 'web/index.html').read_bytes(), 'text/html; charset=utf-8')
                return
            if not self.authorized():
                return
            if self.path != '/api/status':
                self.reply(404, {'error': 'Not found.'})
                return
            available = bool(resolve_sdb())
            self.reply(200, {'sdb_available': available, 'sdb_path': resolve_sdb(),
                             'platform': sys.platform, 'busy': LOCK.locked(),
                             'devices': devices() if available and not LOCK.locked() else []})
        except (InstallerError, OSError) as e:
            self.reply(400, {'error': str(e)})

    def do_POST(self):
        if not self.authorized():
            return
        if not LOCK.acquire(blocking=False):
            self.reply(409, {'error': 'Another operation is in progress. Wait for it to finish.'})
            return
        self.connection.settimeout(30)
        try:
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise InstallerError('Invalid content length.')
            url = urlsplit(self.path)
            limit = MAX_UPLOAD if url.path == '/api/package' else 16384
            if length <= 0 or length > limit:
                raise InstallerError('Request is empty or too large (packages: maximum 128 MB).')
            if self.headers.get('Transfer-Encoding'):
                raise InstallerError('Chunked uploads are not supported.')
            if url.path == '/api/package':
                filename = parse_qs(url.query).get('filename', [''])[0]
                if Path(filename).suffix.lower() not in ('.wgt', '.tpk'):
                    raise InstallerError('Choose a .wgt or .tpk file.')
                upload_id = secrets.token_hex(16)
                path = Path(self.server.storage.name) / (upload_id + Path(filename).suffix.lower())
                try:
                    with path.open('wb') as f:
                        remaining = length
                        while remaining:
                            data = self.rfile.read(min(65536, remaining))
                            if not data:
                                raise InstallerError('Upload ended early.')
                            f.write(data)
                            remaining -= len(data)
                    package = inspect_package(path, filename)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                while len(self.server.uploads) >= 4:
                    old = next(iter(self.server.uploads))
                    self.server.uploads.pop(old)[0].unlink(missing_ok=True)
                self.server.uploads[upload_id] = (path, package)
                self.reply(200, {'upload_id': upload_id, 'package': package})
                return
            body = self.rfile.read(length)
            if len(body) != length:
                raise InstallerError('Request ended early.')
            data = json.loads(body)
            if not isinstance(data, dict):
                raise InstallerError('Expected a JSON object.')
            if url.path == '/api/connect':
                host = str(ipaddress.IPv4Address(data.get('host', '').strip()))
                address = ipaddress.IPv4Address(host)
                if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
                    raise InstallerError('Enter the watch’s local Wi-Fi IPv4 address.')
                port = int(data.get('port', 26101))
                if not 1 <= port <= 65535:
                    raise InstallerError('Invalid port.')
                rc, out = run_sdb(['connect', '%s:%d' % (host, port)], timeout=45)
                found = devices()
                connected = any(d['serial'] == '%s:%d' % (host, port) and d['state'] == 'device' for d in found)
                self.reply(200, {'success': connected and rc == 0, 'output': out + (
                    '' if connected else '\nAccept the debugging prompt on the watch, then connect again.'),
                    'devices': found})
            elif url.path == '/api/install':
                entry = self.server.uploads.get(data.get('upload_id', ''))
                if not entry:
                    raise InstallerError('Select your package again; the upload has expired.')
                self.reply(200, install_package(str(data.get('target', '')), *entry))
            else:
                self.reply(404, {'error': 'Not found.'})
        except (InstallerError, ValueError, TypeError, OSError) as e:
            self.reply(400, {'error': str(e)})
        finally:
            LOCK.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', action='store_true', help='Download hash-verified official Mac SDB only')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if args.setup:
        setup_sdb()
        rc, out = run_sdb(['version'])
        print(out)
        return rc
    binary = resolve_sdb()
    if binary:
        rc, out = run_sdb(['version'])
        print(out)
        if rc:
            raise InstallerError('SDB did not start successfully.')
    server = InstallerServer(('127.0.0.1', args.port))
    url = 'http://127.0.0.1:%d/#token=%s' % (server.server_address[1], server.token)
    print('\nTizenInstaller for Mac\n' + url + '\n\nLeave this window open. Press Control-C to stop.\n', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (InstallerError, OSError, subprocess.CalledProcessError) as e:
        print('Error: ' + str(e), file=sys.stderr)
        sys.exit(1)
