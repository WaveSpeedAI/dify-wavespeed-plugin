"""Client tests against a local fake WaveSpeed HTTP server."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import client as client_mod  # noqa: E402
from utils.client import WaveSpeedClient, WaveSpeedError  # noqa: E402


class FakeServer:
    def __init__(self):
        self.posts = 0
        self.gets = 0
        self.post_status = 200
        self.get_script: list = []  # HTTP status ints or dict bodies

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                outer.posts += 1
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if outer.post_status == 200:
                    self._send(200, {"code": 200, "data": {"id": "t1"}})
                else:
                    self._send(outer.post_status, {"message": "upstream error"})

            def do_GET(self):
                outer.gets += 1
                item = (
                    outer.get_script.pop(0)
                    if len(outer.get_script) > 1
                    else outer.get_script[0]
                )
                if isinstance(item, int):
                    self._send(item, {"message": "err"})
                else:
                    self._send(200, {"code": 200, "data": item})

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"


@pytest.fixture
def server(monkeypatch):
    s = FakeServer()
    monkeypatch.setattr(client_mod, "BASE_URL", s.url)
    monkeypatch.setattr(client_mod, "POLL_INTERVAL_SECONDS", 0.01)
    yield s
    s.httpd.shutdown()


def test_poll_502_then_completed(server):
    server.get_script = [502, 502, {"status": "completed", "outputs": ["u"]}]
    data = WaveSpeedClient("k").wait("t1")
    assert data["status"] == "completed"
    assert server.gets == 3


def test_poll_429_and_network_error_retried(server, monkeypatch):
    server.get_script = [429, {"status": "completed"}]
    c = WaveSpeedClient("k")
    real_get = c.session.get
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise client_mod.requests.ConnectionError("reset")
        return real_get(*a, **kw)

    monkeypatch.setattr(c.session, "get", flaky)
    assert c.wait("t1")["status"] == "completed"
    assert server.gets == 2


def test_poll_persistent_502_raises_with_task_id(server):
    server.get_script = [502]
    with pytest.raises(WaveSpeedError) as ei:
        WaveSpeedClient("k").wait("t1")
    msg = str(ei.value)
    assert "t1" in msg and "may still be running" in msg
    assert server.gets == client_mod.POLL_MAX_RETRIES + 1


def test_poll_401_not_retried(server):
    server.get_script = [401]
    with pytest.raises(WaveSpeedError):
        WaveSpeedClient("k").wait("t1")
    assert server.gets == 1


@pytest.mark.parametrize("status", ["failed", "cancelled", "timeout", "deleted"])
def test_terminal_statuses(server, status):
    server.get_script = [{"status": status}]
    with pytest.raises(WaveSpeedError, match="t1"):
        WaveSpeedClient("k").wait("t1")
    assert server.gets == 1


def test_submit_504_single_post_with_warning(server):
    server.post_status = 504
    with pytest.raises(WaveSpeedError, match="may already exist"):
        WaveSpeedClient("k").submit("m/x", {"prompt": "p"})
    assert server.posts == 1


def test_submit_read_timeout_warns(server, monkeypatch):
    c = WaveSpeedClient("k")

    def boom(*a, **kw):
        raise client_mod.requests.ReadTimeout("slow")

    monkeypatch.setattr(c.session, "post", boom)
    with pytest.raises(WaveSpeedError, match="may already exist"):
        c.submit("m/x", {})


def test_submit_401_no_warning(server):
    server.post_status = 401
    with pytest.raises(WaveSpeedError) as ei:
        WaveSpeedClient("k").submit("m/x", {})
    assert "may already exist" not in str(ei.value)
    assert server.posts == 1


def test_submit_ok(server):
    assert WaveSpeedClient("k").submit("m/x", {}) == "t1"


def test_wait_has_no_default_cap_for_long_running_task(server, monkeypatch):
    """A task that stays processing far longer than the old 600s cap completes."""
    polls = 5000  # x 1s poll interval = ~83 min of simulated time
    server.get_script = [{"status": "processing"}] * polls + [
        {"status": "completed", "outputs": ["u"]}
    ]
    # Simulated clock: sleep advances it; real sleep is skipped.
    clock = {"t": 1000.0}
    monkeypatch.setattr(client_mod.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        client_mod.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + 1.0)
    )
    # get_script pops until one item is left, so it serves each entry once.
    data = WaveSpeedClient("k").wait("t1")
    assert data["status"] == "completed"
    assert clock["t"] - 1000.0 > 3600
    assert server.gets == polls + 1


def test_wait_explicit_timeout_still_honored(server, monkeypatch):
    server.get_script = [{"status": "processing"}]
    clock = {"t": 0.0}
    monkeypatch.setattr(client_mod.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        client_mod.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + 1.0)
    )
    with pytest.raises(WaveSpeedError, match="still 'processing' after 5s"):
        WaveSpeedClient("k").wait("t1", timeout=5)


def test_request_timeouts_by_type(server, monkeypatch):
    """Submit POST gets 60s; result polls and other GETs get 30s."""
    server.get_script = [{"status": "completed", "outputs": ["u"]}]
    c = WaveSpeedClient("k")
    seen = {"post": [], "get": []}
    real_post, real_get = c.session.post, c.session.get

    def post(*a, **kw):
        seen["post"].append(kw.get("timeout"))
        return real_post(*a, **kw)

    def get(*a, **kw):
        seen["get"].append(kw.get("timeout"))
        return real_get(*a, **kw)

    monkeypatch.setattr(c.session, "post", post)
    monkeypatch.setattr(c.session, "get", get)
    c.submit("m/x", {})
    c.wait("t1")
    c.check_credentials()
    assert seen["post"] == [60]
    assert seen["get"] == [30, 30]
