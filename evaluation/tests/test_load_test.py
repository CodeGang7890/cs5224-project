"""Check that technical measurements sign the exact bytes they send."""

import hashlib
import hmac
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from evaluation.load_test import request_once, summarize, target_is_remote


class Receiver(BaseHTTPRequestHandler):
    received = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.received.append((body, self.headers.get("X-Hub-Signature-256")))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *_args):
        pass


class LoadTestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_unique_signed_payloads_and_response_summary(self):
        Receiver.received.clear()
        url = f"http://127.0.0.1:{self.server.server_port}/webhook"
        rows = [request_once(url, "POST", '{"id":"{{request_id}}"}', {}, None, "test-secret", 5)
                for _ in range(2)]
        self.assertEqual([row["status"] for row in rows], [200, 200])
        self.assertNotEqual(Receiver.received[0][0], Receiver.received[1][0])
        for body, signature in Receiver.received:
            expected = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
            self.assertEqual(signature, "sha256=" + expected)
        result = summarize(rows, {200})
        self.assertEqual((result["requests"], result["unexpected"], result["error_rate"]), (2, 0, 0))
        self.assertIsNotNone(result["p95_ms"])

    def test_remote_target_needs_explicit_opt_in(self):
        self.assertFalse(target_is_remote("http://127.0.0.1:8002/webhook"))
        self.assertTrue(target_is_remote("https://example.com/webhook"))
        with self.assertRaises(ValueError):
            target_is_remote("not-a-url")


if __name__ == "__main__":
    unittest.main()
