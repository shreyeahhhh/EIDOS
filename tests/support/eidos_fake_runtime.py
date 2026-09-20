"""A local fake of the model runtime's HTTP API, for testing the provider adapter without any real model (decisions.md D-136).

It listens on ``127.0.0.1`` on a free port, records every request it receives, and answers as a test scripted. It is a test double:
nothing it returns is a measurement of anything.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeRuntime:
    """``behavior(handler, body)`` answers each POST; ``requests`` records ``(path, headers, parsed body)`` per call."""

    def __init__(self, behavior):
        self.behavior = behavior
        self.requests: list[tuple[str, dict, object]] = []
        self._lock = threading.Lock()
        runtime = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw)
                except ValueError:
                    body = None
                with runtime._lock:
                    runtime.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                runtime.behavior(self, body)

            def log_message(self, *args):  # keep test output quiet
                pass

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):  # a client that gave up is not an error worth printing
                pass

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


# --- behaviours ---------------------------------------------------------------------------------------------------


def send_json(handler, document, status=200):
    payload = json.dumps(document).encode("utf-8")
    send_bytes(handler, payload, status)


def send_bytes(handler, payload: bytes, status=200):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def answers(text, **extra):
    return lambda handler, body: send_json(handler, {"model": body["model"], "response": text, "done": True, **extra})


def answers_by_prompt(research, analysis):
    """Answer a research prompt and an analysis prompt differently, as the scripted model in the scenarios does."""
    return lambda handler, body: send_json(
        handler, {"response": research if "Documents:" in body["prompt"] else analysis, "done": True}
    )


def sleeps_then(seconds, inner):
    def behavior(handler, body):
        time.sleep(seconds)
        try:
            inner(handler, body)
        except OSError:
            pass  # the client gave up and closed

    return behavior


def closes_without_answering(handler, body):
    handler.close_connection = True
    handler.connection.shutdown(socket.SHUT_RDWR)


def sends_garbage(handler, body):
    handler.wfile.write(b"this is not http at all\r\n\r\n")
    handler.close_connection = True


def sends_a_truncated_body(handler, body):
    handler.send_response(200)
    handler.send_header("Content-Length", "1000")
    handler.end_headers()
    handler.wfile.write(b'{"response": "cut sh')
    handler.close_connection = True


def free_port_with_nothing_listening() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
