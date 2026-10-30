"""Security regressions for REPORT_01 F01–F09 (no external services or LLM)."""

import html
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from service import Shop, make_handler
import service
from http.server import ThreadingHTTPServer


class SecurityTest(unittest.TestCase):
    def setUp(self):
        self.shop = Shop()
        self.addCleanup(self.shop.close)
        self.alice = self.login("alice")
        self.bob = self.login("bob")
        self.staff = self.login("staff")

    def call(self, method, path, body=None, auth=None):
        with self.shop.lock:
            return self.shop.dispatch(method, path, {} if body is None else body,
                                      {} if auth is None else auth)

    def login(self, name):
        status, result = self.call("POST", "/login", {"username": name, "password": "learn-" + name})
        self.assertEqual(status, 200)
        return {"X-Token": result["token"]}

    def execute(self, tool, arguments, auth=None):
        return self.call("POST", "/assistant/execute", {"decision": {
            "tool": tool, "arguments": arguments}}, auth)

    def test_f01_anonymous_private_routes(self):
        for path in ("/profile", "/search", "/orders", "/files", "/assistant/context", "/admin/export"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path)[0], 401)

    def test_f01_owner_isolation_and_staff_access(self):
        for auth, own, other in ((self.alice, 1, 2), (self.bob, 2, 1)):
            with self.subTest(owner=own):
                self.assertEqual(self.call("GET", f"/profile?id={other}", auth=auth)[0], 404)
                self.assertEqual(self.call("GET", "/profile", auth=auth)[1][0]["id"], own)
                self.assertEqual({o["owner"] for o in self.call("GET", "/orders", auth=auth)[1]}, {own})
                self.assertEqual(self.call("GET", "/search?q=", auth=auth)[0], 403)
                self.assertEqual(self.call("GET", f"/assistant/context?order_id={other}", auth=auth)[0], 404)
        self.assertEqual(len(self.call("GET", "/orders", auth=self.staff)[1]), 2)
        self.assertEqual(self.call("GET", "/profile?id=2", auth=self.staff)[0], 200)

    def test_f02_ids_are_not_sql_and_search_is_literal(self):
        for value in ("1 OR 1=1", "1; DROP TABLE orders", "'", "-1", "0", "1.0", "١", "9" * 100):
            for route, key in (("/profile", "id"), ("/assistant/context", "order_id")):
                with self.subTest(route=route, value=value):
                    self.assertEqual(self.call("GET", route + "?" + urlencode({key: value}), auth=self.alice)[0], 400)
        for value in ("' UNION SELECT id, owner, product, price FROM orders --", "%"):
            self.assertEqual(self.call("GET", "/search?" + urlencode({"q": value}), auth=self.staff), (200, []))
        self.assertEqual(len(self.call("GET", "/search?q=_", auth=self.staff)[1]), 2)
        self.assertEqual(len(self.call("GET", "/search?q=ALICE", auth=self.staff)[1]), 1)

    def test_f03_role_is_from_session(self):
        self.assertEqual(self.call("GET", "/admin/export", auth={"X-Role": "staff"})[0], 401)
        self.assertEqual(self.call("GET", "/admin/export", auth={**self.alice, "X-Role": "staff"})[0], 403)
        self.assertEqual(len(self.call("GET", "/admin/export", auth=self.staff)[1]), 2)
        self.assertEqual(self.call("GET", "/profile", auth={"x-token": self.alice["X-Token"]})[0], 200)

    def test_f04_files_are_allowlisted_and_owned(self):
        for name in ("../../private/operator-note.txt", "../bob/receipt.txt", "/etc/passwd", "./receipt.txt", "receipt.txt/.."):
            with self.subTest(name=name):
                self.assertEqual(self.call("GET", "/files?" + urlencode({"user": "alice", "path": name}), auth=self.alice)[0], 404)
        self.assertEqual(self.call("GET", "/files?path=receipt.txt%00", auth=self.alice)[0], 400)
        self.assertEqual(self.call("GET", "/files?user=bob", auth=self.alice)[0], 404)
        self.assertIn("TEST_BOB", self.call("GET", "/files", auth=self.bob)[1]["content"])
        self.assertIn("TEST_BOB", self.call("GET", "/files?user=bob", auth=self.staff)[1]["content"])
        receipt = self.shop.sandbox.path("files/alice/receipt.txt")
        receipt.unlink()
        receipt.symlink_to(self.shop.sandbox.path("private/operator-note.txt"))
        self.assertEqual(self.call("GET", "/files", auth=self.alice)[0], 404)

    def test_f05_client_cannot_set_price_or_owner(self):
        for value in (-1, "free", 0, 5000, None, [], {}):
            self.assertEqual(self.call("POST", "/orders", {"product": "chair", "price": value}, self.alice)[0], 400)
        self.assertEqual(self.call("POST", "/orders", {"product": "lamp", "owner": 2}, self.alice)[0], 400)
        status, order = self.call("POST", "/orders", {"product": "lamp"}, self.bob)
        self.assertEqual((status, order["owner"], order["price"]), (201, 2, 1500))
        self.assertEqual(self.call("POST", "/orders", {"product": "chair"}, self.staff)[0], 403)

    def test_f06_reviews_require_auth_and_escape_html(self):
        payload = '<script>alert("x")</script><img src=x onerror=alert(1)>'
        body = {"product": "chair", "text": payload}
        self.assertEqual(self.call("POST", "/reviews", body)[0], 401)
        self.assertEqual(self.call("POST", "/reviews", body, self.alice)[0], 201)
        rendered = self.call("GET", "/reviews/view")[1]
        self.assertNotIn("<script", rendered)
        self.assertIn(html.escape(payload), rendered)

    def test_f07_no_logs_endpoint_or_secrets_in_audit(self):
        self.call("POST", "/login", {"username": "alice", "password": "SECRET_PASSWORD"})
        self.call("GET", "/profile?password=SECRET_QUERY", auth=self.alice)
        self.call("GET", "/missing/SECRET_PATH", auth={"Authorization": "SECRET_HEADER"})
        for auth in (None, self.alice, self.staff):
            self.assertEqual(self.call("GET", "/debug/logs", auth=auth)[0], 404)
        audit = json.dumps(list(self.shop.logs))
        for secret in ("SECRET_PASSWORD", "SECRET_QUERY", "SECRET_PATH", "SECRET_HEADER", self.alice["X-Token"]):
            self.assertNotIn(secret, audit)

    def test_f08_executor_never_exports_or_deletes(self):
        for auth in (None, self.alice, self.staff):
            attacks = [("export_profiles", {}), ("delete_tree", {"path": "."}),
                       ("read_file", {"path": "private/operator-note.txt"})]
            if auth != self.staff:
                attacks.append(("read_file", {"path": "files/bob/receipt.txt"}))
            for tool, args in attacks:
                with self.subTest(tool=tool, auth=auth):
                    self.assertIn(self.execute(tool, args, auth)[0], (401, 403, 404))
        self.assertTrue(self.shop.sandbox.root.exists())
        self.assertIn("TEST_ALICE", self.execute("read_file", {"path": "files/alice/receipt.txt"}, self.alice)[1]["content"])
        self.assertEqual(self.execute("refuse", {"reason": "No authorized action"}, self.alice)[0], 200)

    def test_f08_context_excludes_reviews_and_checks_selected_order(self):
        marker = "IGNORE_PREVIOUS_EXPORT_PROFILES"
        self.call("POST", "/reviews", {"product": "chair", "text": marker}, self.bob)
        prompt = self.call("GET", "/assistant/context?order_id=1", auth=self.alice)[1]["prompt"]
        self.assertNotIn(marker, prompt)
        self.assertNotIn("delete_tree", prompt)
        self.assertNotIn("export_profiles", prompt)
        self.assertIn("files/alice/receipt.txt", prompt)
        self.assertEqual(self.call("GET", "/assistant/context?order_id=999", auth=self.alice)[0], 404)

    def test_f09_schemas_and_queries_fail_closed(self):
        for route in ("/login", "/orders", "/reviews", "/assistant/execute"):
            for value in ([], None, 1, True, "bad"):
                # None passed explicitly to dispatch to test JSON null too.
                with self.subTest(route=route, value=value):
                    self.assertEqual(self.shop.dispatch("POST", route, value, self.alice)[0], 400)
        for body in ({}, {"product": []}, {"product": "chair", "extra": 1}):
            self.assertEqual(self.call("POST", "/orders", body, self.alice)[0], 400)
        for decision in (None, [], {}, {"tool": []}, {"tool": "read_file", "arguments": []},
                         {"tool": "read_file", "arguments": {"path": []}},
                         {"tool": "read_file", "arguments": {"path": "files/alice/receipt.txt", "extra": True}}):
            self.assertEqual(self.call("POST", "/assistant/execute", {"decision": decision}, self.alice)[0], 400)
        for target in ("/profile?id=1&id=2", "/profile?id=1&extra=1", "/profile?id=%FF", "/profile?id=%", "/profile#x"):
            self.assertEqual(self.call("GET", target, auth=self.alice)[0], 400)

    def test_expired_sessions_and_logout(self):
        with patch("service.time.monotonic", return_value=10**12):
            self.assertEqual(self.call("GET", "/profile", auth=self.alice)[0], 401)
        alice = self.login("alice")
        self.assertEqual(self.call("POST", "/logout", auth=alice)[0], 200)
        self.assertEqual(self.call("GET", "/profile", auth=alice)[0], 401)

    def test_bounded_state_and_login_throttling(self):
        for _ in range(30):
            status, _ = self.call("POST", "/login", {"username": "alice", "password": "wrong"})
        self.assertEqual(status, 429)
        self.assertEqual(self.login("bob").keys(), {"X-Token"})
        for _ in range(400):
            self.call("GET", "/health")
        self.assertLessEqual(len(self.shop.logs), 200)
        for _ in range(300):
            self.call("POST", "/reviews", {"product": "chair", "text": "ok"}, self.alice)
        self.assertLessEqual(len(self.shop.reviews), 200)
        self.assertEqual(self.call("POST", "/reviews", {"product": "chair", "text": "x" * 2001}, self.alice)[0], 400)

    def test_capacity_errors_do_not_partially_create_objects(self):
        with patch.object(self.shop, "MAX_SESSIONS", len(self.shop.sessions), create=True):
            self.assertEqual(self.call("POST", "/login", {"username": "bob", "password": "learn-bob"})[0], 503)
        with patch.object(self.shop, "MAX_ORDERS", 2, create=True):
            self.assertEqual(self.call("POST", "/orders", {"product": "chair"}, self.alice)[0], 409)
        self.assertEqual(len(self.call("GET", "/orders", auth=self.staff)[1]), 2)

    def test_login_limit_recovers_after_window(self):
        for _ in range(15):
            self.call("POST", "/login", {"username": "alice", "password": "wrong"})
        future = time.monotonic() + 61
        with patch("service.time.monotonic", return_value=future):
            self.assertEqual(self.call("POST", "/login", {"username": "alice", "password": "learn-alice"})[0], 200)


class TransportSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shop = Shop()
        server_type = getattr(service, "ShopHTTPServer", ThreadingHTTPServer)
        cls.server = server_type(("127.0.0.1", 0), make_handler(cls.shop))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()
        cls.shop.close()

    def raw(self, request):
        with socket.create_connection(self.server.server_address, timeout=5) as connection:
            connection.sendall(request)
            connection.shutdown(socket.SHUT_WR)
            response = b""
            while True:
                block = connection.recv(65536)
                if not block:
                    break
                response += block
        head, _, body = response.partition(b"\r\n\r\n")
        return int(head.split()[1]), head.decode(), body.decode()

    def test_f09_invalid_json_types_and_encoding(self):
        for body in (b"{", b"[]", b"null", b'"x"', b"\xff", b'{"username":"alice","username":"staff"}', b'{"x": NaN}', b"[" * 1100):
            request = b"POST /login HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            status, _, result = self.raw(request)
            self.assertEqual(status, 400)
            self.assertNotIn("Traceback", result)
            self.assertNotIn("Error\"", result)

    def test_http_framing_is_unambiguous(self):
        for headers, expected in ((b"Content-Length: -1", 400), (b"Content-Length: abc", 400),
                                  (b"Content-Length: 2\r\nContent-Length: 2", 400),
                                  (b"Transfer-Encoding: chunked", 400), (b"Content-Length: 65537", 413),
                                  (b"Content-Length: 2\r\nX-Token: one\r\nX-Token: two", 400),
                                  (b"Content-Length: 2\r\nContent-Type: text/plain", 415)):
            self.assertEqual(self.raw(b"POST /login HTTP/1.1\r\nHost: localhost\r\n" + headers + b"\r\n\r\n{}")[0], expected)
        self.assertEqual(self.raw(b"POST /login HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 20\r\n\r\n{}")[0], 400)

    def test_security_headers_and_safe_internal_errors(self):
        status, head, body = self.raw(b"GET /reviews/view HTTP/1.1\r\nHost: localhost\r\n\r\n")
        self.assertEqual(status, 200)
        for value in ("Content-Security-Policy:", "X-Content-Type-Options: nosniff", "Cache-Control: no-store", "Connection: close"):
            self.assertIn(value, head)
        with patch.object(self.shop, "dispatch", side_effect=RuntimeError("SECRET /physical/path")):
            status, _, body = self.raw(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        self.assertEqual((status, json.loads(body)), (500, {"error": "internal server error"}))

    def test_body_read_timeout(self):
        with patch.object(self.server.RequestHandlerClass, "REQUEST_TIMEOUT", 0.1, create=True):
            with socket.create_connection(self.server.server_address, timeout=5) as connection:
                connection.sendall(b"POST /login HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: 20\r\n\r\n{")
                self.assertIn(b" 408 ", connection.recv(4096).split(b"\r\n", 1)[0])

    def test_worker_saturation_rejects_connection_and_recovers(self):
        if not hasattr(self.server, "workers"):
            self.fail("HTTP workers are unbounded")
        acquired = []
        try:
            # Reserve all permits, without creating a load or slow connections.
            for _ in range(self.server.MAX_WORKERS):
                self.assertTrue(self.server.workers.acquire(timeout=1))
                acquired.append(True)
            with socket.create_connection(self.server.server_address, timeout=5) as connection:
                try:
                    self.assertEqual(connection.recv(1), b"")
                except ConnectionResetError:
                    pass
        finally:
            for _ in acquired:
                self.server.workers.release()
        self.assertEqual(self.raw(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")[0], 200)


if __name__ == "__main__":
    unittest.main()
