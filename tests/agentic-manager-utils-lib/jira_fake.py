"""A fake Jira, served on a local port, that answers each path as a test sets
it; shared by the tests of the library's Jira client and of every skill whose
scripts, run as programs, reach Jira at the config's base-url.

It answers only what a test gives it, so a call a test didn't expect fails as
a 404 rather than passing quietly, and it records every request, so a test
can check what was asked.
"""
import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse


class FakeJira(BaseHTTPRequestHandler):
    """Answers each path from `routes`: a payload, or a function of the query,
    or of a POST's JSON body, that returns one. A payload of (code, body)
    sends that status, and of (code, body, headers) those headers too. Any
    other path is answered by `fallback`, a function of the path and the
    query or body that returns a payload, or None for a 404, when a test
    sets one, and is a 404 otherwise. When a test sets `authorization`, a
    request with any other Authorization header is a 401. Every request is
    recorded in `requests` as (path, query or body), and its Authorization
    header in `authorizations`; a POST's Content-Type in `content_types`."""
    routes = {}
    fallback: Optional[Callable] = None
    authorization: Optional[str] = None
    requests = []
    authorizations = []
    content_types = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        self.answer(url.path, {k: v[0]
                    for k, v in parse_qs(url.query).items()})

    def do_POST(self):
        FakeJira.content_types.append(self.headers.get("Content-Type"))
        self.answer(urlparse(self.path).path, json.loads(
            self.rfile.read(int(self.headers["Content-Length"]))))

    def answer(self, path, query):
        FakeJira.requests.append((path, query))
        FakeJira.authorizations.append(self.headers.get("Authorization"))
        answer = self.route(path, query)
        code, body, *headers = answer if isinstance(
            answer, tuple) else (200, answer)
        data = json.dumps(body).encode()
        self.send_response(code)
        for name, value in (headers[0] if headers else {}).items():
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def route(self, path, query):
        """The answer to a request for `path` with `query`, or its body."""
        if FakeJira.authorization is not None and self.headers.get("Authorization") != FakeJira.authorization:
            return (401, {"errorMessages": ["unauthorized"]})
        if path in FakeJira.routes:
            answer = FakeJira.routes[path]
            return answer(query) if callable(answer) else answer
        answer = FakeJira.fallback(path, query) if FakeJira.fallback else None
        return (404, {"errorMessages": ["not found"]}) if answer is None else answer


def reset():
    """Clears the fake's routes, fallback and authorization, and what it
    recorded."""
    FakeJira.routes = {}
    FakeJira.fallback = None
    FakeJira.authorization = None
    FakeJira.requests = []
    FakeJira.authorizations = []
    FakeJira.content_types = []


def serve():
    """(server, base url) of the fake, started on a free local port in a
    thread of its own; a test stops it with stop()."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeJira)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def stop(server):
    """Stops the fake `server` that serve() started."""
    server.shutdown()
    server.server_close()
