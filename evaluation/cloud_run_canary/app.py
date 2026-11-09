"""Disposable Cloud Run canary for autoscaling and instance replacement checks.

No application data or GCP credentials are used. Deploy privately and delete the
service after the evaluation. POST /fail deliberately exits this one container.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


INSTANCE_ID = uuid.uuid4().hex
MAX_DELAY_MS = 3000


class Handler(BaseHTTPRequestHandler):
    def respond(self, status: int, payload: dict) -> None:
        body = json.dumps({"instance_id": INSTANCE_ID, **payload}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self.respond(200, {"ready": True})
        elif parsed.path == "/work":
            try:
                delay_ms = int(parse_qs(parsed.query).get("delay_ms", ["1500"])[0])
            except ValueError:
                return self.respond(400, {"error": "delay_ms must be an integer"})
            if not 0 <= delay_ms <= MAX_DELAY_MS:
                return self.respond(400, {"error": f"delay_ms must be 0-{MAX_DELAY_MS}"})
            time.sleep(delay_ms / 1000)
            self.respond(200, {"delay_ms": delay_ms})
        else:
            self.respond(404, {"error": "not found"})

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/fail":
            return self.respond(404, {"error": "not found"})
        self.respond(202, {"exiting": True})
        # Give the response time to leave the socket, then fail only this process.
        threading.Timer(0.2, lambda: os._exit(42)).start()

    def log_message(self, format: str, *args: object) -> None:
        print(f"instance={INSTANCE_ID} {self.address_string()} {format % args}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    print(f"canary started instance={INSTANCE_ID} port={port}", flush=True)
    server.serve_forever()
