from __future__ import annotations

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from .pipeline_utils import SITE_DIR


def main(port: int = 8000) -> None:
    handler = partial_handler()
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Serving TrabahoLens at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")


def partial_handler():
    class SiteHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(SITE_DIR), **kwargs)

        def end_headers(self):
            # A local preview must always show the files as they are now. Without
            # this, a browser may reuse a stale script or stylesheet for a while
            # and show an older colour scale after the code has changed.
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    return SiteHandler
