import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from chaosusers.demo.acmebot import AcmeBot


def build_server(port: int = 8787) -> ThreadingHTTPServer:
    bot = AcmeBot()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/chat":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            self._send(bot.handle(body["session_id"], body["message"]))

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send({"ok": True})
                return
            if self.path.startswith("/state/"):
                self._send(bot.state(self.path.removeprefix("/state/")))
                return
            self.send_error(404)

        def log_message(self, _format: str, *_args) -> None:
            return None

        def _send(self, payload: dict) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int = 8787) -> None:
    server = build_server(port)
    bound = server.server_address[1]
    print(f"AcmeBot listening on http://127.0.0.1:{bound}", flush=True)
    server.serve_forever()
