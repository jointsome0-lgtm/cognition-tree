"""Serve the tree on localhost and keep it fresh.

Every request rebuilds the tree from the progress files, so a reload always shows
the current state. The page asks for /version every few seconds and reloads
itself when the data has changed, so an open tab follows the files on its own.

    python3 -m cognition_tree.serve --root ~/learn --port 4747
"""

import argparse
import hashlib
import json
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .build import TEMPLATE_PATH, build
from .collect import collect

_RELOAD = """<script>
(() => {
  let seen = null;
  async function check() {
    try {
      const reply = await fetch("/version", { cache: "no-store" });
      if (reply.ok) {
        const version = (await reply.text()).trim();
        if (seen !== null && version !== seen) location.reload();
        seen = version;
      }
    } catch { /* the server may be restarting; try again later */ }
  }
  check();
  setInterval(check, %d);
})();
</script>
"""


class _Tree:
    """Builds the page on demand and keeps the last good build if one fails."""

    def __init__(self, root: Path, hub: str, interval_ms: int):
        self.root, self.hub = root, hub
        self.reload = _RELOAD % interval_ms
        self.page = self.version = self.error = None

    def refresh(self) -> None:
        try:
            tree = collect(self.root, self.hub)
        except (OSError, ValueError) as error:
            # A file caught mid-save; keep showing the last good build.
            self.error = str(error)
            return
        self.error = None
        # The build time changes on every call; only the progress itself counts.
        content = {key: value for key, value in tree.items() if key != "generated_at"}
        # A changed template is a new page too, though the data stay the same.
        content["template"] = TEMPLATE_PATH.stat().st_mtime_ns
        data = json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
        version = hashlib.sha256(data).hexdigest()[:16]
        if version == self.version:
            return
        with tempfile.TemporaryDirectory() as out:
            build(tree, out)
            page = (Path(out) / "index.html").read_text(encoding="utf-8")
        self.page = page.replace("</body>", self.reload + "</body>", 1)
        self.version = version


def _handler(tree: _Tree):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            tree.refresh()
            if path == "/version":
                self._send(tree.version or "none", "text/plain")
            elif path in ("/", "/index.html"):
                if tree.page is None:
                    self._send(f"cognition-tree: {tree.error}", "text/plain",
                               HTTPStatus.INTERNAL_SERVER_ERROR)
                else:
                    self._send(tree.page, "text/html")
            else:
                self._send("not found", "text/plain", HTTPStatus.NOT_FOUND)

        def _send(self, body: str, kind: str, status=HTTPStatus.OK):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):  # quiet: no line per request
            pass

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a live learning progress tree.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--hub", default="learning-hub")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4747)
    parser.add_argument("--interval", type=float, default=3.0,
                        help="seconds between the page's checks for changes")
    args = parser.parse_args(argv)
    tree = _Tree(args.root.expanduser(), args.hub, int(args.interval * 1000))
    tree.refresh()
    server = ThreadingHTTPServer((args.host, args.port), _handler(tree))
    print(f"cognition-tree: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
