"""
Small local HTTP media streamer for the React audio player.
"""

from __future__ import annotations

import http.server
import mimetypes
import os
import re
import socketserver
import threading
import time


class LocalMediaServer:
    _server = None
    _file_path = ""
    _port = 0

    @classmethod
    def stream_url_for_file(cls, file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError("File audio non trovato.")

        cls._file_path = file_path
        if cls._port > 0:
            return f"http://127.0.0.1:{cls._port}/stream.media?t={time.time()}"

        class MediaHandler(http.server.BaseHTTPRequestHandler):
            def end_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                super().end_headers()

            def do_GET(self):
                try:
                    path = cls._file_path
                    if not os.path.exists(path):
                        self.send_error(404, "File not found")
                        return

                    size = os.path.getsize(path)
                    start, end = 0, size - 1
                    status_code = 200
                    range_header = self.headers.get("Range")
                    if range_header:
                        match = re.search(r"bytes=(\d+)-(\d*)", range_header)
                        if match:
                            start = int(match.group(1))
                            if match.group(2):
                                end = int(match.group(2))
                            status_code = 206

                    length = end - start + 1
                    self.send_response(status_code)
                    ctype, _ = mimetypes.guess_type(path)
                    self.send_header("Content-Type", ctype or "audio/mpeg")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    if status_code == 206:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.end_headers()

                    with open(path, "rb") as handle:
                        handle.seek(start)
                        remaining = length
                        while remaining > 0:
                            chunk = handle.read(min(remaining, 65536))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                except Exception:
                    pass

            def log_message(self, format, *args):
                pass

        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), MediaHandler)
        cls._port = server.server_address[1]
        cls._server = server
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{cls._port}/stream.media?t={time.time()}"
