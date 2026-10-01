"""The container probe must validate HTTP/OSRM, not just an open TCP port."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
from threading import Thread
import pytest
from test_osrm_prepare import BASH, ROOT


@pytest.mark.parametrize('status,body,success', [
    (200, '{"code":"Ok","waypoints":[{"location":[14,40]}]}', True),
    (200, '{"code": "Ok", "waypoints": [ {"location": [14,40]}]}', True),
    (503, '{"code":"Ok","waypoints":[{}]}', False),
    (200, '{"code":"NoSegment","waypoints":[{}]}', False),
    (200, '{"code":"Ok","waypoints":[]}', False),
    (200, '<html>Service online</html>', False),
])
def test_probe_requires_http_and_successful_osrm_result(status, body, success):
    if not BASH or not Path(BASH).exists():
        pytest.skip('Bash not installed')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == '/nearest/v1/driving/0,0?number=1'
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body.encode())
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([BASH, str(ROOT/'scripts/osrm_healthcheck.sh')],
            env=dict(os.environ, OSRM_HEALTH_PORT=str(server.server_port)),
            capture_output=True, timeout=15)
        assert (result.returncode == 0) is success, result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
