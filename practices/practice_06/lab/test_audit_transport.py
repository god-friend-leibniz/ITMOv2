"""Independent transport regressions: local authority, origin and total read deadline."""

import json
import socket
import threading
import time
import unittest
from unittest.mock import patch

import service
from service import Shop, ShopHTTPServer, make_handler


class AuditTransportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shop = Shop()
        cls.handler = make_handler(cls.shop)
        cls.server = ShopHTTPServer(("127.0.0.1", 0), cls.handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls.shop.close()

    def read_response(self, connection):
        result = b""
        while True:
            try:
                block = connection.recv(65536)
            except ConnectionResetError:
                break
            if not block:
                break
            result += block
        if not result:
            return None, "", ""
        head, _, body = result.partition(b"\r\n\r\n")
        return int(head.split()[1]), head.decode(), body.decode()

    def request(self, host="default", origin=None, method="GET", path="/health", body=None,
                version="HTTP/1.1", extra_headers=()):
        headers = []
        if host == "default":
            host = f"localhost:{self.port}"
        if host is not None:
            headers.append(("Host", host))
        if origin is not None:
            headers.append(("Origin", origin))
        headers.extend(extra_headers)
        payload = b"" if body is None else json.dumps(body).encode()
        if method == "POST":
            headers.extend((("Content-Type", "application/json"), ("Content-Length", str(len(payload)))))
        raw = f"{method} {path} {version}\r\n".encode()
        raw += b"".join(f"{name}: {value}\r\n".encode() for name, value in headers)
        raw += b"\r\n" + payload
        with socket.create_connection(self.server.server_address, timeout=3) as connection:
            connection.sendall(raw)
            connection.shutdown(socket.SHUT_WR)
            return self.read_response(connection)

    def test_loopback_host_aliases_and_actual_port_are_allowed(self):
        for host in ("localhost", "LOCALHOST", "127.0.0.1", "[::1]",
                     f"localhost:{self.port}", f"127.0.0.1:{self.port}", f"[::1]:{self.port}"):
            with self.subTest(host=host):
                self.assertEqual(self.request(host=host)[0], 200)

    def test_foreign_malformed_and_wrong_port_hosts_are_rejected(self):
        other_port = self.port + 1 if self.port < 65535 else self.port - 1
        for host in ("rebinding.example.invalid", "localhost.evil.invalid", "127.0.0.2",
                     "127.1", "2130706433", "localhost@evil.invalid", "evil.invalid@localhost",
                     "localhost/", "localhost.", "[::ffff:127.0.0.1]", "localhost:abc",
                     "[::1]evil.invalid", f"[::1]localhost:{self.port}", "local\thost", "localhost:0",
                     "localhost:", "localhost:65536", f"localhost:{other_port}",
                     f"127.0.0.1:{other_port}", f"[::1]:{other_port}"):
            with self.subTest(host=host):
                self.assertEqual(self.request(host=host)[0], 403)

    def test_http11_requires_exactly_one_host(self):
        self.assertEqual(self.request(host=None)[0], 400)
        self.assertEqual(self.request(extra_headers=(("Host", f"localhost:{self.port}"),))[0], 400)
        self.assertEqual(self.request(extra_headers=(("host", "evil.invalid"),))[0], 400)

    def test_http10_legacy_hostless_client_is_allowed(self):
        self.assertEqual(self.request(host=None, version="HTTP/1.0")[0], 200)
        self.assertEqual(self.request(host="evil.invalid", version="HTTP/1.0")[0], 403)
        self.assertEqual(self.request(host=None, origin="http://localhost", version="HTTP/1.0")[0], 403)

    def test_exact_same_origin_and_default_port_normalization(self):
        for host, origin in ((f"localhost:{self.port}", f"http://localhost:{self.port}"),
                             (f"LOCALHOST:{self.port}", f"http://localhost:{self.port}"),
                             (f"[::1]:{self.port}", f"http://[::1]:{self.port}"),
                             ("localhost", "http://localhost"),
                             ("localhost", "http://localhost:80"),
                             ("127.0.0.1", "http://127.0.0.1"),
                             ("[::1]", "http://[::1]:80")):
            with self.subTest(host=host, origin=origin):
                self.assertEqual(self.request(host=host, origin=origin)[0], 200)

    def test_cross_origin_is_rejected_including_other_loopback_aliases(self):
        for origin in ("http://evil.invalid", "null", "https://localhost", "file://localhost",
                       "http://127.0.0.1", "http://[::1]", f"http://127.0.0.1:{self.port}",
                       "http://localhost", f"http://localhost:{self.port + 1}"):
            with self.subTest(origin=origin):
                self.assertEqual(self.request(origin=origin)[0], 403)

    def test_origin_cannot_contain_url_components_or_credentials(self):
        base = f"http://localhost:{self.port}"
        for origin in (base + "/", base + "/path", base + "?q=x", base + "#fragment",
                       base + "?", base + "#", f"http://user@localhost:{self.port}",
                       f"http://user:password@localhost:{self.port}",
                       f"http://localhost:{self.port}, http://evil.invalid", "http://localhost:bad"):
            with self.subTest(origin=origin):
                self.assertEqual(self.request(origin=origin)[0], 403)
        self.assertEqual(self.request(origin=base, extra_headers=(("Origin", base),))[0], 400)
        self.assertEqual(self.request(host="[::1]", origin="http://[::1]evil.invalid")[0], 403)

    def test_origin_validation_runs_before_mutation_or_authentication(self):
        body = {"username": "alice", "password": "learn-alice"}
        before = len(self.shop.sessions)
        self.assertEqual(self.request(origin="http://evil.invalid", method="POST", path="/login", body=body)[0], 403)
        self.assertEqual(len(self.shop.sessions), before)
        self.assertEqual(self.request(host="rebinding.example.invalid", origin="http://rebinding.example.invalid",
                                      method="POST", path="/login", body=body)[0], 403)
        self.assertEqual(len(self.shop.sessions), before)

    def test_native_client_without_origin_and_same_origin_login_work(self):
        body = {"username": "bob", "password": "learn-bob"}
        for origin in (None, f"http://localhost:{self.port}"):
            status, _, result = self.request(origin=origin, method="POST", path="/login", body=body)
            self.assertEqual(status, 200)
            self.assertIn("token", json.loads(result))

    def drip(self, prefix, suffix):
        """One low-volume connection; continue bytes across several inactivity windows."""
        timeout = 0.2
        with patch.object(self.handler, "REQUEST_TIMEOUT", timeout):
            with socket.create_connection(self.server.server_address, timeout=3) as connection:
                started = time.monotonic()
                connection.sendall(prefix)
                while time.monotonic() - started < 0.8:
                    time.sleep(0.06)
                    try:
                        connection.sendall(b" ")
                    except (BrokenPipeError, ConnectionResetError):
                        break
                try:
                    connection.sendall(suffix)
                    connection.shutdown(socket.SHUT_WR)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                result = self.read_response(connection)
                elapsed = time.monotonic() - started
        return result, elapsed

    def test_total_deadline_stops_slow_headers_and_server_recovers(self):
        prefix = f"GET /health HTTP/1.1\r\nHost: localhost:{self.port}\r\nX-Slow: x".encode()
        (status, _, _), elapsed = self.drip(prefix, b"\r\n\r\n")
        self.assertIn(status, (None, 400, 408))
        self.assertLess(elapsed, 0.65)
        self.assertEqual(self.request()[0], 200)

    def test_total_deadline_stops_slow_body_with_408_and_server_recovers(self):
        prefix = (f"POST /login HTTP/1.1\r\nHost: localhost:{self.port}\r\n"
                  "Content-Type: application/json\r\nContent-Length: 64\r\n\r\n{").encode()
        (status, _, _), elapsed = self.drip(prefix, b"")
        self.assertEqual(status, 408)
        self.assertLess(elapsed, 0.65)
        self.assertEqual(self.request()[0], 200)

    def test_completed_request_cancels_deadline_timer(self):
        actual_timer = threading.Timer
        timers, fired = [], []

        def tracked_timer(interval, function, args=None, kwargs=None):
            def callback():
                fired.append(True)
                function(*(args or ()), **(kwargs or {}))
            timer = actual_timer(interval, callback)
            timers.append(timer)
            return timer

        with patch.object(self.handler, "REQUEST_TIMEOUT", 0.2), patch("service.threading.Timer", side_effect=tracked_timer):
            self.assertEqual(self.request()[0], 200)
            self.assertTrue(timers, "Request must have an absolute deadline timer")
            for timer in timers:
                timer.join(timeout=1)
                self.assertFalse(timer.is_alive())
                self.assertTrue(timer.finished.is_set())
            self.assertFalse(fired, "Completed requests must cancel their deadline callback")
        self.assertEqual(self.request()[0], 200)


if __name__ == "__main__":
    unittest.main()
