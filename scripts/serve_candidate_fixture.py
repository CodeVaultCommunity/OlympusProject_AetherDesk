"""Serve the built candidate UI with synthetic same-origin API responses."""

from __future__ import annotations

import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


SESSION = {'username': 'fixture', 'role': 'admin', 'account_id': 'w006-ui-fixture',
           'permissions': ['files.read', 'files.write', 'terminal.open', 'metrics.self',
                           'preferences.read', 'preferences.write', 'accounts.view'],
           'permissions_version': 1}
DESKTOP = {'schemaVersion': 2, 'windows': [], 'activeId': None, 'theme': 'dark'}


class Handler(SimpleHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        content = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == '/api/v1/me':
            self._json(200, {'data': SESSION})
        elif path == '/api/v1/desktop/state':
            self._json(200, {'data': DESKTOP, 'revision': 0})
        elif path.startswith('/api/'):
            self._json(404, {'detail': 'NOT_FOUND'})
        else:
            super().do_GET()

    def do_PUT(self) -> None:
        if urlsplit(self.path).path == '/api/v1/desktop/state':
            self._json(200, {'data': {}, 'revision': 1})
        else:
            self._json(404, {'detail': 'NOT_FOUND'})

    def do_POST(self) -> None:
        self._json(200, {'data': {}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8175)
    args = parser.parse_args()
    if not (args.dist / 'index.html').is_file():
        raise RuntimeError('Candidate web/dist unavailable')
    server = ThreadingHTTPServer(('0.0.0.0', args.port), partial(Handler, directory=str(args.dist)))
    server.serve_forever()
